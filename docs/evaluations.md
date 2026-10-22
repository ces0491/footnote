# Agent evaluations

How well the agents word the showcase match's cards, measured on every card an agent drafts. Each
case is a job the agents service gets in a replay: every card from kick-off, the 81st-minute goal
again after its correction, and the catch-up that opens a replay from 23', 31', 60' and 81'. The
writer runs as it does in the service: the same instructions, the match tools over MCP, and code's
checks with one revision ([insights.md](insights.md#the-agents)).

The checks make sure every figure and name came from code. The evaluators here judge some of what
the checks can't. Four are code (`src/footnote/evals/judges.py`), and each is a rough test: whether
the card has the surname of who it is about, whether each of a short list of claims made in words
(an equaliser, an own goal, a goal ruled out and a few more) has a fact of its kind among the
writer's facts, whether the casual line is more than the template's reworded, and whether a number
fact takes up both lines. None of them can tell whose a claim is, so a card that gives the right
words to the wrong player or moment passes all four. The fifth is a
model's judgement: Azure AI Evaluation's groundedness evaluator, on the same Foundry deployment,
reads each card against the facts its writer was given and scores it from 1 to 5, passing at 3
(`src/footnote/evals/groundedness.py`). It catches a sentence that contradicts the facts, such as
"the only shot of the match" when the match has had three, but it is lenient: in the runs of 21
October it scored 4 or 5 a card that gave Varlan's pass the minute of the VAR decision on it, one
that wrote of a handball VAR had found no offence in, and one that said a counter started with the
pass that ended it. Reading the cards stays part of a review.

CI replays the recorded drafts through the current checks and evaluators on every push
(`tests/test_evals.py`), and fails unless three cards in four pass every evaluation and every draft
accepted when recorded is still accepted: a change to the checks or the facts that a recorded draft
no longer passes fails the build. Each part of what the writers are told and shown (the
instructions, the match tools with the templates' wording they return, the writer's workflow) is
named by its version and a fingerprint of its code, as is the model's reasoning effort, and the
recording keeps them, so a change to any of them fails the build too until the evaluations are run
and recorded again. The judge's verdicts are replayed as recorded; a reply from the judge that can't
be read is asked for again, up to three times, before it counts as a fail.

The cards were drafted and judged by `uv run --group evals python -m footnote.evals live --record` on 2026-10-22, against gpt-5-mini (reasoning effort low; prompt 2026-10-22.1+5f67465f84aa, tools 2026-10-22.2+b1c4328e276f, writer 2026-10-21.2+f9570304a5df). This report replays them through the current checks and code evaluators: `uv run python -m footnote.evals replay --report`.

## Results

| | |
| --- | --- |
| Cases | 19 |
| Accepted at the first attempt | 12 |
| Accepted after a revision | 6 |
| Rejected, late or failed: the template stands | 1 |
| Accepted with every evaluation passed | 15 |
| Evaluations passed | 87 of 90 |
| Time to a draft | median 14.4 s, slowest 23.2 s |
| Tokens per card | median 9985 in, 1051 out |
| Cost of the drafts at list prices (the judge's calls aside) | US$0.087 |

## Evaluators

| Evaluator | Passed | What it judges |
| --- | --- | --- |
| names the subject | 18 of 18 | The headline or the casual line has the surname of who the moment is about; a recap's, of every scorer. It looks for the name, not at what the card says about them. |
| claims hold | 18 of 18 | Each claim from a short list that the card makes in words (against the run of play, an equaliser, an own goal, offside, handball, a penalty given or checked for, a goal ruled out, a sending-off, a correction) has a fact of its kind among those its writer was given, whoever that fact is about. |
| adds to the template | 18 of 18 | Fewer than four in five of the casual line's words are in the template's casual line, so a line that only rewords the template fails; one that keeps most of it and adds a clause passes. |
| one line per figure | 16 of 18 | No number fact sits in both lines under the same key, so casual and analyst readers each get something of their own. A minute or a spell's stretch may be in both: they frame the rest. A text fact, such as a score line, isn't counted. |
| grounded | 17 of 18 | A model reads the card against its writer's facts and scores it 1 to 5; it passes at 3. |

## Every case

| Case | Outcome | Headline and casual line | Evaluations |
| --- | --- | --- | --- |
| `pressure-sal-1-318/v1` | rejected, 2 attempts, 20.8 s | casual sentence 1: 'forcing the ball to change hands': the ball changing hands counts both sides losing it, so no side forced it; say how often it changed hands | none |
| `goal-e0391/v1` | accepted, 1 attempt, 17.0 s | **Adeyani scores** Saltmarsh 0–1 Kingsferry: Femi Adeyani finishes at 23' to put Kingsferry ahead. Saltmarsh had been on top for 66% of the 10 minutes before the strike. | all passed |
| `goal-e0532/v1` | accepted, 1 attempt, 23.2 s | **Dellow levels for Saltmarsh** Saltmarsh equalise to restore parity while they had been on top for 10 minutes. | grounded: scored 2.0: Let's think step by step: The response provides the three requested elements — a headline ("Dellow levels for Saltmarsh"), a casual-fan line ("Saltmarsh equalise to restore parity while they had been on top for 10 minutes"), and an analyst line (shot distance 19 m, speed 111.3 km/h, assist by Teo Va |
| `var-e0534/v1` | accepted, 1 attempt, 12.2 s | **VAR: no goal** Saltmarsh's chance to equalise was ruled out after Marco Dellow was offside when Teo Varlan played the pass. The score remains Saltmarsh 0–1 Kingsferry. | all passed |
| `pressure-kin-1-2134/v1` | accepted, 2 attempts, 18.4 s | **Kingsferry pinning Saltmarsh back** The sustained pressure has left Saltmarsh unable to build long moves: the ball changed hands 7 times, Kingsferry's longest sequence was only 3 passes and it produced no shots. | one line per figure: segment.shots in both lines |
| `pressure-sal-1-2440/v1` | accepted, 1 attempt, 13.8 s | **Saltmarsh pinning Kingsferry back** Saltmarsh have forced play into Kingsferry's half for 73% of the last 3 minutes, helping them create 3 shots. | all passed |
| `ht/v1` | accepted, 1 attempt, 10.4 s | **Half-time: Saltmarsh 0–1 Kingsferry** Saltmarsh dominated long spells early on, controlling the ball from 2' and pinning Kingsferry back in the periods that followed. Femi Adeyani put Kingsferry ahead at 23' with a quick counter finished by Femi Adeyani, and a potential equaliser was later ruled out by VAR for offside at 33'. | all passed |
| `pressure-sal-2-1/v1` | accepted, 1 attempt, 16.1 s | **Saltmarsh pinning Kingsferry back** Saltmarsh have kept Kingsferry pinned in their own half for 100% of the last 3 minutes, but that pressure has so far produced no shots. | all passed |
| `goal-e1029/v1` | accepted, 1 attempt, 17.3 s | **Teo Varlan scores** Saltmarsh 1–1 Kingsferry: Teo Varlan equalises with a long-range effort at 52'. | all passed |
| `chaos-2-1108/v1` | accepted, 2 attempts, 17.0 s | **Neither side in control** Play has gone messy, with the ball changing hands 7 times in the last 3 minutes and neither side in control for 51% of that time. | one line per figure: segment.changes in both lines |
| `pressure-sal-2-1342/v1` | accepted, 2 attempts, 17.0 s | **Saltmarsh pinning Kingsferry back** Sustained pressure has left Kingsferry defending for 61% of the last 3 minutes, forcing them into repeated clearances while Saltmarsh pressed on. | all passed |
| `var-e1456/v1` | accepted, 1 attempt, 13.3 s | **VAR: No penalty** No penalty was given for handball by Uche Asatoye, so the score stays Saltmarsh 1–1 Kingsferry. | all passed |
| `goal-e1586/v1` | accepted, 2 attempts, 20.1 s | **Own goal: Jory Penhallow** Kingsferry move into the lead late in the game after an own goal by Jory Penhallow at 81'. | all passed |
| `goal-e1586/v2` | accepted, 1 attempt, 14.2 s | **Femi Adeyani puts Kingsferry ahead** Femi Adeyani puts Kingsferry ahead at 81' with a long-range strike from a counter, giving them the lead late in the match. | all passed |
| `ft/v1` | accepted, 1 attempt, 10.8 s | **Final score: Saltmarsh 1–2 Kingsferry** Saltmarsh 1–2 Kingsferry at full time. Teo Varlan levelled for Saltmarsh at 52', but Femi Adeyani's late counter gave Kingsferry the winner — the 81' goal is now credited to Femi Adeyani, originally recorded as Jory Penhallow. Saltmarsh spent the closing minutes in control but could not find a leveller. | all passed |
| `catchup@23` | accepted, 2 attempts, 14.4 s | **What you missed, up to 22'** Saltmarsh have spent 74% of a spell from 2' in control, a spell that ran for 5 minutes and saw the ball change hands 5 times. Those 3 minutes from 6' saw Saltmarsh pin Kingsferry back for 62% of the time, during which they had 1 shot. | all passed |
| `catchup@31` | accepted, 2 attempts, 13.5 s | **What you missed, up to 30'** Saltmarsh have dominated possession and spent long spells on top, including a spell from 17' when they had 89% of the passes. Kingsferry took the lead at 23' when Femi Adeyani finished a counter move from a pass by Javi Ferrano. | all passed |
| `catchup@60` | accepted, 1 attempt, 9.4 s | **What you missed, up to 59'** Femi Adeyani put Kingsferry ahead at 23' from a pass by Javi Ferrano. A potential equaliser was ruled out by VAR for offside at 33' after a pass from Teo Varlan. Teo Varlan levelled for Saltmarsh at 52' and Saltmarsh have since spent long spells in control and pinning Kingsferry back. | all passed |
| `catchup@81` | accepted, 1 attempt, 14.4 s | **What you missed, up to 80'** Femi Adeyani put Kingsferry ahead at 23', but VAR ruled out a Saltmarsh goal at 33'. Teo Varlan levelled for Saltmarsh at 52', and Saltmarsh have mostly pressed since, with a spell from 46' and another from 68'. VAR also checked a possible penalty at 75' and found no handball. | all passed |
