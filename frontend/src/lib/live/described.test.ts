import { describe, expect, it } from "vitest";

import type { EventMessage, FeedEvent, MatchMeta } from "./contract";
import { atDetail, cardLines, type DescribedLine, eventLines, merged, nextSaying, openingLine, spokenScore, where } from "./described";
import { roster } from "./describe";
import { KICK_OFF_VIEW } from "./run-reducer";
import { eventPush, feedEventFixture, insightFixture } from "./test-fixtures";

const club = (id: string, name: string, short: string) => ({ id, code: id.toUpperCase(), name, short_name: short, colours: ["#000", "#fff"] as [string, string], formation: "4-3-3" });
const player = (id: string, name: string) => ({ player_id: id, name, shirt: 1, position: "CM" });

// Saltmarsh attack towards x = 105 in the first half, Kingsferry towards x = 0.
const MATCH: MatchMeta = {
  match_id: "m",
  competition: "Footnote League",
  season: "2026/27",
  venue: "The Saltings",
  kickoff: "2027-03-07T13:00:00Z",
  referee: { id: "ref", name: "Ref" },
  home: club("sal", "Saltmarsh Rovers", "Saltmarsh"),
  away: club("kin", "Kingsferry Athletic", "Kingsferry"),
  lineups: [
    {
      club_id: "sal",
      formation: "4-3-3",
      attacking_direction: { first_half: "+x", second_half: "-x" },
      starters: [player("sal-10", "Teo Varlan"), player("sal-09", "Marco Dellow")],
      bench: [],
    },
    {
      club_id: "kin",
      formation: "4-4-2",
      attacking_direction: { first_half: "-x", second_half: "+x" },
      starters: [player("kin-07", "Femi Adeyani"), player("kin-01", "Isaac Brennholt"), player("kin-04", "Jory Penhallow")],
      bench: [],
    },
  ],
};
const R = roster(MATCH);

function said(seq: number, event: Partial<FeedEvent>, extra: Partial<EventMessage> = {}): DescribedLine {
  const lines = eventLines(MATCH, R, KICK_OFF_VIEW, 0, [eventPush(seq, { event: feedEventFixture(seq, event), ...extra })]);
  return lines[1];
}

describe("where the ball is", () => {
  it("names the part of the pitch from the side in possession's view", () => {
    expect(where({ u: 95, v: 34 })).toBe("in the box");
    expect(where({ u: 8, v: 30 })).toBe("in their own box");
    expect(where({ u: 52, v: 36 })).toBe("in the centre circle");
    expect(where({ u: 80, v: 60 })).toBe("in the final third on the left");
    expect(where({ u: 40, v: 10 })).toBe("in their own half on the right");
    expect(where({ u: 20, v: 34 })).toBe("deep in their own half");
  });

  it("turns with the side's attacking direction", () => {
    // The same spot on the pitch: near Kingsferry's goal for Saltmarsh, their own box for Kingsferry.
    const sal = said(1, { type: "possession_change", team_id: "sal", cause: "interception", x: 95, y: 34 });
    const kin = said(2, { type: "possession_change", team_id: "kin", cause: "interception", x: 95, y: 34 });
    expect(sal.text).toBe("Saltmarsh intercept, in the box.");
    expect(kin.text).toBe("Kingsferry intercept, in their own box.");
  });
});

