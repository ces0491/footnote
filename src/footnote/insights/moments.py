"""Moments: what in a match is worth a card, found as a run's feed is folded, and how each ranks.

`MomentFinder.observe` looks at each feed message once the run's state has taken it in and returns
the insights it starts. It reads the score and counts, the match state and its timeline, each pass's
difficulty and the tags from the tracking off the run's state (live/state.py), so it sees what a
viewer has seen at that point and nothing later. Every figure it states is a fact (facts.py), and
its wording is the template for the moment's topic (templates.py).

Each insight carries a rank between 0 and 1 and the reason for it, so the producer's shortlist
(docs/experience.md) can put the strongest few first. A rank is a base for the topic, raised by what
the match state and the numbers say about this moment. The full rule is in docs/insights.md; the
figures live in BASE_RANK and the functions below.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from footnote.insights import facts as F
from footnote.insights.facts import Fact, Facts
from footnote.live.timeline import PERIOD_SECONDS

if TYPE_CHECKING:
    from footnote.insights.book import Insight
    from footnote.live.state import RunState

# Topic -> kind. Kinds are what the overlay contract names (docs/experience.md).
KIND = {
    "goal": "moment",
    "own_goal": "moment",
    "penalty": "moment",
    "red_card": "moment",
    "var_started": "rule_call",
    "var_decision": "rule_call",
    "pressure": "segment",
    "chaos": "segment",
    "control": "segment",
    "key_pass": "stat",
    "hard_pass": "stat",
    "shot_speed": "stat",
    "sprint": "player_tag",
    "distance": "player_tag",
    "half_time": "recap",
    "full_time": "recap",
    "catch_up": "recap",
    "correction": "correction",
}

BASE_RANK = {
    "correction": 0.95,
    "half_time": 0.90,
    "full_time": 0.90,
    "catch_up": 0.85,
    "goal": 0.80,
    "own_goal": 0.80,
    "penalty": 0.80,
    "var_decision": 0.78,
    "var_started": 0.70,
    "red_card": 0.70,
    "pressure": 0.55,
    "chaos": 0.50,
    "control": 0.45,
    "key_pass": 0.40,
    "hard_pass": 0.40,
    "shot_speed": 0.35,
    "sprint": 0.35,
    "distance": 0.25,
}

# Topics an agent drafts; the rest keep their template. Agents go where wording adds something: a
# recap's template can list the goals, but only a writer can tell the story of the half.
AGENT_TOPICS = frozenset(
    {
        "goal",
        "own_goal",
        "penalty",
        "red_card",
        "var_decision",
        "pressure",
        "chaos",
        "correction",
        "half_time",
        "full_time",
        "catch_up",
    }
)

# How long, in match seconds, an insight stays on the shortlist after its moment.
SHELF_SECONDS = {
    "goal": 300,
    "own_goal": 300,
    "penalty": 120,
    "red_card": 240,
    "var_started": 180,
    "var_decision": 180,
    "pressure": 240,
    "chaos": 240,
    "control": 240,
    "key_pass": 180,
    "hard_pass": 180,
    "shot_speed": 180,
    "sprint": 120,
    "distance": 120,
    "half_time": 600,
    "full_time": 600,
    "catch_up": 300,
    "correction": 600,
}

PLACEMENT = {"moment": "lower_third", "rule_call": "lower_third", "correction": "lower_third", "recap": "full_card"}
# The catch-up is for a fan's own screen, not the world feed's.
PLACEMENT_BY_TOPIC = {"catch_up": "side_panel"}
# Kinds that wait for the next stoppage, so live play stays uncluttered (docs/audience.md, P5).
HOLD_FOR_STOPPAGE = frozenset({"segment", "stat"})
# Seconds of match time a graphic stays on screen once shown, by placement. A side-panel card stays
# in the viewer's panel instead (docs/overlay.md).
DURATION = {"lower_third": 12.0, "full_card": 20.0}
# Graphics that may animate on and off screen; the rest appear and leave without motion, and calm
# mode keeps every graphic still (docs/audience.md, P8).
ANIMATED_KINDS = frozenset({"moment"})

# Run of play: who was on top over the ten minutes before a goal, leaving out the half-minute of
# the move itself, from the state shown each second. Against the run of play means the scorers held
# a state of their own for at most a quarter of that time and the other side for at least 45%.
RUN_OF_PLAY_WINDOW = 600
RUN_OF_PLAY_GAP = 30
RUN_OF_PLAY_MIN_SECONDS = 300
AGAINST_SCORERS_AT_MOST = 0.25
AGAINST_OTHERS_AT_LEAST = 0.45

# Segments, from the state shown each second: (seconds looked back over, share of them needed). One
# side pinning the other back for 60% of the last three minutes, chaos for half of them, or one side
# in control for 70% of the last five. Chaos needs less because the model names it less readily
# (docs/models.md: it catches 42% of chaos seconds). Each topic and club gets at most one card per
# five minutes of a period. The figures were set by hand; docs/insights.md says how.
SEGMENT_RULES = {"pressure": (180, 0.60), "chaos": (180, 0.50), "control": (300, 0.70)}
SEGMENT_GAP = 300
# The most events a spell's figure cites: the latest of the kind it counts. A spell's share of a
# state rests on its shots and changes of possession, the play the model's estimate turned on.
SEGMENT_EVENTS = 12

HARD_PASS_AT_LEAST = 0.80  # difficulty of a completed pass before it can be the hardest yet
SHOT_SPEED_AT_LEAST = 100.0  # km/h, for the fastest-shot card

_INCIDENT = {"offside": "offside", "handball": "handball", "foul": "a foul"}
_DECISION = {"goal": "Goal stands", "no_goal": "No goal", "penalty": "Penalty", "no_penalty": "No penalty"}
_SHOT_OUTCOME = {"goal": "scored", "saved": "saved", "blocked": "blocked", "off_target": "off target"}
_CARD_REASON = {"foul": "a foul", "dissent": "dissent", "second_yellow": "a second yellow card"}


@dataclass
class Found:
    """An insight as the finder starts it. book.Insight adds what happens to it later."""

    insight_id: str
    topic: str
    seq: int
    at: dict  # period, t, minute, added_minute: when it happened, in match time
    rank: float
    reason: str
    evidence: list[str]
    facts: Facts
    corrects: str | None = None

    @property
    def kind(self) -> str:
        return KIND[self.topic]

    @property
    def until(self) -> dict:
        """When it leaves the shortlist: its shelf life on from the moment, in the same period."""
        return {"period": self.at["period"], "t": round(self.at["t"] + SHELF_SECONDS[self.topic], 2)}


@dataclass
class _GoalContext:
    """What a goal's card says beside the goal itself, kept so a corrected goal is restated alike."""

    seq: int
    shot: dict | None
    key_pass: dict | None
    key_pass_difficulty: float | None
    possession: list[str]
    shares: dict[str, float] | None  # club ID -> share of the window it held a state of its own
    covered: int  # seconds the shares cover
    situation: str
    rank: float
    reason: str


