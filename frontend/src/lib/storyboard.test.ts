import { describe, expect, it } from "vitest";
import { moveShot, recomputeTimeline, timecode, totalDuration } from "./storyboard";

const shots = [
  { id: "s1", duration_s: 2, start_s: 0, end_s: 2, index: 1 },
  { id: "s2", duration_s: 3, start_s: 2, end_s: 5, index: 2 },
  { id: "s3", duration_s: 2.5, start_s: 5, end_s: 7.5, index: 3 },
];

describe("moveShot", () => {
  it("moves before a target", () => {
    expect(moveShot(shots, "s3", "s1", false).map((s) => s.id)).toEqual(["s3", "s1", "s2"]);
  });

  it("moves after a target", () => {
    expect(moveShot(shots, "s1", "s3", true).map((s) => s.id)).toEqual(["s2", "s3", "s1"]);
  });

  it("is a no-op for the same shot or a missing id", () => {
    expect(moveShot(shots, "s2", "s2", false)).toBe(shots);
    expect(moveShot(shots, "nope", "s1", false)).toBe(shots);
  });
});

describe("recomputeTimeline", () => {
  it("rebuilds start/end in array order", () => {
    const moved = recomputeTimeline(moveShot(shots, "s2", "s1", false));
    expect(moved.map((s) => [s.id, s.start_s, s.end_s])).toEqual([
      ["s2", 0, 3],
      ["s1", 3, 5],
      ["s3", 5, 7.5],
    ]);
  });

  it("keeps a minimum shot duration", () => {
    const tiny = recomputeTimeline([{ id: "s1", duration_s: 0, start_s: 0, end_s: 0, index: 1 }]);
    expect(tiny[0].duration_s).toBe(2.5);
  });
});

describe("helpers", () => {
  it("totals and formats timecode", () => {
    expect(totalDuration(shots)).toBe(7.5);
    expect(timecode(7.5)).toBe("0:07.5");
  });
});
