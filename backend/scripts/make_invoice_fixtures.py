"""生成发票解析单测用的虚构样本（PDF / XML / OFD）。

用法（在 backend/ 下）：uv run python scripts/make_invoice_fixtures.py
所有名称、税号、号码均为虚构值；生成后提交到 tests/fixtures/invoices/。
"""

import io
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path

import pdfplumber
from invoice_fixture_layouts import discount_lines, jd_spaced_labels_lines, write_sized_pdf
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

OUT_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "invoices"
TTF_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
)
CID_FONT = "STSong-Light"
PROBE_TEXT = "名称：华东师范大学"

BUYER = "华东师范大学"
BUYER_ID = "12310000EXAMPLE001"
SELLER = "上海示例科技有限公司"
SELLER_ID = "91310000MA1EXAMPLE"

Line = tuple[float, float, str]  # (x, y, text)


def _probe_font(font_name: str) -> bool:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    canvas.setFont(font_name, 10)
    canvas.drawString(40, 700, PROBE_TEXT)
    canvas.save()
    buffer.seek(0)
    with pdfplumber.open(buffer) as pdf:
        return PROBE_TEXT in (pdf.pages[0].extract_text() or "")


def register_font() -> str:
    """优先 Arial Unicode（TTF），提取乱码或不存在时退回 STSong-Light。"""
    for path in TTF_CANDIDATES:
        if not path.exists():
            continue
        pdfmetrics.registerFont(TTFont("ArialUnicode", str(path)))
        if _probe_font("ArialUnicode"):
            return "ArialUnicode"
    pdfmetrics.registerFont(UnicodeCIDFont(CID_FONT))
    if not _probe_font(CID_FONT):
        raise RuntimeError("没有可被 pdfplumber 正确提取中文的字体")
    return CID_FONT


def write_pdf(name: str, lines: list[Line], font: str, encrypt: str | None = None) -> None:
    encryption = StandardEncryption(encrypt, canPrint=0) if encrypt else None
    canvas = Canvas(str(OUT_DIR / name), pagesize=A4, encrypt=encryption)
    canvas.setTitle("fixture")
    for x, y, text in lines:
        canvas.setFont(font, 9)
        canvas.drawString(x, y, text)
    canvas.save()


def vertical(x: float, top: float, text: str, step: float = 13) -> list[Line]:
    return [(x, top - index * step, char) for index, char in enumerate(text)]


@dataclass(frozen=True)
class DigitalSpec:
    title: str
    invoice_no: str
    issued: str
    seller: str
    seller_id: str
    items: tuple[tuple[str, ...], ...]  # 名称 规格 单位 数量 单价 金额 税率 税额
    subtotal: tuple[str, str]
    upper: str
    lower: str
    same_line: bool


ITEM_COLUMNS = (30, 170, 225, 260, 300, 360, 430, 500)


def _item_rows(items: tuple[tuple[str, ...], ...], top: float) -> list[Line]:
    header = ("项目名称", "规格型号", "单位", "数量", "单价", "金额", "税率/征收率", "税额")
    rows = [(x, top, label) for x, label in zip(ITEM_COLUMNS, header, strict=True)]
    for index, item in enumerate(items, start=1):
        cells = zip(ITEM_COLUMNS, item, strict=True)
        rows.extend((x, top - 15 * index, cell) for x, cell in cells if cell)
    return rows


def _digital_parties(spec: DigitalSpec) -> list[Line]:
    seller_offset = 0 if spec.same_line else 13
    lines = vertical(28, 745, "购买方信息") + vertical(305, 745, "销售方信息")
    lines += [
        (45, 740, f"名称：{BUYER}"),
        (45, 712, f"统一社会信用代码/纳税人识别号：{BUYER_ID}"),
        (322, 740 - seller_offset, f"名称：{spec.seller}"),
        (322, 712 - seller_offset, f"统一社会信用代码/纳税人识别号：{spec.seller_id}"),
    ]
    return lines


