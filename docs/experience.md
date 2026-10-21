# What each person sees

One showcase match, five people watching it, the screens they use, what the
overlay data has to carry to serve them all, and the two-minute video that comes
out of it. The people and their needs come from [audience.md](audience.md);
numbers in principle references (P1–P8) point to its design principles.

Figures in the sketches show format only. The showcase match's real figures come
from the generator.

## The showcase match

**Saltmarsh Rovers v Kingsferry Athletic.** Saltmarsh keep the ball and press
high. Kingsferry sit deep and break quickly. The match isn't scripted: a search
reruns the generator from saved points with new seeds until each moment below
happens, as [data.md](data.md#the-showcase-match) explains.

| Cast | Club | Role |
| --- | --- | --- |
| Teo Varlan (10) | Saltmarsh | Playmaker; the player-focus subject |
| Marco Dellow (9) | Saltmarsh | Striker |
| Jory Penhallow (4) | Saltmarsh | Centre-back |
| Femi Adeyani (7) | Kingsferry | Winger |
| Isaac Brennholt (1) | Kingsferry | Goalkeeper |

| Minute | What happens | Match state | Exercises |
| --- | --- | --- | --- |
| 0–22 | Saltmarsh dominate the ball | Control (Saltmarsh) | State timeline |
| 23 | Kingsferry score from their first counter | Transition | P1, P4 |
| 31 | Dellow scores; VAR rules it out for offside | Stoppage | P5 |
| 38–45 | Saltmarsh pin Kingsferry back | Sustained pressure | P1, P6 |
| HT | Half-time recap | | P7 |
| 52 | Varlan equalises from distance | Control | Player focus, shot speed |
| 60 | A viewer joins late | | P7 |
| 63–68 | Possession changes hands repeatedly | Chaos | Rhythm explanation |
| 74 | Handball penalty claim; VAR says no | Stoppage | P5 |
| 81 | Goal credited as a Penhallow own goal | Transition | |
| 84 | Credit amended to Adeyani | | P2, P3 |
| FT | Full-time recap | | P7 |

## The people

| Person | Situation | Settings |
| --- | --- | --- |
| **Nadia**, producer | Runs the world feed's graphics for this match | Producer console |
| **Sam**, casual fan | Follows Saltmarsh because family does; streams on a service about 40 s behind live | Casual, club Saltmarsh, delay 40 s |
| **Priya**, fantasy manager | Owns Varlan; wants to know if he's worth keeping | Analyst, focus Varlan, metric pass difficulty |
| **Lucía**, late joiner | In Madrid; joins at minute 60 after work | Casual, Spanish |
| **Tom**, blind fan | Follows on a phone with a screen reader | Described feed, standard detail |

## Screens

The fan app is one web app. On a desktop it shows the match (our own 2D pitch
render standing in for the video) with overlays, plus a side panel. On a phone
it shows the panel only, as a second screen next to the TV.

### Producer console

```text
PRODUCER                                 Saltmarsh 0–1 Kingsferry   23:41
State  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒        control → transition
───────────────────────────┬──────────────────────────────────────────────
 Feed preview              │ Shortlist
                           │ 1  Against the run of play          rank 0.91
   [ pitch + overlay ]     │    Kingsferry scored with their first
                           │    counter. Saltmarsh had 71% of the ball.
                           │    Evidence e1043 e1044 e1047 e1049
                           │    [Approve] [Edit] [Kill]   template · agent drafting
                           │ 2  Adeyani sprint 33.8 km/h         rank 0.74
                           │ 3  Key pass difficulty 0.82         rank 0.66
───────────────────────────┴──────────────────────────────────────────────
 On air: —       Queue: 1       Corrections: 0
```

Each card shows its reason and its evidence, and opening the evidence lists the
events. A card starts as the template version and swaps to the agent's version
when it arrives, marked either way. Nothing airs without Approve (P3), and Approve
waits for an agent's draft that is on its way, so what airs is the wording Nadia
saw. A lower third approved after its moment goes on air from the approval.

### Fan view, casual

```text
CASUAL · Saltmarsh                              Your stream: 40 s behind live
┌──────────────────────────────────────────────┐
│                                              │
│          [ match / 2D pitch ]                │
│                                              │
│   ┌──────────────────────────────────────┐   │
│   │ 0–1  Kingsferry score on the break   │   │
│   └──────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
Who's on top   Saltmarsh ▓▓▓▓▓▓▓▓▓▓▓▓░░░░ Kingsferry
Why it matters Saltmarsh have had most of the ball, but Kingsferry
               only needed one quick break.                 [events ▸]
```

Rule calls get a card during the stoppage (P5):

```text
VAR CHECK · Offside
Dellow was beyond the last defender when Varlan passed.
[ freeze-frame at the pass, offside line drawn ]
Offside is judged at the moment of the pass.                [events ▸]
```

### Fan view, analyst with player focus

```text
ANALYST · Focus Varlan (10) · Metric pass difficulty
State   0' ▓▓▓▓▓▓▓▓▓▓▓▒▒░░░▓▓▓▓▓▓▓▓ 45'
           control     trans  pressure
38'–45' Sustained pressure, Saltmarsh
        Final-third entries 14 · Shots 5 · Possession 78%
Varlan  Passes 41/46 · Avg difficulty 0.48 · Hardest 0.86 (31')
        Distance 6.2 km · Top speed 31.4 km/h
23'     Against the run of play
        Key pass completion chance 18% → difficulty 0.82   [events ▸]
```

Player focus keeps the club context on screen and adds the player's line to
every moment the player is involved in (P6). The chosen metric is pinned at the top.

### Described feed

```text
DESCRIBED FEED     Detail: Standard ▾   Pace: Normal ▾   [Pause]
30:36  Saltmarsh win the ball in a duel, in the opposition half.
30:47  Varlan, in the centre circle, plays a pass forward to Dellow,
       in the final third.
30:51  Dellow shoots with the right foot from 19 metres: goal.
30:51  Goal for Saltmarsh, scored by Dellow. Saltmarsh 1, Kingsferry 1.
30:51  VAR is checking the goal for offside.
32:11  VAR decision: no goal. The decision on the field is overturned.
       Saltmarsh 0, Kingsferry 1.
       On screen: VAR: No goal. Marco Dellow was offside when Teo Varlan
       played the pass, so the goal is ruled out. ...
```

Lines come from templates over the event data, so they say only what the events
contain, and each graphic is read out once, as it airs, in the viewer's language
and marked as such for the screen reader. The detail levels are key moments only
(goals, shots, VAR, cards, substitutions, corrections, the clock), standard (adds
the build-up: changes of possession in open play, passes and runs that take the
ball forward, crosses, fouls and set pieces other than throw-ins) and full (every
pass and run, throw-ins, tackles, interceptions, clearances and blocks). The
device's screen reader speaks the feed through a live region at the pace the
listener picks. Up to three lines waiting are said together, so a pass and the
shot it sets up are heard as one; when more back up in a fast replay, it says
the key moments among them, each with the line that led up to it, and the latest
line, and after a pause every key moment that waited and the latest line, rather
than the whole backlog (P8).

### Catch-up

```text
WHAT YOU MISSED, UP TO 59'
Saltmarsh had long spells of possession and pinned Kingsferry back
before the opener. Adeyani scored on the break at 23', then VAR ruled
out a Saltmarsh goal for offside. Varlan levelled at 52' and Saltmarsh
have controlled the game since.
Before you joined   23'      Femi Adeyani scores
                    33'      VAR: No goal
                    44'      Saltmarsh pinning Kingsferry back
                    52'      Teo Varlan scores
[Back to the match]
```

The recap agent writes it from the match's moments when the replay reaches its starting point. It
tells what happened, goals included, and leaves the score line to the scoreboard beside it. A fan
reading in Spanish or French gets it, and the moments under it, in their language.

### Settings

Mode, club, player, metric, language, stream delay, calm mode and described-feed
detail and pace. They're stored under the viewer's profile and restored on the
next visit.

## One match, five people

**23', Kingsferry score.** The state model ranks "against the run of play" first
because a goal came from Kingsferry's first transition after a long Saltmarsh
control spell. Nadia gets the card at once with the template wording, the agent
version replaces it a few seconds later, and Nadia approves it for air. Sam's
stream is 40 s behind, so the overlay and the "why it matters" card wait until
the goal appears on Sam's screen, or until Nadia approves the card if that comes
later, and carry the wording she approved. Priya
sees the same moment with the key pass's difficulty. Tom hears the build-up as
it happens on the event feed and the goal line straight after.

**31', offside.** Every viewer gets the VAR status as soon as the check starts,
timed to their own playback. When the decision lands, Sam's card shows the
freeze-frame and the one-line rule. Tom hears "No goal. Dellow was offside when
Varlan passed." Priya's view logs it against Varlan's pass, the hardest Varlan
has attempted so far.

**38'–45', pressure.** The state model marks a sustained pressure spell. Nadia's
shortlist offers it as a segment graphic. Priya's timeline shades it with the
spell's numbers. Sam sees "Saltmarsh are camped in Kingsferry's half" during the
next stoppage, not mid-attack.

**Half-time.** Recaps in each mode. Tom's feed reads the score, the two key
moments and who has had the ball.

**52', Varlan equalises.** Shot speed tag on the overlay. Priya's player line
updates. Sam's "who's on top" bar moves with the shift in control.

**60', Lucía joins.** Lucía opens the app in Spanish, reads "what you missed"
in Spanish, goes back to the match, and from then on gets Spanish versions of
every card. Numbers, minutes and names in them are checked
against the English source.

**63'–68', chaos.** The state model detects the match losing its shape: rapid
changes of possession, few completed sequences. Nadia gets a rhythm card:
"Neither side has strung more than four passes together since the hour." Priya
sees the chaos segment on the timeline.

**74', handball check.** Same pattern as the offside: status first, decision and
rule explanation in the stoppage.

**81' and 84', the amended goal.** The 81st-minute goal is first recorded as a
Penhallow own goal, and an "own goal" card airs. At 84' the feed amends the
credit to Adeyani. Every insight citing the original event is flagged, and the
goal's card is restated with the corrected facts. Nadia approved the old wording,
so the corrected card comes off air and waits for her again, listed under
corrections beside the correction notice. Nadia approves the corrected card and
the notice. Fans' cards update when their streams reach 84', and say the provider
corrected them. Tom's feed reads the correction.

**Full time.** Recaps in each mode and language.

## What the overlay data has to carry

From the walkthrough, each item in the overlay feed needs:

- **Identity and lineage:** item ID, match ID, the event IDs it cites, and the ID
  of any item it corrects or replaces
- **Timing:** match clock (period, minute, second), feed timestamp, display-at in
  match time (so each client can hold it against its own playback), duration
- **Ranking:** rank score and the reason it was ranked
- **Kind:** moment, stat, player tag, rule call, segment, recap, correction
- **Content:** template ID and field values for graphics systems; text per mode
  and language; a plain-text equivalent for screen readers
- **Provenance:** template or agent, the agent run ID, and which checks passed
- **Status:** drafted, approved, aired, withdrawn, with who changed it and when
- **Presentation hints:** placement (lower third, side panel, full card), motion
  level for calm mode

The contract that carries them, and the rules for timing, approval and corrections,
is [overlay.md](overlay.md).

## The video

Under two minutes, recorded from the deployed app.

| Time | Beat | Shows |
| --- | --- | --- |
| 0:00–0:10 | What Footnote does, in one line | Pitch with an overlay landing |
| 0:10–0:35 | 23' goal: ranked shortlist, reason, evidence, approve | Nadia's console |
| 0:35–1:00 | The same goal for Sam (held for the stream delay), Priya (player focus), Lucía (Spanish) | Split screen |
| 1:00–1:20 | 31' offside, read by a real screen reader from Tom's feed | Described feed with audio |
| 1:20–1:35 | 84' correction flows to the console and every fan | Correction alert, the corrected card back for approval |
| 1:35–1:50 | How it runs: architecture, state model scored against the answer key, measured latency | Diagram and figures |
| 1:50–1:58 | Close and synthetic-data disclaimer | End card |

## The judges' path

1. Open the live URL and pick who to watch as: Nadia the producer, or one of the
   ready-made fans. Starting as Nadia means approving each graphic by hand; a
   fan's replay approves them as they're found.
2. Start the showcase match from a jump point: 23', 31', 60' or 81'. The start
   page says what happens at each and who to watch it as.
3. Switch between Nadia and the fans mid-match to see the same moment change: Sam
   gets it 40 seconds of match time after Nadia's console does, which is 20
   seconds at 2×, or as Nadia approves it if that comes later.
4. Open any card's evidence to see the events behind it, and in the console the
   agents' runs on it.
