from datetime import datetime
from pathlib import Path

import mss
import mss.tools


class ScreenshotService:
    """只采集像素，不控制鼠标、键盘或浏览器。"""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def capture(self, region: tuple[int, int, int, int] | None = None) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"scan_{timestamp}.png"
        with mss.mss() as sct:
            monitor = (
                {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
                if region else sct.monitors[1]
            )
            image = sct.grab(monitor)
            mss.tools.to_png(image.rgb, image.size, output=str(path))
        return path

