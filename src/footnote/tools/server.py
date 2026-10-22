"""The match tools' MCP server.

Eight read-only tools, each answering for the scope its request names (scope.py):

    get_moment         what happened, why it was picked, its facts and the template's wording
    get_story          the moments of the match so far, in order, each with its facts: for recaps
    get_match_stats    the score and each club's counts, shares and figures from the models
    get_match_state    the match-state model: the state now, and who was on top over recent minutes
    get_player         one player's passing, distance, speed, shots and goals
    get_events         particular events, as they stand at the moment (corrections applied)
    get_recent_events  the key events of the last few minutes before the moment
    get_lineups        both squads, with who is on the pitch

Each returns compact JSON with `facts` (key -> value, display, about) and the IDs of the `events`
it mentions. A tool returns a fact only for a figure code computed; it never estimates one.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from footnote.insights import facts as F
from footnote.insights.draft import PLACEHOLDER
from footnote.insights.facts import Fact, Facts, facts_to_json
from footnote.interpret.state import LABELS
from footnote.live.state import KEY_EVENT_TYPES
from footnote.live.timeline import broadcast_minute
from footnote.tools.scope import INSIGHT_HEADER, RUN_HEADER, Scope, Scopes

INSTRUCTIONS = (
    "Match data for one moment of a live football match, as viewers had it at that moment. "
    "Every figure is a fact with a key: write cards with {key} placeholders, never the figures."
)

# Part of the agents' cache key (agents/worker.py): change it whenever a tool's output changes, so
# replays stop reusing drafts written from the old output (versions.py adds a fingerprint of this
# file and the templates in case it isn't). 2026-10-21.1: get_story. 2026-10-21.2: the state of play
# described in clauses, the correction's facts and the templates reworded. 2026-10-22.1: how a move
# started in football's words ("open play", not "regular play"). 2026-10-22.2: a goal's reason and a
# correction's flag without a colon inside them.
TOOLS_VERSION = "2026-10-22.2"

# Read-only, and about a closed world: the match as stored.
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

MAX_EVENTS = 12
MAX_MINUTES = 45

# The moments a recap tells: what changed the match, and the spells when one side was on top.
# Stats and tags have their own cards and stay out of the story.
STORY_TOPICS = frozenset(
    {"goal", "own_goal", "penalty", "red_card", "var_decision", "pressure", "chaos", "control", "correction"}
)
MAX_STORY = 24  # the latest moments, if a match ever has more
STORY_EVENTS = 4  # events cited for each moment

_TYPE = {
    "pass": "pass",
    "shot": "shot",
    "goal": "goal",
    "var_check": "VAR check",
    "card": "card",
    "foul": "foul",
    "offside": "offside",
    "substitution": "substitution",
    "injury": "injury",
    "possession_change": "change of possession",
    "period_start": "kick-off",
    "period_end": "end of the half",
    "match_end": "full time",
    "added_time": "added time",
}
_STATE = {
    "control": "{club} in control",
    "pressure": "{club} pinning {other} back",
    "transition": "{club} on the break",
    "chaos": "neither side in control",
    "balanced": "evenly balanced",
}


def _counted(n: int, singular: str, plural: str, about: str, events: tuple[str, ...] = ()) -> Fact:
    """A count shown with its noun: "13 shots", "1 shot", "no shots"."""
    shown = f"no {plural}" if n == 0 else f"1 {singular}" if n == 1 else f"{n} {plural}"
    return Fact(n, shown, about, events)


def _result(facts: Facts, events: list[str] | None = None, **extra: object) -> str:
    out: dict = {"facts": facts_to_json(facts), "events": events or []}
    out.update(extra)
    return json.dumps(out, separators=(",", ":"), ensure_ascii=False)


# --- the figures behind each tool ------------------------------------------------------------


def moment(scope: Scope) -> str:
    row = scope.insight
    return _result(
        F.facts_from_json(row["facts"]),
        list(row["evidence"]),
        insight_id=row["insight_id"],
        kind=row["kind"],
        topic=row["topic"],
        minute=F.minute_label(row["at"]["minute"], row["at"]["added_minute"]),
        reason=row["reason"],
        rank=row["rank"],
        corrects=row["corrects"],
        flag=row["flag"],
        template=row["template"],
    )


def story(scope: Scope) -> str:
    """The match's moments up to the scope's, in order, each with its facts under its own keys.

    The moments are the run's insights as they stand at the scope's seq: a goal VAR ruled out is left
    out (the VAR decision tells it), and a goal a correction restated carries the corrected facts.
    Each moment's facts are renamed from `moment.scorer` to `story.<n>.scorer`, so two goals' scorers
    don't share a key, and its template's wording is given with the renamed placeholders. A fact keeps
    only the events its moment cites, which is what a recap links to; the rest would only lengthen
    what the writer reads.
    """
    book = scope.state.book
    if book is None:
        return _result({}, moments=[], note="The match has no moments yet.")
    told = [i for i in book.insights.values() if i.topic in STORY_TOPICS and (i.flag is None or i.flag["seq"] == i.seq)]
    told.sort(key=lambda i: (i.at["period"], i.at["t"], i.seq))
    f: Facts = {}
    moments, cited = [], []
    for n, insight in enumerate(told[-MAX_STORY:], start=1):
        minute = F.minute_label(insight.at["minute"], insight.at["added_minute"])
        what = f"{insight.topic.replace('_', ' ')} at {minute}"
        events = insight.evidence[:STORY_EVENTS]
        keys = {key: f"story.{n}.{key.split('.', 1)[1]}" for key in insight.facts}
        for key, fact in insight.facts.items():
            kept = tuple(e for e in fact.events if e in events)
            f[keys[key]] = Fact(fact.value, fact.display, f"{fact.about} ({what})", kept)
        template = insight.template
        cited += events
        moment = {
            "moment": n,
            "minute": minute,
            "topic": insight.topic,
            "reason": insight.reason,
            "headline": _renamed(template.headline, keys),
            "line": " ".join(_renamed(s.text, keys) for s in template.casual),
            "events": events,
        }
        if insight.flag is not None:
            moment["corrected"] = insight.flag["reason"]
        moments.append(moment)
    return _result(f, list(dict.fromkeys(cited)), moments=moments)


def _renamed(text: str, keys: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: "{" + keys.get(m.group(1), m.group(1)) + "}", text)


def match_stats(scope: Scope) -> str:
    view = scope.state.live_fields()
    finder = scope.finder
    meta = finder.meta
    f: Facts = {"score.line": F.text(finder.score_line(view["score"]), "the score")}
    clock = view["clock"] or {"minute": 1, "added_minute": None}
    f["clock.minute"] = F.minute(clock["minute"], clock["added_minute"], "the minute the moment came in")
    for side in ("home", "away"):
        club = meta[side]
        t = view["teams"][club["id"]]
        p = f"teams.{club['code']}"
        name = club["short_name"]
        f[f"score.{club['code']}"] = F.count(view["score"][side], f"goals for {name}")
        f[f"{p}.name"] = F.text(name, "the club's name as cards print it")
        f[f"{p}.shots"] = _counted(t["shots"], "shot", "shots", f"shots by {name}")
        f[f"{p}.on_target"] = _counted(t["on_target"], "shot on target", "shots on target", f"{name}'s shots on target")
        f[f"{p}.passes"] = _counted(t["passes"], "pass", "passes", f"passes attempted by {name}, throw-ins excluded")
        f[f"{p}.corners"] = _counted(t["corners"], "corner", "corners", f"corners taken by {name}")
        f[f"{p}.fouls"] = _counted(t["fouls"], "foul", "fouls", f"fouls committed by {name}")
        f[f"{p}.offsides"] = _counted(t["offsides"], "offside", "offsides", f"times {name} were caught offside")
        f[f"{p}.yellow_cards"] = _counted(t["yellow_cards"], "yellow card", "yellow cards", f"{name}'s yellow cards")
        f[f"{p}.red_cards"] = _counted(t["red_cards"], "red card", "red cards", f"{name}'s red cards")
        if t["possession"] is not None:
            f[f"{p}.possession"] = F.share(t["possession"], f"{name}'s share of the passes (possession)")
        if t["pass_accuracy"] is not None:
            f[f"{p}.pass_accuracy"] = F.share(t["pass_accuracy"], f"share of {name}'s passes completed")
        if t.get("pass_length") is not None:
            f[f"{p}.pass_length"] = F.metres(t["pass_length"], f"{name}'s average pass length")
        if t.get("pass_difficulty") is not None:
            f[f"{p}.pass_difficulty"] = F.rating(t["pass_difficulty"], f"{name}'s average pass difficulty, 0 to 1")
        if t.get("distance_km") is not None:
            f[f"{p}.distance"] = F.kilometres(t["distance_km"], f"distance covered by {name}'s players")
        if t.get("top_shot_kmh") is not None:
            f[f"{p}.fastest_shot"] = F.speed(t["top_shot_kmh"], f"{name}'s fastest shot")
    return _result(f)


def _state_text(label: str, scope: Scope, texts: dict[str, str] = _STATE) -> str:
    state, _, side = label.partition(":")
    meta = scope.finder.meta
    club = meta[side]["short_name"] if side else ""
    other = meta["away" if side == "home" else "home"]["short_name"] if side else ""
    return texts[state].format(club=club, other=other)


# A state in a clause, for the shares' descriptions: a writer may copy one, and "shown as on top"
# came out of the last wording ("Kingsferry had 2% of that stretch shown as on top").
_WHEN = {
    "control": "{club} were in control",
    "pressure": "{club} were pinning {other} back",
    "transition": "{club} were on the break",
    "chaos": "neither side was in control",
    "balanced": "play was evenly balanced",
}


def _when(label: str, scope: Scope) -> str:
    return _state_text(label, scope, _WHEN)


def _label(state: str, team_id: str | None, meta: dict) -> str:
    """The state model's label for a state and the club holding it: "control:home", "chaos"."""
    if team_id is None:
        return state
    return f"{state}:{'home' if team_id == meta['home']['id'] else 'away'}"


