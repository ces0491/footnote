"""Reading a match the way an analyst would: models over the feed and the tracking.

- `difficulty`: the chance a pass reaches its target, from where it was played, where it was going
  and where the opponents stood. Difficulty is one minus that chance.
- `state`: the hidden match state (control, pressure, transition, chaos, balanced), estimated live
  from the events and each side's shape in the tracking (`shape`) by a small neural network, a few
  seconds behind play.
- `physical`: distance covered and top speeds from the tracking, and the moments a player crosses a
  threshold.

The models are fitted on generated matches by `python -m footnote.interpret` and scored against the
answer key on matches involving clubs whose playing styles they never saw (docs/models.md). The
services load the fitted parameters from `params/` and never read the answer key.
"""
