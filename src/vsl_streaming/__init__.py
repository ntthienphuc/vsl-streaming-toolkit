"""Keypoint stream segmentation and model deployment contracts."""
from .core import ProtocolError, Segment, StreamConfig, StreamSession

__version__ = "0.1.2"
__all__ = ["ProtocolError", "Segment", "StreamConfig", "StreamSession"]
