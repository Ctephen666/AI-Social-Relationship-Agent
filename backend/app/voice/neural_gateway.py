from __future__ import annotations

import logging
import os

import numpy as np

from app.personal_agent.settings_store import AgentSettingsStore
from app.voice.model_manager import VoiceModelPaths, discover_voice_models
from app.voice.sapi_gateway import StateCallback, TranscriptCallback, WindowsSapiVoiceGateway


logger = logging.getLogger(__name__)


class LocalNeuralVoiceGateway(WindowsSapiVoiceGateway):
    """SenseVoice + Silero VAD ASR with a Windows SAPI recognition fallback.

    All microphone samples and neural inference remain on the local computer.
    The fallback keeps the desktop agent usable while models are being installed.
    """

    SAMPLE_RATE = 16_000

    def __init__(
        self,
        settings_store: AgentSettingsStore,
        on_command: TranscriptCallback,
        on_state: StateCallback | None = None,
    ) -> None:
        super().__init__(settings_store, on_command, on_state)
        self._models: VoiceModelPaths = discover_voice_models()
        self.active_asr_backend = "pending"

    @property
    def model_status(self) -> dict[str, object]:
        self._models = discover_voice_models()
        return {
            "asr_ready": self._models.asr_ready,
            "asr_backend": self.active_asr_backend,
            "model_root": str(self._models.root),
        }

    def restart(self) -> None:
        self._models = discover_voice_models()
        super().restart()

    def _listen_loop(self) -> None:
        preferences = self.settings_store.load()
        if preferences.asr_backend != "sensevoice":
            self.active_asr_backend = "Windows SAPI"
            super()._listen_loop()
            return
        try:
            self._models = discover_voice_models()
            if not self._models.asr_ready:
                raise RuntimeError("SenseVoice/Silero VAD 模型尚未安装")
            self._listen_with_sensevoice()
        except Exception as exc:
            logger.exception("Local neural ASR unavailable; falling back to Windows SAPI")
            self.on_state("voice_loading", f"SenseVoice 不可用，切换 Windows SAPI：{exc}")
            self.active_asr_backend = "Windows SAPI（降级）"
            super()._listen_loop()

    def _listen_with_sensevoice(self) -> None:
        import sherpa_onnx
        import sounddevice as sd

        assert self._models.asr_model and self._models.asr_tokens and self._models.vad_model
        self.on_state("voice_loading", "正在加载 SenseVoice 中文识别模型")
        threads = max(1, min(4, (os.cpu_count() or 2) // 2))
        recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(self._models.asr_model),
            tokens=str(self._models.asr_tokens),
            num_threads=threads,
            use_itn=True,
            debug=False,
        )
        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = str(self._models.vad_model)
        vad_config.silero_vad.min_silence_duration = 0.32
        vad_config.silero_vad.min_speech_duration = 0.18
        vad_config.sample_rate = self.SAMPLE_RATE
        window_size = vad_config.silero_vad.window_size
        vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)
        samples_per_read = int(0.1 * self.SAMPLE_RATE)
        pending = np.empty(0, dtype=np.float32)

        self.active_asr_backend = "SenseVoice Small INT8"
        self.on_state("idle", "SenseVoice 本地语音唤醒已开启")
        with sd.InputStream(channels=1, dtype="float32", samplerate=self.SAMPLE_RATE) as microphone:
            while not self._stop.is_set():
                samples, overflowed = microphone.read(samples_per_read)
                self._expire_arm_if_needed()
                if overflowed:
                    logger.debug("Microphone input overflow")
                if self._speaking.is_set():
                    continue
                pending = np.concatenate((pending, samples.reshape(-1)))
                while len(pending) >= window_size:
                    vad.accept_waveform(pending[:window_size])
                    pending = pending[window_size:]
                while not vad.empty():
                    segment = vad.front.samples
                    vad.pop()
                    if len(segment) < int(self.SAMPLE_RATE * 0.18):
                        continue
                    stream = recognizer.create_stream()
                    stream.accept_waveform(self.SAMPLE_RATE, segment)
                    recognizer.decode_stream(stream)
                    transcript = stream.result.text.strip()
                    if transcript:
                        logger.info("SenseVoice transcript received: chars=%d", len(transcript))
                        self._process_transcript(transcript)
