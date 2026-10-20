"""The tracking the browser's pitch view draws, cut into chunks of a few seconds.

The pitch view stands in for the viewer's video: it draws every player and the ball as of the
viewer's playback. The processor stores the committed tracking file in Postgres when it starts
(`tracking_chunks`, migration 0004), and the web app serves a run's viewers the frames up to the
run's live point and none beyond (frontend/src/app/api/runs/[runId]/tracking).

Each frame is `VALUES_PER_FRAME` little-endian int16 values: the 22 slots' x and y and the ball's x,
y and z, in centimetres in the feed's absolute frame (docs/data.md), with -32768 for an empty slot;
then the index of the line-up in force, `slot_players[index]` naming the player in each slot. Chunk
`n` of a period holds its frames from `n * FRAMES_PER_CHUNK`; the last chunk of each period is
shorter.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FRAMES_PER_CHUNK = 50  # five seconds at ten frames a second
SLOTS = 22
VALUES_PER_FRAME = SLOTS * 2 + 3 + 1


@dataclass(frozen=True)
class PitchTracking:
    layout: dict  # what `matches.tracking` holds: how to read the chunks
    chunks: list[tuple[int, int, bytes]]  # (period, chunk, frames)


def load(path: Path) -> PitchTracking:
    """Cut a match's tracking file into the chunks the web app serves."""
    raw = path.read_bytes()
    with np.load(path) as z:
        frame_rate = int(z["frame_rate"])
        period = z["period"].astype(np.int64)
        players = z["players_cm"].astype("<i2")
        ball = z["ball_cm"].astype("<i2")
        occupancy = z["occupancy"].astype("<i2")
        slot_players = [[str(p) for p in row] for row in z["slot_players"]]
    frames = np.concatenate([players.reshape(len(period), SLOTS * 2), ball, occupancy[:, None]], axis=1).astype("<i2")
    chunks: list[tuple[int, int, bytes]] = []
    lengths: dict[str, int] = {}
    for p in (1, 2):
        own = frames[period == p]
        lengths[str(p)] = len(own)
        for n, start in enumerate(range(0, len(own), FRAMES_PER_CHUNK)):
            chunks.append((p, n, own[start : start + FRAMES_PER_CHUNK].tobytes()))
    layout = {
        "digest": hashlib.sha256(raw).hexdigest(),
        "frame_rate": frame_rate,
        "frames_per_chunk": FRAMES_PER_CHUNK,
        "values_per_frame": VALUES_PER_FRAME,
        "frames": lengths,
        "slot_players": slot_players,
    }
    return PitchTracking(layout, chunks)


def frames_of(chunk: bytes) -> Iterator[np.ndarray]:
    """The frames in a chunk, each as its `VALUES_PER_FRAME` values."""
    values = np.frombuffer(chunk, dtype="<i2")
    yield from values.reshape(-1, VALUES_PER_FRAME)
