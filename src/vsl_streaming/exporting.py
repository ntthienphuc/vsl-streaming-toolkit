"""Optional PyTorch-to-ONNX export with fixed-probe numerical parity."""
from __future__ import annotations

import importlib
from pathlib import Path
import tempfile

import numpy as np

from .bundle import (_publish_bundle, _read_json, check_logits, check_session, sha256,
                     create_session, input_shape, validate_labels, validate_profile)


def export_pytorch(factory: str, checkpoint_path, labels_path, profile_path,
                   output_dir, model_kwargs: dict = None, overwrite=False,
                   validation_tensors_path=None) -> dict:
    """Load a trusted local factory and a weights-only state_dict checkpoint.

    Factories are executable Python supplied by the model owner. This function
    cannot infer architectures or reproduce unspecified training preprocessing.
    Parity on three fixed probes is an export smoke check, not dataset accuracy.
    """
    import torch
    import onnx

    labels = validate_labels(_read_json(labels_path))
    profile = validate_profile(_read_json(profile_path))
    if not isinstance(factory, str) or factory.count(":") != 1:
        raise ValueError("factory must be an importable module:function")
    module_name, function_name = factory.split(":")
    constructor = getattr(importlib.import_module(module_name), function_name)
    model = constructor(**(model_kwargs or {}))
    if not isinstance(model, torch.nn.Module):
        raise ValueError("factory must return torch.nn.Module")
    checkpoint = torch.load(str(checkpoint_path), map_location="cpu", weights_only=True)
    if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        checkpoint = checkpoint["state_dict"]
    model.load_state_dict(checkpoint, strict=True)
    model = model.cpu().eval()
    shape = input_shape(profile)
    rng = np.random.default_rng(20261003)
    probes = [np.zeros(shape, dtype=np.float32), np.ones(shape, dtype=np.float32),
              rng.normal(0, 0.25, size=shape).astype(np.float32)]
    validation_hash = None
    if validation_tensors_path is not None:
        # Samples must already have the exact training preprocessing applied.
        # No object deserialization and no claim about label accuracy is made.
        with np.load(validation_tensors_path, allow_pickle=False) as archive:
            if set(archive.files) != {"inputs"}:
                raise ValueError("Validation NPZ must contain only the 'inputs' array")
            samples = archive["inputs"]
        if (samples.dtype != np.float32 or samples.ndim != len(shape)
                or samples.shape[1:] != shape[1:] or not 1 <= len(samples) <= 10000
                or not np.isfinite(samples).all()):
            raise ValueError("Validation inputs must be finite float32 [samples, *model_input_without_batch]")
        probes.extend(samples[index:index + 1] for index in range(len(samples)))
        validation_hash = sha256(validation_tensors_path)
    with tempfile.TemporaryDirectory(prefix="vsl-export-") as temporary:
        model_path = Path(temporary) / "model.onnx"
        with torch.inference_mode():
            torch.onnx.export(model, torch.from_numpy(probes[0]), str(model_path),
                              input_names=[profile["input_name"]], output_names=[profile["output_name"]],
                              opset_version=17, do_constant_folding=True, dynamo=False)
        graph = onnx.load(str(model_path))
        onnx.checker.check_model(graph)
        session = create_session(model_path)
        check_session(session, profile, labels)
        errors = []
        with torch.inference_mode():
            for index, probe in enumerate(probes):
                source = model(torch.from_numpy(probe))
                if not isinstance(source, torch.Tensor):
                    raise ValueError("Factory must expose one logits tensor; wrap tuple/dict outputs")
                reference = source.detach().cpu().numpy()
                actual = session.run([profile["output_name"]], {profile["input_name"]: probe})[0]
                check_logits(reference, len(labels))
                check_logits(actual, len(labels))
                error = float(np.max(np.abs(reference - actual)))
                errors.append(error)
                if not np.allclose(reference, actual, atol=1e-5, rtol=1e-4) or not np.array_equal(reference.argmax(axis=1), actual.argmax(axis=1)):
                    raise ValueError("ONNX export parity failed on fixed probe %d (max absolute error %g)" % (index, error))
        del session
        parity = {"status": "passed", "scope": ("three synthetic tensors plus user-supplied tensors; source/export agreement only"
                  if validation_hash else "three fixed synthetic tensors; not real-data validation"),
                  "probe_seed": 20261003, "num_probes": len(probes),
                  "num_user_tensors": len(probes) - 3, "validation_npz_sha256": validation_hash,
                  "atol": 1e-5, "rtol": 1e-4,
                  "argmax_agreement": True, "max_absolute_error": max(errors),
                  "torch_version": torch.__version__, "onnx_version": onnx.__version__, "opset": 17}
        return _publish_bundle(model_path, labels, profile, output_dir, parity, overwrite)
