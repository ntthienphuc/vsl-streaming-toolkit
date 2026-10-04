"""Versioned model artifacts and their input/label contract.

Hashes detect accidental edits; they are not a signature of model provenance.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict

import numpy as np

SCHEMA_VERSION = 1
ARTIFACTS = ("model.onnx", "labels.json", "profile.json")


def _read_json(path):
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_profile(profile):
    if not isinstance(profile, dict) or profile.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("profile.schema_version must be 1")
    required = {"schema_version", "input_name", "output_name", "layout", "num_frames", "num_points", "num_channels", "preprocessing"}
    missing = required - profile.keys()
    if missing:
        raise ValueError("Missing profile fields: " + ", ".join(sorted(missing)))
    unknown = profile.keys() - required - {"temporal_sampling"}
    if unknown:
        raise ValueError("Unknown profile fields: " + ", ".join(sorted(unknown)))
    for key in ("input_name", "output_name"):
        if not isinstance(profile[key], str) or not profile[key].strip():
            raise ValueError(key + " must be a nonempty string")
    for key in ("num_frames", "num_points", "num_channels"):
        if type(profile[key]) is not int or not 1 <= profile[key] <= 10000:
            raise ValueError(key + " must be an integer in [1, 10000]")
    if profile["layout"] not in ("BTVC", "BCTVM"):
        raise ValueError("layout must be BTVC or BCTVM")
    preprocessing = profile["preprocessing"]
    if not isinstance(preprocessing, dict) or set(preprocessing) != {"name", "config"}:
        raise ValueError("preprocessing must contain exactly name and config")
    if preprocessing["name"] not in ("identity-v1", "mediapipe49-shoulder-v1", "external-python-v1"):
        raise ValueError("Unsupported preprocessing name")
    sampling = "external-python-v1" if preprocessing["name"] == "external-python-v1" else "uniform-nearest-v1"
    if profile.get("temporal_sampling", sampling) != sampling:
        raise ValueError("temporal_sampling must match the selected preprocessing contract: " + sampling)
    if sampling == "external-python-v1":
        config = preprocessing["config"]
        if not isinstance(config, dict) or set(config) != {"factory", "source_sha256", "kwargs", "source_dependencies"}:
            raise ValueError("External preprocessing config requires factory, source_sha256, kwargs, source_dependencies")
        if not isinstance(config["factory"], str) or config["factory"].count(":") != 1:
            raise ValueError("External factory must be module:function")
        if not isinstance(config["kwargs"], dict) or not isinstance(config["source_dependencies"], dict):
            raise ValueError("External kwargs and source_dependencies must be objects")
        hashes = [config["source_sha256"]] + list(config["source_dependencies"].values())
        if any(not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest) for digest in hashes):
            raise ValueError("External source hashes must be lowercase SHA-256 strings")
        if any(not isinstance(path, str) or not path for path in config["source_dependencies"]):
            raise ValueError("External source dependency paths must be nonempty strings")
    elif preprocessing["config"] != {}:
        raise ValueError("v1 preprocessing config must be {}; unknown options are rejected")
    if preprocessing["name"] == "mediapipe49-shoulder-v1" and (profile["num_points"], profile["num_channels"]) != (49, 2):
        raise ValueError("mediapipe49-shoulder-v1 requires 49 points and 2 xy channels")
    canonical = dict(profile)
    canonical["temporal_sampling"] = sampling
    return canonical


def validate_labels(labels):
    if not isinstance(labels, list) or not labels or any(not isinstance(label, str) or not label.strip() for label in labels):
        raise ValueError("labels must be an ordered nonempty JSON list of nonempty strings")
    if len(set(labels)) != len(labels):
        raise ValueError("labels must be unique; class order is significant")
    return labels


def input_shape(profile):
    t, v, c = (profile[key] for key in ("num_frames", "num_points", "num_channels"))
    return (1, t, v, c) if profile["layout"] == "BTVC" else (1, c, t, v, 1)


def create_session(model_path, provider="CPUExecutionProvider"):
    import onnxruntime as ort

    if provider not in ort.get_available_providers():
        raise ValueError("Requested ONNX provider is unavailable: " + provider)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    if provider != "CPUExecutionProvider":
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
    session = ort.InferenceSession(str(model_path), sess_options=options, providers=[provider])
    session.disable_fallback()
    if session.get_providers()[0] != provider:
        raise ValueError("ONNX Runtime did not activate requested provider: " + provider)
    return session


def check_session(session, profile, labels):
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if len(inputs) != 1 or inputs[0].name != profile["input_name"]:
        raise ValueError("Model must have exactly the declared input")
    expected = input_shape(profile)
    actual = inputs[0].shape
    if inputs[0].type != "tensor(float)" or len(actual) != len(expected):
        raise ValueError("Model input must be float32 with declared layout rank")
    if any(isinstance(dim, int) and dim != target for dim, target in zip(actual, expected)):
        raise ValueError("Model input shape disagrees with profile: %s versus %s" % (actual, expected))
    selected = [output for output in outputs if output.name == profile["output_name"]]
    if len(selected) != 1 or selected[0].type != "tensor(float)" or len(selected[0].shape) != 2:
        raise ValueError("Declared output must be float32 logits shaped [batch, classes]")
    shape = selected[0].shape
    if any(isinstance(dim, int) and dim != target for dim, target in zip(shape, (1, len(labels)))):
        raise ValueError("Output class count/shape disagrees with ordered labels")
    # Also check dynamic dimensions and executable input compatibility.
    output = session.run([profile["output_name"]], {profile["input_name"]: np.zeros(expected, dtype=np.float32)})[0]
    check_logits(output, len(labels))


def check_logits(output, classes):
    if not isinstance(output, np.ndarray) or output.shape != (1, classes) or not np.isfinite(output).all():
        raise ValueError("Model must return finite logits shaped [1, number of labels]")


def validate_bundle(bundle_dir) -> Dict[str, Any]:
    directory = Path(bundle_dir)
    manifest = _read_json(directory / "manifest.json")
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("format") != "vsl-streaming-bundle":
        raise ValueError("Unsupported bundle format/version")
    if set(manifest.get("sha256", {})) != set(ARTIFACTS):
        raise ValueError("Manifest must hash model, ordered labels, and profile")
    for name in ARTIFACTS:
        if sha256(directory / name) != manifest["sha256"][name]:
            raise ValueError("Bundle checksum mismatch: " + name)
    labels = validate_labels(_read_json(directory / "labels.json"))
    profile = validate_profile(_read_json(directory / "profile.json"))
    if manifest.get("num_classes") != len(labels):
        raise ValueError("Manifest class count disagrees with labels")
    return {"manifest": manifest, "profile": profile, "labels": labels}


def _publish_bundle(model_path, labels, profile, output_dir, parity, overwrite=False):
    destination = Path(output_dir).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise FileExistsError("Bundle output already exists: " + str(destination))
    if destination.exists() and not (destination / "manifest.json").is_file():
        raise ValueError("Refusing to overwrite a directory that is not a bundle")
    if destination.exists():
        validate_bundle(destination)
        if any(path.name not in set(ARTIFACTS) | {"manifest.json"} for path in destination.iterdir()):
            raise ValueError("Refusing to overwrite a bundle directory containing extra files")
    staging = Path(tempfile.mkdtemp(prefix=".vsl-bundle-", dir=str(destination.parent)))
    backup = None
    try:
        shutil.copyfile(model_path, staging / "model.onnx")
        _write_json(staging / "labels.json", labels)
        _write_json(staging / "profile.json", profile)
        manifest = {"schema_version": SCHEMA_VERSION, "format": "vsl-streaming-bundle", "num_classes": len(labels),
                    "sha256": {name: sha256(staging / name) for name in ARTIFACTS}, "parity": parity}
        _write_json(staging / "manifest.json", manifest)
        validate_bundle(staging)
        if destination.exists():
            backup = Path(tempfile.mkdtemp(prefix=".vsl-backup-", dir=str(destination.parent)))
            backup.rmdir()
            os.replace(destination, backup)
        try:
            os.replace(staging, destination)
        except BaseException:
            if backup is not None:
                os.replace(backup, destination)
                backup = None
            raise
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup is not None and backup.exists():
            shutil.rmtree(backup)


def register_onnx(model_path, labels_path, profile_path, output_dir, overwrite=False) -> dict:
    import onnx

    labels = validate_labels(_read_json(labels_path))
    profile = validate_profile(_read_json(profile_path))
    model = onnx.load(str(model_path), load_external_data=False)
    if any(tensor.data_location == onnx.TensorProto.EXTERNAL for tensor in model.graph.initializer):
        raise ValueError("External-data ONNX models are unsupported; export a single-file model")
    onnx.checker.check_model(model)
    session = create_session(model_path)
    check_session(session, profile, labels)
    del session
    return _publish_bundle(model_path, labels, profile, output_dir,
                           {"status": "unverified", "reason": "Registered ONNX without source-framework outputs"}, overwrite)
