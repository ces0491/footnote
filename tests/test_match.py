"""Invariants every generated match must satisfy: the feed's contract, internal consistency,
physical plausibility, and a clean split between the feed and the answer key."""

from __future__ import annotations

import json

import numpy as np
import pytest

from footnote.generator import officials
from footnote.generator.league import League
from footnote.generator.pitch import LENGTH, to_frame
from footnote.generator.schema import validate_message
from footnote.generator.season import Fixture, GeneratedMatch, generate_match, match_seed
from footnote.generator.sim import MatchSim

HIDDEN_KEYS = {
    "truth",
    "regime",
    "p_complete",
    "p_win",
    "p_keep",
    "xg",
    "probs",
    "margin",
    "offside_margin",
    "arm_unnatural",
    "deflected_by",
    "foul_in_build_up",
}
# The answer key's probability for each kind of event the simulation draws from a model.
PROBABILITY = {"pass": "p_complete", "shot": "xg", "tackle": "p_win", "duel": "p_win", "carry": "p_keep"}


def _all_keys(obj: object) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _all_keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _all_keys(v)}
    return set()


def test_same_seed_same_match(league: League, fixture_sal_kin: Fixture, match: GeneratedMatch) -> None:
    again = generate_match(league, fixture_sal_kin, match_id="test-sal-kin")
    assert json.dumps(again.output.feed) == json.dumps(match.output.feed)
    assert again.output.answer_key == match.output.answer_key


def test_a_later_reseed_at_the_same_step_holds(league: League, fixture_sal_kin: Fixture) -> None:
    """Two reseeds can land on one step (see showcase._last_per_step); the later one must win, in the
    order given, or a recipe replays a different match from the one the search found."""
    both = generate_match(league, fixture_sal_kin, reseeds=[(400, 7), (400, 3)], match_id="test-reseed")
    later = generate_match(league, fixture_sal_kin, reseeds=[(400, 3)], match_id="test-reseed")
    assert json.dumps(both.output.feed) == json.dumps(later.output.feed)


def test_every_message_matches_the_contract(match: GeneratedMatch, matches: list[GeneratedMatch]) -> None:
    for gm in [match, *matches]:
        for msg in gm.output.feed:
            validate_message(msg)


def test_nothing_hidden_reaches_the_feed(match: GeneratedMatch, matches: list[GeneratedMatch]) -> None:
    for gm in [match, *matches]:
        leaked = _all_keys(gm.output.feed) & HIDDEN_KEYS
        assert not leaked, leaked
        assert not _all_keys(gm.output.meta) & HIDDEN_KEYS


def test_message_order_and_ids(match: GeneratedMatch) -> None:
    feed = match.output.feed
    assert [m["seq"] for m in feed] == list(range(1, len(feed) + 1))
    stamps = [m["ts"] for m in feed]
    assert stamps == sorted(stamps)
    keys = [(m["event_id"], m["version"]) for m in feed]
    assert len(keys) == len(set(keys))
    assert feed[0]["type"] == "match_info"


def _final_score(feed: list[dict]) -> tuple[int, int]:
    ruled_out = {m["goal_event_id"] for m in feed if m["type"] == "var_check" and m.get("decision") == "no_goal"}
    home = feed[0]["info"]["home"]["id"]
    goals = [m for m in feed if m["type"] == "goal" and m["event_id"] not in ruled_out]
    return sum(g["team_id"] == home for g in goals), sum(g["team_id"] != home for g in goals)


def test_goals_add_up_to_the_score(match: GeneratedMatch, matches: list[GeneratedMatch]) -> None:
    for gm in [match, *matches]:
        feed = gm.output.feed
        end = next(m for m in feed if m["type"] == "match_end")
        assert _final_score(feed) == (end["score"]["home"], end["score"]["away"])
        assert gm.output.answer_key["final_score"] == end["score"]


def test_passes_go_to_team_mates(match: GeneratedMatch) -> None:
    for m in match.output.feed:
        if m["type"] == "pass" and m["recipient_id"]:
            assert m["recipient_id"].split("-")[0] == m["player_id"].split("-")[0]


