import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "@/app/dashboard/page";
import type { PatientResponse } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  listPatients: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("@/lib/api/patients", () => ({
  listPatients: mocks.listPatients,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
}));

vi.mock("@/components/AuthGate", () => ({
  AuthGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));

vi.mock("@/components/LoadingSkeleton", () => ({
  LoadingSkeleton: ({ label }: { label: string }) => <div role="status">{label}</div>,
}));

vi.mock("@/components/StatusBanner", () => ({
  StatusBanner: ({ children }: { children: React.ReactNode }) => <div role="alert">{children}</div>,
}));

vi.mock("@/components/PatientForm", () => ({
  PatientForm: ({ onCreated }: { onCreated: (patient: PatientResponse) => void }) => (
    <button type="button" onClick={() => onCreated(samplePatient)}>
      Create patient
    </button>
  ),
}));

vi.mock("@/lib/hooks/usePageTitle", () => ({
  usePageTitle: vi.fn(),
}));

const samplePatient: PatientResponse = {
  id: "patient-1",
  user_id: "user-1",
  name: "Asha Rao",
  age: 42,
  sex: "female",
  weight_kg: 62,
  renal_flag: false,
  hepatic_flag: false,
  created_at: "2026-09-08T08:00:00Z",
  updated_at: "2026-09-08T08:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DashboardPage", () => {
  it("renders an honest empty state when there are no patients", async () => {
    mocks.listPatients.mockResolvedValue([]);

    render(<DashboardPage />);

    await waitFor(() => expect(screen.getByText("No patients yet")).toBeInTheDocument());
    expect(screen.getByText(/Add a patient to start a medication record/)).toBeInTheDocument();
  });

  it("renders patient records and opens the selected patient", async () => {
    mocks.listPatients.mockResolvedValue([samplePatient]);

    render(<DashboardPage />);

    await waitFor(() => expect(screen.getAllByText("Asha Rao")).toHaveLength(2));
    fireEvent.click(screen.getByRole("button", { name: "Open Asha Rao" }));

    expect(mocks.push).toHaveBeenCalledWith("/patients/patient-1");
  });

  it("redirects to login when the API reports an unauthenticated session", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    mocks.listPatients.mockRejectedValue(new ApiError(401, "Unauthorized"));

    render(<DashboardPage />);

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/login"));
  });

  it("opens the patient form and navigates to the created patient", async () => {
    mocks.listPatients.mockResolvedValue([]);

    render(<DashboardPage />);

    fireEvent.click(screen.getByRole("button", { name: "Add patient" }));
    fireEvent.click(screen.getByRole("button", { name: "Create patient" }));

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/patients/patient-1"));
  });
});
