import { describe, expect, it } from "vitest";

import type { FeedEvent, MatchMeta, Tag } from "./contract";
import { describe as line, NBSP, roster, tickerLines } from "./describe";

const match = {
  home: { id: "sal", short_name: "Saltmarsh" },
  away: { id: "kin", short_name: "Kingsferry" },
  lineups: [
    {
      club_id: "sal",
      starters: [
        { player_id: "sal-10", name: "Teo Varlan", shirt: 10, position: "AM" },
        { player_id: "sal-04", name: "Jory Penhallow", shirt: 4, position: "CB" },
      ],
      bench: [],
    },
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

  it("marks an event the provider amended later, and keeps the amendment's own line", () => {
    // The showcase's 81st-minute goal, first given as a Penhallow own goal and credited to Adeyani at 84'.
    const goal = feedEvent(1580, 2, 2110, { event_id: "e1586", type: "goal", team_id: "kin", player_id: "sal-04", own_goal: true, minute: 81 });
    const shot = feedEvent(1581, 2, 2111, { event_id: "e1587", type: "shot", team_id: "sal", player_id: "sal-10", outcome: "saved", minute: 81 });
    const amendment = feedEvent(1620, 2, 2300, {
      event_id: "e1586",
      version: 2,
      type: "amendment",
      amends: "goal",
      changes: { player_id: { before: "sal-04", after: "kin-07" }, own_goal: { before: true, after: false } },
      corrected_event: { event_id: "e1586", minute: 81, added_minute: null, own_goal: false },
      minute: 84,
    });
    expect(tickerLines([goal, shot], [], r).map((l) => l.correctedAt)).toEqual([null, null]); // before the amendment reaches the list
    const lines = tickerLines([goal, shot, amendment], [], r);
    expect(lines.map((l) => [l.text, l.correctedAt])).toEqual([
      ["Goal, Kingsferry: own goal by Jory Penhallow", "84'"],
      ["Teo Varlan (Saltmarsh) shoots: saved", null],
      ["Correction: the 81' goal is now credited to Femi Adeyani; it had been given as an own goal by Jory Penhallow", null],
    ]);
  });
});

describe("describe", () => {
  it("gives a shot's speed", () => {
    const shot = feedEvent(5, 2, 403, { team_id: "sal", player_id: "sal-10", outcome: "goal", speed_kmh: 97.4 });
    expect(line(shot, r).text).toBe(`Teo Varlan (Saltmarsh) shoots: scores, 97${NBSP}km/h`);
  });

  it("says who a correction credits now, and who it had credited", () => {
    const amendment = (changes: Record<string, { before: unknown; after: unknown }>, own_goal: boolean) =>
      line(feedEvent(9, 2, 2300, { type: "amendment", amends: "goal", changes, corrected_event: { minute: 81, added_minute: null, own_goal } }), r).text;
    expect(amendment({ player_id: { before: "sal-10", after: "kin-07" } }, false)).toBe(
      "Correction: the 81' goal is now credited to Femi Adeyani; it had been credited to Teo Varlan",
    );
    expect(amendment({ player_id: { before: "kin-07", after: "sal-04" }, own_goal: { before: false, after: true } }, true)).toBe(
      "Correction: the 81' goal is now given as an own goal by Jory Penhallow; it had been credited to Femi Adeyani",
    );
  });

  it("names a correction's other changes in words", () => {
    const amendment = (changes: Record<string, { before: unknown; after: unknown }>) =>
      line(feedEvent(9, 2, 2300, { type: "amendment", amends: "goal", changes, corrected_event: { minute: 81, added_minute: null } }), r).text;
    expect(amendment({ assist_id: { before: null, after: "sal-10" } })).toBe("Correction: the assist on the 81' goal now goes to Teo Varlan");
    expect(amendment({ assist_id: { before: "sal-10", after: null } })).toBe("Correction: the assist on the 81' goal is withdrawn");
    expect(amendment({ outcome: { before: "saved", after: "goal" }, speed_kmh: { before: 80, after: 82 } })).toBe(
      "Correction to the 81' goal: outcome and speed",
    );
  });
});