def match_state(scope: Scope, minutes: int) -> str:
    insight = scope.state.insight
    if insight is None or insight.match_state is None:
        return _result({}, note="There is no estimate of the state of play yet.")
    ms = insight.match_state
    meta = scope.finder.meta
    f: Facts = {
        "state.now": F.text(
            _state_text(_label(ms["state"], ms["team_id"], meta), scope),
            "the match state the model shows now, a few seconds behind play",
        ),
        "state.confidence": F.share(ms["confidence"], "the model's chance of the state it shows"),
    }
    for side in ("home", "away"):
        club = meta[side]
        f[f"state.on_top.{club['code']}"] = F.share(
            ms["on_top"][side], f"the model's chance {club['short_name']} hold a state of their own now"
        )
    window = max(1, min(int(minutes), MAX_MINUTES)) * 60
    end = int(ms["second"]) + 1
    labels = insight.shown_between(int(ms["period"]), end - window, end)
    if labels:
        f["state.last.window"] = F.duration(len(labels), "the stretch of this half the shares below cover")
        for label in LABELS:
            state, _, side = label.partition(":")
            key = f"state.last.{meta[side]['code']}.{state}" if side else f"state.last.{state}"
            f[key] = F.share(labels.count(label) / len(labels), f"share of that stretch when {_when(label, scope)}")
    spells = []
    for i, spell in enumerate(insight.timeline[-6:]):
        f[f"state.spell.{i}.from"] = F.minute(*broadcast_minute(spell["period"], spell["start"]), "when it began")
        f[f"state.spell.{i}.to"] = F.minute(*broadcast_minute(spell["period"], spell["end"]), "when it was last shown")
        state = _state_text(_label(spell["state"], spell["team_id"], meta), scope)
        spells.append({"state": state, "from": f"state.spell.{i}.from", "to": f"state.spell.{i}.to"})
    return _result(f, spells=spells)


