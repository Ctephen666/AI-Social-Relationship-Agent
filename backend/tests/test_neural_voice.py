from __future__ import annotations

from pathlib import Path

from app.personal_agent.settings_store import AgentPreferences, AgentSettingsStore
from app.voice.model_manager import discover_voice_models
from app.voice.sapi_gateway import WindowsSapiVoiceGateway
from app.desktop_app import resolve_display_state


def test_discovers_complete_voice_model_bundle(tmp_path: Path) -> None:
    asr = tmp_path / "sense-voice-int8"
    asr.mkdir()
    (asr / "model.int8.onnx").write_bytes(b"model")
    (asr / "tokens.txt").write_text("token", encoding="utf-8")
    (tmp_path / "silero_vad.onnx").write_bytes(b"vad")

    models = discover_voice_models(tmp_path)
    assert models.asr_ready
    assert models.ready


def test_neural_voice_defaults_are_local() -> None:
    preferences = AgentPreferences()
    assert preferences.asr_backend == "sensevoice"
    assert "tts_backend" not in AgentPreferences.model_fields


def test_default_wake_word_accepts_common_homophone(tmp_path: Path) -> None:
    store = AgentSettingsStore(tmp_path / "settings.json")
    commands: list[str] = []
    gateway = WindowsSapiVoiceGateway(store, commands.append)

    gateway._process_transcript("史蒂分，打开设置")

    assert commands == ["打开设置"]


def test_voice_idle_does_not_overwrite_task_state() -> None:
    assert resolve_display_state("confirming", "idle") == "confirming"
    assert resolve_display_state("error", "idle") == "error"
    assert resolve_display_state("confirming", "speaking") == "speaking"
    assert resolve_display_state("confirming", "listening") == "confirm_listening"
