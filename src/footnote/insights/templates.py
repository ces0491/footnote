"""The code's own wording for each kind of moment.

Every insight starts as its template: viewers and the producer see it at once, and it stays when an
agent's draft doesn't arrive in time or fails a check. A template writes placeholders for figures
and names, exactly as an agent must, so `draft.check` holds templates to the same rules
(tests/test_insights.py checks every template the showcase match produces).

Templates say only what the facts record. Anything that needs judgement, such as why a moment
matters, is left to the agents and checked.
"""

from __future__ import annotations

from collections.abc import Callable

from footnote.insights.draft import Draft, Sentence
from footnote.insights.facts import Facts


def _s(text: str, *events: str) -> Sentence:
    return Sentence(text=text, events=list(events))


def _event(facts: Facts, key: str) -> list[str]:
    fact = facts.get(key)
    return list(fact.events) if fact else []


def goal(f: Facts) -> Draft:
    casual = [_s("{moment.score_line}: {moment.scorer} scores at {moment.minute}.", *_event(f, "moment.scorer"))]
    if "moment.run_of_play" in f:
        casual.append(
            _s("{moment.other_club} had been on top for {moment.other_on_top} of the {moment.window} before.")
        )
    analyst = [
        _s(
            "The shot, from {moment.shot_distance}, left the boot at {moment.shot_speed}.",
            *_event(f, "moment.shot_speed"),
        )
    ]
    if "moment.key_pass_difficulty" in f:
        analyst.append(_s("{moment.passer} made the last pass, difficulty {moment.key_pass_difficulty}."))
    return Draft(headline="{moment.scorer} scores", casual=casual, analyst=analyst)


def own_goal(f: Facts) -> Draft:
    return Draft(
        headline="Own goal: {moment.scorer}",
        casual=[
            _s("{moment.score_line}: an own goal by {moment.scorer} at {moment.minute}.", *_event(f, "moment.scorer"))
        ],
        analyst=[
            _s("It came from a shot by {moment.shooter} at {moment.shot_speed}.", *_event(f, "moment.shot_speed"))
        ],
    )


def var_started(f: Facts) -> Draft:
    if f["moment.check"].value == "goal":
        casual = [_s("VAR is checking {moment.subject}'s goal for {moment.incident}.", *_event(f, "moment.check"))]
    else:
        casual = [
            _s("VAR is checking for a penalty: {moment.incident} by {moment.subject}.", *_event(f, "moment.check"))
        ]
    return Draft(
        headline="VAR check: {moment.incident}",
        casual=casual,
        analyst=[_s("The check started at {moment.minute}.", *_event(f, "moment.check"))],
    )


def var_decision(f: Facts) -> Draft:
    events = _event(f, "moment.decision")
    if f["moment.decision"].value == "no_goal" and "moment.passer" in f:
        casual = [
            _s("{moment.subject} was offside when {moment.passer} played the pass, so the goal is ruled out.", *events),
            _s("It stays {moment.score_line}.", *events),
        ]
    elif f["moment.decision"].value == "no_goal":
        casual = [
            _s("The goal is ruled out for {moment.incident}.", *events),
            _s("It stays {moment.score_line}.", *events),
        ]
    elif f["moment.decision"].value == "no_penalty":
        casual = [_s("No penalty after the check for {moment.incident} by {moment.subject}.", *events)]
    else:
        casual = [_s("{moment.decision_text} after the check for {moment.incident}.", *events)]
    return Draft(
        headline="VAR: {moment.decision_text}",
        casual=casual,
        analyst=[_s("The on-field decision {moment.overturned}.", *events)],
    )


def red_card(f: Facts) -> Draft:
    return Draft(
        headline="Red card: {moment.player}",
        casual=[_s("{moment.club} are down to {moment.players_left}.", *_event(f, "moment.player"))],
        analyst=[
            _s("{moment.player} is sent off at {moment.minute} for {moment.reason}.", *_event(f, "moment.player"))
        ],
    )


def penalty(f: Facts) -> Draft:
    return Draft(
        headline="Penalty to {moment.club}",
        casual=[_s("{moment.fouler} fouls {moment.fouled} in the box.", *_event(f, "moment.fouled"))],
        analyst=[_s("Awarded at {moment.minute}.", *_event(f, "moment.fouled"))],
    )


def key_pass(f: Facts) -> Draft:
    return Draft(
        headline="Key pass: {moment.passer}",
        casual=[
            _s(
                "{moment.passer} set up the goal with a pass rated {moment.difficulty} for difficulty.",
                *_event(f, "moment.difficulty"),
            )
        ],
        analyst=[
            _s(
                "The model gave it a {moment.completion} chance of reaching {moment.receiver}.",
                *_event(f, "moment.difficulty"),
            )
        ],
    )


