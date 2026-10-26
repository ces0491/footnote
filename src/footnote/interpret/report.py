"""docs/models.md, written from a fit's saved scores (params/scores.json)."""

from __future__ import annotations

import textwrap

from footnote.interpret.dataset import VALIDATION_MATCHDAYS
from footnote.interpret.difficulty import DEFENDER_SPEED, REACTION
from footnote.interpret.physical import DISTANCE_KM, SPRINT_KMH
from footnote.interpret.state import LABELS, WINDOWS
from footnote.interpret.train import FIT_EVERY, SPELL_SECONDS, STEADY_COST, UNITS

WIDTH = 100

_STATE_NAMES = {
    "balanced": "Balanced",
    "chaos": "Chaos",
    "control:home": "Control, home",
    "control:away": "Control, away",
    "pressure:home": "Pressure, home",
    "pressure:away": "Pressure, away",
    "transition:home": "Break, home",
    "transition:away": "Break, away",
}
_ARCHETYPE_NAMES = {"wing_crossing": "wing crossing", "direct_aerial": "direct aerial"}


def _pct(x: float, digits: int = 1) -> str:
    return f"{100 * x:.{digits}f}%"


def _num(x: float, digits: int = 3) -> str:
    return f"{x:.{digits}f}"


def _thousands(n: int) -> str:
    return f"{n:,}"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def render(scores: dict) -> str:
    meta = scores["meta"]
    d = scores["difficulty"]
    s = scores["state"]
    counts = meta["matches"]
    out: list[str] = []

    def par(text: str) -> None:
        out.append(textwrap.fill(" ".join(text.split()), WIDTH, break_long_words=False, break_on_hyphens=False) + "\n")

    def raw(text: str) -> None:
        out.append(text)

    def bullets(*items: str) -> None:
        out.append(
            "".join(
                textwrap.fill(
                    " ".join(item.split()),
                    WIDTH,
                    initial_indent="- ",
                    subsequent_indent="  ",
                    break_long_words=False,
                    break_on_hyphens=False,
                )
                + "\n"
                for item in items
            )
        )

    raw("# Models\n")
    par(
        "Two models read each match: one rates how hard a pass was, the other estimates the hidden match "
        "state live. This page says what they read, how they were fitted and how well they recover the truth "
        "on matches involving clubs whose playing styles they never saw."
    )
    par(
        f"Generated on {meta['date']} from all {sum(counts.values())} fixtures of the league under seed "
        f"{meta['league_seed']}, in {round(meta['seconds'] / 60)} minutes. Generator fingerprint "
        f"`{meta['generator']}`. Regenerate with `python -m footnote.interpret`, which also writes the fitted "
        "parameters the processor loads (`src/footnote/interpret/params/`); `--report-only` rewrites this page "
        "from the saved scores without fitting."
    )

    raw("## How they are tested\n")
    par(
        "The generator writes an answer key beside every match ([data.md](data.md)): the true chance of every "
        "pass reaching its target, and the true state at every second. The services never read it. The "
        "match-state network is fitted on the true states and scored against them. The pass model is fitted on "
        "whether each pass was completed; its log loss and Brier score below are measured against those "
        "outcomes, and its gap against the true chances."
    )
    archetypes = " and ".join(_ARCHETYPE_NAMES[a] for a in meta["held_out_archetypes"])
    clubs = ", ".join(c.upper() for c in meta["held_out_clubs"])
    par(
        "The split is by playing style. Each club's style is one of seven archetypes plus a little seeded "
        f"noise, so another league seed wouldn't give new styles. Clubs from two archetypes, {archetypes} "
        f"({clubs}), are held out: the {counts['test']} matches involving them are the test set and are used "
        f"for nothing but these scores. The other {counts['fit'] + counts['validate']} matches fit the models. "
        f"The {counts['validate']} of them on matchdays {VALIDATION_MATCHDAYS.start} to "
        f"{VALIDATION_MATCHDAYS.stop - 1} first choose how the state model's output is steadied for display, "
        "then join the final fit."
    )

    # ----- pass difficulty
    o = d["overall"]
    raw("## Pass difficulty\n")
    par(
        "A pass's difficulty is one minus the modelled chance that it reaches its target. The model is a "
        "logistic regression over what the feed and the tracking show as the ball is played:"
    )
    bullets(
        "the pass: where it starts, its length, height and speed, whether it is a cross, a through ball, a "
        "header or a set piece, and whether the passer is under pressure;",
        "its target: where it is, how far forward of the start, and whether the pass enters the box from outside it;",
        "the players around it, from the tracking: how much space the passer and the target have, how many "
        "opponents crowd the target and how near a team-mate is to it, how many opponents stand near the line "
        "of the pass, how much time the best-placed of them would have in hand to cut it out (reacting after "
        f"{REACTION:g} s and closing at {DEFENDER_SPEED:.0f} m/s; a lofted pass can be cut out only near either "
        "end), and how many defenders are goal-side of the target.",
    )
    par(
        "The target is the point the pass's length away from the passer, towards where the intended receiver "
        "stood in the tracking; a cross aims at a fixed point in front of goal, since a cross names its "
        "receiver only when it reaches one. The feed's end point would give the outcome away: a pass that was "
        "cut out ends where it was cut out. Nothing about the passer or the club goes in, so a rating "
        "describes only the situation."
    )
    par(f"On the {_thousands(d['test_passes'])} passes in the test matches (lower is better in every column):")
    raw(
        _table(
            ["Model", "Log loss", "Brier score", "Average gap from the true chance"],
            [
                [name, _num(r["log_loss"]), _num(r["brier"]), "0" if r is o["truth"] else _num(r["mae_truth"])]
                for name, r in (
                    ("Every pass at the training completion rate", o["constant"]),
                    ("The pass and its target, without the players around it", o["feed_only"]),
                    ("With the players around it: the live model", o["full"]),
                    ("The answer key's true chances", o["truth"]),
                )
            ],
        )
    )
    par(
        "The true chances set the floor: knowing them exactly still leaves each pass's outcome to chance. The "
        "model leaves out by design the passer's and receiver's skill, the clubs' strength and the hidden match "
        "state, all of which move the true chance."
    )
    par("Calibration on the test passes, in tenths by the model's chance:")
    raw(
        _table(
            ["Model's chance (average)", "Passes", "Completed", "True chance (average)"],
            [
                [_pct(c["predicted"]), _thousands(c["passes"]), _pct(c["observed"]), _pct(c["truth"])]
                for c in d["calibration"]
            ],
        )
    )
    par("By kind of pass (the processor doesn't rate throw-ins live; they're scored here all the same):")
    raw(
        _table(
            [
                "Kind",
                "Passes",
                "Completed",
                "Model's average chance",
                "Gap from the true chance",
                "Log loss",
                "Log loss of the true chances",
            ],
            [
                [
                    name,
                    _thousands(k["passes"]),
                    _pct(k["observed"]),
                    _pct(k["predicted"]),
                    _num(k["model"]["mae_truth"]),
                    _num(k["model"]["log_loss"]),
                    _num(k["truth"]["log_loss"]),
                ]
                for name, k in d["kinds"].items()
            ],
        )
    )
    held, opp = d["sides"]["held_out"], d["sides"]["opponents"]
    par(
        f"Passes by the held-out clubs themselves ({_thousands(held['passes'])}) completed "
        f"{_pct(held['observed'])} against a modelled {_pct(held['predicted'])}; their opponents' "
        f"({_thousands(opp['passes'])}) completed {_pct(opp['observed'])} against {_pct(opp['predicted'])}."
    )

    # ----- match state
    t = s["test"]
    live = t["live"]
    raw("## Match state\n")
    par(
        "At any moment the generator has the match in one of eight states: one side in control, one side "
        "pinning the other back (pressure), one side breaking at speed (transition), chaos, or balanced. The "
        "feed never names them."
    )
    windows = ", ".join(f"{w}" for w in WINDOWS[:-1]) + f" and {WINDOWS[-1]} seconds"
    par(
        f"Every second gets a vector of evidence over windows of {windows} that reach {s['lag']} seconds "
        "past it. From the events: each side's share of the ball, where it has the ball and wins it back, "
        "how fast it moves the ball forward, its passing, crosses, shots, long balls, fouls and pressing, and "
        "how often the ball changes hands. From the tracking: how high each side's block stands, where its "
        "back and front lines are, how wide it spreads and how fast its players are moving. How recently "
        "each side won the ball and how far it has taken it since. And the match situation: the minute, the "
        "time since the half began or the last goal (counted up to two minutes), and the goal difference, "
        "capped at three either way, with a copy of it weighted from nothing at the hour to full at the 90th "
        "minute."
    )
    if s["smoothing"]:
        steadied = (
            f"Its output is steadied by an exponential average, keeping {s['smoothing']:.0%} of the running "
            "average each second and restarting it at each kick-off and after each goal."
        )
    else:
        steadied = "Its output is used as it comes: the validation matches chose no smoothing (below)."
    par(
        f"A small neural network, one hidden layer of {UNITS} tanh units under a softmax, turns the evidence "
        f"into the chance of each state. It is fitted on one second in every {FIT_EVERY} from the training "
        "matches, and on each of those seconds again with home and away swapped, so each state, home or away, "
        f"is learned from both sides' play. {steadied} The live estimate is the state a viewer is shown: it "
        f"changes only once another state has led the network's estimate for {s['hold']} seconds in a row. A "
        "break, which lasts seconds, is shown and dropped at once, and at each kick-off and after each goal "
        f"the shown state moves at once to the state in the lead. It all runs {s['lag']} seconds behind play: "
        f"the estimate for a second is ready once the next {s['lag']} seconds of events are in."
    )
    par(
        f"On every second of the {s['test_matches']} test matches ({_thousands(live['seconds'])} seconds). "
        'Macro F1 averages the eight states equally, so the rare ones count; "side on top" only asks whether '
        "the home side, the away side or neither holds a state of its own:"
    )
    raw(
        _table(
            ["Method", "Seconds right", "Macro F1", "Side on top right"],
            [
                [name, _pct(t[key]["accuracy"]), _num(t[key]["macro_f1"], 2), _pct(t[key]["on_top"])]
                for name, key in (
                    ('Always "balanced"', "always_balanced"),
                    ("Control for a side with 60% of the ball over two minutes, otherwise balanced", "possession_rule"),
                    ("The network alone, second by second", "classifier"),
                    ("The live estimate, as shown", "live"),
                )
            ],
        )
    )
    par("The live estimate state by state:")
    raw(
        _table(
            ["State", "Share of seconds", "Caught (recall)", "Right when named (precision)"],
            [
                [
                    _STATE_NAMES[label],
                    _pct(s["true_shares"][i]),
                    _pct(live["recall"][label], 0),
                    _pct(live["precision"][label], 0),
                ]
                for i, label in enumerate(LABELS)
            ],
        )
    )
    par("Where the seconds go, as a share of each true state's seconds (rows: true state; columns: the live estimate):")
    raw(
        _table(
            ["True state", "Bal", "Chaos", "Ctrl H", "Ctrl A", "Pres H", "Pres A", "Break H", "Break A"],
            [
                [_STATE_NAMES[label]] + [f"{100 * v / max(sum(row), 1):.0f}" for v in row]
                for label, row in zip(LABELS, live["confusion"], strict=True)
            ],
        )
    )
    par(
        f"Spells caught. A control, pressure or chaos spell of {SPELL_SECONDS} seconds or more counts as caught "
        "when the live estimate names it for at least half its seconds; a break counts when any of its seconds "
        "is named as that side's break:"
    )
    det = s["detection"]
    raw(
        _table(
            ["Spell", "Caught", "Of"],
            [
                [
                    name,
                    f"{_thousands(det[kind]['caught'])} ({_pct(det[kind]['caught'] / max(det[kind]['spells'], 1), 0)})",
                    _thousands(det[kind]["spells"]),
                ]
                for kind, name in (
                    ("control", "Control"),
                    ("pressure", "Pressure"),
                    ("chaos", "Chaos"),
                    ("transition", "Break"),
                )
            ],
        )
    )
    changes = s["changes_per_match"]
    par(
        f"The shown state changes {changes['live']:.0f} times in an average test match; the true state changes "
        f"{changes['true']:.0f} times."
    )
    par("By held-out style (a match between the two styles counts in both rows):")
    raw(
        _table(
            ["Matches involving", "Matches", "Seconds right", "Macro F1", "Side on top right"],
            [
                [
                    f"{_ARCHETYPE_NAMES[name]} clubs",
                    str(r["matches"]),
                    _pct(r["accuracy"]),
                    _num(r["macro_f1"], 2),
                    _pct(r["on_top"]),
                ]
                for name, r in s["by_archetype"].items()
            ],
        )
    )
    v = s["validation"]
    par(
        f"The smoothing and the hold were chosen on the {v['matches']} validation matches: of the settings "
        f"whose macro F1 stayed within {STEADY_COST} of the best, the one whose shown state changes least often. "
        "These matches share the training styles, so their scores run higher than the test set's."
    )
    chosen = (v["chosen"]["smoothing"], v["chosen"]["hold"])
    raw(
        _table(
            ["Weight kept each second", "Hold", "Seconds right", "Macro F1", "Shown state changes per match"],
            [
                [
                    str(row["smoothing"]),
                    f"{row['hold']} s" + (" (chosen)" if (row["smoothing"], row["hold"]) == chosen else ""),
                    _pct(row["accuracy"]),
                    _num(row["macro_f1"], 2),
                    f"{row['changes_per_match']:.0f}",
                ]
                for row in v["tuning"]
            ],
        )
    )
    par(f"The true state changes {v['true_changes_per_match']:.0f} times in an average validation match.")

    sc = s["showcase"]
    raw("### The showcase match\n")
    par(
        "The showcase match ([experience.md](experience.md)) involves two training styles, so it isn't part of "
        f"the test. Over the whole match the live estimate is right for {_pct(sc['overall']['accuracy'])} of "
        "seconds. For the beats the story names a state for:"
    )
    raw(
        _table(
            ["Beat", "State", "Its share of the beat, true", "Its share, live estimate", "Seconds right"],
            [
                [
                    b["beat"],
                    _STATE_NAMES[b["state"]],
                    _pct(b["truth_share"], 0),
                    _pct(b["model_share"], 0),
                    _pct(b["agreement"], 0),
                ]
                for b in sc["beats"]
            ],
        )
    )
    caught = sc["first_goal_break"]
    if caught:
        verdict = "caught" if all(caught) else "missed" if not any(caught) else "partly caught"
        par(f"The break that ended in the first goal is {verdict} by the live estimate.")

    raw("## Tags from the tracking\n")
    par(
        f"No model is involved. A sprint tag marks a player going above {SPRINT_KMH:.0f} km/h, with speed "
        "averaged over the trailing second, and is reported with its peak once the player slows below the "
        f"threshold again. A distance tag marks a player passing {DISTANCE_KM:.0f} km covered."
    )
    return "\n".join(out).rstrip() + "\n"
