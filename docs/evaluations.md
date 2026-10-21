# Agent evaluations

How well the agents word the showcase match's cards, measured on every card an agent drafts. Each
case is a job the agents service gets in a replay: every card from kick-off, the 81st-minute goal
again after its correction, and the catch-up that opens a replay from 23', 31', 60' and 81'. The
writer runs as it does in the service: the same instructions, the match tools over MCP, and code's
checks with one revision ([insights.md](insights.md#the-agents)).

The checks make sure every figure and name came from code. The evaluators here judge what the checks
can't. Four are code (`src/footnote/evals/judges.py`): whether a card names who it is about, whether
what it claims in words rests on a fact, whether it says more than the template did, and whether it
spends both lines on one figure. The fifth is a model's judgement: Azure AI Evaluation's
groundedness evaluator, on the same Foundry deployment, reads each card against the facts its
writer was given and scores it from 1 to 5, passing at 3 (`src/footnote/evals/groundedness.py`).
It catches a sentence that contradicts the facts, such as "the only shot of the match" when the
match has had three, but it is lenient: in the runs of 21 October it scored 4 or 5 a card that gave
Varlan's pass the minute of the VAR decision on it, and one that wrote of a handball VAR had found
no offence in. Reading the cards stays part of a review.

CI replays the recorded drafts through the current checks and evaluators on every push
(`tests/test_evals.py`), and fails unless three cards in four pass every evaluation: a change to the
checks, the facts or the tools that a recorded draft no longer passes fails the build, and so does a
change to the agents' instructions, tools or workflow until the evaluations are run and recorded
again. The judge's verdicts are replayed as recorded.

The cards were drafted and judged by `uv run --group evals python -m footnote.evals live --record` on 2026-10-21, against gpt-5-mini (reasoning effort low; prompt 2026-10-21.1, tools 2026-10-21.1, writer 2026-10-21.1). This report replays them through the current checks and code evaluators: `uv run python -m footnote.evals replay --report`.

## Results

| | |
| --- | --- |
| Cases | 20 |
| Accepted at the first attempt | 15 |
| Accepted after a revision | 5 |
| Rejected, late or failed: the template stands | 0 |
| Accepted with every evaluation passed | 16 |
| Evaluations passed | 96 of 100 |
| Time to a draft | median 13.1 s, slowest 24.7 s |
| Tokens per card | median 6172 in, 846 out |
| Cost of the drafts at list prices (the judge's calls aside) | US$0.075 |

## Evaluators

| Evaluator | Passed | What it judges |
| --- | --- | --- |
| names the subject | 20 of 20 | The headline or the casual line names who the moment is about; a recap, every scorer. |
| claims hold | 20 of 20 | Every claim the card makes in words rests on a fact its writer was given. |
| adds to the template | 18 of 20 | The casual line is more than the template's in other words: most of its words are its own, which is the agent's reason to be there. |
| one line per figure | 19 of 20 | No figure takes up both lines, so casual and analyst readers each get something of their own. A minute or a spell's stretch may be in both: they frame the rest. |
| grounded | 19 of 20 | A model reads the card against its writer's facts and scores it 1 to 5; it passes at 3. |

## Every case

| Case | Outcome | Headline and casual line | Evaluations |
| --- | --- | --- | --- |
| `pressure-sal-1-318/v1` | accepted, 1 attempt, 16.9 s | **Saltmarsh pinning Kingsferry back** Saltmarsh are keeping Kingsferry under pressure and have forced them to sit deep for 62% of the last 3 minutes. | all passed |
| `goal-e0391/v1` | accepted, 1 attempt, 16.0 s | **Adeyani gives Kingsferry lead** Saltmarsh 0–1 Kingsferry: Femi Adeyani scores at 23'. Saltmarsh had been on top for 66% of the 10 minutes before, so the goal came against the run of play. | all passed |
| `goal-e0532/v1` | accepted, 1 attempt, 13.0 s | **Dellow levels for Saltmarsh** Saltmarsh equalise as Marco Dellow finishes from 19 m after a pass from Teo Varlan. | one line per figure: moment.shot_distance in both lines |
| `var-e0534/v1` | accepted, 1 attempt, 9.2 s | **VAR: No goal** Saltmarsh remain behind as the goal is ruled out after Marco Dellow was offside when Teo Varlan played the pass. It stays Saltmarsh 0–1 Kingsferry. | adds to the template: 82% of its words are the template's |
| `pressure-kin-1-2134/v1` | accepted, 1 attempt, 10.1 s | **Kingsferry pinning Saltmarsh back** Kingsferry are keeping Saltmarsh pinned in their own half, controlling 61% of the last 3 minutes. | all passed |
| `pressure-sal-1-2440/v1` | accepted, 1 attempt, 11.6 s | **Saltmarsh pinning Kingsferry back** Saltmarsh are forcing Kingsferry deep and keeping them under sustained pressure for 73% of the last 3 minutes. | all passed |
| `ht/v1` | accepted, 2 attempts, 17.6 s | **Half-time: Saltmarsh 0–1 Kingsferry** Saltmarsh have largely controlled the game before the break, dominating possession and pinning Kingsferry back in long spells, then Femi Adeyani scored on a counter at 23'. Marco Dellow thought he had levelled it but VAR ruled the finish out for offside when Teo Varlan played the pass, so the score remains Saltmarsh 0–1 Kingsferry. | all passed |
| `pressure-sal-2-1/v1` | accepted, 1 attempt, 12.8 s | **Saltmarsh pinning Kingsferry back** That pressure means Saltmarsh have kept Kingsferry pinned for 100% of the last 3 minutes. | all passed |
| `goal-e1029/v1` | accepted, 2 attempts, 20.5 s | **Teo Varlan scores** Teo Varlan equalise the match, bringing Saltmarsh 1–1 Kingsferry and halting Kingsferry's earlier spell of control. | grounded: scored 2.0: Let's think step by step: The response attempts to produce a live-graphics card and includes a short headline and lines that could serve casual fans and analysts. It correctly names the scorer (Teo Varlan), states it was an equaliser making the score Saltmarsh 1–1, and gives accurate shot details (2 |
| `chaos-2-1108/v1` | accepted, 1 attempt, 8.7 s | **Neither side in control** Play has become untidy, with the ball changing hands 7 times in the last 3 minutes, so neither team can hold sustained possession. | all passed |
| `pressure-sal-2-1342/v1` | accepted, 2 attempts, 16.2 s | **Saltmarsh pinning Kingsferry back** Saltmarsh are keeping Kingsferry under pressure for 61% of the last 3 minutes, restricting their ability to build attacks. | all passed |
| `var-e1456/v1` | accepted, 1 attempt, 11.2 s | **VAR: No penalty** Saltmarsh remain level at Saltmarsh 1–1 Kingsferry after VAR found no penalty for a handball by Uche Asatoye. | all passed |
| `goal-e1586/v1` | accepted, 1 attempt, 19.6 s | **Own goal gives Kingsferry lead** Jory Penhallow's own goal hands Kingsferry the lead at 81', after a counter and a shot from Femi Adeyani. | all passed |
| `goal-e1586/v2` | accepted, 1 attempt, 12.1 s | **Femi Adeyani gives Kingsferry lead** Kingsferry take the lead late in the match as Femi Adeyani finishes a counter at 81'. | all passed |
| `correction-e1586-v2/v1` | accepted, 1 attempt, 9.0 s | **Corrected: Femi Adeyani** The 81' goal is now credited to Femi Adeyani, not Jory Penhallow (own goal). | adds to the template: 100% of its words are the template's |
| `ft/v1` | accepted, 1 attempt, 13.9 s | **Insight: full time** Saltmarsh 1–2 Kingsferry at full time. Kingsferry broke the pattern with a counter finished by Femi Adeyani at 23', despite Saltmarsh controlling large spells beforehand. Teo Varlan levelled at 52', and Femi Adeyani restored Kingsferry's lead at 81'; that goal was later corrected and is now credited to Femi Adeyani. | all passed |
| `catchup@23` | accepted, 2 attempts, 16.9 s | **What you missed, up to 22'** Saltmarsh have spent most of the opening stages on top, controlling 74% of the last 5 minutes and starting that spell at 2'. They followed that with a period of pressure from 6', which produced 1 shot and kept Kingsferry pinned for 62% of the last 3 minutes. | all passed |
| `catchup@31` | accepted, 1 attempt, 12.7 s | **What you missed, up to 30'** Saltmarsh had long periods with the ball early, keeping control for 5 minutes from 2' and again for 5 minutes from 17'. They pinned Kingsferry back in the middle of the half and created chances, but Kingsferry broke away and Femi Adeyani scored on the counter at 23'. | all passed |
| `catchup@60` | accepted, 1 attempt, 13.1 s | **What you missed** Femi Adeyani scored at 23' to put Kingsferry ahead, then a No goal for offside against Marco Dellow wiped out a later effort (VAR check at 33'). Teo Varlan levelled the game at 52', and since then Saltmarsh have had most of the ball and the better chances. | all passed |
| `catchup@81` | accepted, 2 attempts, 24.7 s | **What you missed, up to 80'** Saltmarsh dominated the early spell, building runs of 31 passes and keeping 89% of the passes before the goal at 23'. Femi Adeyani put Kingsferry ahead from a counter move at 23'. A VAR check ruled out a goal for offside against Marco Dellow after a pass from Teo Varlan (No goal), then Teo Varlan equalised at 52'; a later penalty check was also cleared (No penalty). | all passed |
