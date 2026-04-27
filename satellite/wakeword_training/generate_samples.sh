#!/bin/bash
# Generates synthetic positive + confusable-negative samples for "petit pois"
# Run from ~/micro-wake-word with the venv activated
# CUDA is used automatically when available (piper loads with use_cuda=True)
set -e

VOICES_DIR="$HOME/micro-wake-word/voices"
DATA_DIR="$HOME/micro-wake-word/data"
VENV="$HOME/micro-wake-word/.venv/bin/python3"

# Clear old TTS samples (they were generated for "jean fennec")
echo "=== Clearing old TTS positive samples ==="
rm -rf "$DATA_DIR/positive/fr_male"
rm -rf "$DATA_DIR/positive/fr_female"
rm -rf "$DATA_DIR/positive/en_fallback"
rm -rf "$DATA_DIR/positive/_merged"
# Clear old jean_fennec confusables
rm -rf "$DATA_DIR/confusable"

mkdir -p "$DATA_DIR/positive/siwis"
mkdir -p "$DATA_DIR/positive/tom"
mkdir -p "$DATA_DIR/positive/upmc"
mkdir -p "$DATA_DIR/confusable"

echo "=== Generating POSITIVE samples: 'petit pois' ==="

echo "[1/3] fr_FR-siwis (female, 60000 samples)..."
"$VENV" -m piper_sample_generator \
    --model "$VOICES_DIR/fr_FR-siwis-medium.onnx" \
    --max-samples 60000 \
    --output-dir "$DATA_DIR/positive/siwis" \
    "petit pois"

echo "[2/3] fr_FR-tom (male, 70000 samples)..."
"$VENV" -m piper_sample_generator \
    --model "$VOICES_DIR/fr_FR-tom-medium.onnx" \
    --max-samples 70000 \
    --output-dir "$DATA_DIR/positive/tom" \
    "petit pois"

echo "[3/3] fr_FR-upmc (male, 70000 samples)..."
"$VENV" -m piper_sample_generator \
    --model "$VOICES_DIR/fr_FR-upmc-medium.onnx" \
    --max-samples 70000 \
    --output-dir "$DATA_DIR/positive/upmc" \
    "petit pois"

echo ""
echo "=== Generating CONFUSABLE negatives (phonetically close to 'pwa') ==="

# All /Xwa/ confusables — same /wa/ vowel, different initial consonant
CONFUSABLES_FR=(
    "petit bois"
    "petit fois"
    "petit mois"
    "petit roi"
    "petit doigt"
    "c'est moi"
    "chez moi"
    "à moi"
)

for phrase in "${CONFUSABLES_FR[@]}"; do
    safe_name=$(echo "$phrase" | tr ' ' '_' | tr "'" '_')
    echo "Confusable: '$phrase' → 2000 samples (siwis + tom)..."
    mkdir -p "$DATA_DIR/confusable/$safe_name"
    "$VENV" -m piper_sample_generator \
        --model "$VOICES_DIR/fr_FR-siwis-medium.onnx" \
        --max-samples 1000 \
        --output-dir "$DATA_DIR/confusable/$safe_name" \
        "$phrase"
    "$VENV" -m piper_sample_generator \
        --model "$VOICES_DIR/fr_FR-tom-medium.onnx" \
        --max-samples 1000 \
        --output-dir "$DATA_DIR/confusable/$safe_name" \
        "$phrase"
done

echo ""
echo "=== Sample generation complete ==="
echo "Positive samples: $(find "$DATA_DIR/positive" -name '*.wav' | wc -l)"
echo "Confusable samples: $(find "$DATA_DIR/confusable" -name '*.wav' | wc -l)"
