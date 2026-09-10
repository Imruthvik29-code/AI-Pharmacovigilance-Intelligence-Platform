import { expect, test, type Page, type TestInfo } from "@playwright/test";

const patient = { id: "patient-1", user_id: "user-1", name: "Alex Morgan", relation: "Self", age: 42, sex: "Female", weight_kg: 68, renal_flag: false, hepatic_flag: false, created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-01T10:00:00Z" };
const medications = [
  { id: "med-1", patient_id: patient.id, condition_id: null, purpose_text: "Atrial fibrillation", drug_id: "drug-1", dose: "5 mg", times_per_day: 2, interval_hours: 12, duration_days: null, status: "active", start_date: "2026-08-01", end_date: null, created_at: "2026-08-01T10:00:00Z", updated_at: "2026-08-01T10:00:00Z", drug_name: "Apixaban", drug_generic_name: "apixaban", drug_term_type: "IN", drug_source: "RxNorm" },
  { id: "med-2", patient_id: patient.id, condition_id: null, purpose_text: "Pain", drug_id: "drug-2", dose: "400 mg", times_per_day: 1, interval_hours: 24, duration_days: 5, status: "active", start_date: "2026-09-05", end_date: null, created_at: "2026-09-05T10:00:00Z", updated_at: "2026-09-05T10:00:00Z", drug_name: "Ibuprofen", drug_generic_name: "ibuprofen", drug_term_type: "IN", drug_source: "RxNorm" },
];
const symptoms = [{ id: "symptom-1", patient_id: patient.id, condition_id: null, medication_id: "med-2", description: "Easy bruising", severity: "moderate", onset_date: "2026-09-08", resolved_date: null, created_at: "2026-09-08T12:00:00Z", updated_at: "2026-09-08T12:00:00Z" }];
const timeline = [{ id: "event-1", patient_id: patient.id, event_type: "symptom", ref_id: "symptom-1", event_title: "Symptom recorded", event_description: "Easy bruising", event_time: "2026-09-08T12:00:00Z", payload: null, created_at: "2026-09-08T12:00:00Z" }];
const analysis = { id: "analysis-1", patient_id: patient.id, analysis_version: "1.0", deterministic_result: { safety_score: 72, risk_level: "moderate", starting_score: 100, total_points_deducted: 28, interaction_findings: [{ interaction_rule_id: "interaction-1", drug_a_id: "drug-1", drug_a_name: "Apixaban", drug_b_id: "drug-2", drug_b_name: "Ibuprofen", severity: "moderate", mechanism: "Additive bleeding risk", recommendation: "Review concurrent use", source: "Mock clinical rule" }], adr_findings: [], adherence_findings: [], penalties: [{ category: "interaction", description: "Potential bleeding interaction", severity: "moderate", points: 28 }] }, safety_score: 72, risk_level: "moderate", llm_summary: "Concurrent treatment may increase bleeding risk.", llm_reasoning: "Mock-data explanation for visual QA.", llm_recommendations: "Discuss NSAID use with the care team.", confidence_score: .92, confidence_level: "high", created_at: "2026-09-09T10:00:00Z" };

async function authenticateAndMock(page: Page) {
  await page.addInitScript(() => sessionStorage.setItem("pv.session", JSON.stringify({ accessToken: "visual-token", refreshToken: null, tokenType: "bearer", expiresIn: 3600, user: { id: "user-1", email: "qa@example.test" } })));
  await page.route("**/api/v1/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    const responses: Record<string, unknown> = {
      "/api/v1/patients": [patient],
      [`/api/v1/patients/${patient.id}`]: patient,
      [`/api/v1/patients/${patient.id}/medications`]: medications,
      [`/api/v1/patients/${patient.id}/symptoms`]: symptoms,
      [`/api/v1/patients/${patient.id}/timeline`]: timeline,
      [`/api/v1/patients/${patient.id}/analysis`]: [analysis],
    };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(responses[pathname] ?? {}) });
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
}

async function capture(page: Page, testInfo: TestInfo, scenario: string) {
  await page.screenshot({ path: testInfo.outputPath(`${scenario}.png`), fullPage: true });
}

test.beforeEach(async ({ page }) => authenticateAndMock(page));

test("patient list mock-data scenario", async ({ page }, testInfo) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
  await expect(page.getByText("Alex Morgan")).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await capture(page, testInfo, "patient-list");
});

test("patient overview stack supports layout, keyboard, tap, and swipe", async ({ page }, testInfo) => {
  await page.goto(`/patients/${patient.id}`);
  const stack = page.getByTestId("workspace-card-stack");
  await expect(stack).toHaveAttribute("data-active-card", "safety");
  await expectNoHorizontalOverflow(page);

  const active = stack.locator('[data-workspace-card="safety"]');
  const companions = stack.getByTestId("workspace-companion-card");
  const [activeBox, firstCompanion, secondCompanion] = await Promise.all([active.boundingBox(), companions.nth(0).boundingBox(), companions.nth(1).boundingBox()]);
  expect(activeBox && firstCompanion && secondCompanion).toBeTruthy();
  expect(firstCompanion!.x).toBeGreaterThan(activeBox!.x);
  expect(firstCompanion!.y).toBeGreaterThan(activeBox!.y);
  expect(secondCompanion!.x).toBeGreaterThan(firstCompanion!.x);
  expect(secondCompanion!.y).toBeGreaterThan(firstCompanion!.y);
  expect(await stack.locator('[data-workspace-card]:visible').count()).toBe(1);

  await stack.focus();
  await page.keyboard.press("ArrowRight");
  await expect(stack).toHaveAttribute("data-active-card", "medications");
  await page.getByRole("button", { name: "Open Symptoms" }).tap();
  await expect(stack).toHaveAttribute("data-active-card", "symptoms");
  await stack.dispatchEvent("pointerdown", { clientX: 300, clientY: 200, pointerId: 1, pointerType: "touch" });
  await stack.dispatchEvent("pointerup", { clientX: 180, clientY: 200, pointerId: 1, pointerType: "touch" });
  await expect(stack).toHaveAttribute("data-active-card", "timeline");
  await capture(page, testInfo, "patient-overview");
});

test("Safety detail replaces the overview", async ({ page }, testInfo) => {
  await page.goto(`/patients/${patient.id}`);
  await page.getByRole("button", { name: /View safety details/ }).click();
  await expect(page.getByRole("heading", { name: "Safety analysis" })).toBeVisible();
  await expect(page.getByTestId("workspace-card-stack")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Overview" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await capture(page, testInfo, "safety-detail");
});
