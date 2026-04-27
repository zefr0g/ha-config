#!/usr/bin/env python3
"""
Feature extraction + training script for microWakeWord "petit pois" model.
Run from ~/micro-wake-word with the venv activated.

Usage:
    python3 prepare_and_train.py --stage features   # extract spectrograms
    python3 prepare_and_train.py --stage train       # train model
    python3 prepare_and_train.py --stage all         # do both
"""

import argparse
import os
import subprocess
import sys
import yaml
import numpy as np
from pathlib import Path


def _extract_chunk(clips_batch, aug_params, step_ms, slide_frames):
    """Worker: augment + spectrogram + slide for a batch of raw audio arrays."""
    from microwakeword.audio.augmentation import Augmentation
    from microwakeword.audio.spectrograms import generate_features_for_clip
    aug = Augmentation(**aug_params)
    results = []
    for clip in clips_batch:
        aug_clip = aug.augment_clip(clip)
        spec = generate_features_for_clip(aug_clip, step_ms)
        spec_len = spec.shape[0] - slide_frames + 1
        slided = np.lib.stride_tricks.sliding_window_view(spec, (spec_len, spec.shape[1]))
        for i in range(slide_frames):
            results.append(np.squeeze(slided[i].copy()))
    return results

BASE = Path.home() / "micro-wake-word"
DATA = BASE / "data"
FEATURES_DIR = BASE / "generated_augmented_features"
NEG_DIR = BASE / "negative_datasets"
TRAINED_DIR = BASE / "trained_models/petit_pois"
MIC_SAMPLES_DIR = DATA / "positive" / "real_mic"

IMPULSE_PATHS = [str(BASE / "mit_rirs")]


