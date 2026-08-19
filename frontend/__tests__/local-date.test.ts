import { describe, expect, it } from "vitest";
import { localCalendarDate } from "@/lib/dates/localDate";

describe("localCalendarDate", () => {
  it("formats the local calendar day with zero-padded month and day", () => {
    expect(localCalendarDate(new Date(2026, 0, 5, 23, 30, 0))).toBe("2026-01-05");
    expect(localCalendarDate(new Date(2026, 7, 19, 23, 30, 0))).toBe("2026-08-19");
  });
});
