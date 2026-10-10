import copy
import itertools
import random
import unittest

from vsl_streaming.evaluation import (evaluate_events, events_from_responses,
                                     gloss_edit_counts, temporal_iou,
                                     validate_annotations, _match)


def interval(start, end, label, **kwargs):
    return dict(start_ms=start, end_ms=end, label=label, **kwargs)


def annotation(signs=None):
    return {"schema_version": 1, "scope": "synthetic", "recordings": [{
        "recording_id": "synthetic-1", "split_role": "demo", "source_group": "generated-1",
        "speaker_identity": {"status": "unverified"},
        "annotations": signs if signs is not None else [interval(0, 100, "A")]}]}


def evaluate(signs, events, threshold=0.5):
    return evaluate_events(annotation(signs), {"synthetic-1": events}, threshold)


class EvaluationTests(unittest.TestCase):
    def test_exact_and_delayed_boundaries(self):
        result = evaluate([interval(100, 200, "A"), interval(300, 400, "B")],
                          [interval(110, 210, "A"), interval(300, 400, "C")])
        metrics = result["totals"]
        self.assertEqual(metrics["matched_signs"], 2)
        self.assertEqual(metrics["matched_gloss_accuracy"], 0.5)
        self.assertAlmostEqual(metrics["mean_matched_temporal_iou"], (90/110+1)/2)
        self.assertEqual(metrics["onset_error"]["mean_signed_ms"], 5)
        self.assertEqual(metrics["end_error"]["mean_absolute_ms"], 5)
        self.assertEqual(metrics["gloss_sequence"]["substitutions"], 1)

    def test_global_cardinality_beats_greedy_iou(self):
        result = evaluate([interval(0, 100, "A"), interval(100, 200, "B")],
                          [interval(0, 130, "B"), interval(0, 20, "A")], 0.1)
        pairs = [(x["reference_index"], x["event_index"]) for x in result["recordings"][0]["matches"]]
        self.assertEqual(pairs, [(0, 1), (1, 0)])
        self.assertEqual(result["totals"]["matched_gloss_accuracy"], 1)
        self.assertEqual(result["totals"]["gloss_sequence"]["distance"], 2)

    def test_matching_against_exhaustive_small_assignment(self):
        rng = random.Random(42)
        for _ in range(50):
            reference = [interval(i*100, i*100+90, str(i)) for i in range(3)]
            predicted = []
            for i in range(3):
                start = rng.randrange(250)
                predicted.append(interval(start, start+rng.randrange(1, 201), str(i)))
            actual = _match(reference, predicted, 0.1)
            best = (0, 0.0)
            for assignment in itertools.product(range(-1, 3), repeat=3):
                assigned = [j for j in assignment if j >= 0]
                if len(assigned) != len(set(assigned)):
                    continue
                scores = [temporal_iou(reference[i], predicted[j]) for i,j in enumerate(assignment) if j >= 0]
                if any(s < 0.1 for s in scores):
                    continue
                best = max(best, (len(scores), sum(scores)))
            self.assertEqual(len(actual), best[0])
            self.assertAlmostEqual(sum(s for _,_,s in actual), best[1])

    def test_missed_extra_rejected_and_closure_flags(self):
        result = evaluate([interval(0, 100, "A"), interval(200, 300, "B")],
                          [interval(0, 100, None, status="rejected", reason="capacity", quality_flags=["partial"]),
                           interval(500, 600, "X", reason="flush")])
        self.assertEqual(result["totals"]["matched_signs"], 1)
        self.assertEqual(result["totals"]["missed_signs"], 1)
        self.assertEqual(result["totals"]["extra_intervals"], 1)
        self.assertEqual(result["totals"]["matched_gloss_accuracy"], 0)
        self.assertEqual(result["totals"]["gloss_sequence"]["distance"], 2)
        self.assertEqual(result["status_counts"], {"rejected": 1, "predicted": 1})
        self.assertEqual(result["quality_flag_counts"], {"partial": 1})
        self.assertEqual(result["closure_reason_counts"], {"capacity": 1, "flush": 1})

    def test_empty_reference_and_predictions(self):
        empty = evaluate([], [])["totals"]
        self.assertIsNone(empty["interval_f1"])
        self.assertIsNone(empty["gloss_sequence"]["error_rate"])
        self.assertEqual(empty["gloss_sequence"]["distance"], 0)
        inserted = evaluate([], [interval(1, 2, "A")])["totals"]
        self.assertEqual(inserted["extra_intervals"], 1)
        self.assertEqual(inserted["gloss_sequence"]["insertions"], 1)
        self.assertIsNone(inserted["gloss_sequence"]["error_rate"])
        absent = evaluate_events(annotation(), {})
        self.assertEqual(absent["totals"]["missed_signs"], 1)
        self.assertEqual(absent["missing_prediction_recordings"], ["synthetic-1"])
        self.assertEqual(absent["totals"]["gloss_sequence"]["deletions"], 1)

    def test_edits_known_counts_and_tie_break(self):
        edits = gloss_edit_counts(["A", "B", "C"], ["A", "X", "C", "D"])
        self.assertEqual((edits["substitutions"], edits["deletions"], edits["insertions"]), (1, 0, 1))
        self.assertEqual(edits["error_rate"], 2/3)
        self.assertEqual(gloss_edit_counts(["A", "B"], ["B", "A"])["substitutions"], 2)
        self.assertEqual(gloss_edit_counts(["A", "B"], ["B"])["deletions"], 1)
        self.assertEqual(gloss_edit_counts([], ["B"])["insertions"], 1)

    def test_zero_duration_event_is_unmatched(self):
        result = evaluate([interval(0, 100, "A")], [interval(0, 0, "A")])
        self.assertEqual(result["totals"]["matched_signs"], 0)
        self.assertEqual(result["totals"]["gloss_sequence"]["distance"], 0)
        self.assertEqual(temporal_iou(interval(0, 1e308, "A"), interval(0, 1e308, "A")), 1)

    def test_response_conversion_and_cached_retry(self):
        reply = dict(type="result", request_id="r1", replayed=False,
                     events=[dict(start_ms=0, end_ms=100, status="predicted", reason="gap", prediction={"label": "A"})])
        events = events_from_responses([{"type": "ready"}, reply, dict(reply, replayed=True)])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["label"], "A")
        self.assertEqual(events[0]["reason"], "gap")
        self.assertEqual(events_from_responses({"responses": [reply]}), events)
        for replies in ([dict(reply, replayed=True)], [reply, reply], [reply, {"type": "error"}]):
            with self.assertRaises(ValueError):
                events_from_responses(replies)

    def test_annotations_invalid_values_and_source_leakage(self):
        for value in (float("nan"), float("inf"), -1, True, "1", 10**1000):
            with self.subTest(value=repr(value)[:30]), self.assertRaises(ValueError):
                validate_annotations(annotation([interval(value, 100, "A")]))
        for signs in ([interval(0, 0, "A")], [interval(0, 10, "")],
                      [interval(5, 15, "A"), interval(10, 20, "B")]):
            with self.assertRaises(ValueError):
                validate_annotations(annotation(signs))
        bad = annotation()
        row = copy.deepcopy(bad["recordings"][0])
        row.update(recording_id="other", split_role="test")
        bad["recordings"].append(row)
        with self.assertRaisesRegex(ValueError, "multiple split roles"):
            validate_annotations(bad)
        bad = annotation()
        bad["recordings"][0]["speaker_identity"] = {"status": "verified", "id": "s1"}
        with self.assertRaisesRegex(ValueError, "evidence"):
            validate_annotations(bad)

    def test_speaker_overlap_reported_not_inferred_from_group(self):
        doc = annotation()
        doc["recordings"][0]["speaker_identity"] = {"status": "verified", "id": "s1", "evidence": "synthetic fixture"}
        row = copy.deepcopy(doc["recordings"][0])
        row.update(recording_id="other", source_group="other-group", split_role="test")
        doc["recordings"].append(row)
        result = evaluate_events(doc, {})
        self.assertEqual(result["verified_speaker_split_overlap"], {"s1": ["demo", "test"]})

    def test_invalid_predictions_unknown_recording_and_threshold(self):
        with self.assertRaises(ValueError):
            evaluate_events(annotation(), {"not-annotated": []})
        for threshold in (0, -1, 2, True, float("nan")):
            with self.assertRaises(ValueError):
                evaluate_events(annotation(), {}, threshold)
        for items in ([interval(100, 150, "A"), interval(0, 50, "B")],
                      [interval(0, 100, "A", status="rejected")],
                      [interval(0, 100, "A", quality_flags="partial")]):
            with self.assertRaises(ValueError):
                evaluate_events(annotation(), {"synthetic-1": items})


if __name__ == "__main__":
    unittest.main()
