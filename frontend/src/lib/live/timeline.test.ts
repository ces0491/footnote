import { describe, expect, it } from "vitest";

import type { RunDescriptor } from "./contract";
import { clockLabel, liveReplaySecond, minuteLabel, moment } from "./timeline";

// The showcase match's first half lasts 3,082.59 s, and replays shorten the break to 30 s.
const timeline = { first_half_end: 3082.59, half_time: 30 };

describe("moment", () => {
  it("places replay seconds in the first half, the break and the second half", () => {
    expect(moment(1357.25, timeline)).toEqual({ period: 1, t: 1357.25 });
    expect(moment(timeline.first_half_end, timeline)).toEqual({ period: 1, t: timeline.first_half_end });
    expect(moment(timeline.first_half_end + 15, timeline)).toBeNull();
    const kickOff = moment(timeline.first_half_end + 30, timeline);
    expect(kickOff?.period).toBe(2);
    expect(kickOff?.t).toBeCloseTo(0);
    expect(moment(timeline.first_half_end + 30 + 2110.06, timeline)?.t).toBeCloseTo(2110.06);
  });

  it("holds the clock at kick-off before the match starts", () => {
    expect(moment(-5, timeline)).toEqual({ period: 1, t: 0 });
  });
});

describe("liveReplaySecond", () => {
  const run = { start_replay: 2070, started_at: 1_800_000_000_000, speed: 4, timeline } as RunDescriptor;

  it("runs from the start point at the run's speed", () => {
    expect(liveReplaySecond(run, run.started_at + 10_000)).toBe(2110);
  });

  it("stays at the start point until the run starts", () => {
    expect(liveReplaySecond(run, run.started_at - 5_000)).toBe(2070);
  });
});

describe("labels", () => {
  it("shows the match clock as a broadcast does, with added time after 45 and 90", () => {
    expect(clockLabel({ period: 1, t: 1421 })).toBe("23:41");
    expect(clockLabel({ period: 1, t: 2700 + 130 })).toBe("45+2:10");
    expect(clockLabel({ period: 2, t: 0 })).toBe("45:00");
    expect(clockLabel({ period: 2, t: 2700 + 185 })).toBe("90+3:05");
  });

  it("shows an event's minute with any added minute", () => {
    expect(minuteLabel(23, null)).toBe("23'");
    expect(minuteLabel(45, 2)).toBe("45+2'");
  });
});
