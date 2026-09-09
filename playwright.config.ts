import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  webServer: { command: 'pnpm run dev', port: 3000, reuseExistingServer: true },
  use: {
    baseURL: 'http://127.0.0.1:3000',
    reducedMotion: 'reduce',
    launchOptions: { executablePath: process.env.CLIO_CHROME_PATH ?? process.env.FILMGRAPH_CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' },
  },
})
