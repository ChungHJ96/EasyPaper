import { test, expect } from '@playwright/test'
import { mockBaseRoutes, gotoApp, SAMPLE_PDF_CITATION } from './helpers.js'

test('참고문헌 목록에 있는 번호의 본문 인용 표기만 클릭 가능한 오버레이가 생기고, 클릭하면 원문 텍스트와 함께 툴팁이 뜬다', async ({ page }) => {
  const docC = { id: 'doc-C', filename: 'Citation.pdf', total_pages: 1, metadata: { title: 'Citation Sample Paper' }, translated_pages: [] }
  await mockBaseRoutes(page, { documents: [docC] })
  await page.route('**/api/library/doc-C/pdf', route =>
    route.fulfill({ status: 200, contentType: 'application/pdf', body: SAMPLE_PDF_CITATION }))
  // [2]는 참고문헌 목록에서 의도적으로 제외 - 목록에 없는 번호는 클릭 불가능해야 한다
  await page.route('**/api/library/doc-C/references', route =>
    route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ references: { '1': 'Vaswani et al. Attention Is All You Need. 2017.' } }),
    }))

  await gotoApp(page)
  await page.evaluate(() => { location.hash = '#viewer?id=doc-C' })
  await page.waitForTimeout(1500)

  const markerBoxes = page.locator('.citation-marker-box')
  await expect(markerBoxes).toHaveCount(1)
  await expect(markerBoxes.first()).toHaveAttribute('data-ref-num', '1')

  await markerBoxes.first().click()
  await expect(page.locator('.citation-tooltip')).not.toHaveClass(/hidden/)
  await expect(page.locator('.citation-tooltip-text')).toHaveText('Vaswani et al. Attention Is All You Need. 2017.')
})

test('툴팁은 자동 원문 검색 없이 Google Scholar 수동 검색을 제공한다', async ({ page, context }) => {
  const docC = { id: 'doc-C', filename: 'Citation.pdf', total_pages: 1, metadata: { title: 'Citation Sample Paper' }, translated_pages: [] }
  await mockBaseRoutes(page, { documents: [docC] })
  await page.route('**/api/library/doc-C/pdf', route =>
    route.fulfill({ status: 200, contentType: 'application/pdf', body: SAMPLE_PDF_CITATION }))
  await page.route('**/api/library/doc-C/references', route =>
    route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ references: { '1': 'Vaswani et al. Attention Is All You Need. 2017.' } }),
    }))
  await context.route('https://scholar.google.com/**', route =>
    route.fulfill({ status: 200, contentType: 'text/html', body: '<html></html>' }))

  await gotoApp(page)
  await page.evaluate(() => { location.hash = '#viewer?id=doc-C' })
  await page.waitForTimeout(1500)

  await page.locator('.citation-marker-box').first().click()
  await expect(page.locator('.citation-tooltip-resolve-btn')).toHaveCount(0)

  const [popup] = await Promise.all([
    context.waitForEvent('page'),
    page.click('.citation-tooltip-scholar-btn'),
  ])
  await popup.waitForLoadState('domcontentloaded')
  expect(decodeURIComponent(popup.url())).toBe('https://scholar.google.com/scholar?q="Attention Is All You Need"')
})

test('인용 표기가 아닌 다른 곳을 클릭하면(예: 스크롤) 열려 있던 툴팁이 닫힌다', async ({ page }) => {
  const docC = { id: 'doc-C', filename: 'Citation.pdf', total_pages: 1, metadata: { title: 'Citation Sample Paper' }, translated_pages: [] }
  await mockBaseRoutes(page, { documents: [docC] })
  await page.route('**/api/library/doc-C/pdf', route =>
    route.fulfill({ status: 200, contentType: 'application/pdf', body: SAMPLE_PDF_CITATION }))
  await page.route('**/api/library/doc-C/references', route =>
    route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ references: { '1': 'Vaswani et al. Attention Is All You Need. 2017.' } }),
    }))

  await gotoApp(page)
  await page.evaluate(() => { location.hash = '#viewer?id=doc-C' })
  await page.waitForTimeout(1500)

  await page.locator('.citation-marker-box').first().click()
  await expect(page.locator('.citation-tooltip')).not.toHaveClass(/hidden/)

  await page.evaluate(() => document.querySelector('#viewer-scroll-container')?.dispatchEvent(new Event('scroll', { bubbles: true })))
  await expect(page.locator('.citation-tooltip')).toHaveClass(/hidden/)
})

test('참고문헌이 길어 툴팁 내부를 스크롤해도 툴팁이 닫히지 않는다', async ({ page }) => {
  const docC = { id: 'doc-C', filename: 'Citation.pdf', total_pages: 1, metadata: { title: 'Citation Sample Paper' }, translated_pages: [] }
  await mockBaseRoutes(page, { documents: [docC] })
  await page.route('**/api/library/doc-C/pdf', route =>
    route.fulfill({ status: 200, contentType: 'application/pdf', body: SAMPLE_PDF_CITATION }))
  await page.route('**/api/library/doc-C/references', route =>
    route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ references: { '1': 'Vaswani et al. ' + 'A long citation entry '.repeat(80) + ' Attention Is All You Need. 2017.' } }),
    }))

  await gotoApp(page)
  await page.evaluate(() => { location.hash = '#viewer?id=doc-C' })
  await page.waitForTimeout(1500)

  await page.locator('.citation-marker-box').first().dispatchEvent('mouseenter')
  const tooltip = page.locator('.citation-tooltip')
  await expect(tooltip).not.toHaveClass(/hidden/)
  await expect.poll(() => tooltip.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true)

  await tooltip.evaluate(el => {
    el.scrollTop = 100
    el.dispatchEvent(new Event('scroll'))
  })

  await expect(tooltip).not.toHaveClass(/hidden/)
  await expect.poll(() => tooltip.evaluate(el => el.scrollTop)).toBeGreaterThan(0)
})
