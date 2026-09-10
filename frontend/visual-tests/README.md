# Browser visual QA

Run `npm run test:visual`. Playwright starts Next.js, injects an authenticated session, and intercepts API calls with deterministic patient data. Each of the patient-list, patient-overview, and Safety-detail scenarios runs at 390×844, 1440×900, and 1920×1080. Screenshots, traces on failure, and the HTML report are written under `test-results/visual` and `playwright-report`.

The suite asserts horizontal fit, the active and companion card geometry, one visible active card, overview-to-detail replacement, keyboard navigation, tap selection, and swipe selection. Install the Chromium runtime once with `npx playwright install chromium` when setting up a new machine.
