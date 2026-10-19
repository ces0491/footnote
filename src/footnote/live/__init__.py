"""Live match processing shared by the replayer, the processor and their tests.

The replayer plays the committed showcase feed into Event Hubs, standing in for a data provider.
The processor folds the feed into match state and pushes it to viewers through Web PubSub. Both
read the match through `match.load_match`, agree on timing through `timeline.Timeline`, and talk
in the messages described in `contract`.
"""
