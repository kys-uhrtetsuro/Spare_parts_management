import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'

type System = { id: number; name: string }
type Part = { id: number; part_number: string; model_number: string; name: string }
type Stock = { system_id: number; system: string; part_id: number; part_number: string; model_number: string; name: string; quantity: number; threshold: number | null; alert: boolean }
type History = { id: number; system_id: number; system: string; part_id: number; part_number: string; model_number: string; name: string; direction: 'IN' | 'OUT'; quantity: number; operator: string; note: string; reversal_of: number | null; corrected: boolean; created_at: string }
type Alert = { part_id: number; threshold: number }
type Version = { id: number; old_part_number: string; old_model_number: string; new_part_number: string; new_model_number: string; changed_at: string }
type View = 'stock' | 'history' | 'parts' | 'alerts' | 'systems'
type PartForm = { part_number: string; model_number: string; name: string }
type Editor = { mode: 'create' | 'edit'; partId?: number; values: PartForm }
type MovementForm = { direction: 'IN' | 'OUT'; quantity: string; operator: string; note: string }
const emptyPart: PartForm = { part_number: '', model_number: '', name: '' }

function token() {
  return document.cookie.split('; ').find(c => c.startsWith('csrftoken='))?.split('=')[1] ?? ''
}
async function api<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
  const response = await fetch('/api/' + path, {
    method,
    headers: { ...(data !== undefined ? { 'Content-Type': 'application/json', 'X-CSRFToken': decodeURIComponent(token()) } : {}) },
    credentials: 'same-origin',
    body: data === undefined ? undefined : JSON.stringify(data),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: '通信エラー' })) as { error?: string }
    throw new Error(error.error ?? 'HTTP ' + response.status)
  }
  return response.json() as Promise<T>
}
function label(p: Part) { return p.part_number + ' / ' + p.model_number + ' — ' + p.name }
function dateTime(v: string) { return new Date(v).toLocaleString('ja-JP', { dateStyle: 'short', timeStyle: 'short' }) }
function useStoredValue(key: string) {
  const [value, setValue] = useState(() => localStorage.getItem(key) ?? '')
  return [value, (next: string) => { setValue(next); localStorage.setItem(key, next) }] as const
}
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return <div className="scrim" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <section className="dialog" role="dialog" aria-modal="true" aria-label={title}>
      <div className="dialog-head"><h2>{title}</h2><button className="iconbutton" type="button" aria-label="閉じる" onClick={onClose}>×</button></div>
      {children}
    </section>
  </div>
}
const views: { id: View; label: string }[] = [
  { id: 'stock', label: '現在庫一覧' }, { id: 'history', label: '入出庫履歴' },
  { id: 'parts', label: '部品マスタ' }, { id: 'alerts', label: '下限アラート設定' },
  { id: 'systems', label: 'システム管理' },
]

