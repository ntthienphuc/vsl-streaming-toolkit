"""Keypoint stream segmentation and model deployment contracts."""
from .core import ProtocolError, Segment, StreamConfig, StreamSession

__version__ = "0.2.1"
__all__ = ["ProtocolError", "Segment", "StreamConfig", "StreamSession"]
