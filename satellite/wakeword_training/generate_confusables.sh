#!/bin/bash
# Generates confusable-negative samples for "petit pois"
# Run AFTER positive samples are generated.
set -e

VOICES_DIR="$HOME/micro-wake-word/voices"
DATA_DIR="$HOME/micro-wake-word/data"
VENV="$HOME/micro-wake-word/.venv/bin/python3"

rm -rf "$DATA_DIR/confusable"
mkdir -p "$DATA_DIR/confusable"

echo "=== Generating CONFUSABLE negatives (phonetically close to 'pwa') ==="

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
    "$VENV" -m piper_sample_generator         --model "$VOICES_DIR/fr_FR-siwis-medium.onnx"         --max-samples 1000         --output-dir "$DATA_DIR/confusable/$safe_name"         "$phrase"
    "$VENV" -m piper_sample_generator         --model "$VOICES_DIR/fr_FR-tom-medium.onnx"         --max-samples 1000         --output-dir "$DATA_DIR/confusable/$safe_name"         "$phrase"
done

echo "Confusable samples: $(find "$DATA_DIR/confusable" -name '*.wav' | wc -l)"
