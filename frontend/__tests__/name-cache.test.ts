import { beforeEach, describe, expect, it } from "vitest";
import {
  UNCACHED_DRUG_LABEL,
  displayDrugName,
  lookupDrug,
  rememberDrug,
} from "@/lib/drugs/nameCache";

describe("drug name cache", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("remembers a catalog search result by drug id", () => {
    rememberDrug({
      id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      name: "Examplecin",
      rxcui: "123",
      source: "RxNorm",
      term_type: "IN",
    });
    expect(lookupDrug("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")).toEqual({
      name: "Examplecin",
      rxcui: "123",
      source: "RxNorm",
      term_type: "IN",
    });
  });

  it("returns a human-readable fallback instead of a UUID", () => {
    const missing = "12345678-aaaa-bbbb-cccc-dddddddddddd";
    expect(lookupDrug(missing)).toBeNull();
    expect(displayDrugName(missing)).toEqual({
      name: UNCACHED_DRUG_LABEL,
      cached: false,
      termType: null,
    });
    expect(displayDrugName(missing).name).not.toContain(missing);
  });
});
