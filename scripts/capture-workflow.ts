/** Capture the compact script-first CLIO workflow. */
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

const baseURL = process.env.CLIO_BASE_URL ?? process.env.FILMGRAPH_BASE_URL ?? 'http://127.0.0.1:3000'
const outputDir = process.env.CLIO_CAPTURE_DIR ?? process.env.FILMGRAPH_CAPTURE_DIR
if (!outputDir) {
  console.error('CLIO_CAPTURE_DIR is not set; refusing to create screenshots.')
  process.exit(1)
}

const { chromium } = await import('playwright')
const executablePath = process.env.CLIO_CHROME_PATH ?? process.env.FILMGRAPH_CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) })
await mkdir(outputDir, { recursive: true })

const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
await desktop.goto(`${baseURL.replace(/\/$/, '')}/workspace`, { waitUntil: 'networkidle' })
await desktop.getByTestId('workspace').waitFor({ state: 'visible' })
await desktop.waitForFunction(() => document.querySelector('[data-testid="workspace"]')?.getAttribute('data-hydrated') === 'true')

const firstRunGuide = desktop.getByTestId('onboarding')
if (await firstRunGuide.count() > 0 && await firstRunGuide.isVisible()) {
  await desktop.screenshot({ path: path.join(outputDir, '00-onboarding.png'), fullPage: false })
}

async function enterMap(page: import('playwright').Page) {
  const guide = page.getByTestId('onboarding')
  if (await guide.count() > 0 && await guide.isVisible()) {
    // Captures document the unobstructed workspace; the guide itself is
    // covered by the first-run interaction and the e2e onboarding test.
    await guide.getByRole('button', { name: 'SKIP', exact: true }).click()
  }
}

await enterMap(desktop)

async function shot(name: string) {
  await desktop.screenshot({ path: path.join(outputDir, name), fullPage: false })
}

async function waitForAgentDone() {
  // The streamed evidence can arrive before the run-status button returns to
  // ANALYZE. Wait for that explicit idle state so captures never look stuck.
  await desktop.getByRole('button', { name: 'ANALYZE', exact: true }).waitFor({ state: 'visible', timeout: 15000 })
}

await shot('01-workspace-loaded.png')
await desktop.getByRole('button', { name: 'TRACE PATH', exact: true }).click()
await shot('02-revision-trace.png')
await desktop.getByRole('button', { name: 'SCENES', exact: true }).click()
await desktop.getByRole('button', { name: /SC 17/ }).click()
await desktop.getByRole('button', { name: 'SHOW MAP', exact: true }).click()
await shot('03-impact-inspector.png')

await desktop.getByRole('button', { name: /ASK AGENT/i }).click()
await desktop.getByRole('button', { name: 'ANALYZE', exact: true }).click()
await desktop.getByText(/UPSTREAM:/i).waitFor({ state: 'visible', timeout: 15000 })
await waitForAgentDone()
await shot('04-agent-recommendation.png')

await desktop.locator('.fg-agent-actions button').filter({ hasText: 'EDIT' }).click()
await desktop.getByRole('button', { name: 'ANALYZE', exact: true }).click()
await desktop.getByText(/AFFECTED:/i).waitFor({ state: 'visible', timeout: 15000 })
await waitForAgentDone()
await shot('05-runtime-decision.png')

await desktop.locator('.fg-agent-actions button').filter({ hasText: 'REMOVE' }).click()
await desktop.getByRole('button', { name: 'ANALYZE', exact: true }).click()
await desktop.getByText(/UNNEEDED IF REMOVED:/i).waitFor({ state: 'visible', timeout: 15000 })
await waitForAgentDone()
await shot('06-editorial-approved.png')

await desktop.locator('.fg-agent-actions button').filter({ hasText: 'ADD' }).click()
await desktop.getByRole('button', { name: 'ANALYZE', exact: true }).click()
await desktop.getByText(/POSSIBLE CONNECTIONS:/i).waitFor({ state: 'visible', timeout: 15000 })
await waitForAgentDone()
await shot('07-delivery-variants.png')

await desktop.getByRole('button', { name: 'Close agent', exact: true }).click()
await desktop.getByRole('button', { name: 'SCRIPT MAP', exact: true }).click()
await desktop.locator('[data-node-kind="revision"]').click()
await desktop.getByText('SCRIPT CHANGE', { exact: true }).waitFor({ state: 'visible' })
await shot('08-provenance-complete.png')

// Git-backed revision proof: public fixture, read-only load, no apply side effect.
await desktop.getByRole('button', { name: 'SCRIPT GIT', exact: true }).click()
await desktop.getByLabel('GITHUB FILE OR REPOSITORY').fill('https://github.com/owner/repository/blob/main/script.fountain')
await desktop.getByRole('button', { name: 'LOAD', exact: true }).click()
await desktop.getByText(/^LOADED .+ · \d+ SCENES$/).waitFor({ state: 'visible', timeout: 20000 })
await shot('10-script-git-loaded.png')
await desktop.close()

const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' })
await mobile.goto(`${baseURL.replace(/\/$/, '')}/workspace`, { waitUntil: 'networkidle' })
await mobile.getByTestId('workspace').waitFor({ state: 'visible' })
await mobile.waitForFunction(() => document.querySelector('[data-testid="workspace"]')?.getAttribute('data-hydrated') === 'true')
await enterMap(mobile)
await mobile.screenshot({ path: path.join(outputDir, '09-mobile-workspace.png'), fullPage: false })
await mobile.close()
await browser.close()

console.log(`Captured workflow screenshots in ${outputDir}`)
