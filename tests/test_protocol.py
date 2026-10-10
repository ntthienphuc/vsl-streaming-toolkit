"""Protocol/state regressions without model or network dependencies."""
import copy
import json
import unittest

from vsl_streaming.config import ServerConfig
from vsl_streaming.core import ProtocolError, StreamConfig
from vsl_streaming.protocol import MessageProcessor, decode_message, error_response


class FakeRecognizer:
    def __init__(self, reject_sequences=()):
        self.calls = []
        self.reject_sequences = set(reject_sequences)

    def predict_segment(self, frames):
        sequences = [frame["seq"] for frame in frames]
        self.calls.append(sequences)
        if sequences[0] in self.reject_sequences:
            raise ValueError("deliberate incompatible segment")
        return {"label": "example", "score": 0.9, "sequences": sequences}


def settings(**overrides):
    defaults = {"stream": StreamConfig(mode="fixed_window", window_frames=3,
                                      min_segment_frames=2, min_up_frames=1)}
    defaults.update(overrides)
    return ServerConfig(**defaults)


def request(start=0, count=3, request_id="r1", **extra):
    return {"type": "frames", "request_id": request_id,
            "frames": [{"seq": i, "timestamp_ms": i * 20,
                        "points": [[i, 0], [1, i]]} for i in range(start, start + count)],
            **extra}


class ProtocolTests(unittest.TestCase):
    def test_retry_does_not_infer_or_mutate_stream_twice(self):
        model = FakeRecognizer()
        processor = MessageProcessor(model, settings())
        first = processor.process(request())
        before = processor.session.status()
        second = processor.process(copy.deepcopy(request()))
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(second["events"], first["events"])
        self.assertEqual(model.calls, [[0, 1, 2]])
        self.assertEqual(processor.session.status(), before)

    def test_conflicting_id_is_atomic(self):
        model = FakeRecognizer()
        processor = MessageProcessor(model, settings())
        processor.process(request())
        before = processor.session.status()
        collision = processor.process(request(start=3))
        self.assertEqual(collision["error"]["code"], "request_id_conflict")
        self.assertEqual(processor.session.status(), before)
        self.assertEqual(model.calls, [[0, 1, 2]])
        accepted = processor.process(request(start=3, request_id="r2"))
        self.assertEqual(accepted["events"][0]["prediction"]["sequences"], [3, 4, 5])

    def test_invalid_whole_batch_can_be_corrected_with_same_id(self):
        model = FakeRecognizer()
        processor = MessageProcessor(model, settings())
        baseline = processor.session.status()
        bad = request(count=4)
        bad["frames"][-1]["timestamp_ms"] = 0
        result = processor.process(bad)
        self.assertEqual(result["error"]["code"], "out_of_order_timestamp")
        self.assertEqual(processor.session.status(), baseline)
        self.assertEqual(model.calls, [])
        self.assertEqual(len(processor.cache), 0)
        fixed = processor.process(request(count=4))
        self.assertEqual(fixed["type"], "result")
        self.assertEqual(fixed["state"]["buffered_frames"], 1)

    def test_multiple_segments_and_flush_remainder(self):
        model = FakeRecognizer()
        processor = MessageProcessor(model, settings())
        result = processor.process(request(count=8, flush=True))
        self.assertEqual([e["reason"] for e in result["events"]], ["window", "window", "flush"])
        self.assertEqual(model.calls, [[0, 1, 2], [3, 4, 5], [6, 7]])
        self.assertEqual(result["state"]["buffered_frames"], 0)

    def test_rejected_inference_is_explicit_and_other_segments_continue(self):
        model = FakeRecognizer(reject_sequences=(3,))
        processor = MessageProcessor(model, settings())
        result = processor.process(request(count=9))
        self.assertEqual([e["status"] for e in result["events"]], ["predicted", "rejected", "predicted"])
        rejected = result["events"][1]
        self.assertEqual(rejected["error"]["code"], "inference_failed")
        self.assertNotIn("prediction", rejected)
        self.assertEqual(result["state"]["emitted_segments"], 3)
        repeat = processor.process(request(count=9))
        self.assertTrue(repeat["replayed"])
        self.assertEqual(len(model.calls), 3)

    def test_processors_isolate_stream_and_cache_even_with_shared_model(self):
        model = FakeRecognizer()
        first, second = MessageProcessor(model, settings()), MessageProcessor(model, settings())
        first.process(request(count=2))
        self.assertEqual(second.session.status()["received_frames"], 0)
        result = second.process(request())
        self.assertFalse(result["replayed"])
        self.assertEqual(model.calls, [[0, 1, 2]])
        final = first.process({"type": "flush", "request_id": "r2"})
        self.assertEqual(final["events"][0]["prediction"]["sequences"], [0, 1])

    def test_reset_retry_does_not_reset_new_work(self):
        processor = MessageProcessor(FakeRecognizer(), settings())
        processor.process(request())
        reset = {"type": "reset", "request_id": "reset-1"}
        self.assertEqual(processor.process(reset)["state"]["received_frames"], 0)
        processor.process(request(count=2, request_id="new-stream"))
        repeated = processor.process(reset)
        self.assertTrue(repeated["replayed"])
        self.assertEqual(processor.session.status()["received_frames"], 2)

    def test_cache_eviction_never_bypasses_sequence_ordering(self):
        model = FakeRecognizer()
        processor = MessageProcessor(model, settings(request_cache_size=1))
        processor.process(request())
        processor.process({"type": "status", "request_id": "status-1"})
        self.assertEqual(list(processor.cache), ["status-1"])
        expired = processor.process(request())
        self.assertEqual(expired["error"]["code"], "out_of_order_seq")
        self.assertEqual(len(model.calls), 1)

    def test_returned_objects_cannot_corrupt_retry_cache(self):
        processor = MessageProcessor(FakeRecognizer(), settings())
        original = processor.process(request())
        original["events"][0]["prediction"]["label"] = "corrupted"
        original["state"]["received_frames"] = -1
        repeated = processor.process(request())
        self.assertEqual(repeated["events"][0]["prediction"]["label"], "example")
        self.assertEqual(repeated["state"]["received_frames"], 3)
        repeated["events"].clear()
        self.assertEqual(len(processor.process(request())["events"]), 1)

    def test_protocol_validation_does_not_touch_state(self):
        processor = MessageProcessor(FakeRecognizer(), settings(max_batch_frames=3))
        before = processor.session.status()
        cases = [(None, "invalid_message"), ({"type": "status"}, "invalid_request_id"),
                 ({"type": "other", "request_id": "r"}, "invalid_type"),
                 ({"type": "reset", "request_id": "r", "extra": 1}, "unknown_field"),
                 (request(count=4), "batch_too_large"), (request(flush=1), "invalid_flush"),
                 (request(count=0), "invalid_frames")]
        for message, expected in cases:
            result = processor.process(message)
            self.assertEqual(result["error"]["code"], expected)
            self.assertEqual(processor.session.status(), before)
        self.assertEqual(len(processor.cache), 0)


