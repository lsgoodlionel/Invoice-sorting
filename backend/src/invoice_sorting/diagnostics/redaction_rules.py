"""脱敏的正则规则表（设计《日志与故障上报》4 脱敏）。

规则是**有序**的：先处理最具体、最敏感的（密钥、邮箱），再处理宽泛的（数字、主机名），
否则宽泛规则会先把敏感串吃掉、留下无法判断的占位符。

白名单式保留：堆栈里的模块路径（`.py`）、异常类型、行号、SQL 语句结构不在任何规则的
匹配范围内，只有可疑串才会被替换。
"""

import re
from collections.abc import Callable

PLACEHOLDER_SECRET = "<已隐去>"
PLACEHOLDER_EMAIL = "<邮箱>"
PLACEHOLDER_PHONE = "<手机号>"
PLACEHOLDER_ID = "<证件号>"
PLACEHOLDER_CARD = "<卡号>"
PLACEHOLDER_TAX = "<税号>"
PLACEHOLDER_INVOICE = "<发票号>"
PLACEHOLDER_NUMBER = "<数字>"
PLACEHOLDER_NAME = "<名称>"
PLACEHOLDER_FILENAME = "<文件名>"
PLACEHOLDER_HOST = "<主机>"
PLACEHOLDER_IP = "<IP>"
PLACEHOLDER_USER = "<用户>"
PLACEHOLDER_SQL_VALUE = "'<值>'"

# 键值对里“值”的字符集：到空白、引号、逗号、分号或括号为止
_VALUE = r"[^\"'\s,;&)}\]]+"
_QUOTE = r"(?:\"|')?"

_SECRET_KEYS = (
    r"(?:token|secret|passwd|password|pwd|cookie|authorization|credential|"
    r"api[_-]?key|access[_-]?key|private[_-]?key|public[_-]?key|license[_-]?key|"
    r"secret[_-]?key|session[_-]?(?:token|id|key)|密钥|令牌|密码|口令)"
)
# 允许 log_token、github_token 这类带前缀的键名；前后用零宽断言收口，避免在长串里反复尝试
_KEY_PREFIX = r"(?<![A-Za-z0-9_\-])[A-Za-z0-9_\-]{0,32}"
_KEY_SUFFIX = r"(?![A-Za-z0-9_\-])"
_NAME_KEYS = (
    r"(?:merchant|seller|vendor|buyer|guest|nickname|username|user[_-]?name|"
    r"display[_-]?name|full[_-]?name|销售方|购买方|开票方|商家|商户|入住人|用户名|"
    r"姓名|显示名|开户名)"
)
_INVOICE_KEYS = (
    r"(?:发票号码?|发票代码|订单号|流水号|交易号|"
    r"invoice[_-]?(?:no|number|code)|order[_-]?(?:no|id|number)|serial[_-]?no)"
)
_AMOUNT_KEYS = r"(?:amount|total|price|金额|税额|价税合计|合计|不含税金额)"

# 发票、凭证原件常见扩展名；`.py`/`.log`/`.json` 等不在其中，堆栈与配置路径不受影响
_MEDIA_EXT = r"(?:pdf|ofd|jpe?g|png|webp|heic|bmp|tiff?|gif|xlsx?|docx?|csv|xml|eml|msg)"
# 保留的“类型词”，顺序即优先级：知道是哪类凭证出问题，但不知道是谁的
TYPE_WORDS = (
    "发票",
    "行程单",
    "火车票",
    "机票",
    "住宿",
    "酒店",
    "订单",
    "回单",
    "水单",
    "小票",
    "收据",
    "凭证",
)
_SAFE_HOSTS = frozenset({"github.com", "api.github.com", "example.com", "localhost"})
_PUBLIC_TLD = r"(?:com|cn|net|org|io|dev|co|top|xyz|info|biz|me|app|site)"
_PRIVATE_IP_PREFIXES = ("10.", "127.", "169.254.", "192.168.")
_LONG_RANDOM_MIN = 40

# 各处都用「前一个字符不属于本串」的零宽断言收口：长串里只在 token 起点尝试一次，
# 避免 `[..]+` 在超长日志行上退化成 O(n²)
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,24}"
)
PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
CN_ID_PATTERN = re.compile(
    r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![\dXx])"
)
CARD_PATTERN = re.compile(r"(?<!\d)\d{13,19}(?!\d)")
TOKEN_SHAPE_PATTERN = re.compile(
    r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"
    r"|\bgithub_pat_[A-Za-z0-9_]{20,}\b"
    r"|(?i:\bbearer\s+)[A-Za-z0-9._\-]{8,}"
    rf"|\b[A-Za-z0-9+/]{{{_LONG_RANDOM_MIN},}}={{0,2}}\b"
)


def _replace_ipv4(match: re.Match[str]) -> str:
    """内网地址保留网段形态（便于判断拓扑），公网地址整体替换。"""
    address = match.group(0)
    if any(address.startswith(prefix) for prefix in _PRIVATE_IP_PREFIXES) or _is_carrier_nat(
        address
    ):
        first, second, _, _ = address.split(".")
        return f"{first}.{second}.x.x"
    return PLACEHOLDER_IP


