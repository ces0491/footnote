"""The replayer: stands in for the data provider, playing the committed showcase feed into Event Hubs.

Each replay is a run with its own ID. A run starts from a jump point: the messages before it go out
at once as a backfill, so the processor's state is right from the first live message, and the rest
follow at the pace their timestamps set, scaled by the run's speed, with the half-time break
shortened (`footnote.live.timeline`). Runs end at the end of the feed, when stopped, after a time
limit, or when evicted to make room for a new one.
"""