def _goals_by_player(scope: Scope) -> dict[str, list[str]]:
    """Each player's goals as they stand: own goals and goals VAR ruled out don't count."""
    goals: dict[str, tuple[str, bool]] = {}
    for m in scope.feed:
        if m["type"] == "goal":
            goals[m["event_id"]] = (m["player_id"], bool(m["own_goal"]))
        elif m["type"] == "amendment" and m["corrected_event"]["type"] == "goal":
            c = m["corrected_event"]
            goals[c["event_id"]] = (c["player_id"], bool(c["own_goal"]))
        elif m["type"] == "var_check" and m.get("decision") == "no_goal" and m.get("goal_event_id"):
            goals.pop(m["goal_event_id"], None)
    out: dict[str, list[str]] = {}
    for event_id, (player_id, own_goal) in goals.items():
        if not own_goal:
            out.setdefault(player_id, []).append(event_id)
    return out


def player(scope: Scope, player_id: str) -> str:
    finder = scope.finder
    p = finder.players.get(player_id)
    if p is None:
        return _result({}, error=f"no player {player_id} in this match; get_lineups lists them")
    insight = scope.state.insight
    k = f"player.{player_id}"
    f: Facts = {
        f"{k}.name": F.text(p["name"], "the player's name"),
        f"{k}.club": F.text(finder.club(p["club_id"]), "the player's club"),
        f"{k}.shirt": F.count(int(p["shirt"]), "shirt number"),
        f"{k}.position": F.text(str(p["position"]), "position"),
    }
    if insight is not None:
        line = insight.player_line(player_id)
        f[f"{k}.passes"] = _counted(line["passes"], "pass", "passes", "passes attempted, throw-ins excluded")
        f[f"{k}.completed"] = _counted(line["completed"], "completed pass", "completed passes", "passes completed")
        if line["passes"]:
            f[f"{k}.pass_accuracy"] = F.share(line["completed"] / line["passes"], "share of passes completed")
        if line["difficulty"] is not None:
            f[f"{k}.pass_difficulty"] = F.rating(
                line["difficulty"], "average difficulty of the player's passes, 0 to 1"
            )
        if line["hardest"] is not None and line["hardest_minute"] is not None:
            f[f"{k}.hardest_pass"] = F.rating(line["hardest"], "difficulty of the player's hardest pass, 0 to 1")
            f[f"{k}.hardest_pass_minute"] = F.minute(line["hardest_minute"], None, "minute of that pass")
        if "distance_km" in line:
            f[f"{k}.distance"] = F.kilometres(line["distance_km"], "distance covered, from the tracking")
            f[f"{k}.top_speed"] = F.speed(line["top_speed_kmh"], "top speed, from the tracking")
    shots = [m["event_id"] for m in scope.feed if m["type"] == "shot" and m["player_id"] == player_id]
    goals = _goals_by_player(scope).get(player_id, [])
    f[f"{k}.shots"] = _counted(len(shots), "shot", "shots", "shots taken", tuple(shots[-MAX_EVENTS:]))
    f[f"{k}.goals"] = _counted(len(goals), "goal", "goals", "goals scored, own goals excluded", tuple(goals))
    return _result(f, [*shots[-MAX_EVENTS:], *goals])


