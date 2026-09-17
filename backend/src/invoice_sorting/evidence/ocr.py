"""RapidOCR 懒加载单例：线程锁串行调用，识别结果转为 TextBox。"""

import logging
import threading
from functools import lru_cache
from typing import Any

from PIL import Image

from invoice_sorting.evidence.lines import TextBox

logger = logging.getLogger(__name__)

# onnxruntime 会话与引擎内部状态在多线程下不保证安全：进程内所有 OCR 调用串行
OCR_LOCK = threading.Lock()
_engine_holder: dict[str, Any] = {}


@lru_cache(maxsize=1)
def ocr_available() -> bool:
    """可选依赖 rapidocr（及 onnxruntime）是否可导入。"""
    try:
        import rapidocr  # noqa: F401
    except Exception as exc:  # ImportError 或其依赖初始化失败
        logger.debug("OCR 不可用：%r", exc)
        return False
    return True


def _engine() -> Any:
    """在 OCR_LOCK 内调用：首次使用时创建引擎。"""
    if "engine" not in _engine_holder:
        from rapidocr import RapidOCR

        _engine_holder["engine"] = RapidOCR()
    return _engine_holder["engine"]


def _to_box(points: Any, text: str) -> TextBox:
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return TextBox(str(text), min(xs), min(ys), max(xs), max(ys))


def ocr_image(image: Image.Image) -> list[TextBox]:
    """识别图片中的文本框；OCR 不可用或无文字时返回空列表。"""
    if not ocr_available():
        return []
    import numpy as np

    array = np.asarray(image.convert("RGB"))
    with OCR_LOCK:
        result = _engine()(array)
    boxes, texts = getattr(result, "boxes", None), getattr(result, "txts", None)
    if boxes is None or texts is None:
        return []
    return [_to_box(points, text) for points, text in zip(boxes, texts, strict=False)]
