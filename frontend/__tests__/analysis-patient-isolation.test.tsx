import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import PatientPageRoute from "@/app/patients/[patientId]/page";
import { getPatient } from "@/lib/api/patients";
import { listAnalysisRuns, runAnalysis } from "@/lib/api/analysis";
import type { AnalysisRunResponse } from "@/lib/api/types";
const route = vi.hoisted(() => ({ patientId: "patient-a" }));
vi.mock("next/navigation", () => ({ useParams: () => route, usePathname: () => `/patients/${route.patientId}`, useSearchParams: () => new URLSearchParams({ category: "safety" }), useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock("@/lib/hooks/usePageTitle", () => ({ usePageTitle: vi.fn() }));
vi.mock("@/lib/api/patients", () => ({ getPatient: vi.fn() }));
vi.mock("@/lib/api/medications", () => ({ listMedications: vi.fn().mockResolvedValue([]) }));
vi.mock("@/lib/api/symptoms", () => ({ listSymptoms: vi.fn().mockResolvedValue([]) }));
vi.mock("@/lib/api/timeline", () => ({ listTimeline: vi.fn().mockResolvedValue([]) }));
vi.mock("@/lib/api/analysis", () => ({ listAnalysisRuns: vi.fn(), runAnalysis: vi.fn() }));
function run(id: string, patientId = "patient-a"): AnalysisRunResponse { return { id, patient_id: patientId, analysis_version: "v1.0", safety_score: 100, risk_level: "low", deterministic_result: { safety_score: 100, risk_level: "low", starting_score: 100, total_points_deducted: 0, interaction_findings: [], adr_findings: [], adherence_findings: [], penalties: [] }, llm_summary: id, llm_reasoning: "Synthetic reasoning", llm_recommendations: "Synthetic recommendations", confidence_score: 50, confidence_level: "moderate", created_at: "2026-10-17T12:00:00Z" }; }
function deferred<T>() { let resolve!: (v: T) => void; const promise = new Promise<T>((r) => { resolve = r; }); return { promise, resolve }; }
beforeEach(() => { vi.clearAllMocks(); route.patientId = "patient-a"; vi.mocked(getPatient).mockImplementation(async (id) => ({ id, user_id: "owner", name: id, age: null, sex: null, weight_kg: null, renal_flag: false, hepatic_flag: false, timezone: null, breakfast_time: null, lunch_time: null, dinner_time: null, created_at: "2026-10-17T12:00:00Z", updated_at: "2026-10-17T12:00:00Z" })); vi.mocked(listAnalysisRuns).mockReset().mockResolvedValue([]); });
it("does not display a late analysis from a previously selected patient", async () => {
 const pending = deferred<AnalysisRunResponse>(); vi.mocked(runAnalysis).mockReturnValue(pending.promise);
 const page = render(<PatientPageRoute />);
 await waitFor(() => expect(screen.queryByText("Loading patient")).not.toBeInTheDocument());
 fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
 route.patientId = "patient-b"; page.rerender(<PatientPageRoute />);
 await waitFor(() => expect(getPatient).toHaveBeenCalledWith("patient-b"));
 await waitFor(() => expect(screen.queryByText("Loading patient")).not.toBeInTheDocument());
 await act(async () => pending.resolve(run("wrong-patient-explanation")));
 expect(screen.queryByText("wrong-patient-explanation")).not.toBeInTheDocument();
 expect(screen.getByRole("button", { name: "Run analysis" })).toBeEnabled();
});
it("does not replace a fresh run with history requested before that run", async () => {
 const history = deferred<AnalysisRunResponse[]>(); vi.mocked(listAnalysisRuns).mockReturnValueOnce(history.promise).mockResolvedValue([]); vi.mocked(runAnalysis).mockResolvedValue(run("fresh-explanation"));
 render(<PatientPageRoute />);
 await waitFor(() => expect(listAnalysisRuns).toHaveBeenCalledTimes(1));
 fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
 expect(await screen.findByText("fresh-explanation")).toBeInTheDocument();
 await act(async () => history.resolve([run("stale-explanation")]));
 expect(screen.getByText("fresh-explanation")).toBeInTheDocument();
 expect(screen.queryByText("stale-explanation")).not.toBeInTheDocument();
});
