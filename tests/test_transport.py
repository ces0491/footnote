"""The replayer-to-processor envelope through the Event Hubs SDK's own AMQP encoding."""

from __future__ import annotations

from datetime import UTC, datetime

from azure.eventhub import EventData, EventDataBatch

# Private SDK modules: the public API offers no way to turn an outgoing event into a received one
# without a live hub. If an SDK upgrade moves them, this test needs updating, not the services.
from azure.eventhub._pyamqp._decode import decode_payload
from azure.eventhub._pyamqp._encode import encode_payload
from azure.eventhub._transport._pyamqp_transport import PyamqpTransport

from footnote.live.contract import KIND_CONTROL
from footnote.live.match import load_match
from footnote.processor.consumer import decode
from footnote.replayer.publish import Envelope, to_event

PUBLISHED = datetime(2026, 10, 19, 16, 48, 1, 943000, tzinfo=UTC)


def _received(event: EventData) -> EventData:
    message = PyamqpTransport.to_outgoing_amqp_message(event._raw_amqp_message)
    buffer = bytearray()
    encode_payload(buffer, message)
    return EventData._from_message(decode_payload(memoryview(buffer)))


def test_every_feed_message_encodes_and_decodes_unchanged() -> None:
    feed = load_match().feed
    batch = EventDataBatch(max_size_in_bytes=4 * 1024 * 1024)
    for m in feed:
        event = to_event("0123456789abcdef", Envelope(m, backfill=m["seq"] < 100), PUBLISHED)
        batch.add(event)  # encodes the message, so a property the AMQP encoder can't take fails here
        incoming = decode(_received(event))
        assert incoming.body == m
        assert incoming.run_id == "0123456789abcdef"
        assert incoming.backfill == (m["seq"] < 100)
        assert incoming.published_at == 1_792_428_481_943  # epoch ms survive (a 32-bit int would not)
    assert len(batch) == len(feed)


def test_a_control_message_keeps_its_kind() -> None:
    envelope = Envelope({"type": "run_end", "run_id": "0123456789abcdef", "reason": "stopped"}, KIND_CONTROL)
    incoming = decode(_received(to_event("0123456789abcdef", envelope, PUBLISHED)))
    assert incoming.kind == KIND_CONTROL and incoming.body["reason"] == "stopped"
