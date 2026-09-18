"""生成凭证识别单测用的虚构样本（酒店订单 PDF、订单截图 PNG）。

用法（在 backend/ 下）：uv run python scripts/make_evidence_fixtures.py
所有姓名、订单号、酒店名均为虚构值；生成后提交到 tests/fixtures/evidence/。
"""

from pathlib import Path

from make_invoice_fixtures import register_font
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

OUT_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "evidence"
IMAGE_FONT = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
IMAGE_WIDTH = 1080
ROW_HEIGHT = 90
FONT_SIZE = 40

CTRIP_LINES = (
    "订单确认单",
    "尊敬的客户,",
    "请查收您的行程确认单。 房费预付到携程,酒店不提供水单。",
    "行程",
    "订单号 1100000000000001 订单金额: ¥1,316.00 (个人支付)",
    "杭州 - 杭州西湖示例假日酒店",
    "入住日期 2026年9月1日 14:00后 离店日期 2026年9月3日 12:00前",
    "房型 高级双床房 房间数量 2",
    "酒店电话 +86-571-00000000 酒店类型 会员酒店",
    "酒店地址 杭州 浙江杭州西湖区示例路1号 酒店确认号",
    "支付方式 个人支付",
    "入住人",
    "张示例",
    "取消政策",
    "2026年9月1日12:00前可免费取消。",
    "Copyright © 1999-2026, ctrip.com. all rights reserved",
)
BOOKING_LINES = (
    "Booking confirmation",
    "Example Canal Hotel",
    "Address: Example Street 1, 1000 AA Amsterdam, Netherlands",
    "Confirmation number: 4012.345.678",
    "PIN code: 0000",
    "Check-in Friday, 4 September 2026 from 15:00",
    "Check-out Sunday, 6 September 2026 until 11:00",
    "Your reservation 2 nights, 1 room",
    "Guest name Jane Example",
    "Total price € 360.00",
    "Copyright © 1996-2026 Booking.com. All rights reserved.",
)
MEITUAN_ROWS = (
    ("订单详情", None),
    ("预订成功", None),
    ("上海示例假日酒店", None),
    ("入住 09月10日 周四", "离店 09月12日 周六"),
    ("共2晚 1间", "大床房"),
    ("入住人 王示例", None),
    ("地址 上海市示例区示例路1号", None),
    ("订单号 2600000000000123", None),
    ("下单时间 2026-09-01 10:20", None),
    ("在线支付", "¥616"),
    ("美团酒店", None),
)
RAIL_ORDER_ROWS = (
    ("订单详情", None),
    ("订单号 E123456789", None),
    ("发车时间 2026-09-10 08:00", None),
    ("上海虹桥站  G7  南京南站", None),
    ("乘车人 张示例", "二等座"),
    ("05车12A号", None),
    ("票价 ¥139.50", None),
    ("已支付", None),
    ("中国铁路12306", None),
)


def write_text_pdf(name: str, lines: tuple[str, ...], font: str) -> None:
    canvas = Canvas(str(OUT_DIR / name), pagesize=A4)
    canvas.setTitle("fixture")
    for index, line in enumerate(lines):
        canvas.setFont(font, 10)
        canvas.drawString(40, 800 - index * 22, line)
    canvas.save()


def write_screenshot(name: str, rows: tuple[tuple[str, str | None], ...]) -> None:
    height = 80 + ROW_HEIGHT * len(rows)
    image = Image.new("RGB", (IMAGE_WIDTH, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(IMAGE_FONT), FONT_SIZE)
    for index, (left, right) in enumerate(rows):
        y = 40 + index * ROW_HEIGHT
        draw.text((40, y), left, fill="black", font=font)
        if right:
            draw.text((IMAGE_WIDTH - 460, y), right, fill="black", font=font)
    image.save(OUT_DIR / name)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    font = register_font()
    write_text_pdf("ctrip_hotel.pdf", CTRIP_LINES, font)
    write_text_pdf("booking_hotel.pdf", BOOKING_LINES, font)
    write_screenshot("meituan_hotel.png", MEITUAN_ROWS)
    write_screenshot("rail_order_12306.png", RAIL_ORDER_ROWS)
    print(f"样本已写入 {OUT_DIR}")


if __name__ == "__main__":
    main()