def check_prerequisites():
    missing = []
    for d in [DATA / "positive" / "siwis", NEG_DIR / "speech", NEG_DIR / "dinner_party"]:
        if not d.exists() or not any(d.iterdir()):
            missing.append(str(d))
    if missing:
        print("ERROR: Missing required data directories:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    print(f"Positive samples found:")
    for sub in ["siwis", "tom", "upmc", "real_mic"]:
        p = DATA / "positive" / sub
        n = len(list(p.glob("*.wav"))) if p.exists() else 0
        print(f"  {sub}: {n}")

    # Warn if RIRs not ready — augmentation will fall back to color noise only
    rir_count = len(list(Path(IMPULSE_PATHS[0]).glob("*.wav"))) if Path(IMPULSE_PATHS[0]).exists() else 0
    if rir_count < 10:
        print(f"WARNING: Only {rir_count} RIR files found — room impulse augmentation will be limited")


def run_feature_extraction():
    from microwakeword.audio.augmentation import Augmentation
    from microwakeword.audio.clips import Clips
    from microwakeword.audio.spectrograms import SpectrogramGeneration
    from mmap_ninja.ragged import RaggedMmap

    # Combine all positive sample directories
    sample_dirs = []
    for sub in ["siwis", "tom", "upmc"]:
        d = DATA / "positive" / sub
        if d.exists() and any(d.glob("*.wav")):
            sample_dirs.append(str(d))
    if (DATA / "positive" / "real_mic").exists() and any((DATA / "positive" / "real_mic").glob("*.wav")):
        sample_dirs.append(str(DATA / "positive" / "real_mic"))

    print(f"Using {len(sample_dirs)} positive sample directories")

    # Load clips from all directories (Clips accepts a single dir; merge via symlinks)
    # Create a merged directory of symlinks
    merged_dir = BASE / "data" / "positive" / "_merged"
    merged_dir.mkdir(exist_ok=True)
    for d in sample_dirs:
        for wav in Path(d).glob("*.wav"):
            target = merged_dir / (d.split("/")[-1] + "_" + wav.name)
            if not target.exists():
                target.symlink_to(wav)
    print(f"Merged positive samples: {len(list(merged_dir.glob('*.wav')))}")

    rir_count = len(list(Path(IMPULSE_PATHS[0]).glob("*.wav"))) if Path(IMPULSE_PATHS[0]).exists() else 0
    aug_probs = {
        "SevenBandParametricEQ": 0.1,
        "TanhDistortion": 0.1,
        "PitchShift": 0.1,
        "BandStopFilter": 0.1,
        "AddColorNoise": 0.3,
        "Gain": 1.0,
    }
    if rir_count >= 10:
        aug_probs["RIR"] = 0.5

    clips = Clips(
        input_directory=str(merged_dir),
        file_pattern="*.wav",
        max_clip_duration_s=None,
        remove_silence=False,
        random_split_seed=42,
        split_count=0.1,
    )

    augmenter = Augmentation(
        augmentation_duration_s=3.2,
        augmentation_probabilities=aug_probs,
        impulse_paths=IMPULSE_PATHS if rir_count >= 10 else [],
        background_paths=[],
        background_min_snr_db=-5,
        background_max_snr_db=10,
        min_jitter_s=0.195,
        max_jitter_s=0.205,
    )

    import itertools
    import os
    import shutil
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from tqdm.auto import tqdm

    N_WORKERS = max(1, os.cpu_count() - 1)
    CHUNK_SIZE = 20  # clips per worker task — small = workers stay fed

    aug_params = dict(
        augmentation_duration_s=3.2,
        augmentation_probabilities=aug_probs,
        impulse_paths=IMPULSE_PATHS if rir_count >= 10 else [],
        background_paths=[],
        background_min_snr_db=-5,
        background_max_snr_db=10,
        min_jitter_s=0.195,
        max_jitter_s=0.205,
    )

    FEATURES_DIR.mkdir(exist_ok=True)
    splits_config = [
        ("training", "train", 3, 5),
        ("validation", "validation", 1, 10),
        ("testing", "test", 1, 1),
    ]

    for split_dir, split_name, repetition, slide_frames in splits_config:
        out_path = FEATURES_DIR / split_dir
        out_path.mkdir(exist_ok=True)
        mmap_path = out_path / "petit_pois_mmap"
        if mmap_path.exists() and (mmap_path / "dtype.ninja").exists():
            print(f"Skipping {split_dir} — already extracted")
            continue
        elif mmap_path.exists():
            print(f"Removing incomplete mmap for {split_dir}...")
            shutil.rmtree(mmap_path)
        print(f"Extracting {split_dir} spectrograms ({N_WORKERS} workers)...")

        clip_gen = clips.audio_generator(split=split_name, repeat=repetition)

        def chunked(gen, size):
            while True:
                chunk = list(itertools.islice(gen, size))
                if not chunk:
                    break
                yield chunk

        memmap = None
        write_batch = []

        with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
            chunk_iter = chunked(clip_gen, CHUNK_SIZE)
            in_flight = {}
            chunk_queue = []

            def submit_next():
                chunk = next(chunk_iter, None)
                if chunk is not None:
                    f = executor.submit(_extract_chunk, chunk, aug_params, 10, slide_frames)
                    in_flight[f] = True
                    return True
                return False

            # Prime with N_WORKERS * 2 tasks
            for _ in range(N_WORKERS * 2):
                submit_next()

            pbar = tqdm()
            while in_flight:
                for future in as_completed(in_flight):
                    del in_flight[future]
                    specs = future.result()
                    write_batch.extend(specs)
                    pbar.update(len(specs))
                    if len(write_batch) >= 1000:
                        if memmap is None:
                            memmap = RaggedMmap.from_lists(str(mmap_path), write_batch)
                        else:
                            memmap.extend(write_batch)
                        write_batch = []
                    submit_next()
                    break  # re-enter as_completed with updated in_flight
            pbar.close()

        if write_batch:
            if memmap is None:
                RaggedMmap.from_lists(str(mmap_path), write_batch)
            else:
                memmap.extend(write_batch)

        print(f"  Done: {split_dir}")

    print("Feature extraction complete.")


def write_training_config():
    config = {
        "window_step_ms": 10,
        "clip_duration_ms": 3200,  # matches augmentation_duration_s=3.2
        "train_dir": str(TRAINED_DIR),
        "features": [
            {
                "features_dir": str(FEATURES_DIR),
                "sampling_weight": 3.0,  # higher weight for positive (real mic included)
                "penalty_weight": 1.0,
                "truth": True,
                "truncation_strategy": "truncate_start",
                "type": "mmap",
            },
            {
                "features_dir": str(NEG_DIR / "speech"),
                "sampling_weight": 10.0,
                "penalty_weight": 1.0,
                "truth": False,
                "truncation_strategy": "random",
                "type": "mmap",
            },
            {
                "features_dir": str(NEG_DIR / "dinner_party"),
                "sampling_weight": 10.0,
                "penalty_weight": 1.0,
                "truth": False,
                "truncation_strategy": "split",
                "type": "mmap",
            },
            {
                "features_dir": str(NEG_DIR / "no_speech"),
                "sampling_weight": 5.0,
                "penalty_weight": 1.0,
                "truth": False,
                "truncation_strategy": "random",
                "type": "mmap",
            },
            {
                "features_dir": str(NEG_DIR / "dinner_party_eval"),
                "sampling_weight": 0,  # ambient eval only, not for training
                "penalty_weight": 1.0,
                "truth": False,
                "truncation_strategy": "split",
                "type": "mmap",
                "use_for_ambient_validation": True,
                "use_for_ambient_testing": True,
            },
        ],
        "positive_class_weight": [1, 1],
        "negative_class_weight": [250, 250],
        "training_steps": [40000, 75000],
        "eval_step_interval": 5000,
        "save_step_interval": 5000,
        "batch_size": 512,
        "learning_rates": [0.001, 0.0005],
        "minimization_metric": "ambient_false_positives_per_hour",
        "maximization_metric": "average_viable_recall",
        "target_minimization": 2.0,
    }

    config_path = BASE / "training_parameters.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    print(f"Training config written to {config_path}")
    return config_path


def run_training(config_path):
    TRAINED_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "microwakeword.model_train_eval",
        f"--training_config={config_path}",
        "--train", "1",
        "--restore_checkpoint", "1",
        "--test_tf_nonstreaming", "0",
        "--test_tflite_nonstreaming", "0",
        "--test_tflite_nonstreaming_quantized", "0",
        "--test_tflite_streaming", "0",
        "--test_tflite_streaming_quantized", "1",
        "--use_weights", "best_weights",
        "mixednet",
        "--pointwise_filters", "64,64,64,64",
        "--repeat_in_block", "1,1,1,1",
        "--mixconv_kernel_sizes", "[5],[7,11],[9,15],[23]",
        "--residual_connection", "0,0,0,0",
        "--first_conv_filters", "32",
        "--first_conv_kernel_size", "5",
        "--stride", "3",
    ]
    print("Starting training...")
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=str(BASE), check=True)