class ConfigurationAndJSONTests(unittest.TestCase):
    def test_literal_unpaired_surrogate_is_a_structured_protocol_error(self):
        for text in ('"\ud800"', '"\\ud800"'):
            with self.subTest(text=repr(text)), self.assertRaises(ProtocolError) as raised:
                decode_message(text, 1024)
            self.assertEqual(raised.exception.code, "invalid_json")

    def test_error_details_are_bounded_and_utf8(self):
        result = error_response(ProtocolError("invalid_json", "\ud800" + "x" * 3000))
        self.assertEqual(len(result["error"]["message"]), 2000)
        json.dumps(result, ensure_ascii=False).encode("utf-8")

    def test_strict_json(self):
        for text in ('{"x":NaN}', '{"x":Infinity}', '{"x":1,"x":2}', '{'):
            with self.assertRaises(ProtocolError) as caught:
                decode_message(text, 1000)
            self.assertEqual(caught.exception.code, "invalid_json")
        with self.assertRaises(ProtocolError) as caught:
            decode_message('"\u0111"', 3)
        self.assertEqual(caught.exception.code, "message_too_large")
        self.assertEqual(decode_message('{"x":[1,2]}', 1000), {"x": [1, 2]})

    def test_configuration_roundtrip_and_rejection(self):
        config = settings(max_sessions=5)
        self.assertEqual(ServerConfig.from_dict(json.loads(json.dumps(config.to_dict()))), config)
        for value in ({"max_sessions": 0}, {"max_sessions": True}, {"unknown": 1},
                      {"stream": []}, {"provider": ""}):
            with self.assertRaises(ValueError):
                ServerConfig.from_dict(value)


if __name__ == "__main__":
    unittest.main()
