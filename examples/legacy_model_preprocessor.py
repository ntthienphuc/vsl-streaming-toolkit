"""Bridge to the owner's separately installed VSL preprocessing code.

No legacy normalization/architecture implementation is copied here. Configure
source hashes for this module AND the original preprocessing files. The
original source and model retain their own rights. This example supports the
existing SPOTER and SL-GCN input contracts; it does not bundle their code.
"""
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np


def prepare(frames, profile, legacy_server_root, backend):
    root = str(Path(legacy_server_root).resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    def landmarks(value):
        if value is None:
            return None
        return SimpleNamespace(landmark=[SimpleNamespace(**point) for point in value])
    converted = [SimpleNamespace(**{key: landmarks(frame.get(key)) for key in
                 ("pose_landmarks", "left_hand_landmarks", "right_hand_landmarks")}) for frame in frames]
    if backend == "spoter":
        from pipelines import spoter_onnx_inference as source
        transforms = (source.JointSelect(), source.Pad(profile["num_frames"]), source.TensorToDict(),
                      source.SingleBodyDictNormalize(), source.SingleHandDictNormalize(),
                      source.DictToTensor(), source.Shift())
        tensor = converted
        for transform in transforms:
            tensor = transform(tensor)
        return np.asarray(tensor, dtype=np.float32)[None]
    if backend == "slgcn":
        from pipelines.slgcn_onnx_inference import SLGCNONNXInferer
        preparation = SLGCNONNXInferer.__new__(SLGCNONNXInferer)
        preparation.num_frames = profile["num_frames"]
        preparation.min_sequence_frames = 30
        preparation.motion_stream = False
        return preparation.preprocess(converted)
    raise ValueError("Supported legacy backends: spoter, slgcn")
