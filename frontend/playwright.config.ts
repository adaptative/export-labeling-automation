/**
 * Playwright configuration for Labelforge E2E tests (INT-024 · Sprint-17).
 *
 * Base URL is configurable via ``PLAYWRIGHT_TEST_URL`` so the same suite
 * can run against a locally-spawned Vite dev server, a docker-compose
 * test stack, or a deployed preview.
 *
 * Running ``npm run test:e2e`` drives this file via the Playwright CLI.
 */
import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.PLAYWRIGHT_TEST_URL ?? 'http://localhost:5173';
const IS_CI = !!process.env.CI;

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.spec.ts',
  fullyParallel: true,
  forbidOnly: IS_CI,
  retries: IS_CI ? 2 : 1,
  workers: IS_CI ? 2 : undefined,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: IS_CI
    ? [['github'], ['html', { outputFolder: 'playwright-report', open: 'never' }], ['list']]
    : [['html', { outputFolder: 'playwright-report', open: 'never' }], ['list']],
  outputDir: 'test-results',
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Boot the Vite preview locally when not running against a live deployment.
  webServer: process.env.PLAYWRIGHT_SKIP_WEBSERVER
    ? undefined
    : {
        command: 'npm run dev -- --host 127.0.0.1 --port 5173',
        url: BASE_URL,
        reuseExistingServer: !IS_CI,
        timeout: 60_000,
      },
});
