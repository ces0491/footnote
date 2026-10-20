# Models

Two models read each match: one rates how hard every pass was, the other estimates the hidden match
state live. This page says what they read, how they were fitted and how well they recover the truth
on matches between clubs whose playing styles they never saw.

Generated on 2026-10-20 from all 380 fixtures of the league under seed 2026, in 16 minutes.
Generator fingerprint `5e1cde3bdb459aba`. Regenerate with `python -m footnote.interpret`, which also
writes the fitted parameters the processor loads (`src/footnote/interpret/params/`).

## How they are tested

The generator writes an answer key beside every match ([data.md](data.md)): the true chance of every
pass reaching its target, and the true state at every second. The services never read it. Training
fits on it, and every score below is measured against it.

The split is by playing style. Each club's style is one of seven archetypes plus a little seeded
noise, so another league seed wouldn't give new styles. Clubs from two archetypes, wing crossing and
direct aerial (FAL, KES, THI, YAR), are held out: the 140 matches involving them are the test set
and are used for nothing but these scores. The other 240 matches fit the models. The 51 of them on
matchdays 31 to 38 first choose how the state model's output is steadied for display, then join the
final fit.

## Pass difficulty

A pass's difficulty is one minus the modelled chance that it reaches its target. The model is a
logistic regression over what the feed and the tracking show as the ball is played: where the pass
starts, its length, height and speed, whether it is a cross, a through ball, a header or a set
piece, whether the passer is under pressure, and from the tracking how much space the passer and the
target have, how many opponents stand near the line of the pass, how much time the nearest of them
would have in hand to cut it out (closing at 7 m/s), and how many defenders are goal-side of the
target.

The target is the point the pass's length away from the passer, towards where the intended receiver
stood. The feed's end point would give the outcome away: a pass that was cut out ends where it was
cut out. Nothing about the passer or the club goes in, so a rating describes the situation, not the
player.

On the 117,537 passes in the test matches (lower is better in every column):

| Model | Log loss | Brier score | Average gap from the true chance |
| --- | --- | --- | --- |
| Every pass at the training completion rate | 0.520 | 0.168 | 0.187 |
| Feed only: the pass's own fields | 0.376 | 0.115 | 0.063 |
| Feed and tracking: the live model | 0.362 | 0.111 | 0.049 |
| The answer key's true chances | 0.341 | 0.103 | 0 |

The true chances set the floor: knowing them exactly still leaves each pass's outcome to chance. The
model leaves out by design the passer's and receiver's skill, the clubs' strength and the hidden
match state, all of which move the true chance.

Calibration on the test passes, in tenths by the model's chance:

| Model's chance (average) | Passes | Completed | True chance (average) |
| --- | --- | --- | --- |
| 22.5% | 11,754 | 23.1% | 22.9% |
| 49.5% | 11,754 | 47.3% | 47.2% |
| 72.1% | 11,753 | 71.1% | 70.7% |
| 83.9% | 11,754 | 83.6% | 83.6% |
| 89.3% | 11,753 | 88.8% | 88.8% |
| 92.1% | 11,754 | 92.0% | 91.9% |
| 93.9% | 11,754 | 94.2% | 94.2% |
| 94.9% | 11,753 | 95.1% | 95.3% |
| 95.8% | 11,754 | 95.9% | 96.2% |
| 97.1% | 11,754 | 96.7% | 96.8% |

By kind of pass:

| Kind | Passes | Completed | Model's average chance | Gap from the true chance | Log loss | Log loss of the true chances |
| --- | --- | --- | --- | --- | --- | --- |
| Throw-ins | 5,450 | 84.3% | 85.0% | 0.086 | 0.319 | 0.267 |
| Crosses | 5,084 | 20.1% | 18.3% | 0.101 | 0.542 | 0.474 |
| Headed passes | 3,013 | 48.3% | 48.5% | 0.164 | 0.534 | 0.441 |
| Other set pieces | 5,745 | 80.6% | 81.0% | 0.040 | 0.384 | 0.372 |
| Lofted passes in open play | 30,304 | 59.6% | 60.1% | 0.082 | 0.573 | 0.542 |
| Ground passes in open play | 67,941 | 92.5% | 92.8% | 0.024 | 0.249 | 0.240 |

Passes by the held-out clubs themselves (51,439) completed 73.9% against a modelled 75.5%; their
opponents' (66,098) completed 82.6% against 81.9%.

## Match state

At any moment the generator has the match in one of eight states: one side in control, one side
pinning the other back (pressure), one side breaking at speed (transition), chaos, or balanced. The
feed never names them.

Every second gets a vector of evidence over windows of 15, 45 and 120 seconds that reach 5 seconds
past it. From the events: each side's share of the ball, where it has the ball and wins it back, how
fast it moves the ball forward, its passing, crosses, shots, long balls, fouls and pressing, and how
often the ball changes hands. From the tracking: how high each side's block stands, where its back
and front lines are, how wide it spreads and how fast its players are moving. And how recently each
side won the ball and how far it has taken it since.

A small neural network, one hidden layer of 48 tanh units under a softmax, turns the evidence into
the chance of each state. It is fitted on one second in every 12 from the training matches, each
also seen with home and away swapped, so neither side's states are learned from the other's alone.
The live estimate is the network's output for each second. The state a viewer is shown changes only
once another has led the estimate for 12 seconds in a row, except that a break, which lasts seconds,
is shown and dropped at once. It all runs 5 seconds behind play: the estimate for a second is ready
once the events of the next few seconds are in.

