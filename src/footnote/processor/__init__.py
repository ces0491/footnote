"""The stream processor: reads the feed from Event Hubs, keeps each run's match state in Postgres
and pushes every event, with the state after it, to the run's viewers through Web PubSub.

`core` holds the processing logic and knows nothing about Azure; `store`, `push` and `consumer`
connect it to Postgres, Web PubSub and Event Hubs.
"""
