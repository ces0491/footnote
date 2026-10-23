# Agent evaluations

How well the agents word the showcase match's cards. Each case is a job the agents service gets in
a replay: every card the agents draft in a replay from kick-off, the 81st-minute goal again after
its correction, and the catch-up that opens a replay from 23', 31', 60' and 81'. The writer runs as
it does in the service: the same instructions, the match tools over MCP, and code's checks with one
revision ([insights.md](insights.md#the-agents)).

The checks refuse a draft that types a figure or names someone the facts don't. The evaluators
judge some of what the checks can't. Four are rough tests in code, described in the table below
(`src/footnote/evals/judges.py`). None of them can tell whose a claim is, so a card that gives the
right words to the wrong player or moment passes all four. The fifth is Azure AI Evaluation's
groundedness evaluator, on the same Foundry deployment (`src/footnote/evals/groundedness.py`). It
catches a sentence that contradicts the facts, such as "the only shot of the match" when the match
has had three, but it is lenient. In earlier recordings, from 21 October, whose cards aren't in the
tables below, it scored 4 or 5 a card that gave Varlan's pass the minute of the VAR decision on it,
one that wrote of a handball VAR had found no offence in, and one that said a counter started with
the pass that ended it. Reading the cards stays part of a review.

CI (`tests/test_evals.py`) replays the recorded drafts through the current checks and evaluators on
each push to main and each pull request. It fails unless three cards in four pass every evaluation,
every draft accepted when recorded is still accepted, and this page is what the replay writes. A
change to the checks or the facts that a recorded draft no longer passes fails the build. The
recording keeps the version and a fingerprint of the code of each part of what the writers are told
and shown (the instructions, the match tools with the templates' wording they return, the writer's
workflow), and the model's reasoning effort, so a change to any of them fails the build too until
the evaluations are recorded again. The judge's verdicts are replayed as recorded. When a reply
from the judge can't be read, the judge is asked again, up to three tries in all, before the card
counts as a fail.

The cards were drafted and judged by `uv run --group evals python -m footnote.evals live --record` on 2026-10-23, against gpt-5-mini (reasoning effort low; prompt 2026-10-22.3+4b5615fb2eb2, tools 2026-10-23.1+910c198d644c, writer 2026-10-22.1+c00cec71c0ca). This report replays them through the current checks and code evaluators: `uv run python -m footnote.evals replay --report`.

## Results

| | |
| --- | --- |
| Cases | 17 |
| Accepted at the first attempt | 11 |
| Accepted after a revision | 6 |
| Rejected, late or failed: the template stands | 0 |
| Accepted with every evaluation passed | 14 |
| Evaluations passed | 82 of 85 |
| Time to a draft | median 15.5 s, slowest 23.8 s |
| Tokens per card | median 10356 in, 973 out |
| Cost of the drafts at list prices (the judge's calls aside) | US$0.080 |

## Evaluators

| Evaluator | Passed | What it judges |
| --- | --- | --- |
| names the subject | 17 of 17 | The headline or the casual line has the surname of who the moment is about; a recap's, of every scorer. It only looks for the name: what the card says about them goes unjudged. |
| claims hold | 17 of 17 | Each claim from a short list that the card makes in words (against the run of play, an equaliser, an own goal, offside, handball, a penalty given or checked for, a goal ruled out, a sending-off, a correction) has a fact of its kind among those its writer was given, whoever that fact is about. |
| adds to the template | 16 of 17 | Fewer than four in five of the casual line's words are in the template's casual line, so a line made mostly of the template's words fails, however they're rearranged; one that keeps most of the template and adds a clause of its own passes. |
| one line per figure | 16 of 17 | No number fact sits in both lines under the same key, so casual and analyst readers each get something of their own. A minute or a spell's stretch may be in both: they frame the rest. A text fact, such as a score line, isn't counted. |
| grounded | 16 of 17 | A model reads the card against its writer's facts and scores it 1 to 5; it passes at 3. |

## Cases

| Case | Outcome | Headline and casual line | Evaluations |
| --- | --- | --- | --- |
| `pressure-sal-1-318/v1` | accepted, 2 attempts, 23.8 s | **Saltmarsh pinning Kingsferry back** Saltmarsh have forced Kingsferry deep into their own half for much of the last 3 minutes, winning territory and creating pressure that produced 1 shot. | one line per figure: segment.shots in both lines |
| `goal-e0391/v1` | accepted, 1 attempt, 23.4 s | **Femi Adeyani scores** Kingsferry take the lead as Femi Adeyani finishes a counter, while Saltmarsh had been on top for 66% of the 10 minutes. | all passed |
| `goal-e0532/v1` | accepted, 1 attempt, 18.7 s | **Dellow levels for Saltmarsh** Saltmarsh equalise through Marco Dellow at 31', cancelling Kingsferry's lead and resetting the game. | all passed |
| `pressure-kin-1-2134/v1` | accepted, 1 attempt, 11.4 s | **Kingsferry pinning Saltmarsh back** Kingsferry are sustaining pressure, keeping Saltmarsh pinned for 61% of the last 3 minutes. | all passed |
| `pressure-sal-1-2440/v1` | accepted, 1 attempt, 8.0 s | **Saltmarsh pinning Kingsferry back** Saltmarsh have kept Kingsferry pinned in their own half for 73% of the last 3 minutes, creating 3 shots. | adds to the template: 88% of its words are the template's |
| `ht/v1` | accepted, 1 attempt, 11.7 s | **Half-time: Saltmarsh 0–1 Kingsferry** Saltmarsh controlled large spells early, but Kingsferry took the lead when Femi Adeyani scored at 23'. A later VAR check ruled out a goal for Marco Dellow and Saltmarsh were pressing again before half-time. | all passed |
| `pressure-sal-2-1/v1` | accepted, 1 attempt, 15.1 s | **Saltmarsh pinning Kingsferry back** Saltmarsh are on top and have kept Kingsferry pinned for 100% of the last 3 minutes. | all passed |
| `goal-e1029/v1` | accepted, 2 attempts, 17.9 s | **Varlan levels it** Saltmarsh equalise with a 21 m strike after they had been on top for 100% of the previous 6 minutes. | all passed |
| `chaos-2-1108/v1` | accepted, 2 attempts, 19.0 s | **Neither side has control** Play has turned scrappy: the ball changed hands 7 times in the last 3 minutes, so neither side has been able to establish control. | all passed |
| `pressure-sal-2-1342/v1` | accepted, 2 attempts, 19.1 s | **Saltmarsh pinning Kingsferry back** Saltmarsh have kept Kingsferry pinned in their own half for 61% of the last 3 minutes, creating 2 shots and a longest passing run of 20 passes. | all passed |
| `goal-e1586/v1` | accepted, 1 attempt, 15.5 s | **Own goal: Jory Penhallow** Kingsferry take the lead late after an own goal by Jory Penhallow at 81'. | all passed |
| `goal-e1586/v2` | accepted, 2 attempts, 18.9 s | **Adeyani scores** Saltmarsh 1–2 Kingsferry: Femi Adeyani struck from a counter at 81'. They had been on top for only 2% of the last 10 minutes, so it is a decisive, late break. | all passed |
| `ft/v1` | accepted, 1 attempt, 10.9 s | **Final score: Saltmarsh 1–2 Kingsferry** Saltmarsh 1–2 Kingsferry at full time. Femi Adeyani put Kingsferry ahead at 23', Teo Varlan levelled for Saltmarsh at 52' and Femi Adeyani restored Kingsferry's lead at 81'. The 81' goal, originally recorded as Jory Penhallow's own goal, is now credited to Femi Adeyani. | all passed |
| `catchup@23` | accepted, 1 attempt, 8.7 s | **What you missed, up to 22'** Saltmarsh had a spell from 2' and spent 74% of the following 5 minutes in control, completing 44 passes as their longest move. They then pinned Kingsferry back in a spell from 6' that lasted 3 minutes with 62% of that stretch in their favour. There have been no goals so far. | all passed |
| `catchup@31` | accepted, 1 attempt, 9.9 s | **What you missed, up to 30'** 2' and 17' saw Saltmarsh dominate possession, but Femi Adeyani scored for Kingsferry at 23' with a 21 m shot after a pass from Javi Ferrano. | all passed |
| `catchup@60` | accepted, 2 attempts, 18.2 s | **What you missed, up to 59'** Saltmarsh had most of the play early on, but Femi Adeyani put Kingsferry ahead from Javi Ferrano's pass at 23'. A VAR check later ruled a Saltmarsh shot out for offside, and then Teo Varlan levelled for Saltmarsh at 52'. | all passed |
| `catchup@81` | accepted, 1 attempt, 10.4 s | **What you missed, up to 80'** A quick start from Saltmarsh gave them long spells of control before Femi Adeyani put Kingsferry ahead at 23', a decision that stood after VAR checked an incident at 33', and Saltmarsh levelled when Teo Varlan scored at 52'. Since the equaliser Saltmarsh have pressed hard, pinning Kingsferry back in several spells late on. | grounded: scored 2.0: Let's think step by step: The response is clearly grounded in the provided context — it references the match time (up to 80'), the two goals (Femi Adeyani 23' and Teo Varlan 52'), the passing shares (Saltmarsh 64% / Kingsferry 36%) and the shot counts (23 vs 2), and it summarises Saltmarsh pressing  |