def _is_carrier_nat(address: str) -> bool:
    """172.16.0.0/12 也是内网段，需要按第二段判断。"""
    parts = address.split(".")
    return parts[0] == "172" and parts[1].isdigit() and 16 <= int(parts[1]) <= 31


def _replace_filename(match: re.Match[str]) -> str:
    """保留扩展名与类型词，其余换成占位符。"""
    stem, _, extension = match.group(0).rpartition(".")
    kept = next((word for word in TYPE_WORDS if word in stem), "")
    return f"{PLACEHOLDER_FILENAME}{kept}.{extension}"


def _replace_host(match: re.Match[str]) -> str:
    host = match.group(0)
    return host if host.lower() in _SAFE_HOSTS else PLACEHOLDER_HOST


Rule = tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]

# 只针对密钥的规则：运行日志实时过滤用它，成本低、不会打乱堆栈与业务文案
SECRET_RULES: tuple[Rule, ...] = (
    # 1. 密钥、令牌、Cookie、密码：保留键名，值一律隐去
    (
        re.compile(
            rf"(?i)({_QUOTE}{_KEY_PREFIX}{_SECRET_KEYS}{_KEY_SUFFIX}{_QUOTE}\s*[=:：]\s*)"
            rf"{_QUOTE}{_VALUE}{_QUOTE}"
        ),
        rf"\1{PLACEHOLDER_SECRET}",
    ),
    (
        re.compile(r"(?i)\b(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})\b"),
        PLACEHOLDER_SECRET,
    ),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{8,}"), rf"\1{PLACEHOLDER_SECRET}"),
)

RULES: tuple[Rule, ...] = (
    *SECRET_RULES,
    # 2. 邮箱要排在“长随机串”前面，否则超长本地部分会先被当成密钥
    (EMAIL_PATTERN, PLACEHOLDER_EMAIL),
    (re.compile(rf"\b[A-Za-z0-9+/]{{{_LONG_RANDOM_MIN},}}={{0,2}}\b"), PLACEHOLDER_SECRET),
    # 3. 证件类号码：先长后短，避免身份证被当成银行卡
    (PHONE_PATTERN, PLACEHOLDER_PHONE),
    (CN_ID_PATTERN, PLACEHOLDER_ID),
    (
        re.compile(r"(?<![0-9A-Z])[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}(?![0-9A-Z])"),
        PLACEHOLDER_TAX,
    ),
    (re.compile(r"(?<!\d)\d{20}(?!\d)"), PLACEHOLDER_INVOICE),
    (
        re.compile(rf"(?i)({_INVOICE_KEYS}\s*[=:：]?\s*)[0-9A-Za-z\-]{{6,32}}"),
        rf"\1{PLACEHOLDER_INVOICE}",
    ),
    (CARD_PATTERN, PLACEHOLDER_CARD),
    # 4. 金额：只在有货币符号或金额键名时替换，堆栈行号不受影响
    (re.compile(r"[¥￥$]\s?\d[\d,]*(?:\.\d{1,2})?"), PLACEHOLDER_NUMBER),
    (re.compile(r"(?<!\d)\d[\d,]*\.\d{1,2}(?=\s*元)"), PLACEHOLDER_NUMBER),
    (
        re.compile(rf"(?i)({_AMOUNT_KEYS}\s*[=:：]\s*)-?\d[\d,]*(?:\.\d+)?"),
        rf"\1{PLACEHOLDER_NUMBER}",
    ),
    # 5. 文件名、主机名、IP、路径里的用户名
    (
        re.compile(
            rf"(?<![^\s/\\:*?\"<>|])[^\s/\\:*?\"<>|]{{1,120}}\.{_MEDIA_EXT}\b", re.IGNORECASE
        ),
        _replace_filename,
    ),
    (
        re.compile(
            rf"\b(?:[a-z0-9](?:[a-z0-9\-]{{0,61}}[a-z0-9])?\.)+{_PUBLIC_TLD}\b", re.IGNORECASE
        ),
        _replace_host,
    ),
    (re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"), _replace_ipv4),
    (re.compile(r"(/(?:home|Users|export/home)/)[^/\s]+"), rf"\1{PLACEHOLDER_USER}"),
    # 6. 商家、销售方、入住人、用户名与显示名
    (
        re.compile(
            rf"(?i)({_QUOTE}{_KEY_PREFIX}{_NAME_KEYS}{_KEY_SUFFIX}{_QUOTE}\s*[=:：]\s*)"
            rf"{_QUOTE}{_VALUE}{_QUOTE}"
        ),
        rf"\1{PLACEHOLDER_NAME}",
    ),
)

SQL_KEYWORD_PATTERN = re.compile(r"(?i)\b(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b")
SQL_LITERAL_PATTERN = re.compile(r"'[^']{0,200}'")

# 打包后的残留自检：这几类一旦出现就说明脱敏漏了，拒绝上传
RESIDUE_CHECKS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("邮箱", EMAIL_PATTERN),
    ("手机号", PHONE_PATTERN),
    ("身份证号", CN_ID_PATTERN),
    ("银行卡号", CARD_PATTERN),
    ("密钥形态", TOKEN_SHAPE_PATTERN),
)
