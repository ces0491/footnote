import { describe, expect, it } from "vitest";

import type { EventMessage, FeedEvent, MatchMeta } from "./contract";
import { atDetail, cardLines, type DescribedLine, eventLines, merged, nextSaying, openingLine, type Part, spokenScore, where } from "./described";
import { roster } from "./describe";
import { KICK_OFF_VIEW } from "./run-reducer";
import { eventPush, feedEventFixture, insightFixture } from "./test-fixtures";

const textOf = (parts: Part[]) => parts.map((p) => p.text).join(" ");

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

function said(seq: number, event: Partial<FeedEvent>, extra: Partial<EventMessage> = {}): DescribedLine & { text: string } {
  const lines = eventLines(MATCH, R, KICK_OFF_VIEW, 0, [eventPush(seq, { event: feedEventFixture(seq, event), ...extra })]);
  return { ...lines[1], text: textOf(lines[1].parts) };
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

  it("says which way a pass goes from its angle, not its gain alone", () => {
    const pass = (seq: number, length: number, end_x?: number, end_y?: number) =>
      said(seq, { type: "pass", team_id: "sal", player_id: "sal-10", recipient_id: "sal-09", outcome: "complete", pass_type: "open_play", length, x: 30, y: 34, end_x, end_y }).text;
    // 4.2 m forward and 1.5 m sideways; 1 m forward and 12 m sideways; 5 m back and 2 m sideways.
    expect(pass(1, 4.5, 34.2, 35.5)).toBe("Varlan, deep in their own half, plays a short pass forward to Dellow, deep in their own half.");
    expect(pass(2, 12, 31, 46)).toBe("Varlan, deep in their own half, plays a pass across to Dellow, deep in their own half on the left.");
    expect(pass(3, 5.4, 25, 36)).toBe("Varlan, deep in their own half, plays a short pass back to Dellow, deep in their own half.");
    // Without its end, there is no telling which way it went.
    expect(pass(4, 9)).toBe("Varlan, deep in their own half, plays a short pass to Dellow.");
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
    expect(correction.text).toBe(
      "Correction from the data provider: the 81st-minute goal is now credited to Adeyani. It had been given as an own goal by Penhallow.",
    );
    // A restart's change of possession is told by the restart itself.
    expect(eventLines(MATCH, R, KICK_OFF_VIEW, 0, [eventPush(6, { event: feedEventFixture(6, { type: "possession_change", cause: "restart" }) })])).toHaveLength(1);
  });

  it("says who a correction credits now, and who it had credited, in sentences of their own", () => {
    const amendment = (seq: number, changes: Record<string, { before: unknown; after: unknown }>, own_goal: boolean) =>
      said(seq, { type: "amendment", amends: "goal", changes, corrected_event: { minute: 81, own_goal } }).text;
    expect(amendment(1, { player_id: { before: "kin-04", after: "kin-07" } }, false)).toBe(
      "Correction from the data provider: the 81st-minute goal is now credited to Adeyani. It had been credited to Penhallow.",
    );
    expect(amendment(2, { player_id: { before: "kin-07", after: "kin-04" }, own_goal: { before: false, after: true } }, true)).toBe(
      "Correction from the data provider: the 81st-minute goal is now given as an own goal by Penhallow. It had been credited to Adeyani.",
    );
  });

  it("says what else a correction changed", () => {
    const amendment = (seq: number, changes: Record<string, { before: unknown; after: unknown }>) =>
      said(seq, { type: "amendment", amends: "goal", changes, corrected_event: { minute: 81 } }).text;
    expect(amendment(1, { assist_id: { before: null, after: "sal-10" } })).toBe(
      "Correction from the data provider: the assist on the 81st-minute goal now goes to Varlan.",
    );
    expect(amendment(2, { outcome: { before: "saved", after: "goal" } })).toBe(
      "Correction from the data provider to the 81st-minute goal, changing its outcome.",
    );
  });

  it("opens with the score and the minute, or the line-ups before kick-off", () => {
    expect(textOf(openingLine(MATCH, KICK_OFF_VIEW, 0).parts)).toBe("Saltmarsh Rovers against Kingsferry Athletic. Kick-off is coming up.");
    const view = { ...KICK_OFF_VIEW, phase: "second_half" as const, score: { home: 1, away: 1 }, clock: { period: 2, t: 790, clock: 3490, minute: 59, added_minute: null } };
    expect(textOf(openingLine(MATCH, view, 3900).parts)).toBe("Saltmarsh 1, Kingsferry 1, in the 59th minute.");
  });

  it("reads each graphic as it shows, after the event that brought it, but not one VAR undid", () => {
    const goal = { insight: insightFixture("goal-e0391", { card: { headline: "Adeyani scores", casual: "", analyst: "", plain: "Adeyani scores. Kingsferry lead.", evidence: [], facts: [] } }), from: 1300 };
    const undone = { insight: insightFixture("goal-e0532", { flag: { reason: "Ruled out by VAR", event_id: "e0534", version: 1, seq: 535 } }), from: 1310 };
    const cards = cardLines([goal, undone]);
    expect(cards.map((l) => l.parts)).toEqual([[{ text: "On screen: Adeyani scores. Kingsferry lead.", lang: "en" }]]);
    const event = { key: "e9", replay: 1300, clock: "22:37", parts: [{ text: "Goal for Kingsferry.", lang: "en" as const }], level: "key" as const };
    expect(merged([event], cards).map((l) => l.key)).toEqual(["e9", "card-goal-e0391"]);
  });

  it("keys a graphic's line on the graphic, so a later wording or a translation of it isn't news", () => {
    const card = (plain: string) => ({ headline: "Adeyani scores", casual: "", analyst: "", plain, evidence: [], facts: [] });
    const template = insightFixture("goal-e0391", { version: 1, source: "template", card: card("Femi Adeyani scores. Kingsferry lead 1-0.") });
    const agent = insightFixture("goal-e0391", { version: 2, source: "agent", card: card("Adeyani finishes Kingsferry's first counter.") });
    const [before] = cardLines([{ insight: template, from: 1357.2 }]);
    const [after] = cardLines([{ insight: agent, from: 1357.2 }]);
    const [spanish] = cardLines([{ insight: { ...agent, card: card("Adeyani culmina el primer contragolpe del Kingsferry.") }, from: 1357.2, lang: "es" }]);
    expect(new Set([before.key, after.key, spanish.key])).toEqual(new Set(["card-goal-e0391"]));
    // The line carries the wording as it now stands.
    expect(textOf(after.parts)).toBe("On screen: Adeyani finishes Kingsferry's first counter.");
  });

  it("reads a producer's edit again, since it may put right what was said", () => {
    const card = (plain: string) => ({ headline: "Adeyani scores", casual: "", analyst: "", plain, evidence: [], facts: [] });
    const agent = insightFixture("goal-e0391", { version: 2, source: "agent", card: card("Adeyani finishes Kingsferry's first counter.") });
    const edited = insightFixture("goal-e0391", { version: 3, source: "producer", card: card("Adeyani finishes the first counter.") });
    const [read] = cardLines([{ insight: agent, from: 1357.2 }]);
    const [again] = cardLines([{ insight: edited, from: 1357.2 }]);
    expect(again.key).not.toBe(read.key);
    expect(textOf(again.parts)).toBe("On screen: Adeyani finishes the first counter.");
  });

  it("marks a graphic's Spanish or French wording with its language, and says the rest in English", () => {
    const insight = insightFixture("goal-e0391", { card: { headline: "Femi Adeyani marca", casual: "", analyst: "", plain: "Femi Adeyani marca. Kingsferry se adelanta.", evidence: [], facts: [] } });
    const [card] = cardLines([{ insight, from: 1357.2, lang: "es" }]);
    expect(card.parts).toEqual([
      { text: "On screen:", lang: "en" },
      { text: "Femi Adeyani marca. Kingsferry se adelanta.", lang: "es" },
    ]);
    // An announcement runs the English on either side of it together.
    const goal = { key: "e392", replay: 1357.25, clock: "22:37", parts: [{ text: "Goal for Kingsferry.", lang: "en" as const }], level: "key" as const };
    const next = { key: "e394", replay: 1360, clock: "23:40", parts: [{ text: "Saltmarsh win the ball.", lang: "en" as const }], level: "standard" as const };
    expect(nextSaying([goal, card, next], false)).toEqual([
      { text: "Goal for Kingsferry. On screen:", lang: "en" },
      { text: "Femi Adeyani marca. Kingsferry se adelanta.", lang: "es" },
      { text: "Saltmarsh win the ball.", lang: "en" },
    ]);
  });
});