def describe(m: dict, scope: Scope) -> str:
    """One line on an event, from its own fields, for an agent to understand it."""
    finder = scope.finder
    who = f"{finder.name(m.get('player_id'))} ({finder.club(m.get('team_id'))})" if m.get("player_id") else ""
    kind = m["type"]
    if kind == "pass":
        to = finder.name(m.get("recipient_id")) if m.get("recipient_id") else "no one"
        return f"{who} pass to {to}: {m['outcome']}, {m['height']}" + (", a cross" if m.get("cross") else "")
    if kind == "shot":
        return f"{who} shot: {m['outcome'].replace('_', ' ')}, {finder.play_pattern(m['play_pattern'])}"
    if kind == "goal":
        own = " (own goal)" if m["own_goal"] else ""
        return (
            f"goal for {finder.club(m['team_id'])}: {finder.name(m['player_id'])}{own}, {finder.score_line(m['score'])}"
        )
    if kind == "var_check":
        if m["status"] == "started":
            return f"VAR checking the {m['check']} for {m['incident']} by {finder.name(m.get('subject_id'))}"
        return f"VAR decision: {str(m['decision']).replace('_', ' ')}" + (", overturned" if m.get("overturned") else "")
    if kind == "card":
        return f"{m['card'].replace('_', ' ')} card for {who}, {m.get('reason', '')}"
    if kind == "foul":
        return f"foul by {who} on {finder.name(m.get('fouled_id'))}" + (", penalty" if m.get("penalty") else "")
    if kind == "substitution":
        return f"{finder.club(m['team_id'])} substitution: {finder.name(m['player_on_id'])} on for {finder.name(m['player_off_id'])}"
    if kind == "offside":
        return f"{who} caught offside"
    return f"{_TYPE.get(kind, kind.replace('_', ' '))}" + (f" by {who}" if who else "")


