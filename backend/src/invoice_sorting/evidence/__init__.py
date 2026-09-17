"""凭证识别：OCR/PDF 文本 → 识别器 → RecognizedEvidence；文件名线索。

接口（由 evidence 模块实现，其他模块只依赖这些名称）：
  recognize_evidence(path, original_name) -> RecognizedEvidence   永不抛异常
  filename_hints(original_name) -> FilenameHints
  file_key(original_name) -> str
  ocr_available() -> bool
"""

from invoice_sorting.evidence.base import FilenameHints, RecognizedEvidence
from invoice_sorting.evidence.service import (
    file_key,
    filename_hints,
    ocr_available,
    recognize_evidence,
)

__all__ = [
    "FilenameHints",
    "RecognizedEvidence",
    "file_key",
    "filename_hints",
    "ocr_available",
    "recognize_evidence",
]