def test_references_point_at_real_events(match: GeneratedMatch, matches: list[GeneratedMatch]) -> None:
    for gm in [match, *matches]:
        ids = {m["event_id"] for m in gm.output.feed}
        for m in gm.output.feed:
            for key in ("from_event_id", "pass_event_id", "related_event_id", "goal_event_id"):
                if m.get(key):
                    assert m[key] in ids


def test_offside_calls_match_the_positions(match: GeneratedMatch, matches: list[GeneratedMatch]) -> None:
    """Every offside flag points to a pass with a freeze frame, and in it the player was beyond the
    second-last defender, past halfway and ahead of the ball."""
    checked = 0
    for gm in [match, *matches]:
        feed = gm.output.feed
        home = feed[0]["info"]["home"]["id"]
        passes = {m["event_id"]: m for m in feed if m["type"] == "pass"}
        for m in feed:
            if m["type"] != "offside":
                continue
            team = m["team_id"]
            attacking_plus_x = (team == home) == (m["period"] == 1)
            direction = 1 if attacking_plus_x else -1
            frame = passes[m["pass_event_id"]]["freeze_frame"]
            assert frame is not None, m["event_id"]
            me = next(p for p in frame["players"] if p["player_id"] == m["player_id"])
            u = to_frame(np.array([me["x"], me["y"]]), direction)[0]
            defenders = sorted(
                to_frame(np.array([p["x"], p["y"]]), direction)[0] for p in frame["players"] if p["team_id"] != team
            )
            ball_u = to_frame(np.array([frame["ball"]["x"], frame["ball"]["y"]]), direction)[0]
            assert u > defenders[-2] and u > LENGTH / 2 and u > ball_u
            checked += 1
    assert checked > 0


def test_a_freeze_frame_on_a_pass_means_an_offside_position(
    match: GeneratedMatch, matches: list[GeneratedMatch]
) -> None:
    """Passes carry a freeze frame only when the player they were meant for was offside, and every
    VAR offside check points to one."""
    for gm in [match, *matches]:
        key = gm.output.answer_key["events"]
        feed = gm.output.feed
        passes = {m["event_id"]: m for m in feed if m["type"] == "pass"}
        for m in passes.values():
            if m.get("freeze_frame") is not None:
                assert key[m["event_id"]]["offside_margin"] > 0.0
        for m in feed:
            if m["type"] == "var_check" and m["incident"] == "offside":
                assert passes[m["pass_event_id"]]["freeze_frame"] is not None


def test_nobody_runs_faster_than_a_person_can(match: GeneratedMatch) -> None:
    tr = match.tracking
    assert tr is not None
    same = (tr.period[1:] == tr.period[:-1]) & (tr.occupancy[1:] == tr.occupancy[:-1])
    speed = np.linalg.norm(np.diff(tr.players, axis=0), axis=2)[same] * 10.0
    assert np.nanmax(speed) <= 10.5


def test_tracking_agrees_with_freeze_frames(match: GeneratedMatch) -> None:
    tr = match.tracking
    assert tr is not None
    slots = {pid: i for i, pid in enumerate(tr.slot_players[0])}
    worst = 0.0
    for m in match.output.feed:
        ff = m.get("freeze_frame")
        if not ff or m["period"] != 1:
            continue
        frame = int(np.argmin(np.abs(tr.t.astype(float) - m["t"]) + (tr.period != 1) * 1e9))
        for p in ff["players"]:
            if p["player_id"] in slots and tr.occupancy[frame] == 0:
                pos = tr.players[frame, slots[p["player_id"]]]
                worst = max(worst, float(np.hypot(pos[0] - p["x"], pos[1] - p["y"])))
    # Frames are 0.1 s apart and players move at most about a metre in that time.
    assert worst < 1.2


def test_answer_key_covers_the_match(match: GeneratedMatch) -> None:
    key = match.output.answer_key
    for period in (1, 2):
        segments = [r for r in key["regimes"] if r["period"] == period]
        assert segments[0]["start"] == 0.0
        for a, b in zip(segments, segments[1:], strict=False):
            assert a["end"] == pytest.approx(b["start"])
    # Every pass (crosses and headers included), shot, tackle, duel and carry has the probability
    # its outcome was drawn from.
    seen = set()
    for m in match.output.feed:
        if m["type"] in PROBABILITY:
            value = key["events"][m["event_id"]][PROBABILITY[m["type"]]]
            assert 0.0 < value < 1.0, (m["event_id"], m["type"], value)
            seen.add(m["type"] if m["type"] != "pass" else ("head" if m["body_part"] == "head" else "pass"))
    assert seen == {"pass", "head", "shot", "tackle", "duel", "carry"}


