from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata


backend_dir = Path(SPECPATH)
project_root = backend_dir.parent
datas = []
binaries = []
hiddenimports = [
    "tkinter",
    "tkinter.messagebox",
    "rapidocr.inference_engine.onnxruntime",
    "pywinauto.uia_element_info",
    "pywinauto.controls.uiawrapper",
    "pywinauto.controls.uia_controls",
    "comtypes.client",
    "pythoncom",
    "pywintypes",
    "win32com.client",
    "sherpa_onnx",
    "sounddevice",
]

# collect_all(rapidocr) imports every optional backend, which can accidentally
# bundle Paddle/Torch/TensorRT and break ONNX Runtime's DLL initialization.
# The desktop build uses ONNX Runtime only, so include data/models explicitly.
datas += collect_data_files("rapidocr", includes=["*.yaml", "models/*", "fonts/*"])
binaries += collect_dynamic_libs("sherpa_onnx")

for distribution in ("rapidocr", "onnxruntime", "sherpa-onnx", "sounddevice", "pywinauto", "comtypes"):
    datas += copy_metadata(distribution)

a = Analysis(
    [str(backend_dir / "app" / "desktop_app.py")],
    pathex=[str(backend_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "fastapi", "uvicorn", "apscheduler", "pytest", "matplotlib", "IPython", "jupyter",
        "paddle", "paddleocr", "paddlex", "torch", "tensorrt", "openvino", "MNN",
        "langgraph", "langchain_core",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StephenAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    version=str(backend_dir / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="StephenAgent",
)
