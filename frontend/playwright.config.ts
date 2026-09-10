import { defineConfig } from "@playwright/test";

const viewports = [
  { name: "mobile-390x844", width: 390, height: 844 },
  { name: "desktop-1440x900", width: 1440, height: 900 },
  { name: "wide-1920x1080", width: 1920, height: 1080 },
];

export default defineConfig({
  testDir: "./visual-tests",
  outputDir: "./test-results/visual",
  fullyParallel: true,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    browserName: "chromium",
    colorScheme: "light",
    reducedMotion: "reduce",
    hasTouch: true,
    trace: "retain-on-failure",
  },
  projects: viewports.map(({ name, width, height }) => ({ name, use: { viewport: { width, height } } })),
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:3000/login",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