On every second of the 140 test matches (847,220 seconds). Macro F1 averages the eight states
equally, so the rare ones count; "side on top" only asks whether the home side, the away side or
neither holds a state of its own:

| Method | Seconds right | Macro F1 | Side on top right |
| --- | --- | --- | --- |
| Always "balanced" | 32.7% | 0.06 | 51.0% |
| Control for a side with 60% of the ball over two minutes, otherwise balanced | 26.0% | 0.12 | 39.1% |
| The network alone, second by second | 57.9% | 0.52 | 76.9% |
| The live estimate, as shown | 57.1% | 0.51 | 75.3% |

The live estimate state by state:

| State | Share of seconds | Caught (recall) | Right when named (precision) |
| --- | --- | --- | --- |
| Balanced | 32.7% | 69% | 54% |
| Chaos | 18.3% | 42% | 51% |
| Control, home | 18.7% | 55% | 66% |
| Control, away | 15.6% | 54% | 64% |
| Pressure, home | 7.4% | 55% | 59% |
| Pressure, away | 6.1% | 58% | 54% |
| Break, home | 0.6% | 33% | 37% |
| Break, away | 0.5% | 33% | 36% |

Where the seconds go, as a share of each true state's seconds (rows: true state; columns: the live
estimate):

| True state | Bal | Chaos | Ctrl H | Ctrl A | Pres H | Pres A | Break H | Break A |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Balanced | 69 | 13 | 6 | 7 | 2 | 2 | 0 | 0 |
| Chaos | 42 | 42 | 5 | 5 | 2 | 2 | 1 | 1 |
| Control, home | 28 | 6 | 55 | 1 | 8 | 1 | 0 | 0 |
| Control, away | 25 | 7 | 2 | 54 | 1 | 10 | 0 | 0 |
| Pressure, home | 13 | 6 | 22 | 2 | 55 | 1 | 0 | 0 |
| Pressure, away | 13 | 6 | 3 | 18 | 1 | 58 | 0 | 0 |
| Break, home | 27 | 12 | 8 | 9 | 5 | 5 | 33 | 0 |
| Break, away | 26 | 13 | 9 | 8 | 6 | 6 | 1 | 33 |

Spells caught. A control, pressure or chaos spell of 60 seconds or more counts as caught when the
live estimate names it for at least half its seconds; a break counts when any of its seconds is
named as that side's break:

| Spell | Caught | Of |
| --- | --- | --- |
| Control | 832 (55%) | 1,514 |
| Pressure | 442 (62%) | 718 |
| Chaos | 347 (39%) | 884 |
| Break | 604 (36%) | 1,685 |

The shown state changes 103 times in an average test match; the true state changes 51 times.

By held-out style (a match between the two styles counts in both rows):

| Matches involving | Matches | Seconds right | Macro F1 | Side on top right |
| --- | --- | --- | --- | --- |
| wing crossing clubs | 108 | 57.8% | 0.51 | 75.1% |
| direct aerial clubs | 38 | 54.2% | 0.49 | 75.7% |

The smoothing and the hold were chosen on the 51 validation matches: of the settings whose macro F1
stayed within 0.02 of the best, the one whose shown state changes least often. These matches share
the training styles, so their scores run higher than the test set's.

| Weight kept each second | Hold | Seconds right | Macro F1 | Shown state changes per match |
| --- | --- | --- | --- | --- |
| 0.0 | 0 s | 60.0% | 0.53 | 487 |
| 0.0 | 3 s | 60.0% | 0.53 | 245 |
| 0.0 | 5 s | 59.8% | 0.52 | 178 |
| 0.0 | 8 s | 59.5% | 0.52 | 126 |
| 0.0 | 12 s (chosen) | 59.0% | 0.52 | 93 |
| 0.5 | 0 s | 60.3% | 0.53 | 323 |
| 0.5 | 3 s | 59.9% | 0.52 | 227 |
| 0.5 | 5 s | 59.7% | 0.52 | 178 |
| 0.5 | 8 s | 59.4% | 0.52 | 128 |
| 0.5 | 12 s | 59.0% | 0.51 | 95 |
| 0.7 | 0 s | 60.5% | 0.52 | 250 |
| 0.7 | 3 s | 60.0% | 0.52 | 200 |
| 0.7 | 5 s | 59.7% | 0.52 | 166 |
| 0.7 | 8 s | 59.3% | 0.51 | 127 |
| 0.7 | 12 s | 59.0% | 0.51 | 96 |
| 0.8 | 0 s | 60.7% | 0.51 | 204 |
| 0.8 | 3 s | 60.2% | 0.51 | 172 |
| 0.8 | 5 s | 59.8% | 0.51 | 147 |
| 0.8 | 8 s | 59.2% | 0.50 | 120 |
| 0.8 | 12 s | 58.9% | 0.50 | 93 |

The true state changes 53 times in an average validation match.

### The showcase match

The showcase match ([experience.md](experience.md)) involves two training styles, so it isn't part
of the test. Over the whole match the live estimate is right for 62.0% of seconds. For the beats the
story names a state for:

| Beat | State | Its share of the beat, true | Its share, live estimate | Seconds right |
| --- | --- | --- | --- | --- |
| 0-21' | Control, home | 68% | 50% | 62% |
| 38-45' | Pressure, home | 64% | 49% | 60% |
| 63-68' | Chaos | 64% | 54% | 39% |

The break that ended in the first goal is caught by the live estimate.

## Tags from the tracking

No model is involved. A sprint tag marks a player going above 32 km/h, averaged over a second as
tracking providers report top speed, with its peak once the player slows below the threshold again.
A distance tag marks a player passing 10 km covered.
