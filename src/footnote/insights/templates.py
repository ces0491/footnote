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

from footnote.insights.draft import Draft, Sentence, indefinite
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
        # "Made the last pass" came back as "realizó la última pasada" and "a effectué le dernier passage".
        analyst.append(_s("{moment.passer} played the final pass, difficulty {moment.key_pass_difficulty}."))
    return Draft(headline="{moment.scorer} scores", casual=casual, analyst=analyst)


def own_goal(f: Facts) -> Draft:
    return Draft(
        headline="Own goal: {moment.scorer}",
        casual=[
            _s("{moment.score_line}: an own goal by {moment.scorer} at {moment.minute}.", *_event(f, "moment.scorer"))
        ],
        analyst=[
            # Named, not "it", which French made feminine ("Elle provenait d'un tir").
            _s(
                "The own goal came from a shot by {moment.shooter} at {moment.shot_speed}.",
                *_event(f, "moment.shot_speed"),
            )
        ],
    )


def var_started(f: Facts) -> Draft:
    if f["moment.check"].value == "goal":
        casual = [_s("VAR is checking {moment.subject}'s goal for {moment.incident}.", *_event(f, "moment.check"))]
    else:
        # A question, not the offence: the check may find none.
        casual = [
            _s(
                "VAR is checking whether {moment.subject} gave away a penalty for {moment.incident}.",
                *_event(f, "moment.check"),
            )
        ]
    return Draft(
        headline="VAR check: {moment.incident}",
        casual=casual,
        analyst=[_s("The check started at {moment.minute}.", *_event(f, "moment.check"))],
    )


def var_decision(f: Facts) -> Draft:
    events = _event(f, "moment.decision")
    # "The score stays Saltmarsh 0–1 Kingsferry" came back as "0–1 para Saltmarsh y Kingsferry", and
    # "is still" with a level score as "reste 1–1 pour Saltmarsh Kingsferry".
    unchanged = _s("The score is unchanged: {moment.score_line}.", *events)
    if f["moment.decision"].value == "no_goal" and "moment.passer" in f:
        casual = [
            _s("{moment.subject} was offside when {moment.passer} played the pass, so the goal is ruled out.", *events),
            unchanged,
        ]
    elif f["moment.decision"].value == "no_goal":
        casual = [
            _s("The goal is ruled out for {moment.incident}.", *events),
            unchanged,
        ]
    elif f["moment.decision"].value == "no_penalty":
        # VAR found no offence, so the card doesn't write one ("handball by Uche Asatoye").
        offence = "foul" if f["moment.incident"].value == "a foul" else "{moment.incident}"
        casual = [_s(f"VAR found no {offence} by {{moment.subject}}, so there is no penalty.", *events)]
    elif f["moment.decision"].value == "penalty":
        casual = [_s("VAR gives a penalty for {moment.incident} by {moment.subject}.", *events)]
    else:
        casual = [_s("The goal counts after the VAR check for {moment.incident}.", *events)]
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
                "{moment.passer}'s pass set up the goal, difficulty {moment.difficulty}.",
                *_event(f, "moment.difficulty"),
            )
        ],
        analyst=[
            _s(
                f"The model gave it {indefinite(f['moment.completion'].display)} {{moment.completion}} chance of"
                " reaching {moment.receiver}.",
                *_event(f, "moment.difficulty"),
            )
        ],
    )


def hard_pass(f: Facts) -> Draft:
    # "Of the match": "Hardest pass yet" came back as "Passe le plus difficile" and "Le passage le plus
    # difficile".
    return Draft(
        headline="Hardest pass of the match so far: {moment.passer}",
        casual=[
            _s(
                "{moment.passer} finds {moment.receiver} with the hardest completed pass of the match so far.",
                *_event(f, "moment.difficulty"),
            )
        ],
        analyst=[
            _s(
                f"Difficulty {{moment.difficulty}}: {indefinite(f['moment.completion'].display)}"
                " {moment.completion} chance of arriving.",
                *_event(f, "moment.difficulty"),
            )
        ],
    )


def shot_speed(f: Facts) -> Draft:
    # Headed like the hardest pass, so it can't be taken for a sprint's "hits 33.9 km/h".
    return Draft(
        headline="Fastest shot yet: {moment.shooter}",
        casual=[
            # "Struck it at" came back as "lo acertó" (got it right).
            _s(
                "{moment.shooter}'s shot reached {moment.speed}, the fastest of the match so far.",
                *_event(f, "moment.speed"),
            )
        ],
        analyst=[_s("From {moment.distance}, the shot was {moment.outcome}.", *_event(f, "moment.speed"))],
    )