def digital_lines(spec: DigitalSpec) -> list[Line]:
    lines: list[Line] = [
        (220, 805, spec.title),
        (400, 785, f"发票号码：{spec.invoice_no}"),
        (400, 771, f"开票日期：{spec.issued}"),
    ]
    lines += _digital_parties(spec)
    lines += _item_rows(spec.items, 660)
    subtotal_y = 560
    lines += [
        (60, subtotal_y, "合 计"),
        (360, subtotal_y, f"¥{spec.subtotal[0]}"),
        (500, subtotal_y, f"¥{spec.subtotal[1]}"),
        (30, 540, "价税合计（大写）"),
        (150, 540, f"⊗{spec.upper}"),
        (400, 540, f"（小写）¥{spec.lower}"),
        (30, 510, "备注"),
        (30, 480, "开票人：示例"),
    ]
    return lines


MOUSE = ("*计算机配套产品*鼠标", "M100", "个", "2", "424.78", "849.56", "13%", "110.44")


def digital_same_line() -> DigitalSpec:
    return DigitalSpec(
        title="电子发票（普通发票）",
        invoice_no="26312000000123456789",
        issued="2026年09月15日",
        seller=SELLER,
        seller_id=SELLER_ID,
        items=(MOUSE,),
        subtotal=("849.56", "110.44"),
        upper="玖佰陆拾圆整",
        lower="960.00",
        same_line=True,
    )


def digital_multiline() -> DigitalSpec:
    items = (
        ("*计算机配套产品*键盘", "K1", "个", "1", "176.99", "176.99", "13%", "23.01"),
        ("*信息技术服务*软件维护服务", "", "次", "1", "471.70", "471.70", "6%", "28.30"),
        ("*纸制品*打印纸", "A4", "包", "5", "17.70", "88.50", "13%", "11.50"),
    )
    return DigitalSpec(
        title="电子发票（增值税专用发票）",
        invoice_no="26312000000987654321",
        issued="2026年08月03日",
        seller="上海示例信息服务有限公司",
        seller_id="91310000MA3EXAMPLE",
        items=items,
        subtotal=("737.19", "62.81"),
        upper="捌佰圆整",
        lower="800.00",
        same_line=False,
    )


def digital_upper_mismatch() -> DigitalSpec:
    return replace(digital_same_line(), invoice_no="26312000000000000001", upper="玖佰伍拾圆整")


def vat_normal_lines() -> list[Line]:
    password = "03*+<8/>9-2*1<6>>*/58+-7<3"
    lines: list[Line] = [
        (200, 805, "上海增值税电子普通发票"),
        (40, 778, "机器编号：499000000000"),
        (400, 790, "发票代码：031001900111"),
        (400, 778, "发票号码：12345678"),
        (400, 766, "开票日期：2026年03月20日"),
        (400, 754, "校 验 码：12345 67890 12345 67890"),
    ]
    lines += vertical(28, 732, "购买方") + vertical(315, 732, "密码区")
    lines += [
        (45, 730, f"名    称：{BUYER}"),
        (45, 716, f"纳税人识别号：{BUYER_ID}"),
        (45, 702, "地 址、电 话："),
        (45, 688, "开户行及账号："),
    ]
    lines += [(330, 730 - 14 * row, password) for row in range(4)]
    header = (
        "货物或应税劳务、服务名称",
        "规格型号",
        "单位",
        "数量",
        "单价",
        "金额",
        "税率",
        "税额",
    )
    row = ("*餐饮服务*餐费", "", "次", "1", "283.02", "283.02", "6%", "16.98")
    lines += [(x, 650, text) for x, text in zip(ITEM_COLUMNS, header, strict=True)]
    lines += [(x, 635, text) for x, text in zip(ITEM_COLUMNS, row, strict=True) if text]
    lines += [
        (60, 600, "合 计"),
        (360, 600, "¥283.02"),
        (500, 600, "¥16.98"),
        (30, 585, "价税合计（大写） ⊗叁佰圆整"),
        (400, 585, "（小写）¥300.00"),
    ]
    lines += vertical(28, 562, "销售方") + vertical(315, 562, "备注")
    lines += [
        (45, 560, "名    称：上海示例餐饮管理有限公司"),
        (45, 546, "纳税人识别号：91310000MA2EXAMPLE"),
        (45, 532, "地 址、电 话：上海市示例路1号"),
        (30, 490, "收款人：示例 复核：示例 开票人：示例 销售方：（章）"),
    ]
    return lines