def _at(m: dict) -> dict:
    return {"period": m["period"], "t": m["t"], "minute": m["minute"], "added_minute": m["added_minute"]}


@dataclass
class MomentFinder:
    meta: dict
    clubs: dict[str, dict] = field(init=False)
    players: dict[str, dict] = field(init=False)
    events: dict[str, dict] = field(init=False, default_factory=dict)  # every event so far, by ID
    difficulty: dict[str, float] = field(init=False, default_factory=dict)  # pass event ID -> rating
    goals: dict[str, _GoalContext] = field(init=False, default_factory=dict)
    _possessions: dict[int, list[str]] = field(init=False, default_factory=dict)
    _onball: list[dict] = field(init=False, default_factory=list)  # in order, for spell figures
    _hardest: float = field(init=False, default=0.0)
    _fastest: float = field(init=False, default=0.0)
    _reported: dict[tuple[str, str | None, int], int] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.clubs = {self.meta["home"]["id"]: self.meta["home"], self.meta["away"]["id"]: self.meta["away"]}
        self.players = {}
        for lineup in self.meta["lineups"]:
            for p in [*lineup["starters"], *lineup["bench"]]:
                self.players[p["player_id"]] = {**p, "club_id": lineup["club_id"]}

    # --- names ---------------------------------------------------------------------------------

    def club(self, club_id: str | None) -> str:
        return str(self.clubs[club_id]["short_name"]) if club_id in self.clubs else "Unknown club"

    def code(self, club_id: str) -> str:
        return str(self.clubs[club_id]["code"])

    def other(self, club_id: str) -> str:
        return next(c for c in self.clubs if c != club_id)

    def name(self, player_id: str | None) -> str:
        return str(self.players[player_id]["name"]) if player_id in self.players else "Unknown player"

    def score_line(self, score: dict) -> str:
        home, away = self.meta["home"], self.meta["away"]
        return F.score_line(home["short_name"], score["home"], score["away"], away["short_name"])

    # --- folding -------------------------------------------------------------------------------

    def observe(self, m: dict, state: RunState) -> list[Found]:
        """The insights this message starts, once `state` has applied it."""
        kind = m["type"]
        if kind in ("match_info", "amendment"):
            return []
        self.events[m["event_id"]] = m
        extras = state.insight.extras() if state.insight is not None else {}
        if kind == "pass" and extras.get("difficulty") is not None:
            self.difficulty[m["event_id"]] = float(extras["difficulty"])
        if m.get("possession") is not None and m.get("team_id"):
            self._possessions.setdefault(int(m["possession"]), []).append(m["event_id"])
            self._onball.append(m)

        found: list[Found] = []
        if kind == "goal":
            found += self._goal(m, state)
        elif kind == "var_check":
            found.append(self._var(m, state))
        elif kind == "card" and m["card"] in ("red", "second_yellow"):
            found.append(self._red_card(m, state))
        elif kind == "foul" and m.get("penalty"):
            found.append(self._penalty(m))
        elif kind == "pass":
            found += self._hard_pass(m)
        elif kind == "shot":
            found += self._shot_speed(m)
        elif kind == "period_end" and m["period"] == 1:
            found.append(self._recap(m, state, "half_time"))
        elif kind == "match_end":
            found.append(self._recap(m, state, "full_time"))
        found += [self._tag(tag, m) for tag in extras.get("tags", []) if tag["kind"] == "distance" or tag["record"]]
        found += self._segment(m, state)
        return found

    # --- goals ---------------------------------------------------------------------------------

    def _goal(self, m: dict, state: RunState) -> list[Found]:
        shot = self.events.get(m["from_event_id"])
        shooter = shot["player_id"] if shot else m["player_id"]
        possession = [e for e in self._possessions.get(int(m["possession"]), []) if e != m["event_id"]][-12:]
        key_pass = None
        for event_id in reversed(possession):
            e = self.events[event_id]
            if e["type"] == "pass" and e["outcome"] == "complete" and e.get("recipient_id") == shooter:
                key_pass = e
                break
        shares, covered = self._on_top_before(m, state)
        score = m["score"]
        side = "home" if m["team_id"] == self.meta["home"]["id"] else "away"
        scored, conceded = score[side], score["away" if side == "home" else "home"]
        # Clubs take plural verbs: "Saltmarsh equalise".
        situation = (
            "equalise"
            if scored == conceded
            else "take the lead"
            if scored == conceded + 1
            else "extend the lead"
            if scored > conceded
            else "pull one back"
        )
        rank, reasons = BASE_RANK["goal"], []
        other = self.other(m["team_id"])
        if shares and shares[m["team_id"]] <= AGAINST_SCORERS_AT_MOST and shares[other] >= AGAINST_OTHERS_AT_LEAST:
            rank += 0.10
            reasons.append(
                f"against the run of play: {self.club(other)} were on top for {round(shares[other] * 100)}% of the "
                f"{F.duration(covered, '').display} before"
            )
        if situation in ("equalise", "take the lead"):
            rank += 0.05
            reasons.append(f"{self.club(m['team_id'])} {situation}")
        if m["minute"] >= 80:
            rank += 0.03
            reasons.append("late in the match")
        difficulty = self.difficulty.get(key_pass["event_id"]) if key_pass else None
        context = _GoalContext(
            seq=m["seq"],
            shot=shot,
            key_pass=key_pass,
            key_pass_difficulty=difficulty,
            possession=possession,
            shares=shares,
            covered=covered,
            situation=situation,
            rank=round(min(rank, 0.99), 2),
            reason="Goal" + (": " + "; ".join(reasons) if reasons else ""),
        )
        self.goals[m["event_id"]] = context
        found = [self.goal_insight(m, context, m["seq"])]
        if key_pass is not None and difficulty is not None:
            found.append(self._key_pass(m, key_pass, difficulty))
        return found

    def goal_insight(self, goal: dict, context: _GoalContext, seq: int) -> Found:
        """A goal's insight, from the goal as recorded or as corrected later."""
        topic = "own_goal" if goal["own_goal"] else "goal"
        scorer_events = (goal["event_id"],)
        f: Facts = {
            "moment.minute": F.minute(goal["minute"], goal["added_minute"], "minute of the goal", scorer_events),
            "moment.club": F.text(self.club(goal["team_id"]), "the club the goal counts for"),
            "moment.other_club": F.text(self.club(self.other(goal["team_id"])), "the other club"),
            "moment.scorer": F.text(
                self.name(goal["player_id"]),
                "who put the ball in the net" + (" (own goal)" if goal["own_goal"] else ""),
                scorer_events,
            ),
            "moment.score_line": F.text(self.score_line(goal["score"]), "the score after the goal", scorer_events),
            "moment.situation": F.text(context.situation, "what the goal does to the score"),
        }
        shot = context.shot
        if shot is not None:
            shot_events = (shot["event_id"],)
            f["moment.shooter"] = F.text(self.name(shot["player_id"]), "who took the shot", shot_events)
            f["moment.shot_speed"] = F.speed(float(shot["speed_kmh"]), "speed of the shot", shot_events)
            f["moment.shot_distance"] = F.metres(float(shot["distance"]), "distance of the shot from goal", shot_events)
            f["moment.play_pattern"] = F.text(
                str(shot["play_pattern"]).replace("_", " "), "how the move started", shot_events
            )
        if context.key_pass is not None and context.key_pass_difficulty is not None:
            pass_events = (context.key_pass["event_id"],)
            f["moment.passer"] = F.text(self.name(context.key_pass["player_id"]), "who made the last pass", pass_events)
            f["moment.key_pass_difficulty"] = F.rating(
                context.key_pass_difficulty, "difficulty of the last pass, 0 to 1", pass_events
            )
        if context.shares is not None:
            other = self.other(goal["team_id"])
            f["moment.window"] = F.duration(context.covered, "the stretch before the goal the shares cover")
            f["moment.club_on_top"] = F.share(
                context.shares[goal["team_id"]], "share of that stretch the scoring club was on top"
            )
            f["moment.other_on_top"] = F.share(context.shares[other], "share of that stretch the other club was on top")
            if context.reason.startswith("Goal: against the run of play"):
                f["moment.run_of_play"] = F.text("against the run of play", "the state model's view of the goal")
        evidence = [goal["event_id"], *([shot["event_id"]] if shot else []), *reversed(context.possession)]
        return Found(
            insight_id=f"goal-{goal['event_id']}",
            topic=topic,
            seq=seq,
            at=_at(goal),
            rank=context.rank,
            reason=context.reason,
            evidence=list(dict.fromkeys(evidence)),
            facts=f,
        )

    def _on_top_before(self, m: dict, state: RunState) -> tuple[dict[str, float] | None, int]:
        """Each club's share of the seconds before the goal in which the state shown was its own."""
        if state.insight is None:
            return None, 0
        end = int(m["t"]) - RUN_OF_PLAY_GAP
        labels = state.insight.shown_between(int(m["period"]), end - RUN_OF_PLAY_WINDOW, end)
        if len(labels) < RUN_OF_PLAY_MIN_SECONDS:
            return None, len(labels)
        home, away = self.meta["home"]["id"], self.meta["away"]["id"]
        return {
            home: sum(label.endswith(":home") for label in labels) / len(labels),
            away: sum(label.endswith(":away") for label in labels) / len(labels),
        }, len(labels)

    def _key_pass(self, goal: dict, key_pass: dict, difficulty: float) -> Found:
        events = (key_pass["event_id"],)
        f: Facts = {
            "moment.passer": F.text(self.name(key_pass["player_id"]), "who made the pass", events),
            "moment.receiver": F.text(self.name(key_pass["recipient_id"]), "who received it", events),
            "moment.difficulty": F.rating(difficulty, "difficulty of the pass, 0 to 1", events),
            "moment.completion": F.share(1 - difficulty, "the model's chance the pass would arrive", events),
            "moment.minute": F.minute(key_pass["minute"], key_pass["added_minute"], "minute of the pass", events),
        }
        return Found(
            insight_id=f"keypass-{key_pass['event_id']}",
            topic="key_pass",
            seq=goal["seq"],
            at=_at(goal),
            rank=round(BASE_RANK["key_pass"] + 0.3 * difficulty, 2),
            reason=f"Key pass for the goal, difficulty {difficulty:.2f}",
            evidence=[key_pass["event_id"], goal["event_id"]],
            facts=f,
        )

    # --- rule calls, cards, penalties ----------------------------------------------------------

    def _var(self, m: dict, state: RunState) -> Found:
        events = (m["event_id"],)
        incident = _INCIDENT.get(m["incident"], str(m["incident"]).replace("_", " "))
        f: Facts = {
            "moment.minute": F.minute(m["minute"], m["added_minute"], "minute of the check", events),
            "moment.check": Fact(m["check"], str(m["check"]), "what VAR is checking: goal or penalty", events),
            "moment.incident": F.text(incident, "what the check is for", events),
            "moment.subject": F.text(self.name(m.get("subject_id")), "the player the check is about", events),
        }
        evidence = [m["event_id"]]
        for key in ("related_event_id", "goal_event_id", "pass_event_id"):
            if m.get(key):
                evidence.append(m[key])
        if m.get("pass_event_id") in self.events:
            passed = self.events[m["pass_event_id"]]
            f["moment.passer"] = F.text(self.name(passed["player_id"]), "who played the pass", (passed["event_id"],))
        if m["status"] == "started":
            return Found(
                insight_id=f"var-{m['event_id']}",
                topic="var_started",
                seq=m["seq"],
                at=_at(m),
                rank=BASE_RANK["var_started"],
                reason=f"VAR check for {incident}: viewers need the status at once",
                evidence=evidence,
                facts=f,
            )
        decision = str(m["decision"])
        score = m.get("score") or state.stats.score
        f["moment.decision"] = Fact(decision, decision.replace("_", " "), "VAR's decision", events)
        f["moment.decision_text"] = F.text(_DECISION.get(decision, decision.replace("_", " ")), "the decision", events)
        f["moment.overturned"] = F.text(
            "was overturned" if m.get("overturned") else "stands", "what happened to the on-field decision", events
        )
        f["moment.score_line"] = F.text(self.score_line(score), "the score after the decision", events)
        overturned = bool(m.get("overturned"))
        return Found(
            insight_id=f"var-{m['event_id']}",
            topic="var_decision",
            seq=m["seq"],
            at=_at(m),
            rank=round(BASE_RANK["var_decision"] + (0.10 if overturned else 0.0), 2),
            reason=f"VAR decision: {_DECISION.get(decision, decision)}"
            + ("; on-field decision overturned" if overturned else ""),
            evidence=evidence,
            facts=f,
        )

    def _red_card(self, m: dict, state: RunState) -> Found:
        events = (m["event_id"],)
        left = 11 - state.stats.teams[m["team_id"]].red_cards
        f: Facts = {
            "moment.player": F.text(self.name(m["player_id"]), "the player sent off", events),
            "moment.club": F.text(self.club(m["team_id"]), "the player's club", events),
            "moment.minute": F.minute(m["minute"], m["added_minute"], "minute of the card", events),
            "moment.reason": F.text(_CARD_REASON.get(m.get("reason", ""), "a foul"), "what the card was for", events),
            "moment.players_left": Fact(left, f"{left} players", "players the club has left on the pitch", events),
        }
        return Found(
            insight_id=f"red-{m['event_id']}",
            topic="red_card",
            seq=m["seq"],
            at=_at(m),
            rank=BASE_RANK["red_card"],
            reason=f"Red card: {self.club(m['team_id'])} down to {left}",
            evidence=[m["event_id"]],
            facts=f,
        )

    def _penalty(self, m: dict) -> Found:
        events = (m["event_id"],)
        fouled = self.players.get(m.get("fouled_id", ""), {})
        f: Facts = {
            "moment.club": F.text(self.club(fouled.get("club_id")), "the club awarded the penalty", events),
            "moment.fouler": F.text(self.name(m["player_id"]), "who committed the foul", events),
            "moment.fouled": F.text(self.name(m.get("fouled_id")), "who was fouled", events),
            "moment.minute": F.minute(m["minute"], m["added_minute"], "minute of the foul", events),
        }
        return Found(
            insight_id=f"penalty-{m['event_id']}",
            topic="penalty",
            seq=m["seq"],
            at=_at(m),
            rank=BASE_RANK["penalty"],
            reason="Penalty awarded",
            evidence=[m["event_id"]],
            facts=f,
        )

    # --- stats and tags ------------------------------------------------------------------------

    def _hard_pass(self, m: dict) -> list[Found]:
        rating = self.difficulty.get(m["event_id"])
        if rating is None or m["outcome"] != "complete" or m["pass_type"] == "throw_in":
            return []
        if rating < HARD_PASS_AT_LEAST or rating <= self._hardest:
            self._hardest = max(self._hardest, rating)
            return []
        self._hardest = rating
        events = (m["event_id"],)
        f: Facts = {
            "moment.passer": F.text(self.name(m["player_id"]), "who made the pass", events),
            "moment.receiver": F.text(self.name(m.get("recipient_id")), "who received it", events),
            "moment.difficulty": F.rating(rating, "difficulty of the pass, 0 to 1", events),
            "moment.completion": F.share(1 - rating, "the model's chance the pass would arrive", events),
            "moment.minute": F.minute(m["minute"], m["added_minute"], "minute of the pass", events),
        }
        return [
            Found(
                insight_id=f"hardpass-{m['event_id']}",
                topic="hard_pass",
                seq=m["seq"],
                at=_at(m),
                rank=round(BASE_RANK["hard_pass"] + (rating - HARD_PASS_AT_LEAST), 2),
                reason=f"Hardest completed pass of the match so far, difficulty {rating:.2f}",
                evidence=[m["event_id"]],
                facts=f,
            )
        ]

    def _shot_speed(self, m: dict) -> list[Found]:
        speed = float(m["speed_kmh"])
        record = speed > self._fastest
        self._fastest = max(self._fastest, speed)
        if not record or speed < SHOT_SPEED_AT_LEAST or m["outcome"] == "goal":
            return []
        events = (m["event_id"],)
        f: Facts = {
            "moment.shooter": F.text(self.name(m["player_id"]), "who took the shot", events),
            "moment.speed": F.speed(speed, "speed of the shot", events),
            "moment.distance": F.metres(float(m["distance"]), "distance from goal", events),
            "moment.outcome": F.text(_SHOT_OUTCOME.get(m["outcome"], m["outcome"]), "what became of it", events),
            "moment.minute": F.minute(m["minute"], m["added_minute"], "minute of the shot", events),
        }
        return [
            Found(
                insight_id=f"shotspeed-{m['event_id']}",
                topic="shot_speed",
                seq=m["seq"],
                at=_at(m),
                rank=BASE_RANK["shot_speed"],
                reason=f"Fastest shot of the match so far, {speed:.0f} km/h",
                evidence=[m["event_id"]],
                facts=f,
            )
        ]

    def _tag(self, tag: dict, m: dict) -> Found:
        at = {"period": tag["period"], "t": tag["t"], "minute": tag["minute"], "added_minute": tag["added_minute"]}
        f: Facts = {
            "moment.player": F.text(self.name(tag["player_id"]), "the player"),
            "moment.club": F.text(self.club(tag["team_id"]), "the player's club"),
            "moment.minute": F.minute(tag["minute"], tag["added_minute"], "when the tracking recorded it"),
        }
        if tag["kind"] == "sprint":
            speed = float(tag["value"])
            f["moment.speed"] = F.speed(speed, "top speed of the sprint, from the tracking")
            return Found(
                insight_id=f"sprint-{tag['player_id']}-{tag['period']}-{round(tag['t'])}",
                topic="sprint",
                seq=m["seq"],
                at=at,
                rank=round(BASE_RANK["sprint"] + min(0.15, (speed - 32.0) / 20.0), 2),
                reason=f"Fastest sprint of the match so far, {speed:.1f} km/h",
                evidence=[],
                facts=f,
            )
        f["moment.distance"] = F.kilometres(float(tag["value"]), "distance covered, from the tracking")
        return Found(
            insight_id=f"distance-{tag['player_id']}-{tag['value']}",
            topic="distance",
            seq=m["seq"],
            at=at,
            rank=BASE_RANK["distance"],
            reason=f"Distance milestone, {tag['value']} km",
            evidence=[],
            facts=f,
        )

    # --- segments: spells of the match state ---------------------------------------------------

    def _segment(self, m: dict, state: RunState) -> list[Found]:
        if state.insight is None or state.insight.match_state is None:
            return []
        period = int(state.insight.match_state["period"])
        now = int(state.insight.match_state["second"]) + 1
        home, away = self.meta["home"]["id"], self.meta["away"]["id"]
        found = []
        for topic, (window, at_least) in SEGMENT_RULES.items():
            labels = state.insight.shown_between(period, now - window, now)
            if len(labels) < window:
                continue
            holders = [(None, "chaos")] if topic == "chaos" else [(home, f"{topic}:home"), (away, f"{topic}:away")]
            for team_id, label in holders:
                held = labels.count(label) / window
                last = self._reported.get((topic, team_id, period))
                if held < at_least or (last is not None and now - last < SEGMENT_GAP):
                    continue
                self._reported[(topic, team_id, period)] = now
                found.append(self._segment_insight(m, topic, team_id, period, now - window, now, held))
        return found

    def _segment_insight(
        self, m: dict, topic: str, team_id: str | None, period: int, start: int, end: int, held: float
    ) -> Found:
        window = [e for e in self._onball if e["period"] == period and start <= e["t"] < end]
        changes = [e for e in window if e["type"] == "possession_change"]
        key = _ids(e for e in window if e["type"] in ("shot", "possession_change"))
        move = _longest_move(window)
        stretch = F.duration(end - start, "the stretch of play the spell's figures cover")
        f: Facts = {
            "segment.window": stretch,
            "segment.state_share": F.share(held, "share of that stretch the match-state model showed this state", key),
            "segment.start_minute": F.minute(*_minute_of(period, start), "when the stretch began"),
            "segment.changes": Fact(
                len(changes), _times(len(changes)), "how often the ball changed hands in that stretch", _ids(changes)
            ),
            "segment.longest_move": _count_of(
                len(move), "pass", "longest run of completed passes by one side in that stretch", _ids(move)
            ),
        }
        rank = BASE_RANK[topic] + 0.25 * (held - SEGMENT_RULES[topic][1])
        if team_id is not None:
            passes = [e for e in window if e["type"] == "pass" and e.get("pass_type") != "throw_in"]
            shots = [e for e in window if e["type"] == "shot" and e["team_id"] == team_id]
            f["segment.club"] = F.text(self.club(team_id), "the club holding the state")
            f["segment.other"] = F.text(self.club(self.other(team_id)), "the other club")
            f["segment.shots"] = _count_of(
                len(shots), "shot", f"shots by {self.club(team_id)} in that stretch", _ids(shots)
            )
            f["segment.pass_share"] = F.share(
                sum(e["team_id"] == team_id for e in passes) / len(passes) if passes else 0.0,
                f"{self.club(team_id)}'s share of the passes in that stretch",
            )
            if topic == "pressure":
                rank += min(0.03 * len(shots), 0.15)
        who = f"{self.club(team_id)} " if team_id else ""
        share_text = f"{round(held * 100)}% of the last {stretch.display}"
        reason = {
            "pressure": f"Sustained pressure: {who}pinning the other side back for {share_text}",
            "chaos": f"No shape: chaos for {share_text}",
            "control": f"Control: {who}in control for {share_text}",
        }[topic]
        team_part = f"-{team_id}" if team_id else ""
        return Found(
            insight_id=f"{topic}{team_part}-{period}-{start}",
            topic=topic,
            seq=m["seq"],
            at=_at(m),
            rank=round(min(rank, 0.75), 2),
            reason=reason + ", from the match-state model",
            evidence=list(dict.fromkeys(e for fact in f.values() for e in fact.events)),
            facts=f,
        )

    # --- recaps --------------------------------------------------------------------------------

    def _recap(self, m: dict, state: RunState, topic: str) -> Found:
        f: Facts = {
            "recap.label": F.text("Half-time" if topic == "half_time" else "Full time", "which break this is"),
            "recap.when": F.text("half-time" if topic == "half_time" else "full time", "the break, in a sentence"),
            **self._recap_facts(m, state),
        }
        return Found(
            insight_id="ht" if topic == "half_time" else "ft",
            topic=topic,
            seq=m["seq"],
            at=_at(m),
            rank=BASE_RANK[topic],
            reason="Half-time recap" if topic == "half_time" else "Full-time recap",
            evidence=[m["event_id"], *_goal_events(f)],
            facts=f,
        )

    def catch_up(self, m: dict, state: RunState) -> Found:
        """What a viewer joining at this message has missed, for a replay that starts mid-match: the
        recap's facts as of the message, with the minute they join at."""
        events = (m["event_id"],)
        f: Facts = {
            "recap.to": F.minute(m["minute"], m["added_minute"], "the minute the viewer joins at", events),
            **self._recap_facts(m, state),
        }
        return Found(
            insight_id="catchup",
            topic="catch_up",
            seq=m["seq"],
            at=_at(m),
            rank=BASE_RANK["catch_up"],
            reason=f"Catch-up for viewers joining at {F.minute_label(m['minute'], m['added_minute'])}",
            evidence=[m["event_id"], *_goal_events(f)],
            facts=f,
        )

    def _recap_facts(self, m: dict, state: RunState) -> Facts:
        """What every recap may state: the score, the goals as they stand, and each club's share of the
        passes and its shots."""
        events = (m["event_id"],)
        teams = state.stats.view()["teams"]
        home, away = self.meta["home"]["id"], self.meta["away"]["id"]
        f: Facts = {
            "recap.score_line": F.text(self.score_line(m.get("score") or state.stats.score), "the score", events),
            "recap.home_club": F.text(self.club(home), "the home club"),
            "recap.away_club": F.text(self.club(away), "the away club"),
            "recap.home_possession": F.share(
                teams[home]["possession"] or 0.0, f"{self.club(home)}'s share of the passes"
            ),
            "recap.away_possession": F.share(
                teams[away]["possession"] or 0.0, f"{self.club(away)}'s share of the passes"
            ),
            "recap.home_shots": _count_of(teams[home]["shots"], "shot", f"shots by {self.club(home)}"),
            "recap.away_shots": _count_of(teams[away]["shots"], "shot", f"shots by {self.club(away)}"),
        }
        goals = _goals_standing(state)
        if goals:
            f["recap.goals"] = F.text(
                ", ".join(_goal_text(g.facts, g.topic == "own_goal") for g in goals),
                "the goals so far as they stand: scorer, the club the goal counts for, and minute",
                tuple(e for g in goals for e in g.facts["moment.scorer"].events),
            )
        return f

    # --- corrections ---------------------------------------------------------------------------

    def correction(self, m: dict, corrects: str | None) -> Found:
        """The card that tells viewers about a correction from the provider."""
        corrected = m["corrected_event"]
        events = (m["event_id"],)
        before = m["changes"].get("player_id", {}).get("before")
        f: Facts = {
            "correction.minute": F.minute(
                corrected["minute"], corrected["added_minute"], "minute of the corrected event", events
            ),
            "correction.after": F.text(self.name(corrected.get("player_id")), "who it is credited to now", events),
            "correction.before": F.text(
                self.name(before) + (" (own goal)" if m["changes"].get("own_goal", {}).get("before") else ""),
                "who it was credited to before",
                events,
            ),
            "correction.reason": F.text(str(m.get("reason", "")), "the provider's reason, as given", events),
        }
        return Found(
            insight_id=f"correction-{m['event_id']}-v{m['version']}",
            topic="correction",
            seq=m["seq"],
            at=_at(m),
            rank=BASE_RANK["correction"],
            reason=f"Correction from the provider: the {m['amends']} at {F.minute_label(corrected['minute'], corrected['added_minute'])}",
            evidence=[m["event_id"]],
            facts=f,
            corrects=corrects,
        )


