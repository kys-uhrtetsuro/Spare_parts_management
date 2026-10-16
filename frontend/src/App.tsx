import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import appIcon from './assets/spare_parts.png'

type System = { id: number; name: string }
type Equipment = { id: number; system_id: number; name: string; alias: string }
type Section = { id: number; equipment_id: number; name: string }
type Category = { id: number; name: string }
type Placement = { system_id: number; equipment_id: number; section_id: number | null }
type Part = { id: number; part_number: string; model_number: string; name: string; previous_part_id: number | null; has_successor: boolean; category_id: number | null; placements: Placement[] }
type Stock = { system_id: number; system: string; part_id: number; part_number: string; model_number: string; name: string; quantity: number; threshold: number | null; alert: boolean; last_updated: string | null }
type History = { id: number; system_id: number; system: string; part_id: number; part_number: string; model_number: string; name: string; direction: 'IN' | 'OUT'; quantity: number; operator: string; note: string; reversal_of: number | null; corrected: boolean; created_at: string }
type Alert = { part_id: number; threshold: number }
type Version = { id: number; old_part_number: string; old_model_number: string; new_part_number: string; new_model_number: string; changed_at: string }
type ImportPreview = {
  checksum: string; systems: string[]; system_count: number; equipment_count: number
  part_count: number; opening_rows: number; quantity_total: number; alert_count: number
  conflicts: string[]; already_imported: boolean; available_targets: System[]
}
type View = 'stock' | 'low-stock' | 'history' | 'parts' | 'alerts' | 'systems' | 'equipment' | 'categories'
type AssignmentForm = { equipment_id: string; section_id: string }
type PartForm = { part_number: string; model_number: string; name: string; system_id: string; placements: AssignmentForm[]; category_id: string }
type Editor = { mode: 'create' | 'edit'; partId?: number; copyFrom?: number; values: PartForm }
type MovementForm = { direction: 'IN' | 'OUT'; quantity: string; operator: string; note: string }
const blankAssignment = (): AssignmentForm => ({ equipment_id: '', section_id: '' })
const emptyPart: PartForm = {
  part_number: '', model_number: '', name: '', system_id: '',
  placements: [blankAssignment()], category_id: '',
}
function valuesFromPart(p: Part, systemId: string): PartForm {
  const resolvedSystem = systemId || String(p.placements[0]?.system_id ?? '')
  const assigned = p.placements.filter(x => String(x.system_id) === resolvedSystem)
  return {
    part_number: p.part_number, model_number: p.model_number, name: p.name,
    system_id: resolvedSystem,
    placements: assigned.length
      ? assigned.map(x => ({
          equipment_id: String(x.equipment_id), section_id: String(x.section_id ?? ''),
        }))
      : [blankAssignment()],
    category_id: String(p.category_id ?? ''),
  }
}

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
async function uploadWorkbook<T>(path: string, file: File, rename?: string, destinationId?: number): Promise<T> {
  const body = new FormData()
  body.append('file', file)
  if (rename?.trim()) body.append('system_name', rename.trim())
  if (destinationId !== undefined) body.append('target_system_id', String(destinationId))
  const response = await fetch('/api/' + path, {
    method: 'POST',
    headers: { 'X-CSRFToken': decodeURIComponent(token()) },
    credentials: 'same-origin',
    body,
  })
  if (!response.ok) {
    const result = await response.json().catch(() => ({ error: '取り込みに失敗しました' })) as { error?: string }
    throw new Error(result.error ?? 'HTTP ' + response.status)
  }
  return response.json() as Promise<T>
}
type NotificationWindow = Window & {
  pywebview?: { api?: { notify_low_stock?: (count: number) => Promise<boolean> } }
}
async function notifyDesktop(count: number) {
  if (count < 1) return
  const native = (window as NotificationWindow).pywebview?.api?.notify_low_stock
  if (native) {
    try { if (await native(count)) return } catch { /* Fall back to browser notifications. */ }
  }
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification('予備品管理システム：下限在庫', {
      body: count + '件の部品が下限値以下です。下限在庫一覧を確認してください。',
    })
  }
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
  { id: 'stock', label: '現在在庫一覧' },
  { id: 'low-stock', label: '下限在庫一覧' },
  { id: 'history', label: '入出庫履歴' },
  { id: 'alerts', label: '下限アラート設定' },
  { id: 'systems', label: 'システム一覧' },
  { id: 'equipment', label: '機器/部位マスタ' },
  { id: 'categories', label: '部品分類マスタ' },
  { id: 'parts', label: '部品マスタ' },
]

