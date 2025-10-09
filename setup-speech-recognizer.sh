#!/usr/bin/env bash
set -euo pipefail


# Priority to Zsh - re-execute in zsh if available and not already running in zsh
if [ -z "${ZSH_VERSION:-}" ] && command -v zsh >/dev/null 2>&1; then
  exec zsh "$0" "$@"
elif [ -z "${BASH_VERSION:-}" ] && command -v bash >/dev/null 2>&1; then
  exec bash "$0" "$@"
elif [ -z "${BASH_VERSION:-}" ] && [ -z "${ZSH_VERSION:-}" ]; then
  echo "Error: neither bash nor zsh found on this system."
  exit 1
fi


source .env

if [[ ! -d "./laserwall" ]]; then
    echo "No virtual environment, cannot continue. Setup via setup-env.sh"
    exit 1
fi

source ./laserwall/bin/activate
pip install --upgrade pip

if command -v brew >/dev/null 2>&1; then
    # Use brew on macOS
    if ! brew list sdl2 &>/dev/null; then
        echo "Installing SDL2 for handling mic input"
        brew install sdl2
    else
        echo "SDL2 already installed, skipping install"
    fi

    if ! brew list ffmpeg &>/dev/null; then
        echo "Installing ffmpeg for handling audio playback"
        brew install ffmpeg
    else
        echo "ffmpeg already installed, skipping install"
    fi
elif command -v apt-get >/dev/null 2>&1; then
    # Use apt-get on Debian/Ubuntu
    if ! dpkg -l | grep -q "^ii.*libsdl2-dev"; then
        echo "Installing SDL2 for handling mic input"
        sudo apt-get update
        sudo apt-get install -y libsdl2-2.0-0 libsdl2-dev
    else
        echo "SDL2 already installed, skipping install"
    fi

    if ! dpkg -l | grep -q "^ii.*ffmpeg"; then
        echo "Installing ffmpeg for handling audio playback"
        sudo apt-get update
        sudo apt-get install -y ffmpeg
    else
        echo "ffmpeg already installed, skipping install"
    fi
else
    echo "Error: Neither brew nor apt-get found. Please install SDL2 and ffmpeg manually."
    exit 1
fi

if [[ -d "whisper.cpp" ]]; then
    echo "Found whisper.cpp, reusing existing installation"
else 
    echo "Cloning whisper.cpp v$WHISPER_CPP_VERSION..."
    git clone --branch "v$WHISPER_CPP_VERSION" --depth 1 https://github.com/ggml-org/whisper.cpp.git whisper.cpp
fi

cd whisper.cpp

if [[ -f "./models/ggml-$SPEECH_RECOGNITION_MODEL.bin" ]]; then
    echo "Model $SPEECH_RECOGNITION_MODEL already present, skipping download"
else
    echo "Downloading model $SPEECH_RECOGNITION_MODEL..."
    sh ./models/download-ggml-model.sh $SPEECH_RECOGNITION_MODEL
fi

if [[ "$USE_NEURAL_ENGINE" == "true" ]]; then
    echo "Building for Neural Engine..."

    pip install ane_transformers
    pip install openai-whisper
    pip install coremltools

    ls -la
    ls -la ./models

    if [[ -d "./models/ggml-"${SPEECH_RECOGNITION_MODEL}"-encoder.mlmodelc" ]]; then
        echo "CoreML model for $SPEECH_RECOGNITION_MODEL already present, skipping conversion"
    else
        echo "Converting model $SPEECH_RECOGNITION_MODEL to CoreML..."
        sh ./models/generate-coreml-model.sh $SPEECH_RECOGNITION_MODEL
    fi

    cmake -B build -DWHISPER_SDL2=ON -DWHISPER_COREML=1
    cmake --build build -j --config Release
else
    echo "Building for GPU..."
    cmake -B build -DWHISPER_SDL2=ON
    cmake --build build --config Release
fi
