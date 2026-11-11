from pathlib import Path

import pytest

from invoice_sorting.attachments.sources import (
    DuplicateSourceError,
    source_absolute_path,
    store_source_document,
)


def test_stores_source_once_and_reports_duplicate(session, settings, tmp_path: Path):
    original = tmp_path / "Gmail - Your purchases from Apple.pdf"
    original.write_bytes(b"%PDF-1.4\nsynthetic")

    source = store_source_document(session, settings, original, original.name)

    stored = source_absolute_path(settings, source)
    assert stored.read_bytes() == original.read_bytes()
    assert source.original_name == original.name
    assert source.size == original.stat().st_size
    with pytest.raises(DuplicateSourceError) as caught:
        store_source_document(session, settings, original, original.name)
    assert caught.value.existing.id == source.id