export default function App() {
  const [tab, setTab] = useState<View>('stock')
  const [inventoryMenuOpen, setInventoryMenuOpen] = useState(true)
  const [systemMenuOpen, setSystemMenuOpen] = useState(false)
  const [systems, setSystems] = useState<System[]>([])
  const [parts, setParts] = useState<Part[]>([])
  const [equipments, setEquipments] = useState<Equipment[]>([])
  const [sections, setSections] = useState<Section[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [stocks, setStocks] = useState<Stock[]>([])
  const [stocksReady, setStocksReady] = useState(false)
  const [desktopNotifyChoice, setDesktopNotifyChoice] = useStoredValue('desktop-low-stock-notifications')
  const lastNotifiedRef = useRef<string | null>(null)
  const [history, setHistory] = useState<History[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [selected, setSelected] = useState('')
  const [query, setQuery] = useState('')
  const [equipmentFilter, setEquipmentFilter] = useState('')
  const [sectionFilter, setSectionFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [importModal, setImportModal] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null)
  const [importRename, setImportRename] = useState('')
  const [importTarget, setImportTarget] = useState('new')
  const [importError, setImportError] = useState('')
  const [editor, setEditor] = useState<Editor | null>(null)
  const [versions, setVersions] = useState<Version[]>([])
  const [systemModal, setSystemModal] = useState<{ id?: number; name: string } | null>(null)
  const [equipmentModal, setEquipmentModal] = useState<{ id?: number; copy_from?: number; system_id: number; name: string; alias: string } | null>(null)
  const [sectionModal, setSectionModal] = useState<{ id?: number; equipment_id: number; name: string } | null>(null)
  const [categoryModal, setCategoryModal] = useState<{ id?: number; name: string } | null>(null)
  const [movementModal, setMovementModal] = useState(false)
  const [correcting, setCorrecting] = useState<History | null>(null)
  const [partSearch, setPartSearch] = useState('')
  const [pickedPart, setPickedPart] = useState<Part | null>(null)
  const [partPicker, setPartPicker] = useState(false)
  const [pickerQuery, setPickerQuery] = useState('')
  const [pickerEquipment, setPickerEquipment] = useState('')
  const [pickerSection, setPickerSection] = useState('')
  const [pickerCategory, setPickerCategory] = useState('')
  const [excludeSuperseded, setExcludeSuperseded] = useState(true)
  const [lastOperator, setLastOperator] = useStoredValue('last-operator')
  const [movement, setMovement] = useState<MovementForm>({ direction: 'IN', quantity: '1', operator: '', note: '' })
  const [alertDraft, setAlertDraft] = useState<Record<number, string>>({})

  const load = useCallback(async () => {
    const filter = selected ? '?system=' + selected : ''
    const [a, b, c, d, e, f, g] = await Promise.all([
      api<{ items: System[] }>('systems'),
      api<{ items: Part[] }>('parts'),
      api<{ items: Stock[] }>('stocks'),
      api<{ items: History[] }>('history' + filter),
      api<{ items: Equipment[] }>('equipment'),
      api<{ items: Section[] }>('equipment/sections'),
      api<{ items: Category[] }>('categories'),
    ])
    setSystems(a.items); setParts(b.items); setStocks(c.items); setStocksReady(true); setHistory(d.items)
    setEquipments(e.items); setSections(f.items); setCategories(g.items)
  }, [selected])
  useEffect(() => { api('health').then(load).catch(e => setError(String(e))) }, [load])
  const refreshAlerts = useCallback(async () => {
    if (!selected) { setAlerts([]); setAlertDraft({}); return }
    const result = await api<{ items: Alert[] }>('alerts?system=' + selected)
    setAlerts(result.items)
    setAlertDraft(Object.fromEntries(result.items.map(a => [a.part_id, String(a.threshold)])))
  }, [selected])
  useEffect(() => { refreshAlerts().catch(e => setError(String(e))) }, [refreshAlerts])

  const act = async (fn: () => Promise<unknown>, success: string) => {
    setError(''); setNotice(''); setBusy(true)
    try {
      await fn()
      setNotice(success)
      // A refresh failure must never make a saved record look unsaved.
      try { await Promise.all([load(), refreshAlerts()]) } catch (refreshError) {
        setError('保存しましたが一覧の再読込に失敗しました: ' + String(refreshError))
      }
      return true
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); return false }
    finally { setBusy(false) }
  }
  // Reverse lookup: all parts assigned to the selected equipment, section, category,
  // regardless of current stock, plus the equivalent filter on the stock overview.
  const matchesClassifications = (p: Part, systemId: string) => {
    const placements = p.placements.filter(x => !systemId || String(x.system_id) === systemId)
    return (!categoryFilter || String(p.category_id) === categoryFilter) &&
      (!equipmentFilter && !sectionFilter || placements.some(x =>
        (!equipmentFilter || String(x.equipment_id) === equipmentFilter) &&
        (!sectionFilter || String(x.section_id) === sectionFilter)))
  }
  const partsById = new Map(parts.map(p => [p.id, p]))
  const filteredStocks = stocks.filter(row => {
    const part = partsById.get(row.part_id)
    return (!selected || String(row.system_id) === selected) &&
      part !== undefined && matchesClassifications(part, String(row.system_id)) &&
      [row.system, row.part_number, row.model_number, row.name].some(
        value => value.toLowerCase().includes(query.toLowerCase())
      )
  })
  const filteredParts = parts.filter(p =>
    (!excludeSuperseded || !p.has_successor) &&
    matchesClassifications(p, selected) &&
    [p.part_number, p.model_number, p.name,
      ...p.placements.flatMap(a => [
        equipments.find(e => e.id === a.equipment_id)?.name ?? '',
        equipments.find(e => e.id === a.equipment_id)?.alias ?? '',
        sections.find(x => x.id === a.section_id)?.name ?? '',
      ]),
      categories.find(c => c.id === p.category_id)?.name ?? '',
    ].some(v => v.toLowerCase().includes(query.toLowerCase()))
  )
  const viewMatchingParts = (equipmentId = '', categoryId = '') => {
    const eq = equipments.find(e => String(e.id) === equipmentId)
    if (eq) setSelected(String(eq.system_id))
    setEquipmentFilter(equipmentId)
    setSectionFilter('')
    setCategoryFilter(categoryId)
    setQuery('')
    setTab('parts')
  }

  const currentParts = parts.filter(x => !x.has_successor)
  const stockedPartIds = new Set(stocks.filter(row =>
    String(row.system_id) === selected && row.quantity > 0
  ).map(row => row.part_id))
  const selectableParts = movement.direction === 'IN'
    ? currentParts
    : parts.filter(part => stockedPartIds.has(part.id))
  const pickerParts = selectableParts.filter(p =>
    label(p).toLocaleLowerCase().includes(pickerQuery.trim().toLocaleLowerCase()) &&
    (!pickerCategory || String(p.category_id) === pickerCategory) &&
    (!pickerEquipment && !pickerSection || p.placements.some(a =>
      String(a.system_id) === selected &&
      (!pickerEquipment || String(a.equipment_id) === pickerEquipment) &&
      (!pickerSection || String(a.section_id) === pickerSection)))
  )
  const candidates = partSearch.trim() ? selectableParts.filter(x =>
    [x.part_number, x.model_number, x.name].some(v => v.toLowerCase().includes(partSearch.trim().toLowerCase()))
  ).slice(0, 4) : []
  // Exactly matching unique part identifiers can be entered directly.
  // Ambiguous numbers must be selected from the candidates or the list.
  const exactMatches = selectableParts.filter(p => {
    const input = partSearch.trim().toLocaleLowerCase()
    return Boolean(input) && (
      p.part_number.toLocaleLowerCase() === input ||
      `${p.part_number} / ${p.model_number}`.toLocaleLowerCase() === input
    )
  })
  const chosenPart = (pickedPart && selectableParts.some(p => p.id === pickedPart.id)
    ? pickedPart : null) ?? (exactMatches.length === 1 ? exactMatches[0] : null)
  const chosenStock = chosenPart
    ? stocks.find(row => String(row.system_id) === selected && row.part_id === chosenPart.id)
    : undefined
  const choosePart = (part: Part) => {
    setPickedPart(part)
    setPartSearch(label(part))
    setPartPicker(false)
  }
  const alertStocks = stocks.filter(x => x.alert)
  const filteredAlertStocks = filteredStocks.filter(x => x.alert)
  const criticalCount = filteredAlertStocks.length
  const alertSignature = alertStocks
    .map(x => x.system_id + ':' + x.part_id)
    .sort().join('|')
  useEffect(() => {
    if (!stocksReady || desktopNotifyChoice === 'off' || !alertSignature) {
      lastNotifiedRef.current = null
      return
    }
    if (lastNotifiedRef.current === alertSignature) return
    lastNotifiedRef.current = alertSignature
    void notifyDesktop(alertStocks.length)
  }, [alertSignature, alertStocks.length, desktopNotifyChoice, stocksReady])
  const toggleDesktopNotifications = async () => {
    if (desktopNotifyChoice !== 'off') {
      setDesktopNotifyChoice('off')
      setNotice('デスクトップ通知を無効にしました')
      return
    }
    const nativeAvailable = Boolean((window as NotificationWindow).pywebview?.api?.notify_low_stock)
    if (!nativeAvailable && 'Notification' in window && Notification.permission !== 'granted') {
      const result = await Notification.requestPermission()
      if (result !== 'granted') {
        setError('デスクトップ通知が許可されていません。画面内の在庫警告は引き続き表示します。')
        return
      }
    }
    if (!nativeAvailable && !('Notification' in window)) {
      setError('この環境ではデスクトップ通知が使えません。画面内の在庫警告は引き続き表示します。')
      return
    }
    setError('')
    setDesktopNotifyChoice('on')
    setNotice('デスクトップ通知を有効にしました')
  }
  const eligibleAlertParts = parts.filter(p => !p.has_successor)
  const eligibleAlertCount = eligibleAlertParts.filter(
    p => !Object.hasOwn(alertDraft, p.id)
  ).length
  const submitMovement = async () => {
    if (!selected || !chosenPart || (
      movement.direction === 'IN' ? chosenPart.has_successor : !chosenStock || chosenStock.quantity <= 0
    )) { setError(movement.direction === 'IN' ? '現行品とシステムを選択してください' : '在庫のある部品とシステムを選択してください'); return }
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
    const form = editor.values
    const values = {
      ...form,
      placements: form.placements.filter(x => x.equipment_id || x.section_id),
    }
    const success = await act(() => api<{ item: Part }>(url, editor.mode === 'edit' ? 'PUT' : 'POST', values).then(r => {
      if (editor.mode === 'create' && movementModal) { setPickedPart(r.item); setPartSearch(label(r.item)) }
    }), editor.mode === 'edit' ? '部品を更新しました' : '部品を登録しました')
    if (success) setEditor(null)
  }
  const submitEquipment = async () => {
    if (!equipmentModal) return
    const success = await act(() => api(
      equipmentModal.id ? 'equipment/' + equipmentModal.id :
        equipmentModal.copy_from ? 'equipment/' + equipmentModal.copy_from + '/copy' : 'equipment',
      equipmentModal.id ? 'PUT' : 'POST',
      { name: equipmentModal.name, alias: equipmentModal.alias, system_id: equipmentModal.system_id },
    ), '機器マスタを保存しました')
    if (success) setEquipmentModal(null)
  }
  const submitSection = async () => {
    if (!sectionModal) return
    const success = await act(() => api(
      sectionModal.id ? 'equipment/sections/' + sectionModal.id : 'equipment/sections',
      sectionModal.id ? 'PUT' : 'POST',
      { name: sectionModal.name, equipment_id: sectionModal.equipment_id },
    ), '部位マスタを保存しました')
    if (success) setSectionModal(null)
  }
  const submitCategory = async () => {
    if (!categoryModal) return
    const success = await act(() => api(
      categoryModal.id ? 'categories/' + categoryModal.id : 'categories',
      categoryModal.id ? 'PUT' : 'POST', { name: categoryModal.name },
    ), '部品分類を保存しました')
    if (success) setCategoryModal(null)
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
    await act(
      () => api('alerts/bulk', 'POST', { system_id: Number(selected), items }),
      '下限アラートを一括保存しました',
    )
  }
  const previewImport = async () => {
    if (!importFile) { setImportError('Excelファイルを指定してください'); return }
    setImportError('')
    setBusy(true)
    try {
      const data = await uploadWorkbook<ImportPreview>('import/preview', importFile)
      setImportPreview(data)
      setImportTarget('new')
    } catch (err) {
      setImportError(err instanceof Error ? err.message : String(err))
    } finally { setBusy(false) }
  }
  const applyImport = async () => {
    if (!importFile || !importPreview) return
    if (importPreview.already_imported) {
      setImportError('このExcelは既に取り込まれています')
      return
    }
    setImportError('')
    setBusy(true)
    try {
      const result = await uploadWorkbook<{ systems: string[]; opening_rows: number }>(
        'import/apply', importFile,
        importTarget === 'new' ? importRename : undefined,
        importTarget === 'new' ? undefined : Number(importTarget),
      )
      setNotice(result.systems.join('、') + 'を取り込みました（期首在庫' + result.opening_rows + '件）')
      setImportModal(false)
      setImportPreview(null)
      setImportFile(null)
      setImportRename('')
      setImportTarget('new')
      setSelected('')
      try { await load() } catch { setError('保存しましたが、一覧の再読込に失敗しました') }
    } catch (err) {
      setImportError(err instanceof Error ? err.message : String(err))
    } finally { setBusy(false) }
  }
  const openMovement = (direction: 'IN' | 'OUT') => {
    setPickedPart(null); setPartSearch(''); setPartPicker(false)
    setMovement({ direction, quantity: '1', operator: lastOperator, note: '' })
    setMovementModal(true)
  }
  const openCorrection = (h: History) => {
    setMovement({ direction: h.direction, quantity: String(h.quantity), operator: lastOperator || h.operator, note: '' })
    setCorrecting(h)
  }
  const openEditor = async (part: Part) => {
    setVersions([])
    setEditor({ mode: 'edit', partId: part.id, values: valuesFromPart(part, selected) })
    try { setVersions((await api<{ items: Version[] }>('parts/' + part.id + '/versions')).items) }
    catch (e) { setError(String(e)) }
  }
  const copyPart = (part: Part) => {
    setVersions([])
    setEditor({ mode: 'create', copyFrom: part.id, values: valuesFromPart(part, selected) })
  }
  const openNewPart = () => {
    setVersions([])
    setEditor({ mode: 'create', values: { ...emptyPart, system_id: selected, part_number: partSearch.trim() } })
  }
  const needSystem = tab === 'alerts' || tab === 'history' || tab === 'stock' || tab === 'low-stock' || tab === 'parts' || tab === 'equipment'

  return <div className="app">
    <aside className="sidebar">
      <div className="brand"><div className="brandmark"><img src={appIcon} alt="" aria-hidden="true" /></div><div><strong>SPARE PARTS</strong><small>予備品管理システム</small></div></div>
      <p className="nav-label">メニュー</p>
      <nav aria-label="メインメニュー">
        {([
          { title: '在庫管理', ids: ['stock', 'low-stock', 'history', 'alerts'] as View[], opened: inventoryMenuOpen, toggle: setInventoryMenuOpen },
          { title: 'システム管理', ids: ['systems', 'equipment', 'categories', 'parts'] as View[], opened: systemMenuOpen, toggle: setSystemMenuOpen },
        ]).map(group => <details className="nav-group" key={group.title}
            open={group.opened} onToggle={e => group.toggle(e.currentTarget.open)}>
          <summary className="nav-group-title">【{group.title}】<span className="nav-chevron" aria-hidden="true">⌄</span></summary>
          <div className="nav-group-items">
            {group.ids.map(id => {
              const view = views.find(v => v.id === id)
              if (!view) return null
              return <button key={id} className={'navitem ' + (tab === id ? 'active' : '')}
                aria-current={tab === id ? 'page' : undefined}
                onClick={() => { setTab(id); setQuery(''); setError(''); setNotice('') }}>
                {view.label}
              </button>
            })}
          </div>
        </details>)}
      </nav>
      
    </aside>
    <main className="main">
      <div className="topbar">
        <div><span className="eyebrow">INVENTORY CONTROL</span><h1>{views.find(v => v.id === tab)?.label}</h1></div>
        <button className="button secondary notification-toggle" type="button" onClick={toggleDesktopNotifications}>
          デスクトップ通知：{desktopNotifyChoice === 'off' ? 'OFF' : 'ON'}
        </button>
      </div>
      {error && <div className="message error" role="alert">{error}<button aria-label="エラーを閉じる" onClick={() => setError('')}>×</button></div>}
      {notice && <div className="message success" role="status">{notice}<button aria-label="通知を閉じる" onClick={() => setNotice('')}>×</button></div>}
      {stocksReady && alertStocks.length > 0 && <div className="low-stock-notice" role="alert">
        <div><strong>下限在庫の警告：{alertStocks.length}件</strong>
          <p>下限値以下の部品があります。対象のシステム・品番・不足数を確認してください。</p></div>
        <button className="button secondary" type="button" onClick={() => {
          setTab('low-stock'); setSelected(''); setQuery('')
          setEquipmentFilter(''); setSectionFilter(''); setCategoryFilter('')
        }}>下限在庫一覧を開く</button>
      </div>}
      <div className="toolbar">
        {needSystem && <label className="field compact">対象システム
          <select value={selected} onChange={e => { setSelected(e.target.value); setEquipmentFilter(''); setSectionFilter('') }}>
            <option value="">{tab === 'alerts' || tab === 'equipment' ? 'システムを選択してください' : 'すべてのシステム'}</option>
            {systems.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>}
        {tab !== 'alerts' && tab !== 'systems' && tab !== 'equipment' && tab !== 'categories' && <label className="field grow">検索<input value={query} onChange={e => setQuery(e.target.value)} placeholder="品番・型式・品名で検索" /></label>}
        {(tab === 'parts' || tab === 'stock' || tab === 'low-stock') && <>
          <label className="field compact">機器
            <select aria-label="機器で絞り込み" value={equipmentFilter} onChange={e => { setEquipmentFilter(e.target.value); setSectionFilter('') }}>
              <option value="">すべて</option>
              {equipments.filter(e => !selected || String(e.system_id) === selected).map(e => <option key={e.id} value={e.id}>{e.name}{e.alias ? '（' + e.alias + '）' : ''}</option>)}
            </select>
          </label>
          <label className="field compact">部位
            <select aria-label="部位で絞り込み" value={sectionFilter} disabled={!equipmentFilter} onChange={e => setSectionFilter(e.target.value)}>
              <option value="">すべて</option>
              {sections.filter(sec => String(sec.equipment_id) === equipmentFilter).map(sec => <option key={sec.id} value={sec.id}>{sec.name}</option>)}
            </select>
          </label>
          <label className="field compact">分類
            <select aria-label="分類で絞り込み" value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)}>
              <option value="">すべて</option>
              {categories.map(cat => <option key={cat.id} value={cat.id}>{cat.name}</option>)}
            </select>
          </label>
        </>}
        <div className="toolbar-actions">
          {tab === 'stock' && <>
            <button className="button secondary" onClick={() => {
              setImportModal(true); setImportFile(null); setImportPreview(null)
              setImportRename(''); setImportTarget('new'); setImportError('')
            }}>Excel取込</button>
            <a className="button secondary" href={'/api/export?' + new URLSearchParams({
              ...(selected ? { system: selected } : {}),
              ...(equipmentFilter ? { equipment: equipmentFilter } : {}),
              ...(sectionFilter ? { section: sectionFilter } : {}),
              ...(categoryFilter ? { category: categoryFilter } : {}),
            }).toString()}>Excel出力</a>
            <button className="button primary" onClick={() => openMovement('IN')} disabled={!selected}>＋ 入庫登録</button>
            <button className="button secondary" onClick={() => openMovement('OUT')} disabled={!selected}>－ 出庫登録</button>
          </>}
          {tab === 'history' && <>
            <button className="button primary" disabled={!selected} onClick={() => openMovement('IN')}>＋ 入庫登録</button>
            <button className="button secondary" disabled={!selected} onClick={() => openMovement('OUT')}>－ 出庫登録</button>
          </>}
          {tab === 'parts' && <button className="button primary" onClick={() => { setVersions([]); setEditor({ mode: 'create', values: { ...emptyPart, system_id: selected } }) }}>＋ 部品を追加</button>}
          {tab === 'systems' && <button className="button primary" onClick={() => setSystemModal({ name: '' })}>＋ 新規システム名称を登録</button>}
          {tab === 'equipment' && <button className="button primary" disabled={!selected} onClick={() => setEquipmentModal({ name: '', alias: '', system_id: Number(selected) })}>＋ 機器を追加</button>}
          {tab === 'categories' && <button className="button primary" onClick={() => setCategoryModal({ name: '' })}>＋ 分類を追加</button>}
          {tab === 'alerts' && <button className="button primary" disabled={!selected || busy} onClick={submitAlerts}>変更を一括保存</button>}
        </div>
      </div>
      {tab === 'stock' && <>
        <div className="stats">
          <div className="stat"><span>表示中の部品</span><strong>{filteredStocks.length}</strong></div>
          <div className="stat"><span>現在庫合計</span><strong>{filteredStocks.reduce((n, x) => n + x.quantity, 0).toLocaleString()}</strong></div>
          <div className="stat warning"><span>下限以下の部品</span><strong>{criticalCount}</strong></div>
        </div>
        <section className="panel"><div className="panel-head"><h2>在庫サマリー</h2><span className="help">在庫1以上、または下限アラート設定あり</span></div>
          <div className="table-wrap"><table><thead><tr><th>システム</th><th>品番</th><th>型式</th><th>品名</th><th className="right">現在庫</th><th className="right">下限値</th><th>最終更新</th><th>状態</th></tr></thead>
            <tbody>{filteredStocks.map(x => <tr key={x.system_id + ':' + x.part_id}><td>{x.system}</td><td className="mono">{x.part_number}</td><td className="mono">{x.model_number}</td><td>{x.name}</td><td className="right quantity">{x.quantity}</td><td className="right">{x.threshold ?? '—'}</td><td className="nowrap">{x.last_updated ? dateTime(x.last_updated) : '—'}</td><td>{x.alert ? <span className="chip bad">下限以下</span> : <span className="chip ok">正常</span>}</td></tr>)}</tbody></table></div>
          {!filteredStocks.length && <p className="empty">該当する在庫がありません。</p>}
        </section>
      </>}
      {tab === 'low-stock' && <>
        <div className="stats">
          <div className="stat warning"><span>下限以下の部品</span><strong>{filteredAlertStocks.length}</strong></div>
          <div className="stat"><span>補充が必要な数量の合計</span><strong>{filteredAlertStocks.reduce((sum, x) => sum + Math.max(0, (x.threshold ?? 0) - x.quantity), 0).toLocaleString()}</strong></div>
          <div className="stat"><span>監視中の部品</span><strong>{filteredStocks.filter(x => x.threshold !== null).length}</strong></div>
        </div>
        <section className="panel"><div className="panel-head"><h2>下限在庫一覧</h2>
          <span className="help">現在庫が下限値以下の部品のみ表示。現在庫＝下限値の場合も警告対象です。</span></div>
          <div className="table-wrap"><table><thead><tr><th>システム</th><th>品番</th><th>型式</th><th>品名</th><th className="right">現在庫</th><th className="right">下限値</th><th className="right">不足数</th><th>状態</th></tr></thead>
            <tbody>{filteredAlertStocks.map(x => <tr key={x.system_id + ':' + x.part_id}>
              <td>{x.system}</td><td className="mono">{x.part_number}</td><td className="mono">{x.model_number}</td><td>{x.name}</td>
              <td className="right quantity">{x.quantity}</td><td className="right">{x.threshold}</td>
              <td className="right quantity">{Math.max(0, (x.threshold ?? 0) - x.quantity)}</td>
              <td><span className="chip bad">{x.quantity === x.threshold ? '下限到達' : '下限未満'}</span></td>
            </tr>)}</tbody></table></div>
          {filteredAlertStocks.length === 0 && <p className="empty">下限値以下の部品はありません。</p>}
        </section>
      </>}
      {tab === 'history' && <section className="panel"><div className="panel-head"><h2>記録履歴</h2><span className="help">直近500件をID昇順で表示 / 訂正時は元履歴を保持</span></div>
        <div className="table-wrap"><table><thead><tr><th>日時</th><th>システム</th><th>品番 / 型式</th><th>区分</th><th className="right">数量</th><th>登録者</th><th>備考</th><th></th></tr></thead>
          <tbody>{history.map(h => <tr key={h.id}><td className="nowrap">{dateTime(h.created_at)}</td><td>{h.system}</td><td>{h.part_number}<br/><small>{h.model_number}</small></td><td><span className={'chip ' + (h.direction === 'IN' ? 'ok' : 'neutral')}>{h.direction === 'IN' ? '補充' : '使用'}</span></td><td className="right quantity">{h.direction === 'IN' ? '+' : '−'}{h.quantity}</td><td>{h.operator}</td><td>{h.note}{h.reversal_of && <small> (取消レコード)</small>}</td><td>{!h.corrected && !h.reversal_of && <button className="button tiny secondary" onClick={() => openCorrection(h)}>訂正</button>}</td></tr>)}</tbody></table></div>
        {!history.length && <p className="empty">まだ入出庫履歴がありません。</p>}
      </section>}
      {tab === 'parts' && <section className="panel"><div className="panel-head"><h2>部品マスタ</h2><label className="inline-filter">
          <input type="checkbox" checked={excludeSuperseded} onChange={e => setExcludeSuperseded(e.target.checked)} />
          後継登録済みを除外
        </label></div>
        <div className="table-wrap"><table><thead><tr><th>品番</th><th>型式</th><th>品名</th><th>機器 / 部位</th><th>分類</th><th>新旧の対応</th><th>操作</th></tr></thead>
          <tbody>{filteredParts.map(p => <tr key={p.id}>
            <td className="mono">{p.part_number}</td><td className="mono">{p.model_number}</td><td>{p.name}</td>
            <td>{p.placements.filter(a => !selected || String(a.system_id) === selected).map(a =>
              <div key={a.system_id + '-' + a.equipment_id + '-' + (a.section_id ?? 'none')}>{equipments.find(e => e.id === a.equipment_id)?.name ?? '—'}
                {a.section_id && <small> / {sections.find(x => x.id === a.section_id)?.name}</small>}
                {!selected && <small>（{systems.find(sys => sys.id === a.system_id)?.name}）</small>}</div>
            )}</td>
            <td>{categories.find(c => c.id === p.category_id)?.name ?? '—'}</td>
            <td>
              {p.previous_part_id ? <span className="lineage-tag">前：{(() => {
                const prev = parts.find(x => x.id === p.previous_part_id)
                return prev ? prev.part_number + ' / ' + prev.model_number : '—'
              })()}</span> : '—'}
              {parts.filter(x => x.previous_part_id === p.id).map(next =>
                <span className="lineage-tag" key={next.id}>次：{next.part_number} / {next.model_number}</span>
              )}
            </td>
            <td><div className="master-card-actions">
              {p.has_successor ? <span className="chip neutral">後継登録済み・編集不可</span> :
                <button className="button tiny secondary" onClick={() => openEditor(p)}>編集・後継登録</button>}
              <button className="button tiny secondary" onClick={() => copyPart(p)}>コピー</button>
            </div></td>
          </tr>)}</tbody></table></div>
        {!filteredParts.length && <p className="empty">登録部品がありません。</p>}
      </section>}
      {tab === 'systems' && <section className="panel"><div className="panel-head"><h2>登録システム</h2><span className="help"></span></div>
        <div className="system-grid">{systems.map(s => <div className="system-card" key={s.id}><strong>{s.name}</strong><button className="button tiny secondary" onClick={() => setSystemModal({ id: s.id, name: s.name })}>名称変更</button></div>)}</div>
        {!systems.length && <p className="empty">最初にシステムを登録してください。</p>}
      </section>}
      {tab === 'equipment' && <section className="panel">
        <div className="panel-head"><h2>登録機器と部位</h2><span className="help">部位なしの機器も登録可能</span></div>
        <div className="system-grid">{equipments.filter(e => selected && String(e.system_id) === selected).map(e => <div className="system-card" key={e.id}>
          <strong>{e.name}</strong><small>システム：{systems.find(sys => sys.id === e.system_id)?.name}</small>{e.alias && <small>通称：{e.alias}</small>}
          <div className="master-card-actions"><button className="button tiny secondary" onClick={() => setEquipmentModal({ ...e })}>編集</button>
          <button className="button tiny secondary" onClick={() => setEquipmentModal({ copy_from: e.id, system_id: Number(selected), name: e.name, alias: e.alias })}>コピー</button>
          <button className="button tiny secondary" onClick={() => viewMatchingParts(String(e.id))}>関連部品を見る</button>
          <button className="button tiny secondary" onClick={() => setSectionModal({ equipment_id: e.id, name: '' })}>＋ 部位を追加</button></div>
          {sections.filter(section => section.equipment_id === e.id).map(section =>
            <div key={section.id} className="section-row"><span>{section.name}</span><div className="master-card-actions">
              <button className="button tiny secondary" onClick={() => {
                viewMatchingParts(String(e.id)); setSectionFilter(String(section.id))
              }}>関連部品</button>
              <button className="button tiny secondary" onClick={() => setSectionModal({ ...section })}>編集</button>
            </div></div>)}
        </div>)}</div>{!selected ? <p className="empty">システムを選択してください。</p> : equipments.filter(e => String(e.system_id) === selected).length === 0 && <p className="empty">このシステムには機器が未登録です。</p>}
      </section>}
      {tab === 'categories' && <section className="panel">
        <div className="panel-head"><h2>部品分類マスタ</h2></div>
        <div className="system-grid">{categories.map(c => <div className="system-card" key={c.id}>
          <strong>{c.name}</strong><div className="master-card-actions">
            <button className="button tiny secondary" onClick={() => viewMatchingParts('', String(c.id))}>関連部品を見る</button>
            <button className="button tiny secondary" onClick={() => setCategoryModal({ ...c })}>名称変更</button>
          </div>
        </div>)}</div>{categories.length === 0 && <p className="empty">分類が未登録です。</p>}
      </section>}
      {tab === 'alerts' && <section className="panel"><div className="panel-head"><h2>監視部品の選択</h2><span className="help">新規監視は現行品のみ。旧品の設定は後継品に在庫が入ると自動移行し、旧品の在庫がなくなれば解除します。</span></div>
        {!selected ? <p className="empty">設定するシステムを選択してください。</p> : <div className="pick-grid">
          <div className="pick-column"><h3>未設定の現行品 <span>{eligibleAlertCount}件</span></h3>
            <input className="full-input" placeholder="品番・型式・品名で検索" value={query} onChange={e => setQuery(e.target.value)} />
            <div className="pick-list">{eligibleAlertParts.filter(p => !Object.hasOwn(alertDraft, p.id) && label(p).toLowerCase().includes(query.toLowerCase())).map(p => <button key={p.id} className="pick-item" onClick={() => setAlertDraft(prev => ({ ...prev, [p.id]: '' }))}><span>{p.part_number} / {p.model_number}<small>{p.name}</small></span><b>＋</b></button>)}</div>
          </div>
          <div className="pick-column"><h3>設定対象 <span>{Object.keys(alertDraft).length}件</span></h3>
            <div className="pick-list configured">{Object.entries(alertDraft).map(([id, threshold]) => {
              const p = parts.find(x => x.id === Number(id))
              if (!p) return null
              return <div className="pick-item" key={id}><span>{p.part_number} / {p.model_number}<small>{p.name}{p.has_successor ? '（旧品：設定の変更不可・自動移行待ち）' : ''}</small></span><label>下限 <input type="number" min="1" step="1" disabled={p.has_successor} value={threshold} onChange={e => setAlertDraft(prev => ({ ...prev, [id]: e.target.value }))} /></label><button className="remove" title="監視対象から除外" onClick={() => setAlertDraft(prev => { const next = { ...prev }; delete next[Number(id)]; return next })}>×</button></div>
            })}</div>
          </div>
        </div>}
        {selected && <div className="panel-foot"><span>{alerts.length}件の保存済み設定</span><button className="button primary" disabled={busy} onClick={submitAlerts}>設定を一括保存</button></div>}
      </section>}
      <footer className="footer"><span>Spare Parts Management</span><button onClick={async () => { await act(() => api('backup', 'POST', {}), 'data/backups にSQLiteバックアップを作成しました') }}>DBバックアップを作成</button></footer>
    </main>

    {importModal && <Modal title="Excelからシステム・現在庫を取り込む" onClose={() => setImportModal(false)}>
      <p className="help">Excel出力で作ったファイルを選択してください。表示中の在庫数・下限値はExcel上で変更できます。
        非表示シートの機器・部位・分類・部品情報を使って、対象システムと期首在庫を新規作成します。入出庫の過去履歴はコピーしません。</p>
      <div className="form-grid">
        <label className="field wide">Excelファイル（.xlsx）
          <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            aria-label="取り込むExcelファイル" onChange={e => {
              setImportFile(e.target.files?.[0] ?? null); setImportPreview(null); setImportError('')
            }}/>
        </label>
      </div>
      {importError && <div className="message error" role="alert">{importError}</div>}
      {importPreview && <div className="import-summary">
        <h3>取り込み内容の確認</h3>
        <p>システム：{importPreview.systems.join('、')}</p>
        <p>機器：{importPreview.equipment_count}件 / 部品：{importPreview.part_count}件 /
          期首在庫：{importPreview.opening_rows}件（合計{importPreview.quantity_total}個） /
          下限設定：{importPreview.alert_count}件</p>
        {importPreview.already_imported && <p className="import-warning">このExcelは既に取り込み済みです。</p>}
        {importPreview.system_count === 1 && <>
          <label className="field wide">取り込み先
            <select aria-label="Excelの取り込み先" value={importTarget} onChange={e => {
              setImportTarget(e.target.value); setImportError('')
            }}>
              <option value="new">新規システムを作成（フォーク）</option>
              {importPreview.available_targets.map(s =>
                <option key={s.id} value={s.id}>既存の空システム：{s.name}</option>
              )}
            </select>
          </label>
          {importTarget === 'new' ? <>
            {importPreview.conflicts.length > 0 && <p className="import-warning">
              同名システムが存在：{importPreview.conflicts.join('、')}。新しいシステム名を指定してください。
            </p>}
            <label className="field">新規システム名（未入力ならExcelと同じ名前）
              <input value={importRename} onChange={e => setImportRename(e.target.value)} placeholder="例：制御A（別設備）" />
            </label>
          </> : <p className="help">
            指定した空システムに機器・部位・期首在庫・下限設定を取り込みます。
            既に在庫履歴や機器・割当・下限設定のあるシステムは選択できません。
          </p>}
        </>}
        {importPreview.system_count > 1 && importPreview.conflicts.length > 0 && <p className="import-warning">
          同名システムが存在：{importPreview.conflicts.join('、')}。複数システムのExcelは重複する名称を変更してから取り込んでください。
        </p>}
      </div>}
      <div className="dialog-actions">
        <button className="button secondary" onClick={() => setImportModal(false)}>キャンセル</button>
        {!importPreview ? <button className="button primary" disabled={busy || !importFile} onClick={previewImport}>内容を確認</button>
          : <button className="button primary" disabled={
            busy || importPreview.already_imported ||
            (importTarget === 'new' && importPreview.conflicts.length > 0 &&
              (!importRename.trim() || importPreview.system_count !== 1))
          } onClick={applyImport}>取り込みを確定</button>}
      </div>
    </Modal>}
    {movementModal && <Modal title={movement.direction === 'IN' ? '入庫登録' : '出庫登録'} onClose={() => setMovementModal(false)}>
      <div className="form-grid">
        <label className="field">システム<input disabled value={systems.find(s => String(s.id) === selected)?.name ?? ''} /></label>
        <label className="field">区分<input disabled value={movement.direction === 'IN' ? '補充' : '使用'} /></label>
        <div className="field wide">部品の検索・選択（品番・型式・品名）
          <div className="part-search-row">
            <input autoFocus aria-label="部品を直接入力して検索" value={partSearch} onChange={e => { setPartSearch(e.target.value); setPickedPart(null) }} placeholder="品番を直接入力、または候補から選択" />
            <button className="button secondary" onClick={() => {
              setPickerQuery(''); setPickerEquipment(''); setPickerSection(''); setPickerCategory('')
              setPartPicker(true)
            }}>一覧から選択</button>
          </div>
          {chosenPart ? <p className="selected-part">選択中：{label(chosenPart)}{!pickedPart && '（完全一致）'}</p> : <div className="suggestions">{candidates.map(p => <button key={p.id} onClick={() => choosePart(p)}>{label(p)}</button>)}{movement.direction === 'IN' && <button className="create-suggestion" onClick={openNewPart}>＋ 未登録品を新規登録する</button>}</div>}
        </div>
        <label className="field">数量<input type="number" min="1" step="1" max={movement.direction === 'OUT' ? chosenStock?.quantity : undefined} value={movement.quantity} onChange={e => setMovement(p => ({ ...p, quantity: e.target.value }))} /></label>
        {movement.direction === 'OUT' && <p className="help">出庫候補は現在庫が1以上の部品のみ（旧品番を含む）。{chosenStock ? '選択部品の現在庫：' + chosenStock.quantity + '個' : ''}</p>}
        <label className="field">登録者名<input value={movement.operator} onChange={e => setMovement(p => ({ ...p, operator: e.target.value }))} /></label>
        <label className="field wide">備考（任意）<input value={movement.note} onChange={e => setMovement(p => ({ ...p, note: e.target.value }))} /></label>
      </div>
      <div className="dialog-actions"><button className="button secondary" onClick={() => setMovementModal(false)}>キャンセル</button><button className="button primary" disabled={busy || !chosenPart || (movement.direction === 'OUT' && (
          !chosenStock || !Number.isInteger(Number(movement.quantity)) || Number(movement.quantity) > chosenStock.quantity
        ))} onClick={submitMovement}>{movement.direction === 'IN' ? '入庫を登録' : '出庫を登録'}</button></div>
    </Modal>}
    {movementModal && partPicker && <Modal title="部品一覧から選択" onClose={() => setPartPicker(false)}>
      <div className="form-grid picker-filters">
        <label className="field wide">品番・型式・品名
          <input autoFocus value={pickerQuery} onChange={e => setPickerQuery(e.target.value)} placeholder="一覧から部品を検索" />
        </label>
        <label className="field">機器
          <select aria-label="選択画面の機器" value={pickerEquipment} onChange={e => { setPickerEquipment(e.target.value); setPickerSection('') }}>
            <option value="">すべて</option>
            {equipments.filter(e => String(e.system_id) === selected).map(e => <option key={e.id} value={e.id}>{e.name}{e.alias ? '（' + e.alias + '）' : ''}</option>)}
          </select>
        </label>
        <label className="field">部位
          <select aria-label="選択画面の部位" value={pickerSection} disabled={!pickerEquipment} onChange={e => setPickerSection(e.target.value)}>
            <option value="">すべて</option>
            {sections.filter(x => String(x.equipment_id) === pickerEquipment).map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        </label>
        <label className="field">分類
          <select aria-label="選択画面の分類" value={pickerCategory} onChange={e => setPickerCategory(e.target.value)}>
            <option value="">すべて</option>
            {categories.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        </label>
      </div>
      <div className="table-wrap part-picker-table">
        <table><thead><tr><th>品番</th><th>型式</th><th>品名</th><th>分類</th><th>選択</th></tr></thead>
          <tbody>{pickerParts.map(p =>
            <tr key={p.id}><td>{p.part_number}</td><td>{p.model_number}</td><td>{p.name}</td>
              <td>{categories.find(c => c.id === p.category_id)?.name ?? '—'}</td>
              <td><button className="button tiny secondary" onClick={() => choosePart(p)}>選択</button></td></tr>)}</tbody>
        </table>
        {!pickerParts.length && <p className="empty">{movement.direction === 'IN' ? '条件に一致する現行品がありません。' : '条件に一致する在庫ありの部品がありません。'}</p>}
      </div>
      <div className="dialog-actions">
        <button className="button secondary" onClick={() => setPartPicker(false)}>閉じる</button>
      </div>
    </Modal>}
    {editor && <Modal title={editor.mode === 'edit' ? '部品変更・品番/型式引継ぎ' : editor.copyFrom ? '部品マスタのコピー登録' : '新規部品マスタ登録'} onClose={() => setEditor(null)}>
      <p className="help">{editor.copyFrom ? '既存品の内容を複写しました。品番・型式は重複しない値へ変更して新規登録してください。元データや在庫は変更されません。' : '品番または型式を変更すると新しい後継部品を作ります。旧品番の在庫・入出庫履歴は旧レコードのまま保持し、自動移動しません。'}</p>
      <div className="form-grid">{([
        ['part_number', '品番'], ['model_number', '型式'], ['name', '品名'],
      ] as const).map(([key, title]) => <label className="field" key={key}>{title}<input value={editor.values[key]} onChange={e => setEditor(p => p && ({ ...p, values: { ...p.values, [key]: e.target.value } }))} /></label>)}
        <label className="field">割当先システム（任意）
          <select aria-label="割当先システム（任意）" value={editor.values.system_id}
            onChange={e => setEditor(prev => {
              if (!prev) return prev
              const systemId = e.target.value
              const origin = parts.find(part => part.id === prev.partId || part.id === prev.copyFrom)
              const assigned = origin?.placements.filter(x => String(x.system_id) === systemId) ?? []
              return { ...prev, values: {
                ...prev.values, system_id: systemId,
                placements: assigned.length ? assigned.map(x => ({
                  equipment_id: String(x.equipment_id), section_id: String(x.section_id ?? ''),
                })) : [blankAssignment()],
              }}
            })}>
            <option value="">機器を割り当てない</option>
            {systems.map(sys => <option key={sys.id} value={sys.id}>{sys.name}</option>)}
          </select>
        </label>
        {editor.values.system_id && <div className="field wide">
          <div className="row between">
            <strong>対象機器・部位（複数登録可能）</strong>
            <button type="button" className="button tiny secondary" onClick={() => setEditor(p =>
              p && ({ ...p, values: { ...p.values, placements: [...p.values.placements, blankAssignment()] } })
            )}>＋ 機器・部位を追加</button>
          </div>
          <p className="help">同じ機器でも部位が違えば別行として登録できます。ほかのシステムの割当は変更されません。</p>
          {editor.values.placements.map((assignment, index) =>
            <div className="placement-edit-row" key={index}>
              <label className="field">機器（任意）{index > 0 ? ' #' + (index + 1) : ''}
                <select value={assignment.equipment_id} onChange={e => setEditor(p => {
                  if (!p) return p
                  const placements = p.values.placements.map((entry, i) => i === index
                    ? { equipment_id: e.target.value, section_id: '' } : entry)
                  return { ...p, values: { ...p.values, placements } }
                })}>
                  <option value="">未指定</option>
                  {equipments.filter(eq => String(eq.system_id) === editor.values.system_id).map(eq =>
                    <option key={eq.id} value={eq.id}>{eq.name}{eq.alias ? '（' + eq.alias + '）' : ''}</option>
                  )}
                </select>
              </label>
              <label className="field">部位（任意）{index > 0 ? ' #' + (index + 1) : ''}
                <select value={assignment.section_id} disabled={!assignment.equipment_id}
                  onChange={e => setEditor(p => {
                    if (!p) return p
                    const placements = p.values.placements.map((entry, i) => i === index
                      ? { ...entry, section_id: e.target.value } : entry)
                    return { ...p, values: { ...p.values, placements } }
                  })}>
                  <option value="">未指定</option>
                  {sections.filter(sec => String(sec.equipment_id) === assignment.equipment_id).map(sec =>
                    <option key={sec.id} value={sec.id}>{sec.name}</option>
                  )}
                </select>
              </label>
              <button type="button" className="button tiny secondary" aria-label={'割当行' + (index + 1) + 'を削除'}
                onClick={() => setEditor(p => p && ({ ...p, values: {
                  ...p.values, placements: p.values.placements.filter((_, i) => i !== index),
                } }))}>削除</button>
            </div>
          )}
        </div>}
        <label className="field">部品分類（任意）
          <select value={editor.values.category_id} onChange={e => setEditor(p => p && ({
            ...p, values: { ...p.values, category_id: e.target.value }
          }))}><option value="">未指定</option>{categories.map(cat => <option key={cat.id} value={cat.id}>{cat.name}</option>)}</select>
        </label>
      </div>
      {versions.length > 0 && <div className="version-list"><h3>過去の引継ぎ履歴</h3>{versions.map(v => <p key={v.id}>{v.old_part_number} / {v.old_model_number} → {v.new_part_number} / {v.new_model_number} <small>{dateTime(v.changed_at)}</small></p>)}</div>}
      <div className="dialog-actions"><button className="button secondary" onClick={() => setEditor(null)}>キャンセル</button><button className="button primary" disabled={busy} onClick={submitPart}>保存する</button></div>
    </Modal>}
    {systemModal && <Modal title={systemModal.id ? 'システム名称変更' : '新規システム登録'} onClose={() => setSystemModal(null)}>
      <label className="field">システム名<input autoFocus value={systemModal.name} onChange={e => setSystemModal(p => p && ({ ...p, name: e.target.value }))} /></label>
      <div className="dialog-actions"><button className="button secondary" onClick={() => setSystemModal(null)}>キャンセル</button><button className="button primary" disabled={busy} onClick={submitSystem}>保存する</button></div>
    </Modal>}
    {equipmentModal && <Modal title={equipmentModal.id ? '機器マスタ編集' : equipmentModal.copy_from ? '機器マスタのコピー登録' : '機器マスタ登録'} onClose={() => setEquipmentModal(null)}>
      {equipmentModal.copy_from && <p className="help">登録先のシステムを選択してください。機器名・通称・配下の部位名をコピーし、元データは変更しません。部品割当はコピーしません。</p>}
      <div className="form-grid">
        {equipmentModal.copy_from && <label className="field wide">コピー先システム
          <select value={equipmentModal.system_id} onChange={e => setEquipmentModal(p => p && ({ ...p, system_id: Number(e.target.value) }))}>
            {systems.map(sys => <option key={sys.id} value={sys.id}>{sys.name}</option>)}
          </select>
        </label>}
        <label className="field">機器名<input autoFocus value={equipmentModal.name} onChange={e => setEquipmentModal(p => p && ({ ...p, name: e.target.value }))} /></label>
        <label className="field">機器通称（任意）<input value={equipmentModal.alias} onChange={e => setEquipmentModal(p => p && ({ ...p, alias: e.target.value }))} /></label>
      </div>
      <div className="dialog-actions"><button className="button secondary" onClick={() => setEquipmentModal(null)}>キャンセル</button>
        <button className="button primary" disabled={busy} onClick={submitEquipment}>保存する</button></div>
    </Modal>}
    {sectionModal && <Modal title={sectionModal.id ? '部位名編集' : '部位を登録'} onClose={() => setSectionModal(null)}>
      <p className="help">対象機器：{equipments.find(e => e.id === sectionModal.equipment_id)?.name}</p>
      <label className="field">部位名<input autoFocus value={sectionModal.name} onChange={e => setSectionModal(p => p && ({ ...p, name: e.target.value }))} /></label>
      <div className="dialog-actions"><button className="button secondary" onClick={() => setSectionModal(null)}>キャンセル</button>
        <button className="button primary" disabled={busy} onClick={submitSection}>保存する</button></div>
    </Modal>}
    {categoryModal && <Modal title={categoryModal.id ? '部品分類編集' : '部品分類登録'} onClose={() => setCategoryModal(null)}>
      <label className="field">分類名<input autoFocus value={categoryModal.name} onChange={e => setCategoryModal(p => p && ({ ...p, name: e.target.value }))} /></label>
      <div className="dialog-actions"><button className="button secondary" onClick={() => setCategoryModal(null)}>キャンセル</button>
        <button className="button primary" disabled={busy} onClick={submitCategory}>保存する</button></div>
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
