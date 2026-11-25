"""从 docs/系统操作说明书.md 生成随前端发布的中文 PDF。"""

import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "系统操作说明书.md"
OUTPUT = ROOT / "frontend" / "public" / "system-manual.pdf"
PAGE_SIZE = landscape(A3)
IMAGE_LINE = re.compile(r"^!\[([^]]+)\]\((manual-images/[^)]+)\)$")
FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def style(name: str, size: int, leading: int, **kwargs: object) -> ParagraphStyle:
    options = {"spaceAfter": 10, "textColor": colors.HexColor("#1f2420"), **kwargs}
    return ParagraphStyle(
        name,
        fontName=FONT,
        fontSize=size,
        leading=leading,
        wordWrap="CJK",
        **options,
    )


TITLE = style("Title", 25, 34, alignment=TA_CENTER, spaceAfter=22)
SUBTITLE = style("Subtitle", 10, 18, alignment=TA_CENTER, spaceAfter=16)
HEADING = style("Heading", 16, 25, spaceBefore=18, spaceAfter=10, keepWithNext=True)
STEP_HEADING = style("StepHeading", 14, 22, spaceBefore=8, spaceAfter=8, keepWithNext=True)
BODY = style("Body", 10.5, 20, alignment=TA_LEFT)
CAPTION = style("Caption", 9, 15, alignment=TA_CENTER, textColor=colors.HexColor("#506057"))


def page_footer(canvas, doc) -> None:
    canvas.saveState()
    width, _ = PAGE_SIZE
    canvas.setStrokeColor(colors.HexColor("#d8d2c3"))
    canvas.line(44, 43, width - 44, 43)
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.HexColor("#706b61"))
    canvas.drawString(44, 29, "发票账本 / 系统操作说明书")
    canvas.drawRightString(width - 44, 29, str(doc.page))
    canvas.restoreState()


def main() -> None:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    headings = [line[3:] for line in lines if line.startswith("## ")]
    story = [
        Spacer(1, 90),
        Paragraph("发票账本", TITLE),
        Paragraph("系统操作说明书", TITLE),
        Paragraph(escape(lines[2]), SUBTITLE),
        Spacer(1, 55),
        Paragraph("从凭证收集到报销到账", SUBTITLE),
        Paragraph("用户、账套管理员与平台管理员操作 / 安装、部署、维护与卸载", SUBTITLE),
        PageBreak(),
        Paragraph("目录", HEADING),
    ]
    story.extend(Paragraph(escape(heading), BODY) for heading in headings)
    story.append(PageBreak())

    first_step_in_chapter = False
    for line in lines[4:]:
        if line.startswith("## "):
            first_step_in_chapter = line.startswith(("## 18.", "## 19.", "## 20."))
            if first_step_in_chapter:
                story.append(PageBreak())
            story.append(Paragraph(escape(line[3:]), HEADING))
        elif line.startswith("### "):
            if not first_step_in_chapter:
                story.append(PageBreak())
            story.append(Paragraph(escape(line[4:]), STEP_HEADING))
            first_step_in_chapter = False
        elif match := IMAGE_LINE.match(line):
            caption, relative_path = match.groups()
            image_path = SOURCE.parent / relative_path
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            screenshot = Image(str(image_path))
            scale = min(1, 1080 / screenshot.imageWidth, 480 / screenshot.imageHeight)
            screenshot.drawWidth *= scale
            screenshot.drawHeight *= scale
            story.extend([Spacer(1, 8), screenshot, Spacer(1, 7), Paragraph(escape(caption), CAPTION)])
        elif line.strip():
            story.append(Paragraph(escape(line).replace("`", ""), BODY))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=PAGE_SIZE,
        rightMargin=48,
        leftMargin=48,
        topMargin=52,
        bottomMargin=55,
        title="发票账本 · 系统操作说明书",
        author="发票账本",
    )
    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(f"生成 {OUTPUT}")


if __name__ == "__main__":
    main()
