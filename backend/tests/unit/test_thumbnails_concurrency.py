"""PDFium 非线程安全：并发渲染缩略图不得导致进程崩溃。"""

import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "invoices"

SCRIPT = """
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from invoice_sorting.attachments.thumbnails import _render_pdf

paths = [Path(p) for p in sys.argv[1:]] * 12
with ThreadPoolExecutor(8) as pool:
    list(pool.map(_render_pdf, paths))
"""


def test_concurrent_pdf_rendering_does_not_crash():
    pdfs = [str(FIXTURES / name) for name in ("digital_same_line.pdf", "rail_ticket.pdf")]

    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, *pdfs], capture_output=True, timeout=120, check=False
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")[-500:]
