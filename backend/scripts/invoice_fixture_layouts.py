"""仿真实数电发票（京东/圆迈开具）版式的虚构样本布局，供 make_invoice_fixtures.py 调用。

坐标取自真实票面经 pdfplumber 抽取的位置（top 向下增大），所有名称、税号、号码均为虚构。
特点：竖排“购买方信息/销售方信息”单字、“名 称”字间空格且冒号另起一行、
“统一社会信用代码 纳税人识别号”后的“/ :”另起一行、项目名称列内小字号折行、折扣行。
"""

from pathlib import Path

from reportlab.pdfgen.canvas import Canvas

PAGE_SIZE = (609.44, 394.01)
LABEL_SIZE = 9.0
ITEM_SIZE = 5.0
ASCENT_RATIO = 0.9
ITEM_LINE_STEP = 5.8

SizedLine = tuple[float, float, str, float]  # (x, top, text, size)
ItemRow = tuple[tuple[str, ...], tuple[str, ...]]  # (名称折行, 首行其余列)

# 规格型号 单位 数量 单价 金额 税率 税额 的 x 坐标（与表头对齐）
CELL_COLUMNS = (159.0, 238.6, 324.0, 378.8, 452.5, 491.9, 575.6)
DISCOUNT_COLUMNS = (452.5, 491.9, 575.6)


def write_sized_pdf(path: Path, lines: list[SizedLine], font: str) -> None:
    canvas = Canvas(str(path), pagesize=PAGE_SIZE)
    canvas.setTitle("fixture")
    for x, top, text, size in lines:
        canvas.setFont(font, size)
        canvas.drawString(x, PAGE_SIZE[1] - top - size * ASCENT_RATIO, text)
    canvas.save()


def _label(x: float, top: float, text: str) -> SizedLine:
    return (x, top, text, LABEL_SIZE)


def _vertical(x: float, top: float, text: str) -> list[SizedLine]:
    return [_label(x, top + index * 10.8, char) for index, char in enumerate(text)]


def _party(offset: float, name: str, tax_id: str) -> list[SizedLine]:
    return [
        _label(41.0 + offset, 97.2, "名"),
        _label(55.2 + offset, 97.2, "称"),
        _label(64.2 + offset, 101.6, ":"),
        _label(71.5 + offset, 97.4, name),
        _label(41.0 + offset, 124.2, "统一社会信用代码"),
        _label(113.0 + offset, 128.6, "/"),
        _label(118.4 + offset, 124.2, "纳税人识别号"),
        _label(172.4 + offset, 128.6, ":"),
        _label(179.2 + offset, 124.2, tax_id),
    ]


def _header() -> list[SizedLine]:
    labels = (
        (58.7, "项目名称"),
        (159.8, "规格型号"),
        (233.8, "单位"),
        (307.9, "数 量"),
        (378.6, "单 价"),
        (450.4, "金 额"),
        (478.3, "税率/征收率"),
        (568.2, "税 额"),
    )
    return [_label(x, 146.2, text) for x, text in labels]


def _item_lines(rows: tuple[ItemRow, ...]) -> list[SizedLine]:
    lines: list[SizedLine] = []
    top = 155.3
    for names, cells in rows:
        columns = CELL_COLUMNS if len(cells) == len(CELL_COLUMNS) else DISCOUNT_COLUMNS
        lines += [(x, top, cell, ITEM_SIZE) for x, cell in zip(columns, cells, strict=True)]
        for name in names:
            lines.append((25.5, top, name, ITEM_SIZE))
            top += ITEM_LINE_STEP
    return lines


def jd_layout_lines(
    head: tuple[str, str],
    parties: tuple[tuple[str, str], tuple[str, str]],
    rows: tuple[ItemRow, ...],
    totals: tuple[str, str, str, str],
    order_no: str,
) -> list[SizedLine]:
    """head=(发票号码, 开票日期)；parties=((购方名, 税号), (销方名, 税号))；
    totals=(合计金额, 合计税额, 大写, 小写)。"""
    (buyer, buyer_id), (seller, seller_id) = parties
    lines = [
        _label(216.3, 28.2, "电子发票(普通发票)"),
        _label(454.7, 26.1, "发票号码:"),
        _label(498.1, 26.5, head[0]),
        _label(454.6, 41.1, "开票日期:"),
        _label(498.1, 41.6, head[1]),
        *_vertical(26.3, 87.1, "购买方信息"),
        *_vertical(312.2, 87.1, "销售方信息"),
        *_party(0.0, buyer, buyer_id),
        *_party(284.8, seller, seller_id),
        *_header(),
        *_item_lines(rows),
        _label(61.1, 258.2, "合"),
        _label(101.9, 258.2, "计"),
        _label(417.2, 256.2, f"¥{totals[0]}"),
        _label(569.1, 256.4, f"¥{totals[1]}"),
        _label(55.8, 276.9, "价税合计(大写)"),
        _label(179.7, 276.0, totals[2]),
        _label(426.8, 276.6, "(小写)"),
        _label(455.5, 276.0, f"¥{totals[3]}"),
        (43.1, 294.3, f"订单号:{order_no}", 6.5),
        _label(29.2, 301.4, "备"),
        _label(29.1, 331.5, "注"),
        _label(47.0, 360.5, "开票人: 示例"),
    ]
    return lines


def jd_spaced_labels_lines(buyer: tuple[str, str]) -> list[SizedLine]:
    """京东版式：名称折行且含空格，北京 11 号码。"""
    rows = (
        (
            ("*电线电缆*示例 DVI转HDMI转接头 DVI24+1/DVI-", "D双向互转 显示器转换头 ZH-340"),
            ("ZH-340", "卷", "1", "11.42", "11.42", "13%", "1.48"),
        ),
    )
    return jd_layout_lines(
        ("25117000009876543210", "2025年10月01日"),
        (buyer, ("北京示例贸易有限公司", "91110000MA0EXAMPLE")),
        rows,
        ("11.42", "1.48", "壹拾贰圆玖角", "12.90"),
        "338600000001",
    )


def discount_lines(buyer: tuple[str, str]) -> list[SizedLine]:
    """圆迈版式：两个商品各带一条同名折扣行（只有金额、税率、税额），上海 31 号码。"""
    first = ("*纸制品*示例牌（DEMO）抽纸 真 抽纸", "M码 无香4层90抽*18包 纸巾餐", "巾纸")
    second = ("*纸制品*示例牌（Demo）抽纸【推荐】", "棉韧3层100抽*24包S码 亲肤 纸巾 整", "箱")
    rows = (
        (first, ("抽纸", "箱", "1", "70.71", "70.71", "13%", "9.19")),
        (first, ("-19.46", "13%", "-2.53")),
        (second, ("抽纸", "箱", "2", "53.01", "106.02", "13%", "13.78")),
        (second, ("-61.49", "13%", "-7.99")),
    )
    return jd_layout_lines(
        ("25317000001234567890", "2025年06月19日"),
        (buyer, ("上海示例贸易有限公司", "91310000MA5EXAMPLE")),
        rows,
        ("95.78", "12.45", "壹佰零捌圆贰角叁分", "108.23"),
        "317600000002",
    )
