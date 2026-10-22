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

The cards were drafted and judged by `uv run --group evals python -m footnote.evals live --record` on 2026-10-22, against gpt-5-mini (reasoning effort low; prompt 2026-10-22.3+4b5615fb2eb2, tools 2026-10-22.3+f6fba1489be1, writer 2026-10-22.1+e6aec247c277). This report replays them through the current checks and code evaluators: `uv run python -m footnote.evals replay --report`.

## Results

| | |
| --- | --- |
| Cases | 17 |
| Accepted at the first attempt | 12 |
| Accepted after a revision | 4 |
| Rejected, late or failed: the template stands | 1 |
| Accepted with every evaluation passed | 15 |
| Evaluations passed | 79 of 80 |
| Time to a draft | median 16.6 s, slowest 21.0 s |
| Tokens per card | median 9905 in, 1225 out |
| Cost of the drafts at list prices (the judge's calls aside) | US$0.082 |

## Evaluators

| Evaluator | Passed | What it judges |
| --- | --- | --- |
| names the subject | 16 of 16 | The headline or the casual line has the surname of who the moment is about; a recap's, of every scorer. It looks for the name, not at what the card says about them. |
| claims hold | 16 of 16 | Each claim from a short list that the card makes in words (against the run of play, an equaliser, an own goal, offside, handball, a penalty given or checked for, a goal ruled out, a sending-off, a correction) has a fact of its kind among those its writer was given, whoever that fact is about. |
| adds to the template | 16 of 16 | Fewer than four in five of the casual line's words are in the template's casual line, so a line that only rewords the template fails; one that keeps most of it and adds a clause passes. |
| one line per figure | 15 of 16 | No number fact sits in both lines under the same key, so casual and analyst readers each get something of their own. A minute or a spell's stretch may be in both: they frame the rest. A text fact, such as a score line, isn't counted. |
| grounded | 16 of 16 | A model reads the card against its writer's facts and scores it 1 to 5; it passes at 3. |

## Every case

| Case | Outcome | Headline and casual line | Evaluations |
| --- | --- | --- | --- |
| `pressure-sal-1-318/v1` | accepted, 2 attempts, 21.0 s | **Saltmarsh pinning Kingsferry back** Saltmarsh have kept Kingsferry under sustained pressure, keeping play in Kingsferry's half and creating chances from long spells of possession. | all passed |
| `goal-e0391/v1` | accepted, 1 attempt, 16.6 s | **Femi Adeyani opens the scoring** Saltmarsh 0–1 Kingsferry: Femi Adeyani finishes a counter to take the lead. Saltmarsh had been on top for 66% of the 10 minutes before the goal. | all passed |
| `goal-e0532/v1` | accepted, 1 attempt, 18.4 s | **Marco Dellow equalises** Saltmarsh are level after Marco Dellow's strike, making it Saltmarsh 1–1 Kingsferry at 31'. | all passed |
| `pressure-kin-1-2134/v1` | accepted, 1 attempt, 11.7 s | **Kingsferry pinning Saltmarsh back** Kingsferry have kept Saltmarsh pinned in their own half for 61% of the last 3 minutes, with the ball changing hands 7 times. | all passed |
| `pressure-sal-1-2440/v1` | accepted, 1 attempt, 15.8 s | **Saltmarsh pinning Kingsferry back** Saltmarsh have spent 73% of the last 3 minutes pinning Kingsferry back, leaving Kingsferry under pressure and creating 3 shots. | all passed |
| `ht/v1` | accepted, 2 attempts, 17.8 s | **Half-time: Saltmarsh 0–1 Kingsferry** Saltmarsh 0–1 Kingsferry at half-time. Saltmarsh dominated early, with a spell from 2' lasting 5 minutes in which they had 74%, but Kingsferry took the lead from a counter move when Javi Ferrano played to Femi Adeyani, who scored at 23'. | all passed |
| `pressure-sal-2-1/v1` | accepted, 1 attempt, 11.2 s | **Saltmarsh pinning Kingsferry back** Saltmarsh have kept Kingsferry pinned in their own half for 100% of the last 3 minutes, with the ball changing hands 6 times. | all passed |
| `goal-e1029/v1` | accepted, 1 attempt, 17.4 s | **Teo Varlan levels** Saltmarsh 1–1 Kingsferry: Teo Varlan equalised at 52', capping a spell in which Saltmarsh were pinning Kingsferry back for 65% of the last 6 minutes. | all passed |
| `chaos-2-1108/v1` | accepted, 2 attempts, 13.4 s | **Game in disorder** The match has gone scrappy, with the ball changing hands 7 times across the last 3 minutes. | all passed |
| `pressure-sal-2-1342/v1` | accepted, 1 attempt, 15.3 s | **Saltmarsh pinning Kingsferry back** Saltmarsh have kept Kingsferry pinned in their own half for 61% of the last 3 minutes, producing 2 shots in that spell. | one line per figure: segment.shots in both lines |
| `goal-e1586/v1` | accepted, 1 attempt, 17.4 s | **Own goal: Jory Penhallow** Saltmarsh 1–2 Kingsferry: an own goal by Jory Penhallow at 81', awarded after a counter finished by Femi Adeyani. | all passed |
| `goal-e1586/v2` | accepted, 1 attempt, 17.7 s | **Femi Adeyani scores** A counter finished by Femi Adeyani gives Kingsferry the lead at 81'. | all passed |
| `ft/v1` | accepted, 1 attempt, 10.4 s | **Final score: Saltmarsh 1–2 Kingsferry** A tight game where Saltmarsh dominated possession and created most of the pressure but fell behind when Femi Adeyani struck for Kingsferry at 23', before Teo Varlan levelled for Saltmarsh at 52' and Femi Adeyani regained the lead for Kingsferry late on at 81'. The 81' goal, originally recorded as Jory Penhallow's own goal, is now credited to Femi Adeyani. | all passed |
| `catchup@23` | accepted, 2 attempts, 14.8 s | **What you missed, up to 22'** No goals so far. Saltmarsh have done most of the attacking since early on, a spell from 2' when they were in control for 74% of the 5 minutes and the ball changed hands 5 times in that stretch. They also pinned Kingsferry back in a spell from 6', holding 62% of the 3 minutes. | all passed |
| `catchup@31` | rejected, 2 attempts, 17.7 s | casual sentence 2: 'a 89.1' once filled in; write 'an' before it | none |
| `catchup@60` | accepted, 1 attempt, 11.3 s | **What you missed, up to 59'** Saltmarsh were on top in spells early on before Femi Adeyani put Kingsferry ahead from a long-range strike at 23'. A goal was then ruled out at 33' after VAR found Marco Dellow offside from Teo Varlan's pass, so the score stayed the same. Teo Varlan levelled for Saltmarsh at 52'. | all passed |
| `catchup@81` | accepted, 1 attempt, 16.6 s | **What you missed, up to 80'** Saltmarsh were on top from 2', controlling 74% of a spell of 5 minutes. Kingsferry took the lead when Femi Adeyani scored at 23', and a later VAR check ruled out a Saltmarsh goal at 33'. Saltmarsh levelled through Teo Varlan at 52' and have since pressed for a winner. | all passed |