describe("the lines", () => {
  it("says the build-up at standard detail and the rest only at full", () => {
    const forward = said(1, { type: "pass", team_id: "sal", player_id: "sal-10", recipient_id: "sal-09", outcome: "complete", pass_type: "open_play", length: 28, x: 50, y: 34, end_x: 78, end_y: 30 });
    expect(forward.text).toBe("Varlan, in the centre circle, plays a pass forward to Dellow, in the final third.");
    expect(forward.level).toBe("standard");
    const sideways = said(2, { type: "pass", team_id: "sal", player_id: "sal-10", recipient_id: "sal-09", outcome: "complete", pass_type: "open_play", length: 8, x: 30, y: 30, end_x: 32, end_y: 38 });
    expect(sideways.level).toBe("full");
    expect(atDetail(sideways, "standard")).toBe(false);
    expect(atDetail(forward, "standard")).toBe(true);
    expect(atDetail(forward, "key")).toBe(false);
  });

  it("gives the score as a screen reader says it after each goal", () => {
    const goal = said(1, { type: "goal", team_id: "kin", player_id: "kin-07", own_goal: false }, { score: { home: 0, away: 1 } });
    expect(goal).toMatchObject({ text: "Goal for Kingsferry, scored by Adeyani. Saltmarsh 0, Kingsferry 1.", level: "key" });
    const own = said(2, { type: "goal", team_id: "kin", player_id: "kin-04", own_goal: true }, { score: { home: 1, away: 2 } });
    expect(own.text).toBe("Goal for Kingsferry: an own goal by Penhallow. Saltmarsh 1, Kingsferry 2.");
    expect(spokenScore(MATCH, { home: 1, away: 1 })).toBe("Saltmarsh 1, Kingsferry 1");
  });

  it("tells VAR, shots, set pieces and corrections from the events' own fields", () => {
    expect(said(1, { type: "var_check", status: "started", check: "goal", incident: "offside" }).text).toBe("VAR is checking the goal for offside.");
    expect(said(2, { type: "var_check", status: "complete", decision: "no_goal", overturned: true }, { score: { home: 0, away: 1 } }).text).toBe(
      "VAR decision: no goal. The decision on the field is overturned. Saltmarsh 0, Kingsferry 1.",
    );
    expect(said(3, { type: "shot", player_id: "sal-09", body_part: "right_foot", distance: 19.4, outcome: "saved", goalkeeper_id: "kin-01" }).text).toBe(
      "Dellow shoots with the right foot from 19 metres: saved by Brennholt.",
    );
    expect(said(4, { type: "ball_out", restart: "corner", last_touch_team_id: "kin" }).text).toBe("Corner to Saltmarsh.");
    const correction = said(5, {
      type: "amendment",
      amends: "goal",
      changes: { player_id: { before: "kin-04", after: "kin-07" }, own_goal: { before: true, after: false } },
      corrected_event: { minute: 81 },
    });
    expect(correction.text).toBe("Correction from the data provider: the 81st-minute goal is now credited to Adeyani, not Penhallow, as an own goal.");
    // A restart's change of possession is told by the restart itself.
    expect(eventLines(MATCH, R, KICK_OFF_VIEW, 0, [eventPush(6, { event: feedEventFixture(6, { type: "possession_change", cause: "restart" }) })])).toHaveLength(1);
  });

  it("opens with the score and the minute, or the line-ups before kick-off", () => {
    expect(openingLine(MATCH, KICK_OFF_VIEW, 0).text).toBe("Saltmarsh Rovers against Kingsferry Athletic. Kick-off is coming up.");
    const view = { ...KICK_OFF_VIEW, phase: "second_half" as const, score: { home: 1, away: 1 }, clock: { period: 2, t: 790, clock: 3490, minute: 59, added_minute: null } };
    expect(openingLine(MATCH, view, 3900).text).toBe("Saltmarsh 1, Kingsferry 1, in the 59th minute.");
  });

  it("reads each graphic as it shows, after the event that brought it, but not one VAR undid", () => {
    const goal = { insight: insightFixture("goal-e0391", { card: { headline: "Adeyani scores", casual: "", analyst: "", plain: "Adeyani scores. Kingsferry lead.", evidence: [], facts: [] } }), from: 1300 };
    const undone = { insight: insightFixture("goal-e0532", { flag: { reason: "Ruled out by VAR", event_id: "e0534", version: 1, seq: 535 } }), from: 1310 };
    const cards = cardLines([goal, undone]);
    expect(cards.map((l) => l.text)).toEqual(["On screen: Adeyani scores. Kingsferry lead."]);
    const event = { key: "e9", replay: 1300, clock: "22:37", text: "Goal for Kingsferry.", level: "key" as const };
    expect(merged([event], cards).map((l) => l.key)).toEqual(["e9", "card-goal-e0391-1"]);
  });
});

describe("pace", () => {
  const line = (key: string, level: DescribedLine["level"], text: string): DescribedLine => ({ key, replay: 0, clock: "", text, level });

  it("says one waiting line as it is, and nothing when none waits", () => {
    expect(nextSaying([line("a", "standard", "Saltmarsh intercept.")], false)).toBe("Saltmarsh intercept.");
    expect(nextSaying([], false)).toBeNull();
  });

  it("catches up on a backlog with its key moments and the latest line", () => {
    const backlog = [
      line("1", "standard", "Saltmarsh intercept."),
      line("2", "key", "Goal for Saltmarsh."),
      line("3", "full", "Varlan plays a short pass."),
      line("4", "standard", "Kingsferry win the ball."),
    ];
    expect(nextSaying(backlog, false)).toBe("Goal for Saltmarsh. Kingsferry win the ball.");
    expect(nextSaying(backlog, true)).toBe("While paused: Goal for Saltmarsh. Kingsferry win the ball.");
  });
});
