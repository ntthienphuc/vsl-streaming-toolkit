"""Strict JSON configuration for local deployment."""
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from .core import StreamConfig


@dataclass(frozen=True)
class ServerConfig:
    stream: StreamConfig = field(default_factory=StreamConfig)
    provider: str = "CPUExecutionProvider"
    top_k: int = 3
    max_sessions: int = 32
    max_batch_frames: int = 120
    max_message_bytes: int = 2_000_000
    request_cache_size: int = 64
    inference_concurrency: int = 1

    def __post_init__(self):
        for name in ("top_k", "max_sessions", "max_batch_frames", "max_message_bytes",
                     "request_cache_size", "inference_concurrency"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(name + " must be a positive integer")
        if not isinstance(self.stream, StreamConfig):
            raise ValueError("stream must be StreamConfig")
        if not isinstance(self.provider, str) or not self.provider:
            raise ValueError("provider must be a nonempty provider name")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("server config must be an object")
        fields = cls.__dataclass_fields__
        unknown = set(value) - set(fields)
        if unknown:
            raise ValueError("Unknown server config: " + ", ".join(sorted(unknown)))
        raw = dict(value)
        if "stream" in raw:
            if not isinstance(raw["stream"], dict):
                raise ValueError("stream config must be an object")
            raw["stream"] = StreamConfig(**raw["stream"])
        return cls(**raw)


def load_config(path=None):
    if path is None:
        return ServerConfig()
    return ServerConfig.from_dict(json.loads(Path(path).read_text(encoding="utf-8-sig")))