def _goals_standing(state: RunState) -> list[Insight]:
    """The goals so far as they stand, in match order: from the run's goal insights, which a correction
    restates (an own goal credited to the scorer after all) and which VAR undoes (a goal ruled out)."""
    if state.book is None:
        return []
    goals = [
        i
        for i in state.book.insights.values()
        if i.topic in ("goal", "own_goal") and (i.flag is None or i.flag["seq"] == i.seq)
    ]
    return sorted(goals, key=lambda i: (i.at["period"], i.at["t"]))


def _goal_text(f: Facts, own_goal: bool) -> str:
    club = f["moment.club"].display
    return f"{f['moment.scorer'].display} ({'own goal, ' if own_goal else ''}{club}) {f['moment.minute'].display}"


def _goal_events(f: Facts) -> list[str]:
    return list(f["recap.goals"].events) if "recap.goals" in f else []


def _minute_of(period: int, second: float) -> tuple[int, int | None]:
    base = 0 if period == 1 else 45
    if second < PERIOD_SECONDS:
        return base + int(second // 60) + 1, None
    return base + 45, int((second - PERIOD_SECONDS) // 60) + 1


def _times(n: int) -> str:
    return "once" if n == 1 else f"{n} times"


def _ids(events: Iterable[dict]) -> tuple[str, ...]:
    """The IDs of the latest SEGMENT_EVENTS of `events`, in order."""
    return tuple(e["event_id"] for e in events)[-SEGMENT_EVENTS:]


def _count_of(n: int, noun: str, about: str, events: tuple[str, ...] = ()) -> Fact:
    """A count shown with its noun, so wording needn't agree with the number: "no shots", "1 pass"."""
    plural = f"{noun}es" if noun.endswith("s") else f"{noun}s"
    return Fact(n, f"no {plural}" if n == 0 else f"1 {noun}" if n == 1 else f"{n} {plural}", about, events)


def _longest_move(window: list[dict]) -> list[dict]:
    """The longest run of completed passes by one side, broken by any on-ball event of the other."""
    best: list[dict] = []
    run: list[dict] = []
    team = None
    for e in window:
        if e["type"] in ("pressure", "possession_change"):
            continue
        if e["team_id"] != team:
            team, run = e["team_id"], []
        if e["type"] == "pass":
            run = [*run, e] if e["outcome"] == "complete" else []
            if len(run) > len(best):
                best = run
    return best
