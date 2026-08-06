from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tarfile
import tempfile
from typing import Callable
from urllib.request import Request, urlopen

from app.core.runtime import data_directory


ASR_ARCHIVE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2"
)
VAD_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
)
ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class VoiceModelPaths:
    root: Path
    asr_model: Path | None
    asr_tokens: Path | None
    vad_model: Path | None

    @property
    def asr_ready(self) -> bool:
        return all(path is not None and path.is_file() for path in (self.asr_model, self.asr_tokens, self.vad_model))

    @property
    def ready(self) -> bool:
        return self.asr_ready


def voice_model_directory() -> Path:
    return data_directory() / "voice_models"


def discover_voice_models(root: Path | None = None) -> VoiceModelPaths:
    root = (root or voice_model_directory()).resolve()
    files = list(root.rglob("*")) if root.is_dir() else []

    def first_file(*names: str) -> Path | None:
        by_name = {path.name.casefold(): path for path in files if path.is_file()}
        return next((by_name[name.casefold()] for name in names if name.casefold() in by_name), None)

    asr_model = first_file("model.int8.onnx")
    if asr_model and "sense" not in str(asr_model.parent).casefold():
        asr_model = next(
            (path for path in files if path.is_file() and path.name == "model.int8.onnx" and "sense" in str(path.parent).casefold()),
            None,
        )
    asr_tokens = asr_model.parent / "tokens.txt" if asr_model else None
    vad_model = first_file("silero_vad.onnx")

    return VoiceModelPaths(
        root=root,
        asr_model=asr_model,
        asr_tokens=asr_tokens if asr_tokens and asr_tokens.is_file() else None,
        vad_model=vad_model,
    )


def install_voice_models(root: Path | None = None, progress: ProgressCallback | None = None) -> VoiceModelPaths:
    """Download official model archives and atomically install their contents."""
    destination = (root or voice_model_directory()).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    report = progress or (lambda _message: None)
    current = discover_voice_models(destination)

    with tempfile.TemporaryDirectory(prefix="stephen-voice-models-") as temporary:
        temp = Path(temporary)
        if not current.asr_ready:
            report("正在下载 SenseVoice Small INT8 中文识别模型…")
            archive = temp / "sensevoice.tar.bz2"
            _download(ASR_ARCHIVE_URL, archive, report)
            _safe_extract(archive, destination)
            report("SenseVoice 模型安装完成")
        if not (destination / "silero_vad.onnx").is_file():
            report("正在下载 Silero VAD…")
            _download(VAD_MODEL_URL, destination / "silero_vad.onnx", report)

    installed = discover_voice_models(destination)
    if not installed.ready:
        raise RuntimeError(f"语音模型安装不完整：{destination}")
    return installed


def _download(url: str, destination: Path, report: ProgressCallback) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "StephenAgent/0.6"})
    with urlopen(request, timeout=60) as response, partial.open("wb") as output:
        total = int(response.headers.get("Content-Length", "0"))
        copied = 0
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            copied += len(chunk)
            if total:
                report(f"下载进度 {copied * 100 // total}%")
    partial.replace(destination)


def _safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, mode="r:bz2") as bundle:
        root = destination.resolve()
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"模型压缩包包含不安全路径：{member.name}")
        bundle.extractall(destination, filter="data")
