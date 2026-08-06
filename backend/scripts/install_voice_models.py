from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.voice.model_manager import install_voice_models


def main() -> None:
    paths = install_voice_models(progress=print)
    print(f"ASR ready: {paths.asr_ready}")
    print(f"TTS ready: {paths.tts_ready}")
    print(f"Model directory: {paths.root}")


if __name__ == "__main__":
    main()