def sprint(f: Facts) -> Draft:
    return Draft(
        headline="{moment.player} hits {moment.speed}",
        casual=[_s("{moment.player} sprints at {moment.speed}, the fastest of the match so far.")],
        # "Smoothed as tracking providers report it" came back as "lissée au fur et à mesure que".
        analyst=[
            _s("Top speed in the tracking data at {moment.minute}, with the smoothing that tracking providers use.")
        ],
    )


def distance(f: Facts) -> Draft:
    # "Reaches": "passes 10.0 km" read as a passing figure, and translated as "pasa a 10,0 km".
    return Draft(
        headline="{moment.player} reaches {moment.distance}",
        casual=[_s("{moment.player} has covered {moment.distance}.")],
        analyst=[_s("Distance in the tracking data, reached at {moment.minute}.")],
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
        analyst=[_s("{segment.club} have {segment.pass_share} of the passes in that time, and {segment.shots}.")],
    )


def chaos(f: Facts) -> Draft:
    # A verb in the headline: without one, Spanish put it in the past ("tenía el control"). "Lost its
    # shape" came back word for word, and "the longest passing move is 4 passes" as "4 pasadas" and
    # "le coup de passe le plus long".
    if f["segment.longest_move"].value:
        analyst = _s("In that time, neither side strung together more than {segment.longest_move}.")
    else:
        analyst = _s("Neither side completed a pass in that time.")
    return Draft(
        headline="Neither side has control",
        casual=[
            _s(
                "The game has become scrappy: the ball has changed hands {segment.changes} in the last {segment.window}."
            )
        ],
        analyst=[analyst],
    )


def control(f: Facts) -> Draft:
    return Draft(
        headline="{segment.club} in control",
        casual=[_s("{segment.club} have controlled the game for {segment.state_share} of the last {segment.window}.")],
        analyst=[_s("{segment.club} have played {segment.pass_share} of the passes in that time.")],
    )


# A club's share of the passes, worded so the Translator keeps it a share: "have had" and "have made"
# came back as "a réussi" (completed them) and "ha anotado" (scored them), and "passes" without the
# shots beside them as "pasos" and "cols".
def _recap_figures(final: bool = False) -> list[Sentence]:
    have = "finished with" if final else "have"
    return [
        _s(f"{{recap.home_club}} {have} {{recap.home_possession}} of the passes and {{recap.home_shots}}."),
        _s(f"{{recap.away_club}} {have} {{recap.away_possession}} of the passes and {{recap.away_shots}}."),
    ]


def _goals(f: Facts, so_far: str = "") -> str:
    """The goals' heading: "Goal" for one, "Goals" for more."""
    return f"{'Goal' if f['recap.goal_count'].value == 1 else 'Goals'}{so_far}: {{recap.goals}}."


def recap(f: Facts) -> Draft:
    casual = [_s("{recap.score_line} at {recap.when}.", *_event(f, "recap.score_line"))]
    if "recap.goals" in f:
        casual.append(_s(_goals(f)))
    return Draft(
        headline="{recap.label}: {recap.score_line}",
        casual=casual,
        analyst=_recap_figures(final=f["recap.label"].value == "Final score"),
    )


def catch_up(f: Facts) -> Draft:
    """What a viewer joining mid-match missed. The score line stays out: the scoreboard beside it shows it."""
    if "recap.goals" in f:
        casual = [_s(_goals(f, " so far"))]
    else:
        casual = [_s("No goals so far.", *_event(f, "recap.to"))]
    return Draft(headline="What you missed, up to {recap.to}", casual=casual, analyst=_recap_figures())


def correction(f: Facts) -> Draft:
    """The new credit first, and the old one in a sentence of its own: after "not" or in a bracket
    ("not Jory Penhallow (own goal)") it read aloud, and in translation, as if it were the new
    scorer's. The reason is given once, without the kind of review it names."""
    events = _event(f, "correction.after")
    if "correction.own_goal_before" in f:
        # A possessive, which needs no article before the name and kept "de Jory Penhallow" in
        # translation, where "an own goal by" came back as "registrado por" (recorded by).
        before = _s("It was originally recorded as {correction.before}'s own goal.", *events)
    else:
        before = _s("It was originally credited to {correction.before}.", *events)
    return Draft(
        headline="Corrected: {correction.after}",
        casual=[_s("The {correction.minute} goal is now credited to {correction.after}.", *events), before],
        analyst=[_s("The data provider's reason: {correction.why}.", *events)],
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
