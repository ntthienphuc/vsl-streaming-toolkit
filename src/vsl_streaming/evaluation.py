"""Offline, annotation-based word-event evaluation; no inference dependencies.

Matching maximizes cardinality first and summed temporal IoU second. Labels do
not influence temporal matching. All emitted intervals, including rejected or
capacity/flush-closed intervals, remain in the primary evaluation.
"""
from collections import Counter
from math import isfinite
from statistics import mean, median


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " must be a nonempty string")
    return value


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be a finite nonnegative number")
    try:
        value = float(value)
    except OverflowError:
        raise ValueError(name + " must be finite") from None
    if not isfinite(value) or value < 0:
        raise ValueError(name + " must be a finite nonnegative number")
    return value


def _interval(value, annotation=False):
    if not isinstance(value, dict):
        raise ValueError("interval must be an object")
    start = _number(value.get("start_ms"), "start_ms")
    end = _number(value.get("end_ms"), "end_ms")
    if end < start or (annotation and end == start):
        raise ValueError("end_ms must follow start_ms; annotations require positive duration")
    result = {"start_ms": start, "end_ms": end}
    if annotation:
        result["label"] = _text(value.get("label"), "label")
    else:
        status = value.get("status", "predicted")
        if status not in ("predicted", "rejected"):
            raise ValueError("event status must be predicted or rejected")
        label = value.get("label")
        if status == "predicted":
            label = _text(label, "predicted label")
        elif label is not None:
            raise ValueError("rejected event cannot carry a predicted label")
        flags = value.get("quality_flags", [])
        if not isinstance(flags, list) or any(not isinstance(x, str) or not x.strip() for x in flags):
            raise ValueError("quality_flags must be a list of nonempty strings")
        result.update(label=label, status=status,
                      reason=_text(value.get("reason", "unspecified"), "reason"),
                      quality_flags=sorted(set(flags)))
    return result