describe("pace", () => {
  const line = (key: string, level: DescribedLine["level"], text: string): DescribedLine => ({ key, replay: 0, clock: "", parts: [{ text, lang: "en" }], level });
  const say = (backlog: DescribedLine[], resumed: boolean) => {
    const parts = nextSaying(backlog, resumed);
    return parts && textOf(parts);
  };

  it("says one waiting line as it is, and nothing when none waits", () => {
    expect(say([line("a", "standard", "Saltmarsh intercept.")], false)).toBe("Saltmarsh intercept.");
    expect(nextSaying([], false)).toBeNull();
  });

  it("says up to three waiting lines in full: the 23' through ball, the shot and the goal", () => {
    // As they reach playback within one announcement at 2x and normal pace, at standard detail.
    const backlog = [
      line("e388", "standard", "Ferrano, in their own half, plays a through ball to Adeyani, in the final third on the right."),
      line("e391", "key", "Adeyani shoots with the left foot from 21 metres: goal."),
      line("e392", "key", "Goal for Kingsferry, scored by Adeyani. Saltmarsh 0, Kingsferry 1."),
    ];
    expect(say(backlog, false)).toBe(
      "Ferrano, in their own half, plays a through ball to Adeyani, in the final third on the right. " +
        "Adeyani shoots with the left foot from 21 metres: goal. Goal for Kingsferry, scored by Adeyani. Saltmarsh 0, Kingsferry 1.",
    );
  });

  it("says the 31' pass, the shot, the goal and the VAR check that back up together", () => {
    const backlog = [
      line("e530", "standard", "Varlan, in the centre circle, plays a pass forward to Dellow, in the final third."),
      line("e532", "key", "Dellow shoots with the right foot from 19 metres: goal."),
      line("e533", "key", "Goal for Saltmarsh, scored by Dellow. Saltmarsh 1, Kingsferry 1."),
      line("e534", "key", "VAR is checking the goal for offside."),
    ];
    expect(say(backlog, false)).toBe(
      "Varlan, in the centre circle, plays a pass forward to Dellow, in the final third. Dellow shoots with the right foot from 19 metres: goal. " +
        "Goal for Saltmarsh, scored by Dellow. Saltmarsh 1, Kingsferry 1. VAR is checking the goal for offside.",
    );
  });

  it("catches up on a longer backlog with each key moment, the build-up just before it, and the latest line", () => {
    const backlog = [
      line("1", "standard", "Saltmarsh intercept."),
      line("2", "standard", "Varlan plays a long pass forward to Dellow."),
      line("3", "key", "Dellow shoots: saved by Brennholt."),
      line("4", "full", "Brennholt claims the ball."),
      line("5", "standard", "Kingsferry win the ball."),
      line("6", "standard", "Adeyani plays a through ball to Penhallow."),
      line("7", "key", "Goal for Kingsferry."),
      line("8", "standard", "Saltmarsh win the ball in a duel."),
    ];
    expect(say(backlog, false)).toBe(
      "Varlan plays a long pass forward to Dellow. Dellow shoots: saved by Brennholt. Adeyani plays a through ball to Penhallow. Goal for Kingsferry. " +
        "Saltmarsh win the ball in a duel.",
    );
  });

  it("after a pause from 22' to 33', says every key moment that waited, both goals among them, and the latest line", () => {
    // The showcase's lines at standard detail from 22' to 33', with some of the build-up left out.
    const backlog = [
      line("e379", "standard", "Varlan, in their own half, plays a long pass forward for O'Fadyen, but it doesn't arrive."),
      line("e388", "standard", "Ferrano, in their own half, plays a through ball to Adeyani, in the final third on the right."),
      line("e391", "key", "Adeyani shoots with the left foot from 21 metres: goal."),
      line("e392", "key", "Goal for Kingsferry, scored by Adeyani. Saltmarsh 0, Kingsferry 1."),
      line("e403", "standard", "Kingsferry intercept, deep in their own half."),
      line("e435", "standard", "Foul by Dahlstrup on Gallino."),
      line("e436", "key", "Yellow card for Dahlstrup, Kingsferry."),
      line("e475", "standard", "Saltmarsh intercept, deep in their own half on the left."),
      line("e530", "standard", "Varlan, in the centre circle, plays a pass forward to Dellow, in the final third."),
      line("e532", "key", "Dellow shoots with the right foot from 19 metres: goal."),
      line("e533", "key", "Goal for Saltmarsh, scored by Dellow. Saltmarsh 1, Kingsferry 1."),
      line("e534", "key", "VAR is checking the goal for offside."),
      line("e535", "key", "VAR decision: no goal. The decision on the field is overturned. Saltmarsh 0, Kingsferry 1."),
      line("e537", "standard", "Ferrano takes the free kick to Belais, deep in their own half."),
    ];
    expect(say(backlog, true)).toBe(
      "While paused: Adeyani shoots with the left foot from 21 metres: goal. Goal for Kingsferry, scored by Adeyani. Saltmarsh 0, Kingsferry 1. " +
        "Yellow card for Dahlstrup, Kingsferry. Dellow shoots with the right foot from 19 metres: goal. " +
        "Goal for Saltmarsh, scored by Dellow. Saltmarsh 1, Kingsferry 1. VAR is checking the goal for offside. " +
        "VAR decision: no goal. The decision on the field is overturned. Saltmarsh 0, Kingsferry 1. " +
        "Ferrano takes the free kick to Belais, deep in their own half.",
    );
    // A short wait is said in full, and says it waited.
    expect(say(backlog.slice(0, 2), true)).toBe(
      "While paused: Varlan, in their own half, plays a long pass forward for O'Fadyen, but it doesn't arrive. " +
        "Ferrano, in their own half, plays a through ball to Adeyani, in the final third on the right.",
    );
  });
});