def rail_lines() -> list[Line]:
    return [
        (200, 805, "电子发票（铁路电子客票）"),
        (380, 780, "发票号码：26319000000087654321"),
        (380, 766, "开票日期：2026年09月10日"),
        (60, 720, "上海虹桥站"),
        (260, 720, "G7"),
        (420, 720, "南京南站"),
        (60, 705, "Shanghaihongqiao"),
        (420, 705, "Nanjingnan"),
        (60, 680, "2026年09月12日 08:00开"),
        (260, 680, "05车12A号"),
        (420, 680, "二等座"),
        (60, 660, "票价：￥139.50"),
        (60, 640, "3101011990****1234 张示例"),
        (60, 620, "电子客票号：E1234567890123456789"),
        (60, 600, f"购买方名称：{BUYER}"),
        (300, 600, f"统一社会信用代码：{BUYER_ID}"),
        (60, 570, "报销凭证 遗失不补 退票改签时须交回车站"),
        (60, 550, "中国铁路祝您旅途愉快"),
    ]


def air_lines() -> list[Line]:
    return [
        (180, 805, "电子发票（航空运输电子客票行程单）"),
        (380, 780, "发票号码：26312000000055556666"),
        (380, 766, "填开日期：2026年09月08日"),
        (40, 730, "旅客姓名：张示例"),
        (220, 730, "有效身份证件号码：3101011990****1234"),
        (190, 705, "承运人"),
        (240, 705, "航班号"),
        (300, 705, "座位等级"),
        (350, 705, "日期"),
        (420, 705, "时间"),
        (40, 690, "自：上海虹桥 SHA"),
        (190, 690, "东航"),
        (240, 690, "MU5101"),
        (300, 690, "Y"),
        (350, 690, "2026-09-20"),
        (420, 690, "08:00"),
        (40, 675, "至：北京首都 PEK"),
        (40, 640, "票价：CNY 1000.00"),
        (180, 640, "民航发展基金：CNY 50.00"),
        (340, 640, "燃油附加费：CNY 30.00"),
        (40, 625, "合计：CNY 1080.00"),
        (40, 600, "电子客票号码：7811234567890"),
        (40, 585, "填开单位：上海示例航空票务有限公司"),
        (40, 570, f"购买方名称：{BUYER}"),
        (300, 570, f"统一社会信用代码：{BUYER_ID}"),
    ]