def validate_annotations(document):
    """Validate schema v1; reject source-group leakage and ambiguous ordering.

    Speaker verification is a supplied provenance assertion, never inferred
    from source-group IDs. Its evidence must be provided for a verified ID.
    """
    if not isinstance(document, dict) or type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise ValueError("annotation schema_version must be 1")
    scope = document.get("scope")
    if scope not in ("synthetic", "research"):
        raise ValueError("scope must be synthetic or research")
    rows = document.get("recordings")
    if not isinstance(rows, list):
        raise ValueError("recordings must be a list")
    recordings, seen, group_roles = [], set(), {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("recording must be an object")
        rid = _text(row.get("recording_id"), "recording_id")
        if rid in seen:
            raise ValueError("duplicate recording_id: " + rid)
        seen.add(rid)
        role = row.get("split_role")
        if role not in ("train", "validation", "test", "demo"):
            raise ValueError("split_role must be train, validation, test, or demo")
        group = _text(row.get("source_group"), "source_group")
        if group in group_roles and group_roles[group] != role:
            raise ValueError("source_group occurs in multiple split roles: " + group)
        group_roles[group] = role
        speaker = row.get("speaker_identity")
        if not isinstance(speaker, dict) or speaker.get("status") not in ("verified", "unverified"):
            raise ValueError("speaker_identity requires verified or unverified status")
        identity = {"status": speaker["status"]}
        if speaker["status"] == "verified":
            identity.update(id=_text(speaker.get("id"), "speaker id"),
                            evidence=_text(speaker.get("evidence"), "speaker verification evidence"))
        elif speaker.get("id") is not None:
            raise ValueError("unverified speaker must not carry a verified id")
        annotations = row.get("annotations")
        if not isinstance(annotations, list):
            raise ValueError("annotations must be a list")
        annotations = [_interval(a, annotation=True) for a in annotations]
        for previous, current in zip(annotations, annotations[1:]):
            if current["start_ms"] < previous["end_ms"]:
                raise ValueError("annotations must be chronological and nonoverlapping")
        recordings.append(dict(recording_id=rid, split_role=role, source_group=group,
                               speaker_identity=identity, annotations=annotations))
    return dict(schema_version=1, scope=scope, recordings=recordings)


def events_from_responses(responses):
    """Convert ordered MessageProcessor/WS result responses into event intervals.

    Pass one recording/session at a time. Explicit cached retransmissions are
    checked against their original response and not double counted. Protocol
    errors raise instead of silently producing a partial accuracy report.
    """
    if isinstance(responses, dict) and "responses" in responses:
        responses = responses["responses"]
    if not isinstance(responses, list):
        raise ValueError("responses must be a list or replay receipt with responses")
    events, requests = [], {}
    ready_seen, result_seen = False, False
    previous_received, last_buffered = None, None
    for response in responses:
        if not isinstance(response, dict):
            raise ValueError("response must be an object")
        if response.get("type") == "ready":
            if ready_seen or result_seen:
                raise ValueError("evaluate one recording/session at a time; unexpected ready response")
            ready_seen = True
            continue
        if response.get("type") != "result":
            raise ValueError("cannot evaluate an incomplete/error response stream")
        result_seen = True
        rid = _text(response.get("request_id"), "request_id")
        items = response.get("events")
        if not isinstance(items, list):
            raise ValueError("result events must be a list")
        converted = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("event must be an object")
            prediction = item.get("prediction", {})
            if not isinstance(prediction, dict):
                raise ValueError("prediction must be an object")
            converted.append(_interval(dict(item, label=prediction.get("label"))))
        replayed = response.get("replayed", False)
        if type(replayed) is not bool:
            raise ValueError("replayed must be boolean")
        if replayed:
            if rid not in requests or requests[rid] != converted:
                raise ValueError("cached reply lacks matching original result")
            continue
        if rid in requests:
            raise ValueError("duplicate result request_id without replayed=true")
        state = response.get("state")
        if state is not None:
            if not isinstance(state, dict):
                raise ValueError("result state must be an object")
            received, buffered = state.get("received_frames"), state.get("buffered_frames")
            if any(type(value) is not int or value < 0 for value in (received, buffered)):
                raise ValueError("result state requires nonnegative received_frames and buffered_frames")
            if buffered > received:
                raise ValueError("buffered_frames cannot exceed received_frames")
            if previous_received is not None and received < previous_received:
                raise ValueError("recording state restarted; evaluate sessions separately")
            previous_received = received
            last_buffered = buffered
        else:
            last_buffered = None  # Missing state cannot certify stream completion.
        requests[rid] = converted
        events.extend(converted)
    if last_buffered:
        raise ValueError("cannot evaluate an incomplete response stream with buffered frames; flush first")
    return events


def temporal_iou(a, b):
    """Continuous-time IoU; zero-duration emitted events have IoU zero."""
    overlap = max(0.0, min(a["end_ms"], b["end_ms"]) - max(a["start_ms"], b["start_ms"]))
    if overlap <= 0:
        return 0.0
    # For overlapping intervals their union is the enclosing interval. Avoid
    # adding two large, finite durations and overflowing before subtraction.
    union = max(a["end_ms"], b["end_ms"]) - min(a["start_ms"], b["start_ms"])
    return overlap / union


def _match(reference, predicted, threshold):
    # Successive shortest augmenting paths: maximum flow fixes cardinality;
    # negative-IoU edge costs then minimize total cost for that cardinality.
    # Bellman-Ford also handles reverse residual edges without scipy.
    n, m = len(reference), len(predicted)
    source, sink = n + m, n + m + 1
    graph = [[] for _ in range(n + m + 2)]

    def edge(a, b, cost):
        forward = [b, len(graph[b]), 1, cost]
        reverse = [a, len(graph[a]), 0, -cost]
        graph[a].append(forward)
        graph[b].append(reverse)
        return forward

    for i in range(n):
        edge(source, i, 0.0)
    for j in range(m):
        edge(n + j, sink, 0.0)
    links = []
    for i, a in enumerate(reference):
        for j, b in enumerate(predicted):
            score = temporal_iou(a, b)
            if score >= threshold:
                links.append((i, j, score, edge(i, n + j, -score)))
    while True:
        distance, previous = [float("inf")] * len(graph), [None] * len(graph)
        distance[source] = 0.0
        for _ in range(len(graph) - 1):
            changed = False
            for node, arcs in enumerate(graph):
                if distance[node] == float("inf"):
                    continue
                for k, arc in enumerate(arcs):
                    target, _, capacity, cost = arc
                    if capacity and distance[node] + cost < distance[target] - 1e-12:
                        distance[target] = distance[node] + cost
                        previous[target] = (node, k)
                        changed = True
            if not changed:
                break
        if previous[sink] is None:
            break
        node = sink
        while node != source:
            parent, k = previous[node]
            arc = graph[parent][k]
            arc[2] -= 1
            graph[node][arc[1]][2] += 1
            node = parent
    return [(i, j, score) for i, j, score, arc in links if arc[2] == 0]


def gloss_edit_counts(reference, hypothesis):
    """Unit-cost Levenshtein counts with deterministic S, D, I tie priority."""
    if not isinstance(reference, list) or not isinstance(hypothesis, list):
        raise ValueError("gloss sequences must be lists")
    for token in reference + hypothesis:
        _text(token, "gloss token")
    n, m = len(reference), len(hypothesis)
    costs = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        costs[i][0] = i
    for j in range(m + 1):
        costs[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            costs[i][j] = min(costs[i - 1][j - 1] + (reference[i - 1] != hypothesis[j - 1]),
                              costs[i - 1][j] + 1, costs[i][j - 1] + 1)
    counts = dict(substitutions=0, deletions=0, insertions=0)
    i, j = n, m
    while i or j:
        if i and j and reference[i - 1] == hypothesis[j - 1] and costs[i][j] == costs[i - 1][j - 1]:
            i, j = i - 1, j - 1
        elif i and j and costs[i][j] == costs[i - 1][j - 1] + 1:
            counts["substitutions"] += 1
            i, j = i - 1, j - 1
        elif i and costs[i][j] == costs[i - 1][j] + 1:
            counts["deletions"] += 1
            i -= 1
        else:
            counts["insertions"] += 1
            j -= 1
    return dict(counts, distance=sum(counts.values()), reference_tokens=n, hypothesis_tokens=m,
                error_rate=sum(counts.values()) / n if n else None)


def _timing(values):
    return dict(mean_signed_ms=mean(values) if values else None,
                mean_absolute_ms=mean(abs(x) for x in values) if values else None,
                median_absolute_ms=median(abs(x) for x in values) if values else None)


def _summary(n, m, correct, edits, onsets, offsets, ious):
    k = len(ious)
    return dict(reference_signs=n, emitted_intervals=m, matched_signs=k,
                missed_signs=n-k, extra_intervals=m-k,
                interval_precision=k/m if m else None, interval_recall=k/n if n else None,
                interval_f1=2*k/(n+m) if n+m else None,
                matched_gloss_correct=correct, matched_gloss_accuracy=correct/k if k else None,
                mean_matched_temporal_iou=mean(ious) if ious else None,
                onset_error=_timing(onsets), end_error=_timing(offsets), gloss_sequence=edits)


def evaluate_events(annotation_document, predictions_by_recording, iou_threshold=0.5):
    """Return per-recording and micro-aggregated event/sequence metrics.

    Missing prediction keys mean zero events, so their references are counted
    as misses. Unknown recording IDs raise. Input event order must already be
    chronological; sorting malformed logs silently would hide transport bugs.
    """
    document = validate_annotations(annotation_document)
    threshold = _number(iou_threshold, "iou_threshold")
    if not 0 < threshold <= 1:
        raise ValueError("iou_threshold must be in (0, 1]")
    if not isinstance(predictions_by_recording, dict):
        raise ValueError("predictions_by_recording must be an object")
    ids = {row["recording_id"] for row in document["recordings"]}
    if set(predictions_by_recording) - ids:
        raise ValueError("predictions contain unknown recording IDs")
    rows, all_onsets, all_offsets, all_ious = [], [], [], []
    totals = Counter()
    closures, quality, statuses = Counter(), Counter(), Counter()
    speaker_roles = {}
    for recording in document["recordings"]:
        rid = recording["recording_id"]
        items = predictions_by_recording.get(rid, [])
        if not isinstance(items, list):
            raise ValueError("recording predictions must be a list")
        predicted = [_interval(item) for item in items]
        if any(b["start_ms"] < a["start_ms"] for a, b in zip(predicted, predicted[1:])):
            raise ValueError("predicted events must be chronological")
        reference = recording["annotations"]
        matches = _match(reference, predicted, threshold)
        onsets = [predicted[j]["start_ms"]-reference[i]["start_ms"] for i,j,_ in matches]
        offsets = [predicted[j]["end_ms"]-reference[i]["end_ms"] for i,j,_ in matches]
        ious = [score for _,_,score in matches]
        correct = sum(predicted[j]["label"] == reference[i]["label"] for i,j,_ in matches)
        edit = gloss_edit_counts([r["label"] for r in reference],
                                 [p["label"] for p in predicted if p["status"] == "predicted"])
        metrics = _summary(len(reference), len(predicted), correct, edit, onsets, offsets, ious)
        reasons = Counter(p["reason"] for p in predicted)
        flags = Counter(flag for p in predicted for flag in p["quality_flags"])
        states = Counter(p["status"] for p in predicted)
        rows.append(dict(recording_id=rid, split_role=recording["split_role"],
                         metrics=metrics, closure_reason_counts=dict(reasons), quality_flag_counts=dict(flags),
                         status_counts=dict(states),
                         matches=[dict(reference_index=i, event_index=j, temporal_iou=s,
                                       onset_error_ms=predicted[j]["start_ms"]-reference[i]["start_ms"],
                                       end_error_ms=predicted[j]["end_ms"]-reference[i]["end_ms"],
                                       gloss_correct=predicted[j]["label"] == reference[i]["label"])
                                  for i,j,s in matches]))
        totals.update(reference_signs=len(reference), emitted_intervals=len(predicted), correct=correct)
        totals.update({k: edit[k] for k in ("substitutions", "deletions", "insertions", "reference_tokens", "hypothesis_tokens")})
        all_onsets.extend(onsets)
        all_offsets.extend(offsets)
        all_ious.extend(ious)
        closures.update(reasons)
        quality.update(flags)
        statuses.update(states)
        speaker = recording["speaker_identity"]
        if speaker["status"] == "verified":
            speaker_roles.setdefault(speaker["id"], set()).add(recording["split_role"])
    edits = {k: totals[k] for k in ("substitutions", "deletions", "insertions", "reference_tokens", "hypothesis_tokens")}
    edits["distance"] = sum(edits[k] for k in ("substitutions", "deletions", "insertions"))
    edits["error_rate"] = edits["distance"] / edits["reference_tokens"] if edits["reference_tokens"] else None
    return dict(schema_version=1, scope=document["scope"], iou_threshold=threshold,
                matching="maximum-cardinality-then-maximum-summed-temporal-iou",
                aggregation="micro across supplied recordings; report split-specific runs separately",
                primary_event_policy="all emitted intervals, including rejected, flush, gap and capacity closures",
                totals=_summary(totals["reference_signs"], totals["emitted_intervals"], totals["correct"],
                                edits, all_onsets, all_offsets, all_ious),
                closure_reason_counts=dict(closures), quality_flag_counts=dict(quality), status_counts=dict(statuses),
                recording_count=len(rows), missing_prediction_recordings=sorted(ids-set(predictions_by_recording)),
                verified_speaker_split_overlap={s: sorted(roles) for s,roles in sorted(speaker_roles.items()) if len(roles)>1},
                recordings=rows)
