# Custom Wake Word Training — "petit pois"

Training a microWakeWord model on `dd-room` (RTX 3060 12GB) for deployment on `pi-satellite`.

---

## Environment (dd-room)

```bash
cd ~/micro-wake-word
source .venv/bin/activate
```

Python 3.12, TensorFlow 2.21, CUDA via pip (`nvidia-cudnn-cu12`). The venv activate script has `LD_LIBRARY_PATH` set to all nvidia package lib dirs. CUDA is auto-detected by piper (`use_cuda=torch.cuda.is_available()`).

---

## Data Layout

```
~/micro-wake-word/
├── data/positive/
│   ├── siwis/            # 60k Piper TTS (fr_FR-siwis-medium, female)
│   ├── tom/              # 70k Piper TTS (fr_FR-tom-medium, male)
│   ├── upmc/             # 70k Piper TTS (fr_FR-upmc-medium, male)
│   ├── real_mic/         # ~155+ recordings from pi-satellite INMP441
│   └── _merged/          # symlinks of all above (auto-created by feature extraction)
├── negative_datasets/
│   ├── speech/           # HuggingFace kahrendt/microwakeword
│   ├── dinner_party/
│   ├── no_speech/
│   └── dinner_party_eval/
├── generated_augmented_features/   # extracted spectrograms (mmap)
│   ├── training/petit_pois_mmap
│   ├── validation/petit_pois_mmap
│   └── testing/petit_pois_mmap
├── trained_models/petit_pois/      # checkpoints + best_weights
├── training_parameters.yaml
├── generate_samples.sh
└── prepare_and_train.py
```

---

## Full Production Run (from scratch)

### 0. Sync real mic samples from pi-satellite

```bash
rsync -av dd@pi-satellite:~/wake_word_samples/ \
    ~/micro-wake-word/data/positive/real_mic/
```

### 1. Generate 200k TTS samples + confusables

Clears old samples (they were generated for "jean fennec") and regenerates:

```bash
cd ~/micro-wake-word && source .venv/bin/activate
bash generate_samples.sh
```

~200k positive samples (60k siwis + 70k tom + 70k upmc) + 16k confusable negatives.

### 2. Clear old extracted features

```bash
rm -rf ~/micro-wake-word/generated_augmented_features/training/petit_pois_mmap
rm -rf ~/micro-wake-word/generated_augmented_features/validation/petit_pois_mmap
rm -rf ~/micro-wake-word/generated_augmented_features/testing/petit_pois_mmap
rm -rf ~/micro-wake-word/generated_augmented_features_confusable
```

### 3. Re-extract features (3 augmentation rounds)

```bash
python3 prepare_and_train.py --stage features
```

Each training clip is augmented 3× (EQ, distortion, pitch shift, noise, RIR reverb). Validation/test use 1 round.

### 4. Train

Stop whisper to free VRAM (it auto-restarts via Docker):

```bash
ssh dd@dd-ha "docker stop wyoming-whisper"
```

Add swap if not present:

```bash
sudo fallocate -l 8G /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
```

```bash
nohup python3 prepare_and_train.py --stage train > training.log 2>&1 &
```

Monitor:

```bash
tr '\r' '\n' < ~/micro-wake-word/training.log | grep 'Step #' | tail -5
```

### Config summary

| Parameter | Value |
|-----------|-------|
| Training steps | 40k + 75k = **115k total** |
| Augmentation rounds | **3** (training only) |
| FP penalty (`negative_class_weight`) | **250** |
| Voices | siwis (F), tom (M), upmc (M) |
| Positive samples | ~200k TTS + real_mic |

---

## Recording Real Mic Samples (pi-satellite)

LVA holds the ALSA device exclusively — use `arecord` directly:

```bash
# On pi-satellite
bash ~/record_wake_word.sh
```

Script uses `arecord -D hw:0,0 -f S32_LE -r 48000 -c 2`, segments to 3s clips at 16kHz mono. Target is 250 samples total, auto-increments from last saved index.

Sync to dd-room:
```bash
rsync -av dd@pi-satellite:~/wake_word_samples/ \
    dd@dd-room:~/micro-wake-word/data/positive/real_mic/
```

---

## Bugs Fixed in `microwakeword/train.py`

The upstream code is incompatible with modern TF/numpy (returns arrays where it expected tensors with `.numpy()`). Three classes of fixes applied:

**1. Added `_to_scalar()` helper at line 29:**
```python
def _to_scalar(x):
    """Convert TF tensor or numpy array to Python float."""
    if hasattr(x, 'numpy'):
        x = x.numpy()
    return float(np.asarray(x).flat[0])
```

**2. Scalar metrics** (`accuracy`, `recall`, `precision`, `auc`, `loss`) wrapped with `_to_scalar()` — lines 68–73.

**3. Array metrics** (`tp`, `fp`, `fn`) kept as `np.asarray()` — lines 81, 111–113. These are 101-element arrays (one per probability threshold) used to build recall/FAPH curves. Must NOT be flattened to scalars.

**4. Missing config keys** added to `training_parameters.yaml`: `minimization_metric`, `maximization_metric`, `target_minimization`.

---

## Packaging

Once training completes:

```bash
cd ~/micro-wake-word && source .venv/bin/activate
python3 prepare_and_train.py --stage package
```

Output:
- `~/micro-wake-word/output/petit_pois.tflite`
- `~/micro-wake-word/output/petit_pois.json`

---

## Deployment to pi-satellite

```bash
# Copy model files
scp dd@dd-room:~/micro-wake-word/output/petit_pois.{tflite,json} \
    dd@pi-satellite:~/.config/linux-voice-assistant/wakewords/

# Activate in preferences
# Edit ~/.config/linux-voice-assistant/preferences.json on pi-satellite:
# "active_wake_words": ["petit_pois"]

# Restart LVA
sudo systemctl restart lva
```

LVA is configured with `--wake-word-dir /app/configuration/wakewords` in `~/lva/docker-compose.yml`, which maps to `~/.config/linux-voice-assistant/` on the host.

---

## Verification

```bash
sudo docker logs -f lva | grep -i wake
```

- "petit_pois" should appear in available wake words at startup
- Say "petit pois" → LED state changes to `listening`
- If false accepts are high: increase `probability_cutoff` in `petit_pois.json` (0.97 → 0.99)
- If misses are high: lower cutoff or add more real mic recordings and retrain
