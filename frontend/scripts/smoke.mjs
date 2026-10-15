import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const cwd = process.cwd().replace(/\/frontend$/, '')
const server = spawn('python', ['backend/manage.py', 'runserver', '127.0.0.1:8000', '--noreload'], {
  cwd, stdio: 'inherit',
})
let browser
try {
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      const result = await fetch('http://127.0.0.1:8000/api/health')
      if (result.ok) break
    } catch {}
    if (attempt === 99) throw new Error('Django server did not start')
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1360, height: 900 }, acceptDownloads: true })
  page.on('pageerror', error => { throw error })
  await page.goto('http://127.0.0.1:8000/')
  await page.getByRole('button', { name: 'システム管理' }).click()
  await page.getByRole('button', { name: '＋ システムを追加' }).click()
  await page.getByRole('dialog').getByLabel('システム名').fill('テストシステムA')
  await page.getByRole('dialog').getByRole('button', { name: '保存する' }).click()
  await page.getByText('システムを保存しました').waitFor()
  await page.getByRole('button', { name: '部品マスタ' }).click()
  await page.getByRole('button', { name: '＋ 部品を追加' }).click()
  await page.getByRole('dialog').getByLabel('品番').fill('P100')
  await page.getByRole('dialog').getByLabel('型式').fill('V1')
  await page.getByRole('dialog').getByLabel('品名').fill('テストセンサ')
  await page.getByRole('dialog').getByRole('button', { name: '保存する' }).click()
  await page.getByText('部品を登録しました').waitFor()
  await page.getByRole('button', { name: '現在庫一覧' }).click()
  await page.getByLabel('対象システム').selectOption({ label: 'テストシステムA' })
  await page.getByRole('button', { name: '＋ 入出庫を登録' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByPlaceholder('入力すると候補を絞り込みます').fill('P100')
  await dialog.locator('.suggestions button').first().click()
  await dialog.getByLabel('数量').fill('5')
  await dialog.getByLabel('企業名').fill('テスト会社')
  await dialog.getByLabel('登録者名').fill('テスト担当者')
  await dialog.getByRole('button', { name: '履歴を登録' }).click()
  await page.getByText('入出庫を記録しました').waitFor()
  assert.equal(await page.getByRole('cell', { name: '5', exact: true }).count(), 1)

  await page.getByRole('button', { name: '下限アラート設定' }).click()
  await page.locator('.pick-column').first().locator('.pick-item').first().click()
  await page.locator('.configured input').first().fill('7')
  await page.getByRole('button', { name: '設定を一括保存' }).click()
  await page.getByText('下限アラートを一括保存しました').waitFor()
  await page.getByRole('button', { name: '現在庫一覧' }).click()
  await page.getByText('下限以下').first().waitFor()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Excel出力' }).click()
  const download = await downloadPromise
  assert.equal(download.suggestedFilename(), 'spare_parts_stock.xlsx')
  console.log('Playwright smoke test OK: master, movement, alert and Excel export')
} finally {
  if (browser) await browser.close()
  server.kill()
}