def hard_pass(f: Facts) -> Draft:
    return Draft(
        headline="Hardest pass yet: {moment.passer}",
        casual=[
            _s(
                "{moment.passer} finds {moment.receiver} with the hardest completed pass of the match so far.",
                *_event(f, "moment.difficulty"),
            )
        ],
        analyst=[
            _s(
                "Difficulty {moment.difficulty}: a {moment.completion} chance of arriving.",
                *_event(f, "moment.difficulty"),
            )
        ],
    )


def shot_speed(f: Facts) -> Draft:
    return Draft(
        headline="{moment.shooter} hits {moment.speed}",
        casual=[_s("The fastest shot of the match so far, from {moment.shooter}.", *_event(f, "moment.speed"))],
        analyst=[_s("Struck from {moment.distance}; outcome: {moment.outcome}.", *_event(f, "moment.speed"))],
    )


def sprint(f: Facts) -> Draft:
    return Draft(
        headline="{moment.player} hits {moment.speed}",
        casual=[_s("{moment.player} sprints at {moment.speed}, the fastest of the match so far.")],
        analyst=[_s("Top speed from the tracking at {moment.minute}, smoothed as tracking providers report it.")],
    )


def distance(f: Facts) -> Draft:
    return Draft(
        headline="{moment.player} passes {moment.distance}",
        casual=[_s("{moment.player} has covered {moment.distance}.")],
        analyst=[_s("Distance from the tracking, reached at {moment.minute}.")],
    )


def pressure(f: Facts) -> Draft:
    return Draft(
        headline="{segment.club} pinning {segment.other} back",
        casual=[
            _s(
                "{segment.club} have kept {segment.other} pinned in their own half for {segment.state_share} "
                "of the last {segment.window}."
            )
        ],
        analyst=[_s("In that time {segment.club} have had {segment.pass_share} of the passes and {segment.shots}.")],
    )


def chaos(f: Facts) -> Draft:
    return Draft(
        headline="Neither side in control",
        casual=[
            _s(
                "The game has lost its shape: the ball has changed hands {segment.changes} in the last {segment.window}."
            )
        ],
        analyst=[_s("The longest passing move in that time is {segment.longest_move}.")],
    )


def control(f: Facts) -> Draft:
    return Draft(
        headline="{segment.club} in control",
        casual=[_s("{segment.club} have controlled the game for {segment.state_share} of the last {segment.window}.")],
        analyst=[_s("{segment.club} have made {segment.pass_share} of the passes in that time.")],
    )


def _recap_figures() -> list[Sentence]:
    return [
        _s("{recap.home_club} have had {recap.home_possession} of the passes and {recap.home_shots}."),
        _s("{recap.away_club} have had {recap.away_possession} of the passes and {recap.away_shots}."),
    ]


def recap(f: Facts) -> Draft:
    casual = [_s("{recap.score_line} at {recap.when}.", *_event(f, "recap.score_line"))]
    if "recap.goals" in f:
        casual.append(_s("Goals: {recap.goals}."))
    return Draft(headline="{recap.label}: {recap.score_line}", casual=casual, analyst=_recap_figures())


def catch_up(f: Facts) -> Draft:
    """What a viewer joining mid-match missed. The score stays out: the viewer asks for it."""
    if "recap.goals" in f:
        casual = [_s("Goals so far: {recap.goals}.")]
    else:
        casual = [_s("No goals so far.", *_event(f, "recap.to"))]
    return Draft(headline="What you missed, up to {recap.to}", casual=casual, analyst=_recap_figures())


def correction(f: Facts) -> Draft:
    return Draft(
        headline="Corrected: {correction.after}",
        casual=[
            _s(
                "Corrected: the {correction.minute} goal is now credited to {correction.after}, not {correction.before}.",
                *_event(f, "correction.after"),
            )
        ],
        analyst=[_s("The provider's reason: {correction.reason}.", *_event(f, "correction.after"))],
    )


TEMPLATES: dict[str, Callable[[Facts], Draft]] = {
    "goal": goal,
    "own_goal": own_goal,
    "var_started": var_started,
    "var_decision": var_decision,
    "red_card": red_card,
    "penalty": penalty,
    "key_pass": key_pass,
    "hard_pass": hard_pass,
    "shot_speed": shot_speed,
    "sprint": sprint,
    "distance": distance,
    "pressure": pressure,
    "chaos": chaos,
    "control": control,
    "half_time": recap,
    "full_time": recap,
    "catch_up": catch_up,
    "correction": correction,
}


def template(topic: str, facts: Facts) -> Draft:
    return TEMPLATES[topic](facts)
