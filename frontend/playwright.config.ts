import { defineConfig } from '@playwright/test'

// End-to-end tests against the REAL stack: PostgreSQL (docker compose up -d), the FastAPI
// backend, the Vite dev server and, for answers, Ollama. Run with: npm run e2e
export default defineConfig({
  testDir: './e2e',
  timeout: 120_000, // a local LLM answer can take a while
  workers: 1, // the tests share one database
  use: {
    baseURL: 'http://localhost:5173',
    channel: 'chrome', // use the installed Google Chrome; no browser download needed
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: '.venv/bin/uvicorn app.main:app --port 8001',
      cwd: '../backend',
      url: 'http://localhost:8001/health',
      reuseExistingServer: true,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
    },
  ],
})
