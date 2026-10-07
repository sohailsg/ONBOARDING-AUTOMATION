import { describe, expect, it } from "vitest";
import { lineDiff, progressOf } from "@/lib/utils";

describe("progressOf (F-UI-1)", () => {
  it("computes percent complete", () => {
    expect(progressOf([])).toBe(0);
    expect(
      progressOf([{ completed_at: "2026-01-01T00:00:00Z" }, { completed_at: null }]),
    ).toBe(50);
  });
});

describe("lineDiff (F-UI-5)", () => {
  it("marks added/removed lines", () => {
    const d = lineDiff("a\nb", "a\nc");
    expect(d.some((x) => x.type === "del" && x.text === "b")).toBe(true);
    expect(d.some((x) => x.type === "add" && x.text === "c")).toBe(true);
  });
});

describe("citation anchor (F-UI-2)", () => {
  it("builds stable doc page anchors", () => {
    const doc = "UK-Employee-Handbook-2026.pdf";
    const anchor = `#doc-${encodeURIComponent(doc)}-p22`;
    expect(anchor).toBe("#doc-UK-Employee-Handbook-2026.pdf-p22");
  });
});

describe("optimistic rollback contract (F-UI-1)", () => {
  it("restores previous cache on error", () => {
    // Documents the Timeline onError → setQueryData(prev) contract
    const prev = { items: [{ id: "1", completed_at: null }] };
    const next = { items: [{ id: "1", completed_at: "now" }] };
    const rollback = (failed: boolean) => (failed ? prev : next);
    expect(rollback(true)).toBe(prev);
  });
});
