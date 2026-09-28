import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./frontend/e2e",
  fullyParallel: false,
  use: { baseURL: "http://127.0.0.1:5174", browserName: "chromium", headless: true },
  webServer: [
    {
      command: ".\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --app-dir backend --port 8000",
      url: "http://127.0.0.1:8000/api/health",
      env: { APP_DATABASE_PATH: "data/v020-browser-e2e.db" },
      reuseExistingServer: false,
    },
    {
      command: "node_modules\\.bin\\vite --host 127.0.0.1 --port 5174",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
    },
  ],
});
