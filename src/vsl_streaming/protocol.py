"""Transport-independent messages. One processor per connection/replay."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import time
from .config import ServerConfig
from .core import ProtocolError, StreamSession


def decode_message(text, max_bytes):
    if len(text.encode("utf-8")) > max_bytes:
        raise ProtocolError("message_too_large", "message exceeds configured byte limit")
    def invalid_constant(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    try:
        message = json.loads(text, parse_constant=invalid_constant, object_pairs_hook=unique_object)
        json.dumps(message, allow_nan=False, ensure_ascii=False).encode("utf-8")
        return message
    except (ValueError, RecursionError) as error:
        raise ProtocolError("invalid_json", str(error)) from None


def error_response(error, request_id=None):
    if not isinstance(request_id, str):
        request_id = None
    elif request_id is not None:
        try:
            request_id.encode("utf-8")
        except UnicodeError:
            request_id = None
    return {"type": "error", "request_id": request_id,
            "error": {"code": error.code, "message": error.message}}


class MessageProcessor:
    """Caches recent exact requests. Predictions are at-most-once per cached ID.

    This is a connection-local retry cache, not durable exactly-once delivery.
    A segment inference failure is returned explicitly; it is never classified
    as successful or silently removed from the response.
    """
    def __init__(self, recognizer, config=None):
        self.config = config or ServerConfig()
        self.session = StreamSession(self.config.stream)
        self.recognizer = recognizer
        self.cache = OrderedDict()

    def process(self, message):
        request_id = None
        try:
            if not isinstance(message, dict):
                raise ProtocolError("invalid_message", "message must be an object")
            request_id = message.get("request_id")
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                raise ProtocolError("invalid_request_id", "request_id must be a string of length 1..128")
            try:
                request_id.encode("utf-8")
            except UnicodeError:
                raise ProtocolError("invalid_request_id", "request_id must be valid UTF-8 text") from None
            try:
                serialized = json.dumps(message, sort_keys=True, allow_nan=False, separators=(",", ":"))
            except (ValueError, TypeError, RecursionError):
                raise ProtocolError("invalid_json", "message must contain finite JSON values") from None
            digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            if request_id in self.cache:
                previous_digest, previous = self.cache[request_id]
                if digest != previous_digest:
                    raise ProtocolError("request_id_conflict", "request_id was already used for a different request")
                self.cache.move_to_end(request_id)
                return dict(deepcopy(previous), replayed=True)
            kind = message.get("type")
            fields = {"type", "request_id"}
            if kind == "frames":
                fields |= {"frames", "flush"}
            elif kind not in ("flush", "reset", "status"):
                raise ProtocolError("invalid_type", "type must be frames, flush, reset, or status")
            if set(message) - fields:
                raise ProtocolError("unknown_field", "message contains undeclared fields")
            segments = []
            started = time.perf_counter()
            if kind == "frames":
                frames = message.get("frames")
                if not isinstance(frames, list) or not frames:
                    raise ProtocolError("invalid_frames", "frames must be a nonempty list")
                if len(frames) > self.config.max_batch_frames:
                    raise ProtocolError("batch_too_large", "batch exceeds configured frame limit")
                flush = message.get("flush", False)
                if type(flush) is not bool:
                    raise ProtocolError("invalid_flush", "flush must be a boolean")
                segments = self.session.push_batch(frames)
                if flush:
                    segments.extend(self.session.flush())
            elif kind == "flush":
                segments = self.session.flush()
            elif kind == "reset":
                self.session.reset()
            events = []
            for segment in segments:
                event = segment.to_dict(include_frames=False)
                inference_started = time.perf_counter()
                try:
                    event["prediction"] = self.recognizer.predict_segment(segment.frames)
                    if not isinstance(event["prediction"], dict):
                        raise ValueError("recognizer must return a JSON prediction object")
                    json.dumps(event["prediction"], allow_nan=False, ensure_ascii=False).encode("utf-8")
                    event["status"] = "predicted"
                except Exception as error:
                    event.pop("prediction", None)
                    event["status"] = "rejected"
                    # A model adapter may raise arbitrary text. Keep even the
                    # failure event serializable as UTF-8, and bound its size.
                    detail = str(error).encode("utf-8", errors="replace").decode("utf-8")[:2000]
                    event["error"] = {"code": "inference_failed", "message": detail}
                event["inference_ms"] = (time.perf_counter() - inference_started) * 1000
                events.append(event)
            response = {"type": "result", "request_id": request_id, "replayed": False,
                        "events": events, "state": self.session.status(),
                        "processing_ms": (time.perf_counter() - started) * 1000}
            self.cache[request_id] = (digest, deepcopy(response))
            while len(self.cache) > self.config.request_cache_size:
                self.cache.popitem(last=False)
            return response
        except ProtocolError as error:
            return error_response(error, request_id)
