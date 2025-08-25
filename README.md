# Laserwall

## Install base software packages
1. Install Homebrew: https://brew.sh/
2. Download ollama: https://ollama.com/download/mac
3. Download [XCode](http://apps.apple.com/us/app/xcode/id497799835) from App Store
4. `xcode-select --install` 

## Setup environment
```zsh
./setup-env.sh
./setup-llm-server.sh
./setup-speech-recognizer.sh
```

### Run main process (spawns LLM server too)
```zsh
./run.sh --personality robot
```
