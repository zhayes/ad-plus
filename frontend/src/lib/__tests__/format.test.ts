import { describe, expect, it } from "vitest";
import { basename, fmtBytes, fmtDur, fmtEta, fmtTime, fmtUsd } from "../format";

describe("format", () => {
  it("prints today's clock without a date", () => {
    const now = new Date();
    expect(fmtTime(now.getTime() / 1000)).toMatch(/^\d{2}:\d{2}$/);
  });

  it("prints older timestamps with a date", () => {
    const old = new Date(2026, 0, 2, 9, 5);
    expect(fmtTime(old.getTime() / 1000)).toBe("1月2日 09:05");
  });

  it("scales byte units", () => {
    expect(fmtBytes(0)).toBe("0");
    expect(fmtBytes(999)).toBe("999B");
    expect(fmtBytes(2048)).toBe("2K");
    expect(fmtBytes(1.4 * 1024 * 1024)).toBe("1.4M");
  });

  it("formats durations and quotes", () => {
    expect(fmtDur(0)).toBe("0:00");
    expect(fmtDur(75)).toBe("1:15");
    expect(fmtUsd(0)).toBe("—");
    expect(fmtUsd(0.4242)).toBe("$0.42");
    expect(fmtEta(720)).toBe("12 分钟");
    expect(fmtEta(5400)).toBe("1 小时 30 分");
  });

  it("takes the last path segment", () => {
    expect(basename("/a/b/c.mp4")).toBe("c.mp4");
    expect(basename(undefined)).toBe("");
  });
});