def _event_facts(m: dict, scope: Scope) -> Facts:
    finder = scope.finder
    e = m["event_id"]
    k = f"event.{e}"
    ev = (e,)
    f: Facts = {
        f"{k}.minute": F.minute(m["minute"], m["added_minute"], "minute of the event", ev),
        f"{k}.type": F.text(_TYPE.get(m["type"], m["type"].replace("_", " ")), "what kind of event", ev),
    }
    if m.get("player_id"):
        f[f"{k}.player"] = F.text(finder.name(m["player_id"]), "the player on the event", ev)
    if m.get("team_id"):
        f[f"{k}.club"] = F.text(finder.club(m["team_id"]), "the club on the event", ev)
    if m["type"] == "pass":
        f[f"{k}.length"] = F.metres(float(m["length"]), "length of the pass", ev)
        f[f"{k}.speed"] = F.speed(float(m["speed_kmh"]), "speed of the pass", ev)
        f[f"{k}.outcome"] = F.text(str(m["outcome"]).replace("_", " "), "what became of the pass", ev)
        if m.get("recipient_id"):
            f[f"{k}.receiver"] = F.text(finder.name(m["recipient_id"]), "the intended receiver", ev)
        rating = finder.difficulty.get(e)
        if rating is not None:
            f[f"{k}.difficulty"] = F.rating(rating, "difficulty of the pass, 0 to 1", ev)
            f[f"{k}.completion_chance"] = F.share(1 - rating, "the model's chance the pass would arrive", ev)
    elif m["type"] == "shot":
        f[f"{k}.speed"] = F.speed(float(m["speed_kmh"]), "how fast the shot left the boot", ev)
        f[f"{k}.distance"] = F.metres(float(m["distance"]), "distance from goal", ev)
        f[f"{k}.outcome"] = F.text(str(m["outcome"]).replace("_", " "), "what became of the shot", ev)
        f[f"{k}.body_part"] = F.text(str(m["body_part"]).replace("_", " "), "what it was struck with", ev)
    elif m["type"] == "goal":
        f[f"{k}.score_line"] = F.text(finder.score_line(m["score"]), "the score after the goal", ev)
        if m.get("assist_id"):
            f[f"{k}.assist"] = F.text(finder.name(m["assist_id"]), "who provided the assist", ev)
    elif m["type"] == "var_check" and m["status"] == "complete":
        f[f"{k}.decision"] = F.text(str(m["decision"]).replace("_", " "), "VAR's decision", ev)
    return f


def events(scope: Scope, event_ids: list[str]) -> str:
    known = scope.events
    f: Facts = {}
    found, missing, lines = [], [], []
    for event_id in event_ids[:MAX_EVENTS]:
        m = known.get(event_id)
        if m is None:
            missing.append(event_id)
            continue
        found.append(event_id)
        f |= _event_facts(m, scope)
        lines.append({"event_id": event_id, "summary": describe(m, scope)})
    extra: dict[str, object] = {"summaries": lines}
    if missing:
        extra["missing"] = missing
        extra["note"] = "Events not in this match up to the moment are left out."
    return _result(f, found, **extra)


RECENT_TYPES = KEY_EVENT_TYPES | {"foul"}


def recent_events(scope: Scope, minutes: int) -> str:
    clock = scope.state.clock
    if clock is None:
        return _result({}, summaries=[])
    since = float(clock["t"]) - max(1, min(int(minutes), MAX_MINUTES)) * 60
    picked = [
        m
        for m in scope.feed
        if m["type"] in RECENT_TYPES and m["type"] != "amendment" and m["period"] == clock["period"] and m["t"] >= since
    ][-MAX_EVENTS:]
    f: Facts = {}
    for m in picked:
        f[f"event.{m['event_id']}.minute"] = F.minute(
            m["minute"], m["added_minute"], "minute of the event", (m["event_id"],)
        )
    lines = [{"event_id": m["event_id"], "summary": describe(m, scope)} for m in picked]
    return _result(f, [m["event_id"] for m in picked], summaries=lines)


