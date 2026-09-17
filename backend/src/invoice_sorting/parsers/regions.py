"""开票地区识别：按发票号码/代码中的省级税务机关代码，兜底用销售方税号的行政区划码。

规则（依次尝试，得到已知省级代码即返回）：
1. 数电发票 20 位号码：第 3–4 位为省级税务机关代码，如 25**31**7… → 上海。
2. 旧版发票“代码-号码”：
   - 12 位发票代码：第 2–3 位为省级代码，如 0**31**001900111 → 上海；
     计划单列市（大连 2102、宁波 3302、厦门 3502、青岛 3702、深圳 4403）的代码前两位
     本就是所在省，因此直接归入所在省（深圳 → 广东 44）。
   - 10 位发票代码（旧版纸票）：第 1–2 位为省级代码，如 **31**00162130 → 上海。
3. 销售方税号：18 位统一社会信用代码第 3–4 位（登记管理机关行政区划码前两位），
   如 91**31**… → 上海；15/17/20 位旧税号前两位为行政区划码。
未知或无法判断时返回 ("", "")。
"""

PROVINCES: dict[str, str] = {
    "11": "北京",
    "12": "天津",
    "13": "河北",
    "14": "山西",
    "15": "内蒙古",
    "21": "辽宁",
    "22": "吉林",
    "23": "黑龙江",
    "31": "上海",
    "32": "江苏",
    "33": "浙江",
    "34": "安徽",
    "35": "福建",
    "36": "江西",
    "37": "山东",
    "41": "河南",
    "42": "湖北",
    "43": "湖南",
    "44": "广东",
    "45": "广西",
    "46": "海南",
    "50": "重庆",
    "51": "四川",
    "52": "贵州",
    "53": "云南",
    "54": "西藏",
    "61": "陕西",
    "62": "甘肃",
    "63": "青海",
    "64": "宁夏",
    "65": "新疆",
}

DIGITAL_NO_LENGTH = 20
LEGACY_CODE_LENGTH = 12
PAPER_CODE_LENGTH = 10
USCC_LENGTH = 18
EMPTY_REGION = ("", "")


def _region(code: str) -> tuple[str, str]:
    name = PROVINCES.get(code, "")
    return (code, name) if name else EMPTY_REGION


def _code_from_invoice_no(invoice_no: str) -> str:
    head = invoice_no.split("-", 1)[0]
    if not head.isdigit():
        return ""
    if "-" not in invoice_no and len(head) == DIGITAL_NO_LENGTH:
        return head[2:4]
    if "-" in invoice_no and len(head) == LEGACY_CODE_LENGTH:
        return head[1:3]
    if "-" in invoice_no and len(head) == PAPER_CODE_LENGTH:
        return head[0:2]
    return ""


def _code_from_tax_id(tax_id: str) -> str:
    value = tax_id.strip().upper()
    if len(value) == USCC_LENGTH and value[2:4].isdigit():
        return value[2:4]
    if len(value) in (15, 17, 20) and value[0:2].isdigit():
        return value[0:2]
    return ""


def region_from_invoice(invoice_no: str | None, seller_tax_id: str) -> tuple[str, str]:
    """返回 (省级代码, 简称)，如 ("31", "上海")；无法判断为 ("", "")。"""
    if invoice_no:
        region = _region(_code_from_invoice_no(invoice_no.strip()))
        if region != EMPTY_REGION:
            return region
    return _region(_code_from_tax_id(seller_tax_id or ""))