export default function App() {
  const [tab, setTab] = useState<View>('stock')
  const [systems, setSystems] = useState<System[]>([])
  const [parts, setParts] = useState<Part[]>([])
  const [stocks, setStocks] = useState<Stock[]>([])
  const [history, setHistory] = useState<History[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [selected, setSelected] = useState('')
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [editor, setEditor] = useState<Editor | null>(null)
  const [versions, setVersions] = useState<Version[]>([])
  const [systemModal, setSystemModal] = useState<{ id?: number; name: string } | null>(null)
  const [movementModal, setMovementModal] = useState(false)
  const [correcting, setCorrecting] = useState<History | null>(null)
  const [partSearch, setPartSearch] = useState('')
  const [pickedPart, setPickedPart] = useState<Part | null>(null)
  const [partPicker, setPartPicker] = useState(false)
  const [pickerQuery, setPickerQuery] = useState('')
  const [lastOperator, setLastOperator] = useStoredValue('last-operator')
  const [movement, setMovement] = useState<MovementForm>({ direction: 'IN', quantity: '1', operator: '', note: '' })
  const [alertDraft, setAlertDraft] = useState<Record<number, string>>({})

  const load = useCallback(async () => {
    const filter = selected ? '?system=' + selected : ''
    const [a, b, c, d] = await Promise.all([
      api<{ items: System[] }>('systems'),
      api<{ items: Part[] }>('parts'),
      api<{ items: Stock[] }>('stocks' + filter),
      api<{ items: History[] }>('history' + filter),
    ])
    setSystems(a.items); setParts(b.items); setStocks(c.items); setHistory(d.items)
  }, [selected])
  useEffect(() => { api('health').then(load).catch(e => setError(String(e))) }, [load])
  useEffect(() => {
    if (!selected) { setAlerts([]); setAlertDraft({}); return }
    api<{ items: Alert[] }>('alerts?system=' + selected).then(result => {
      setAlerts(result.items)
      setAlertDraft(Object.fromEntries(result.items.map(a => [a.part_id, String(a.threshold)])))
    }).catch(e => setError(String(e)))
  }, [selected])

  const act = async (fn: () => Promise<unknown>, success: string) => {
    setError(''); setNotice(''); setBusy(true)
    try { await fn(); await load(); setNotice(success); return true }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); return false }
    finally { setBusy(false) }
  }
  const filteredStocks = useMemo(() => stocks.filter(x =>
    [x.system, x.part_number, x.model_number, x.name].some(v => v.toLowerCase().includes(query.toLowerCase()))
  ), [stocks, query])
  const filteredParts = useMemo(() => parts.filter(x =>
    [x.part_number, x.model_number, x.name].some(v => v.toLowerCase().includes(query.toLowerCase()))
  ), [parts, query])
  const candidates = parts.filter(x =>
    [x.part_number, x.model_number, x.name].some(v => v.toLowerCase().includes(partSearch.toLowerCase()))
  ).slice(0, 12)
  // Exactly matching unique part identifiers can be entered directly.
  // Ambiguous numbers must be selected from the candidates or the list.
  const exactMatches = parts.filter(p => {
    const input = partSearch.trim().toLocaleLowerCase()
    return Boolean(input) && (
      p.part_number.toLocaleLowerCase() === input ||
      `${p.part_number} / ${p.model_number}`.toLocaleLowerCase() === input
    )
  })
  const chosenPart = pickedPart ?? (exactMatches.length === 1 ? exactMatches[0] : null)
  const choosePart = (part: Part) => {
    setPickedPart(part)
    setPartSearch(label(part))
    setPartPicker(false)
  }
  const criticalCount = stocks.filter(x => x.alert).length
  const submitMovement = async () => {
    if (!selected || !chosenPart) { setError('システムと部品を選択してください'); return }
    const success = await act(() => api('history', 'POST', {
      system_id: Number(selected), part_id: chosenPart.id,
      direction: movement.direction, quantity: Number(movement.quantity),
      operator: movement.operator, note: movement.note,
    }), '入出庫を記録しました')
    if (success) { setLastOperator(movement.operator); setMovementModal(false) }
  }
  const submitPart = async () => {
    if (!editor) return
    const url = editor.mode === 'edit' ? 'parts/' + editor.partId : 'parts'
    const success = await act(() => api<{ item: Part }>(url, editor.mode === 'edit' ? 'PUT' : 'POST', editor.values).then(r => {
      if (editor.mode === 'create' && movementModal) { setPickedPart(r.item); setPartSearch(label(r.item)) }
    }), editor.mode === 'edit' ? '部品を更新しました' : '部品を登録しました')
    if (success) setEditor(null)
  }
  const submitSystem = async () => {
    if (!systemModal) return
    const success = await act(() => api(
      systemModal.id ? 'systems/' + systemModal.id : 'systems',
      systemModal.id ? 'PUT' : 'POST', { name: systemModal.name },
    ), 'システムを保存しました')
    if (success) setSystemModal(null)
  }
  const submitCorrection = async () => {
    if (!correcting) return
    const success = await act(() => api('history/' + correcting.id + '/correct', 'POST', {
      direction: movement.direction, quantity: Number(movement.quantity),
      operator: movement.operator, note: movement.note,
    }), '取消・訂正履歴を記録しました')
    if (success) setCorrecting(null)
  }
  const submitAlerts = async () => {
    if (!selected) return
    const items = Object.entries(alertDraft).map(([part_id, threshold]) => ({ part_id: Number(part_id), threshold: Number(threshold) }))
    if (items.some(i => !Number.isSafeInteger(i.threshold) || i.threshold < 1)) { setError('下限値は全て1以上の整数にしてください'); return }
    const success = await act(
      () => api('alerts/bulk', 'POST', { system_id: Number(selected), items }),
      '下限アラートを一括保存しました',
    )
    if (success) setAlerts(items)
  }
  const openMovement = () => {
    setPickedPart(null); setPartSearch(''); setPartPicker(false); setMovement({ direction: 'IN', quantity: '1', operator: lastOperator, note: '' })
    setMovementModal(true)
  }
  const openCorrection = (h: History) => {
    setMovement({ direction: h.direction, quantity: String(h.quantity), operator: lastOperator || h.operator, note: '' })
    setCorrecting(h)
  }
  const openEditor = async (part: Part) => {
    setVersions([])
    setEditor({ mode: 'edit', partId: part.id, values: { part_number: part.part_number, model_number: part.model_number, name: part.name } })
    try { setVersions((await api<{ items: Version[] }>('parts/' + part.id + '/versions')).items) }
    catch (e) { setError(String(e)) }
  }
  const openNewPart = () => {
    setVersions([])
    setEditor({ mode: 'create', values: { ...emptyPart, part_number: partSearch.trim() } })
  }
  const needSystem = tab === 'alerts' || tab === 'history' || tab === 'stock'

  return <div className="app">
    <aside className="sidebar">
      <div className="brand"><div className="brandmark">S</div><div><strong>SPARE PARTS</strong><small>予備品管理システム</small></div></div>
      <p className="nav-label">メニュー</p>
      <nav>{views.map(v => <button key={v.id} className={'navitem ' + (tab === v.id ? 'active' : '')} onClick={() => { setTab(v.id); setQuery(''); setError(''); setNotice('') }}>{v.label}</button>)}</nav>
      <div className="sidebar-foot">LOCAL APPLICATION<br />SQLite / Django / React</div>
    </aside>
    <main className="main">
      <div className="topbar">
        <div><span className="eyebrow">INVENTORY CONTROL</span><h1>{views.find(v => v.id === tab)?.label}</h1></div>
        
      </div>
      <div className="toolbar">
        {needSystem && <label className="field compact">対象システム
          <select value={selected} onChange={e => setSelected(e.target.value)}>
            <option value="">{tab === 'alerts' ? 'システムを選択してください' : 'すべてのシステム'}</option>
            {systems.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>}
        {tab !== 'alerts' && tab !== 'systems' && <label className="field grow">検索<input value={query} onChange={e => setQuery(e.target.value)} placeholder="品番・型式・品名で検索" /></label>}
        <div className="toolbar-actions">
          {tab === 'stock' && <>
            <a className="button secondary" href={'/api/export' + (selected ? '?system=' + selected : '')}>Excel出力</a>
            <button className="button primary" onClick={openMovement} disabled={!selected}>＋ 入出庫を登録</button>
          </>}
          {tab === 'history' && <button className="button primary" disabled={!selected} onClick={openMovement}>＋ 入出庫を登録</button>}
          {tab === 'parts' && <button className="button primary" onClick={() => { setVersions([]); setEditor({ mode: 'create', values: { ...emptyPart } }) }}>＋ 部品を追加</button>}
          {tab === 'systems' && <button className="button primary" onClick={() => setSystemModal({ name: '' })}>＋ 新規システム名称を登録</button>}
          {tab === 'alerts' && <button className="button primary" disabled={!selected || busy} onClick={submitAlerts}>変更を一括保存</button>}
        </div>
      </div>
      {error && <div className="message error" role="alert">{error}<button onClick={() => setError('')}>×</button></div>}
      {notice && <div className="message success" role="status">{notice}<button onClick={() => setNotice('')}>×</button></div>}
      {tab === 'stock' && <>
        <div className="stats">
          <div className="stat"><span>表示中の部品</span><strong>{filteredStocks.length}</strong></div>
          <div className="stat"><span>現在庫合計</span><strong>{filteredStocks.reduce((n, x) => n + x.quantity, 0).toLocaleString()}</strong></div>
          <div className="stat warning"><span>下限以下の部品</span><strong>{criticalCount}</strong></div>
        </div>
        <section className="panel"><div className="panel-head"><h2>在庫サマリー</h2><span className="help">在庫1以上、または下限アラート設定あり</span></div>
          <div className="table-wrap"><table><thead><tr><th>システム</th><th>品番</th><th>型式</th><th>品名</th><th className="right">現在庫</th><th className="right">下限値</th><th>状態</th></tr></thead>
            <tbody>{filteredStocks.map(x => <tr key={x.system_id + ':' + x.part_id}><td>{x.system}</td><td className="mono">{x.part_number}</td><td className="mono">{x.model_number}</td><td>{x.name}</td><td className="right quantity">{x.quantity}</td><td className="right">{x.threshold ?? '—'}</td><td>{x.alert ? <span className="chip bad">下限以下</span> : <span className="chip ok">正常</span>}</td></tr>)}</tbody></table></div>
          {!filteredStocks.length && <p className="empty">該当する在庫がありません。</p>}
        </section>
      </>}
      {tab === 'history' && <section className="panel"><div className="panel-head"><h2>記録履歴</h2><span className="help">最新500件 / 訂正時は元履歴を保持</span></div>
        <div className="table-wrap"><table><thead><tr><th>日時</th><th>システム</th><th>品番 / 型式</th><th>区分</th><th className="right">数量</th><th>登録者</th><th>備考</th><th></th></tr></thead>
          <tbody>{history.map(h => <tr key={h.id}><td className="nowrap">{dateTime(h.created_at)}</td><td>{h.system}</td><td>{h.part_number}<br/><small>{h.model_number}</small></td><td><span className={'chip ' + (h.direction === 'IN' ? 'ok' : 'neutral')}>{h.direction === 'IN' ? '補充' : '使用'}</span></td><td className="right quantity">{h.direction === 'IN' ? '+' : '−'}{h.quantity}</td><td>{h.operator}</td><td>{h.note}{h.reversal_of && <small> (取消レコード)</small>}</td><td>{!h.corrected && !h.reversal_of && <button className="button tiny secondary" onClick={() => openCorrection(h)}>訂正</button>}</td></tr>)}</tbody></table></div>
        {!history.length && <p className="empty">まだ入出庫履歴がありません。</p>}
      </section>}
      {tab === 'parts' && <section className="panel"><div className="panel-head"><h2>部品マスタ</h2><span className="help">品番と型式の組み合わせは一意</span></div>
        <div className="table-wrap"><table><thead><tr><th>品番</th><th>型式</th><th>品名</th><th>操作</th></tr></thead><tbody>{filteredParts.map(p => <tr key={p.id}><td className="mono">{p.part_number}</td><td className="mono">{p.model_number}</td><td>{p.name}</td><td><button className="button tiny secondary" onClick={() => openEditor(p)}>変更・引継ぎ</button></td></tr>)}</tbody></table></div>
        {!filteredParts.length && <p className="empty">登録部品がありません。</p>}
      </section>}
      {tab === 'systems' && <section className="panel"><div className="panel-head"><h2>登録システム</h2><span className="help"></span></div>
        <div className="system-grid">{systems.map(s => <div className="system-card" key={s.id}><strong>{s.name}</strong><button className="button tiny secondary" onClick={() => setSystemModal({ id: s.id, name: s.name })}>名称変更</button></div>)}</div>
        {!systems.length && <p className="empty">最初にシステムを登録してください。</p>}
      </section>}
      {tab === 'alerts' && <section className="panel"><div className="panel-head"><h2>監視部品の選択</h2><span className="help">下限値は必ず1以上の整数 / 未設定は監視対象外</span></div>
        {!selected ? <p className="empty">設定するシステムを選択してください。</p> : <div className="pick-grid">
          <div className="pick-column"><h3>未設定の部品 <span>{parts.length - Object.keys(alertDraft).length}件</span></h3>
            <input className="full-input" placeholder="品番・型式・品名で検索" value={query} onChange={e => setQuery(e.target.value)} />
            <div className="pick-list">{parts.filter(p => !Object.hasOwn(alertDraft, p.id) && label(p).toLowerCase().includes(query.toLowerCase())).map(p => <button key={p.id} className="pick-item" onClick={() => setAlertDraft(prev => ({ ...prev, [p.id]: '' }))}><span>{p.part_number} / {p.model_number}<small>{p.name}</small></span><b>＋</b></button>)}</div>
          </div>
          <div className="pick-column"><h3>設定対象 <span>{Object.keys(alertDraft).length}件</span></h3>
            <div className="pick-list configured">{Object.entries(alertDraft).map(([id, threshold]) => {
              const p = parts.find(x => x.id === Number(id))
              if (!p) return null
              return <div className="pick-item" key={id}><span>{p.part_number} / {p.model_number}<small>{p.name}</small></span><label>下限 <input type="number" min="1" step="1" value={threshold} onChange={e => setAlertDraft(prev => ({ ...prev, [id]: e.target.value }))} /></label><button className="remove" title="監視対象から除外" onClick={() => setAlertDraft(prev => { const next = { ...prev }; delete next[Number(id)]; return next })}>×</button></div>
            })}</div>
          </div>
        </div>}
        {selected && <div className="panel-foot"><span>{alerts.length}件の保存済み設定</span><button className="button primary" disabled={busy} onClick={submitAlerts}>設定を一括保存</button></div>}
      </section>}
      <footer className="footer"><span>Spare Parts Management</span><button onClick={async () => { await act(() => api('backup', 'POST', {}), 'data/backups にSQLiteバックアップを作成しました') }}>DBバックアップを作成</button></footer>
    </main>

    {movementModal && <Modal title="入出庫を登録" onClose={() => setMovementModal(false)}>
      <div className="form-grid">
        <label className="field">システム<input disabled value={systems.find(s => String(s.id) === selected)?.name ?? ''} /></label>
        <label className="field">区分<select value={movement.direction} onChange={e => setMovement(p => ({ ...p, direction: e.target.value as 'IN' | 'OUT' }))}><option value="IN">補充</option><option value="OUT">使用</option></select></label>
        <div className="field wide">部品の検索・選択（品番・型式・品名）
          <div className="part-search-row">
            <input autoFocus aria-label="部品を直接入力して検索" value={partSearch} onChange={e => { setPartSearch(e.target.value); setPickedPart(null) }} placeholder="品番を直接入力、または候補から選択" />
            <button className="button secondary" onClick={() => { setPickerQuery(''); setPartPicker(true) }}>一覧から選択</button>
          </div>
          {chosenPart ? <p className="selected-part">選択中：{label(chosenPart)}{!pickedPart && '（完全一致）'}</p> : <div className="suggestions">{candidates.map(p => <button key={p.id} onClick={() => choosePart(p)}>{label(p)}</button>)}<button className="create-suggestion" onClick={openNewPart}>＋ 未登録品を新規登録する</button></div>}
        </div>
        <label className="field">数量<input type="number" min="1" step="1" value={movement.quantity} onChange={e => setMovement(p => ({ ...p, quantity: e.target.value }))} /></label>
        <label className="field">登録者名<input value={movement.operator} onChange={e => setMovement(p => ({ ...p, operator: e.target.value }))} /></label>
        <label className="field wide">備考（任意）<input value={movement.note} onChange={e => setMovement(p => ({ ...p, note: e.target.value }))} /></label>
      </div>
      <div className="dialog-actions"><button className="button secondary" onClick={() => setMovementModal(false)}>キャンセル</button><button className="button primary" disabled={busy || !chosenPart} onClick={submitMovement}>履歴を登録</button></div>
    </Modal>}
    {movementModal && partPicker && <Modal title="部品一覧から選択" onClose={() => setPartPicker(false)}>
      <label className="field">品番・型式・品名で絞り込み
        <input autoFocus value={pickerQuery} onChange={e => setPickerQuery(e.target.value)} placeholder="一覧から部品を検索" />
      </label>
      <div className="table-wrap part-picker-table">
        <table><thead><tr><th>品番</th><th>型式</th><th>品名</th><th>選択</th></tr></thead>
          <tbody>{parts.filter(p => label(p).toLocaleLowerCase().includes(pickerQuery.toLocaleLowerCase())).map(p =>
            <tr key={p.id}><td>{p.part_number}</td><td>{p.model_number}</td><td>{p.name}</td>
              <td><button className="button tiny secondary" onClick={() => choosePart(p)}>選択</button></td></tr>)}</tbody>
        </table>
      </div>
      <div className="dialog-actions">
        <button className="button secondary" onClick={() => setPartPicker(false)}>閉じる</button>
      </div>
    </Modal>}
    {editor && <Modal title={editor.mode === 'edit' ? '部品変更・品番/型式引継ぎ' : '新規部品マスタ登録'} onClose={() => setEditor(null)}>
      <p className="help">品番または型式を変更しても、部品ID・現在庫・入出庫履歴は引き継がれます。</p>
      <div className="form-grid">{([
        ['part_number', '品番'], ['model_number', '型式'], ['name', '品名'],
      ] as const).map(([key, title]) => <label className="field" key={key}>{title}<input value={editor.values[key]} onChange={e => setEditor(p => p && ({ ...p, values: { ...p.values, [key]: e.target.value } }))} /></label>)}</div>
      {versions.length > 0 && <div className="version-list"><h3>過去の引継ぎ履歴</h3>{versions.map(v => <p key={v.id}>{v.old_part_number} / {v.old_model_number} → {v.new_part_number} / {v.new_model_number} <small>{dateTime(v.changed_at)}</small></p>)}</div>}
      <div className="dialog-actions"><button className="button secondary" onClick={() => setEditor(null)}>キャンセル</button><button className="button primary" disabled={busy} onClick={submitPart}>保存する</button></div>
    </Modal>}
    {systemModal && <Modal title={systemModal.id ? 'システム名称変更' : '新規システム登録'} onClose={() => setSystemModal(null)}>
      <label className="field">システム名<input autoFocus value={systemModal.name} onChange={e => setSystemModal(p => p && ({ ...p, name: e.target.value }))} /></label>
      <div className="dialog-actions"><button className="button secondary" onClick={() => setSystemModal(null)}>キャンセル</button><button className="button primary" disabled={busy} onClick={submitSystem}>保存する</button></div>
    </Modal>}
    {correcting && <Modal title={'履歴 #' + correcting.id + ' を訂正'} onClose={() => setCorrecting(null)}>
      <p className="help">元履歴を残し、反対方向の取消履歴と訂正後の履歴を同時に記録します。訂正後在庫が負になる変更はできません。</p>
      <div className="form-grid">
        <label className="field">訂正区分<select value={movement.direction} onChange={e => setMovement(p => ({ ...p, direction: e.target.value as 'IN' | 'OUT' }))}><option value="IN">補充</option><option value="OUT">使用</option></select></label>
        <label className="field">訂正数量<input type="number" min="1" step="1" value={movement.quantity} onChange={e => setMovement(p => ({ ...p, quantity: e.target.value }))} /></label>
        <label className="field">登録者名<input value={movement.operator} onChange={e => setMovement(p => ({ ...p, operator: e.target.value }))} /></label>
        <label className="field wide">訂正理由（必須）<input value={movement.note} onChange={e => setMovement(p => ({ ...p, note: e.target.value }))} /></label>
      </div>
      <div className="dialog-actions"><button className="button secondary" onClick={() => setCorrecting(null)}>キャンセル</button><button className="button primary" disabled={busy} onClick={submitCorrection}>取消・訂正を確定</button></div>
    </Modal>}
  </div>
}