def test_amendments_correct_real_goals(matches: list[GeneratedMatch]) -> None:
    for gm in matches:
        feed = gm.output.feed
        goals = {m["event_id"] for m in feed if m["type"] == "goal"}
        end = next(m for m in feed if m["type"] == "match_end")
        for m in feed:
            if m["type"] == "amendment":
                assert m["event_id"] in goals and m["version"] == 2 and m["changes"]
                # The clock stops at the final whistle, whenever the correction comes.
                assert m["clock"] <= end["clock"]


def test_substitutes_stay_on(match: GeneratedMatch, matches: list[GeneratedMatch]) -> None:
    """Nobody who comes on is taken off again, and sides don't all make the same number of changes."""
    per_side = []
    for gm in [match, *matches]:
        came_on: set[str] = set()
        count: dict[str, int] = {}
        for m in gm.output.feed:
            if m["type"] == "substitution":
                assert m["player_off_id"] not in came_on, m["event_id"]
                came_on.add(m["player_on_id"])
                count[m["team_id"]] = count.get(m["team_id"], 0) + 1
        per_side += list(count.values())
    assert max(per_side) <= 5 and len(set(per_side)) > 1


def _sim_in_play(league: League, match_id: str) -> MatchSim:
    """A match a minute or two in, with the ball in play."""
    players = {p.id: p for c in league.clubs for p in c.squad}
    sim = MatchSim(
        league.club("SAL"), league.club("KIN"), match_id, match_seed(league, match_id), league.referees[0], players
    )
    while sim.s.t < 90.0 or sim.s.restart is not None:
        sim.step()
    return sim


def test_a_penalty_is_taken_from_the_spot(league: League) -> None:
    sim = _sim_in_play(league, "test-penalty-spot")
    sim._var_review_penalty = lambda fouler, victim: False
    defender, attacker = 3, 20  # a Saltmarsh centre-back and a Kingsferry forward
    sim.s.pos[attacker] = np.array([12.0, 22.0])  # inside Saltmarsh's box, well away from the spot
    assert sim._foul(defender, attacker, "challenge")
    assert sim.s.restart is not None and sim.s.restart.kind == "penalty"
    sim.step()
    shot = [e for e in sim.events if e["type"] == "shot"][-1]
    assert shot["shot_type"] == "penalty"
    # Kingsferry attack towards x = 0 in the first half: their spot is 11 m out, in the middle.
    assert (shot["x"], shot["y"], shot["distance"]) == (11.0, 34.0, 11.0)


def test_a_handball_penalty_given_by_var_is_taken_as_a_penalty(league: League, monkeypatch: pytest.MonkeyPatch) -> None:
    """The penalty is given where the ball struck the arm, wherever the defender has drifted to by the
    time VAR has finished."""
    monkeypatch.setattr(officials, "arm_unnatural", lambda rng: True)
    monkeypatch.setattr(officials, "referee_awards_handball", lambda unnatural, rng: False)
    monkeypatch.setattr(officials, "var_corrects", lambda on_field, truth, rng: True)
    sim = _sim_in_play(league, "test-handball")
    defender, attacker = 3, 20  # a Saltmarsh centre-back and a Kingsferry forward
    spot = np.array([14.0, 30.0])  # inside Saltmarsh's box in the first half
    sim.s.pos[defender] = spot.copy()
    stoppage = sim._stoppage

    def drift_out_of_the_box(*args, **kwargs):
        stoppage(*args, **kwargs)
        sim.s.pos[defender] = np.array([30.0, 34.0])

    sim._stoppage = drift_out_of_the_box
    sim._handball_claim(defender, attacker, spot)
    decision = [e for e in sim.events if e["type"] == "var_check" and e["status"] == "complete"][-1]
    foul = [e for e in sim.events if e["type"] == "foul"][-1]
    assert decision["decision"] == "penalty"
    assert foul["foul_type"] == "handball" and foul["penalty"] and (foul["x"], foul["y"]) == (14.0, 30.0)
    assert sim.s.restart is not None and sim.s.restart.kind == "penalty"
