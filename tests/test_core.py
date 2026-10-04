import copy
import unittest

from vsl_streaming.core import ProtocolError, StreamConfig, StreamSession


def frame(seq, active=True, missing=False):
    pose = [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 1.0} for _ in range(33)]
    for offset in (0, 1):
        pose[11 + offset].update(x=0.4, y=0.3)
        pose[13 + offset].update(x=0.4, y=0.5)
        pose[15 + offset].update(x=0.6 if active else 0.4, y=0.5 if active else 0.7)
        pose[23 + offset].update(x=0.4, y=0.8)
    return {"seq": seq, "timestamp_ms": seq * 100.0, "pose_landmarks": None if missing else pose}


def config(**kwargs):
    defaults = dict(min_up_frames=2, min_down_frames=2, min_down_ms=100.0, min_segment_frames=3)
    defaults.update(kwargs)
    return StreamConfig(**defaults)


class StreamTests(unittest.TestCase):
    def test_fragmentation_and_all_segments(self):
        frames = [frame(i, i % 6 < 4) for i in range(12)]
        expected_session = StreamSession(config())
        expected = [x.to_dict() for x in expected_session.push_batch(frames)]
        self.assertEqual(len(expected), 2)
        self.assertEqual([s["frames"][0]["seq"] for s in expected], [0, 6])
        for size in (1, 2, 3, 5, 7):
            session = StreamSession(config())
            actual = []
            for start in range(0, len(frames), size):
                actual.extend(s.to_dict() for s in session.push_batch(frames[start:start + size]))
            self.assertEqual(actual, expected)
            self.assertEqual(session.status(), expected_session.status())

    def test_invalid_batch_is_atomic(self):
        session = StreamSession(config())
        session.push_batch([frame(0)])
        prior = session.status()
        faults = [frame(0), frame(2), frame(2), frame(2), frame(2)]
        faults[1]["timestamp_ms"] = 0
        faults[2]["pose_landmarks"][1]["x"] = float("nan")
        faults[3]["pose_landmarks"] = []
        faults[4]["seq"] = True
        for fault in faults:
            with self.assertRaises(ProtocolError):
                session.push_batch([frame(1), fault])
            self.assertEqual(session.status(), prior)
        session.push_batch([frame(1), frame(2)])
        self.assertEqual([f["seq"] for f in session.flush()[0].frames], [0, 1, 2])

    def test_capacity_is_bounded_and_frames_preserved(self):
        session = StreamSession(config(max_buffer_frames=5))
        segments = []
        for i in range(13):
            segments.extend(session.push_batch([frame(i)]))
            self.assertLess(session.status()["buffered_frames"], 5)
        segments.extend(session.flush())
        self.assertEqual([x.reason for x in segments], ["capacity", "capacity", "flush"])
        self.assertEqual([f["seq"] for s in segments for f in s.frames], list(range(13)))

    def test_gap_resets_and_reports(self):
        for following in (frame(5), dict(frame(3), timestamp_ms=5000)):
            session = StreamSession(config())
            session.push_batch([frame(i) for i in range(3)])
            segments = session.push_batch([following])
            self.assertEqual(segments[0].reason, "gap")
            self.assertEqual(segments[0].end_ms, 200)
            self.assertEqual(session.status()["gap_resets"], 1)
            self.assertFalse(session.status()["active"])

    def test_missing_pose_ends_segment_and_recovers(self):
        session = StreamSession(config())
        first = session.push_batch([frame(0), frame(1), frame(2), frame(3, missing=True), frame(4, missing=True)])
        self.assertEqual(first[0].reason, "inactive")
        session.push_batch([frame(5), frame(6), frame(7)])
        self.assertEqual(session.flush()[0].start_ms, 500)

    def test_short_dropout_does_not_close(self):
        session = StreamSession(config())
        session.push_batch([frame(0), frame(1), frame(2, missing=True), frame(3)])
        self.assertEqual(len(session.flush()[0].frames), 4)

    def test_flush_reset_and_isolation(self):
        first, second = StreamSession(config()), StreamSession(config())
        first.push_batch([frame(i) for i in range(3)])
        self.assertEqual(second.status()["received_frames"], 0)
        self.assertEqual(first.flush()[0].reason, "flush")
        self.assertEqual(first.flush(), [])
        with self.assertRaises(ProtocolError):
            first.push_batch([frame(0)])
        first.reset()
        self.assertEqual(first.status(), second.status())
        first.push_batch([frame(0)])
        self.assertEqual(first.flush(), [])
        self.assertEqual(first.status()["discarded_candidate_frames"], 1)

    def test_copy_and_unconfirmed_onset(self):
        session = StreamSession(config())
        source = frame(0)
        session.push_batch([source])
        source["pose_landmarks"][0]["x"] = 99
        session.push_batch([frame(1), frame(2)])
        self.assertNotEqual(session.flush()[0].frames[0]["pose_landmarks"][0]["x"], 99)
        session.push_batch([frame(3), frame(4, False), frame(5), frame(6), frame(7)])
        self.assertEqual(session.flush()[0].start_ms, 500)

    def test_hand_above_hip_covers_straight_arm(self):
        frames = [frame(i, False) for i in range(3)]
        for item in frames:
            item["left_hand_landmarks"] = [{"x": 0.4, "y": 0.7} for _ in range(21)]
        session = StreamSession(config())
        session.push_batch(frames)
        self.assertEqual(len(session.flush()), 1)
        hidden = copy.deepcopy(frames)
        for item in hidden:
            item["left_hand_landmarks"][0]["visibility"] = 0
        session.reset()
        session.push_batch(hidden)
        self.assertEqual(session.flush(), [])

    def test_settings_reject_malformed_values(self):
        for kwargs in ({"min_up_frames": 0}, {"min_down_frames": True}, {"min_down_ms": -1},
                       {"visibility_threshold": 2}, {"max_gap_ms": float("nan")},
                       {"max_buffer_frames": 1}, {"angle_threshold": 200}):
            with self.assertRaises(ValueError):
                StreamConfig(**kwargs)

    def test_fixed_windows_generic_points_fragmentation_and_flush(self):
        options = config(mode="fixed_window", window_frames=4)
        frames = [{"seq": i, "timestamp_ms": i * 10, "points": [[i, 0], [1, i]]} for i in range(11)]
        expected_session = StreamSession(options)
        expected = expected_session.push_batch(frames) + expected_session.flush()
        self.assertEqual([s.reason for s in expected], ["window", "window", "flush"])
        self.assertEqual([len(s.frames) for s in expected], [4, 4, 3])
        for size in (1, 3, 7):
            session = StreamSession(options)
            actual = []
            for start in range(0, len(frames), size):
                actual.extend(session.push_batch(frames[start:start + size]))
            actual.extend(session.flush())
            self.assertEqual([s.to_dict() for s in actual], [s.to_dict() for s in expected])

    def test_fixed_window_shapes_are_atomic_and_resettable(self):
        session = StreamSession(config(mode="fixed_window", window_frames=4))
        session.push_batch([{"seq": 0, "timestamp_ms": 0, "points": [[1, 2]]}])
        prior = session.status()
        for bad in ([[1, 2], [3, 4]], [[1, float("inf")]], [[1], [2, 3]], []):
            with self.assertRaises(ProtocolError):
                session.push_batch([{"seq": 1, "timestamp_ms": 1, "points": bad}])
            self.assertEqual(session.status(), prior)
        with self.assertRaises(ProtocolError):
            session.push_batch([frame(1)])
        session.reset()
        session.push_batch([{"seq": 0, "timestamp_ms": 0, "points": [[1, 2, 3]]}])
        self.assertEqual(session.status()["received_frames"], 1)

    def test_fixed_window_gap_emits_remainder(self):
        session = StreamSession(config(mode="fixed_window", window_frames=5))
        frames = [{"seq": i, "timestamp_ms": i * 10, "points": [[1, 2]]} for i in range(3)]
        session.push_batch(frames)
        result = session.push_batch([{"seq": 4, "timestamp_ms": 40, "points": [[1, 2]]}])
        self.assertEqual(result[0].reason, "gap")
        self.assertEqual(len(result[0].frames), 3)
        self.assertEqual(session.flush(), [])

    def test_fixed_window_accepts_mediapipe_without_activity_gate(self):
        session = StreamSession(config(mode="fixed_window", window_frames=3))
        segments = session.push_batch([frame(i, False) for i in range(3)])
        self.assertEqual(segments[0].reason, "window")


if __name__ == "__main__":
    unittest.main()
