from __future__ import annotations

from collections.abc import Callable
import logging
import re
import threading
import time

from app.personal_agent.settings_store import AgentPreferences, AgentSettingsStore


logger = logging.getLogger(__name__)
TranscriptCallback = Callable[[str], None]
StateCallback = Callable[[str, str], None]


class WindowsSapiVoiceGateway:
    """Local Windows SAPI recognizer with wake-word gating.

    It keeps raw audio inside Windows Speech services. Only recognized text is
    passed to the Agent. No microphone data is uploaded by this module.
    """

    def __init__(
        self,
        settings_store: AgentSettingsStore,
        on_command: TranscriptCallback,
        on_state: StateCallback | None = None,
    ) -> None:
        self.settings_store = settings_store
        self.on_command = on_command
        self.on_state = on_state or (lambda _state, _detail: None)
        self._stop = threading.Event()
        self._speaking = threading.Event()
        self._armed_until = 0.0
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        preferences = self.settings_store.load()
        if not preferences.voice_enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._listen_loop, name="sapi-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def restart(self) -> None:
        self.stop()
        if self._thread:
            self._thread.join(timeout=1.5)
        self._thread = None
        self.start()

    def arm(self) -> None:
        preferences = self.settings_store.load()
        self._armed_until = time.monotonic() + preferences.listen_timeout_seconds
        self.on_state("listening", f"请说话，{preferences.listen_timeout_seconds} 秒内有效")

    def acknowledge_and_arm(self) -> None:
        """Enter command listening immediately; no synthesized acknowledgement."""
        self.arm()

    def _expire_arm_if_needed(self) -> None:
        if self._armed_until and time.monotonic() > self._armed_until:
            self._armed_until = 0.0
            self.on_state("idle", "语音等待已结束")

    def _listen_loop(self) -> None:
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            gateway = self

            class RecognitionEvents:
                def OnRecognition(self, _stream_number, _stream_position, _recognition_type, result):
                    if gateway._speaking.is_set():
                        return
                    try:
                        # With an in-process recognizer pywin32 may expose the
                        # event argument as a raw PyIDispatch. Wrap it before
                        # accessing the SAPI recognition-result interface.
                        recognition_result = win32com.client.Dispatch(result)
                        transcript = str(recognition_result.PhraseInfo.GetText()).strip()
                    except Exception:
                        logger.exception("Unable to read SAPI recognition result")
                        return
                    gateway._process_transcript(transcript)

            # SpSharedRecoContext can launch the legacy Windows Speech Control
            # setup UI on first use. An in-process recognizer avoids that side
            # effect and keeps this Agent isolated from OS voice control.
            recognizer = win32com.client.Dispatch("SAPI.SpInprocRecognizer")
            recognizers = recognizer.GetRecognizers()
            audio_inputs = recognizer.GetAudioInputs()
            if recognizers.Count < 1:
                raise RuntimeError("没有安装 Windows 语音识别器")
            if audio_inputs.Count < 1:
                raise RuntimeError("没有可用麦克风")
            recognizer.Recognizer = recognizers.Item(0)
            recognizer.AudioInput = audio_inputs.Item(0)
            raw_context = recognizer.CreateRecoContext()
            context = win32com.client.DispatchWithEvents(raw_context, RecognitionEvents)
            grammar = context.CreateGrammar()
            grammar.DictationSetState(1)
            self.on_state("idle", "语音唤醒已开启")
            while not self._stop.wait(0.04):
                pythoncom.PumpWaitingMessages()
                self._expire_arm_if_needed()
            grammar.DictationSetState(0)
        except Exception as exc:
            logger.exception("Windows speech recognition unavailable")
            self.on_state("voice_error", f"Windows 语音识别不可用：{exc}")
        finally:
            try:
                import pythoncom

                pythoncom.CoUninitialize()
            except Exception:
                pass

    def _process_transcript(self, transcript: str) -> None:
        if not transcript:
            return
        preferences = self.settings_store.load()
        normalized = self._normalize(transcript)
        wake = self._normalize(preferences.wake_word)
        wake_candidates = [wake]
        if wake == "史蒂芬":
            # Common Chinese ASR homophones for the default wake word.  Keep
            # the list intentionally narrow to avoid accidental activation.
            wake_candidates.extend(("史蒂分", "史提芬", "斯蒂芬"))
        matched_wake = next((candidate for candidate in wake_candidates if candidate and candidate in normalized), "")
        if matched_wake:
            position = normalized.find(matched_wake)
            command = normalized[position + len(matched_wake):].strip()
            self.on_state("heard", transcript)
            if command:
                self._armed_until = 0.0
                self.on_command(command)
            else:
                self.acknowledge_and_arm()
            return
        if time.monotonic() <= self._armed_until:
            self._armed_until = 0.0
            self.on_state("heard", transcript)
            self.on_command(transcript)

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[\s，。！？、,.!?：:]", "", text).casefold()
