import { describe, expect, it } from "vitest";

import type { FeedEvent, MatchMeta, Tag } from "./contract";
import { describe as line, NBSP, roster, tickerLines } from "./describe";

const match = {
  home: { id: "sal", short_name: "Saltmarsh" },
  away: { id: "kin", short_name: "Kingsferry" },
  lineups: [
    { club_id: "sal", starters: [{ player_id: "sal-10", name: "Teo Varlan", shirt: 10, position: "AM" }], bench: [] },
    { club_id: "kin", starters: [{ player_id: "kin-07", name: "Femi Adeyani", shirt: 7, position: "RW" }], bench: [] },
  ],
} as unknown as MatchMeta;
const r = roster(match);

function feedEvent(seq: number, period: number, t: number, extra: Partial<FeedEvent> = {}): FeedEvent {
  return { seq, event_id: `e${seq}`, version: 1, type: "shot", period, t, clock: t, minute: Math.floor(t / 60) + 1, added_minute: null, ...extra };
}

function tag(period: number, t: number, kind: Tag["kind"] = "sprint"): Tag {
  return {
    kind,
    player_id: "kin-07",
    team_id: "kin",
    value: kind === "sprint" ? 33.9 : 10,
    unit: kind === "sprint" ? "km/h" : "km",
    period,
    t,
    minute: Math.floor(t / 60) + 1,
    added_minute: null,
    record: kind === "sprint",
  };
}

describe("tickerLines", () => {
  it("places each tag before the first event after it and keeps the events' own order", () => {
    // A correction issued at half-time carries the clock of the whistle, earlier than the event before it.
    const events = [feedEvent(1, 1, 100), feedEvent(2, 1, 900), feedEvent(3, 1, 850, { type: "amendment", changes: {} }), feedEvent(4, 2, 50)];
    const tags = [tag(1, 700.2), tag(2, 10, "distance"), tag(2, 400)];
    const keys = tickerLines(events, tags, r).map((l) => l.key);
    expect(keys).toEqual(["1", "tag-sprint-kin-07-1-700.2", "2", "3", "tag-distance-kin-07-2-10", "4", "tag-sprint-kin-07-2-400"]);
  });

  it("says what a tag records", () => {
    const [sprint, distance] = tickerLines([], [tag(1, 700.2), tag(2, 10, "distance")], r);
    expect(sprint.text).toBe(`Femi Adeyani (Kingsferry) sprints at 33.9${NBSP}km/h, the fastest of the match so far`);
    expect(distance.text).toBe(`Femi Adeyani (Kingsferry) has covered 10${NBSP}km`);
  });
});

describe("describe", () => {
  it("gives a shot's speed", () => {
    const shot = feedEvent(5, 2, 403, { team_id: "sal", player_id: "sal-10", outcome: "goal", speed_kmh: 97.4 });
    expect(line(shot, r).text).toBe(`Teo Varlan (Saltmarsh) shoots: scores, 97${NBSP}km/h`);
  });
});