def invoice_xml(invoice_no: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<EInvoice xmlns="urn:example:einvoice">
  <Header>
    <EIid>{invoice_no}</EIid>
    <InherentLabel><GeneralOrSpecialVAT>
      <LabelCode>02</LabelCode><LabelName>普通发票</LabelName>
    </GeneralOrSpecialVAT></InherentLabel>
  </Header>
  <EInvoiceData>
    <SellerInformation><SellerIdNum>{SELLER_ID}</SellerIdNum><SellerName>{SELLER}</SellerName>
    </SellerInformation>
    <BuyerInformation><BuyerIdNum>{BUYER_ID}</BuyerIdNum><BuyerName>{BUYER}</BuyerName>
    </BuyerInformation>
    <BasicInformation>
      <TotalAmWithoutTax>849.56</TotalAmWithoutTax>
      <TotalTaxAm>110.44</TotalTaxAm>
      <TotalTax-includedAmount>960.00</TotalTax-includedAmount>
      <TotalTax-includedAmountInChinese>玖佰陆拾圆整</TotalTax-includedAmountInChinese>
      <RequestTime>2026-09-15 10:20:30</RequestTime>
    </BasicInformation>
    <IssuItemInformation><ItemName>*计算机配套产品*鼠标</ItemName><Amount>800.00</Amount>
    </IssuItemInformation>
    <IssuItemInformation><ItemName>*计算机配套产品*鼠标垫</ItemName><Amount>49.56</Amount>
    </IssuItemInformation>
  </EInvoiceData>
  <TaxSupervisionInfo>
    <InvoiceNumber>{invoice_no}</InvoiceNumber><IssueTime>2026-09-15</IssueTime>
  </TaxSupervisionInfo>
</EInvoice>
"""


OFD_ROOT = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:OFD xmlns:ofd="http://www.ofdspec.org/2016" Version="1.1" DocType="OFD">
  <ofd:DocBody><ofd:DocRoot>Doc_0/Document.xml</ofd:DocRoot></ofd:DocBody>
</ofd:OFD>
"""


def _text_object(index: int, x: float, y: float, text: str) -> str:
    return (
        f'<ofd:TextObject ID="{index}" Boundary="{x} {y} 200 5" Font="1" Size="3.5">'
        f'<ofd:TextCode X="0" Y="4">{text}</ofd:TextCode></ofd:TextObject>'
    )


def ofd_content(lines: list[Line]) -> str:
    """把 PDF 坐标（y 向上，pt）转成 OFD 坐标（y 向下，mm 近似）。"""
    objects = "".join(
        _text_object(index, round(x / 2.83, 1), round((842 - y) / 2.83, 1), text)
        for index, (x, y, text) in enumerate(lines, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"><ofd:Content><ofd:Layer ID="0">'
        f"{objects}</ofd:Layer></ofd:Content></ofd:Page>"
    )


def write_ofd(name: str, lines: list[Line], attached_xml: str | None) -> None:
    with zipfile.ZipFile(OUT_DIR / name, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("OFD.xml", OFD_ROOT)
        archive.writestr("Doc_0/Document.xml", '<?xml version="1.0"?><ofd:Document/>')
        archive.writestr("Doc_0/Pages/Page_0/Content.xml", ofd_content(lines))
        if attached_xml:
            archive.writestr("Doc_0/Attachs/invoice.xml", attached_xml)


def not_invoice_lines() -> list[Line]:
    return [
        (200, 800, "学术会议通知"),
        (40, 760, "兹定于2026年10月20日在示例楼举行学术研讨会，请各位老师准时参加。"),
        (40, 740, "联系人：示例 电话：021-00000000"),
    ]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    font = register_font()
    print(f"使用字体：{font}")
    write_pdf("digital_same_line.pdf", digital_lines(digital_same_line()), font)
    write_pdf("digital_multiline.pdf", digital_lines(digital_multiline()), font)
    write_pdf("digital_upper_mismatch.pdf", digital_lines(digital_upper_mismatch()), font)
    write_pdf("vat_electronic_normal.pdf", vat_normal_lines(), font)
    buyer = (BUYER, BUYER_ID)
    write_sized_pdf(OUT_DIR / "jd_spaced_labels.pdf", jd_spaced_labels_lines(buyer), font)
    write_sized_pdf(OUT_DIR / "discount_lines.pdf", discount_lines(buyer), font)
    write_pdf("rail_ticket.pdf", rail_lines(), font)
    write_pdf("air_itinerary.pdf", air_lines(), font)
    write_pdf("not_invoice.pdf", not_invoice_lines(), font)
    write_pdf("encrypted.pdf", digital_lines(digital_same_line()), font, encrypt="secret")
    (OUT_DIR / "corrupt.pdf").write_bytes(
        b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R\n\x00\xff"
    )
    (OUT_DIR / "digital_invoice.xml").write_text(invoice_xml("26312000000011112222"), "utf-8")
    write_ofd("digital_with_xml.ofd", [], invoice_xml("26312000000033334444"))
    write_ofd("digital_text_only.ofd", digital_lines(digital_multiline()), None)
    print(f"样本已写入 {OUT_DIR}")


if __name__ == "__main__":
    main()
