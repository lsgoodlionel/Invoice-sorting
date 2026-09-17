"""测试辅助：构造凭证项、识别结果、占位图片，以及注入识别函数的夹具实现。"""

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image

from invoice_sorting.attachments import evidence_records, file_keys
from invoice_sorting.evidence import FilenameHints, RecognizedEvidence
from invoice_sorting.importer.items import EvidenceItem

_counter = {"value": 0}


def item(attachment_id: int, kind: str, **fields: Any) -> EvidenceItem:
    return EvidenceItem(
        attachment_id=attachment_id,
        kind=kind,
        original_name=fields.pop("original_name", f"{attachment_id}.png"),
        has_data=True,
        **fields,
    )


def recognized(doc_type: str, **fields: Any) -> RecognizedEvidence:
    return replace(RecognizedEvidence(doc_type=doc_type, recognizer="test"), **fields)


def png(directory: Path, name: str) -> Path:
    """每次生成尺寸不同的占位 PNG，保证 sha256 不重复。"""
    _counter["value"] += 1
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    size = 8 + _counter["value"]
    Image.new("RGB", (size, size), "white").save(path)
    return path


class FakeRecognition:
    """按原始文件名返回预设识别结果；未预设的文件返回未识别。"""

    def __init__(self) -> None:
        self.results: dict[str, RecognizedEvidence] = {}
        self.keys: dict[str, str] = {}
        self.categories: dict[str, str] = {}
        self.calls: list[str] = []

    def set(self, name: str, result: RecognizedEvidence, key: str = "", category: str = "") -> None:
        self.results[name] = result
        if key:
            self.keys[name] = key
        if category:
            self.categories[name] = category

    def recognize(self, _path: Path, original_name: str) -> RecognizedEvidence:
        self.calls.append(original_name)
        return self.results.get(original_name, RecognizedEvidence("unknown", "filename"))

    def file_key(self, original_name: str) -> str:
        return self.keys.get(original_name, "")

    def hints(self, original_name: str) -> FilenameHints:
        category = self.categories.get(original_name, "")
        return FilenameHints(None, category, None, None, "", self.file_key(original_name))

    def install(self, monkeypatch) -> "FakeRecognition":
        monkeypatch.setattr(evidence_records, "recognize_evidence", self.recognize)
        monkeypatch.setattr(evidence_records, "filename_hints", self.hints)
        monkeypatch.setattr(file_keys, "file_key", self.file_key)
        return self


JUNE_28 = date(2026, 6, 28)