def lineups(scope: Scope) -> str:
    finder = scope.finder
    on: set[str] = set()
    off: set[str] = set()
    for lineup in finder.meta["lineups"]:
        on |= {p["player_id"] for p in lineup["starters"]}
    for m in scope.feed:
        if m["type"] == "substitution":
            on.discard(m["player_off_id"])
            off.add(m["player_off_id"])
            on.add(m["player_on_id"])
    f: Facts = {}
    clubs = []
    for lineup in finder.meta["lineups"]:
        players = []
        for p in [*lineup["starters"], *lineup["bench"]]:
            f[f"player.{p['player_id']}.name"] = F.text(p["name"], "the player's name")
            status = (
                "on the pitch"
                if p["player_id"] in on
                else "substituted off"
                if p["player_id"] in off
                else "on the bench"
            )
            players.append(
                {"player_id": p["player_id"], "shirt": p["shirt"], "position": p["position"], "status": status}
            )
        clubs.append({"club": finder.club(lineup["club_id"]), "players": players})
    return _result(f, clubs=clubs)


# --- the server ------------------------------------------------------------------------------


def build_server(scopes: Scopes, *, allowed_hosts: list[str] | None = None) -> FastMCP:
    """The MCP server for the match tools, answering from `scopes`."""
    server = FastMCP(
        "footnote-match",
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts or ["127.0.0.1:*", "localhost:*"],
            allowed_origins=[],
        ),
    )

    def tool(description: str) -> Callable:
        # Plain text out: the compact JSON each tool writes is what the model reads, not a wrapper.
        return server.tool(description=description, structured_output=False, annotations=READ_ONLY)

    async def scoped(ctx: Context, answer: Callable[[Scope], str]) -> str:
        request = ctx.request_context.request
        headers = request.headers if request is not None else {}
        run_id, insight_id = headers.get(RUN_HEADER), headers.get(INSIGHT_HEADER)
        if not run_id or not insight_id:
            raise ValueError("this server answers only for a scoped agent run")
        return answer(await scopes.get(run_id, insight_id))

    @tool(
        description="The moment this card is about: what happened, why it was picked, its facts and the template's wording. Call it first."
    )
    async def get_moment(ctx: Context) -> str:
        return await scoped(ctx, moment)

    @tool(
        description="The moments of the match so far, in order (goals, VAR decisions, red cards, spells when one side was on top, corrections), each with its facts and events. For recaps."
    )
    async def get_story(ctx: Context) -> str:
        return await scoped(ctx, story)

    @tool(description="The score and each club's counts, shares and model figures at the moment.")
    async def get_match_stats(ctx: Context) -> str:
        return await scoped(ctx, match_stats)

    @tool(
        description="The state of play as the model estimates it: the state now and each club's share of recent"
        " minutes in each state. Cards say what the state of play was, not the model's name."
    )
    async def get_match_state(ctx: Context, minutes: int = 10) -> str:
        return await scoped(ctx, lambda s: match_state(s, minutes))

    @tool(description="One player's passing, distance, top speed, shots and goals at the moment. IDs look like sal-10.")
    async def get_player(ctx: Context, player_id: str) -> str:
        return await scoped(ctx, lambda s: player(s, player_id))

    @tool(description="Particular events by ID, as they stand at the moment, with corrections applied.")
    async def get_events(ctx: Context, event_ids: list[str]) -> str:
        return await scoped(ctx, lambda s: events(s, event_ids))

    @tool(description="The key events of the last few minutes before the moment, newest last.")
    async def get_recent_events(ctx: Context, minutes: int = 5) -> str:
        return await scoped(ctx, lambda s: recent_events(s, minutes))

    @tool(description="Both squads with player IDs and who is on the pitch.")
    async def get_lineups(ctx: Context) -> str:
        return await scoped(ctx, lineups)

    return server