def package_model():
    import json
    import shutil

    tflite_src = TRAINED_DIR / "tflite_stream_state_internal_quant" / "stream_state_internal_quant.tflite"
    if not tflite_src.exists():
        print(f"ERROR: Model not found at {tflite_src}")
        return

    out_dir = BASE / "output"
    out_dir.mkdir(exist_ok=True)
    tflite_dst = out_dir / "petit_pois.tflite"
    shutil.copy(tflite_src, tflite_dst)

    manifest = {
        "type": "micro",
        "wake_word": "petit pois",
        "author": "Maxime",
        "model": "petit_pois.tflite",
        "trained_languages": ["fr"],
        "version": 2,
        "micro": {
            "probability_cutoff": 0.995,
            "feature_step_size": 10,
            "sliding_window_size": 8,
        },
    }
    with open(out_dir / "petit_pois.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Model packaged:")
    print(f"  {tflite_dst} ({tflite_dst.stat().st_size // 1024} KB)")
    print(f"  {out_dir / 'petit_pois.json'}")
    print()
    print("Deploy to pi-satellite:")
    print(f"  scp {tflite_dst} {out_dir / 'petit_pois.json'} dd@pi-satellite:~/lva/wakewords/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["features", "train", "package", "all"], default="all")
    args = parser.parse_args()

    os.chdir(BASE)
    check_prerequisites()

    if args.stage in ("features", "all"):
        run_feature_extraction()

    if args.stage in ("train", "all"):
        config_path = write_training_config()
        run_training(config_path)

    if args.stage in ("package", "all"):
        package_model()
