"""占位实现：仅返回未识别结果，由凭证识别模块替换为真实实现（保持函数签名不变）。"""

from pathlib import Path

from invoice_sorting.evidence.base import DOC_UNKNOWN, FilenameHints, RecognizedEvidence


def ocr_available() -> bool:
    return False


def file_key(original_name: str) -> str:
    return Path(original_name).stem


def filename_hints(original_name: str) -> FilenameHints:
    return FilenameHints(None, "", None, None, "", file_key(original_name))


def recognize_evidence(path: Path, original_name: str) -> RecognizedEvidence:
    return RecognizedEvidence(doc_type=DOC_UNKNOWN, recognizer="none")
