"""商家/平台词表：境外订阅的订单、收据与银行交易描述之间的平台兼容判断（可扩展）。"""

import re

APP_STORE_RECOGNIZER = "app_store_order"
PLATFORM_APPLE = "apple"

# 平台 → 出现在商家、商品或交易描述中的关键词（大写比较）
PLATFORM_KEYWORDS: dict[str, tuple[str, ...]] = {
    PLATFORM_APPLE: ("APPLE", "APP STORE", "APPSTORE", "ITUNES", "苹果"),
    "openai": ("OPENAI", "CHATGPT"),
    "anthropic": ("ANTHROPIC", "CLAUDE"),
    "windsurf": ("WINDSURF", "EXAFUNCTION", "CODEIUM", "STRIPE"),
    "github": ("GITHUB",),
    "google": ("GOOGLE",),
    "microsoft": ("MICROSOFT", "MSFT"),
}
# 通过 App Store 订阅时，订单商品名中的这些平台也视为 Apple 订单
APP_STORE_SUBSCRIPTIONS = frozenset({"openai", "anthropic"})
NON_WORD = re.compile(r"[\s*/._\-]+")


def platform_tokens(*texts: str, recognizer: str = "") -> frozenset[str]:
    """从商家、商品名等文本中识别平台；App Store 订单总是带 apple。"""
    haystack = " ".join(text for text in texts if text).upper()
    squashed = NON_WORD.sub("", haystack)
    found = {
        platform
        for platform, keywords in PLATFORM_KEYWORDS.items()
        if any(keyword in haystack or NON_WORD.sub("", keyword) in squashed for keyword in keywords)
    }
    if recognizer == APP_STORE_RECOGNIZER:
        found.add(PLATFORM_APPLE)
    return frozenset(found)


def platforms_compatible(first: frozenset[str], second: frozenset[str]) -> bool:
    """两侧平台有交集即兼容；订单是 App Store 订阅（Claude/ChatGPT）时与 Apple 扣款兼容。"""
    if first & second:
        return True
    return _app_store_subscription(first, second) or _app_store_subscription(second, first)


def _app_store_subscription(order: frozenset[str], payment: frozenset[str]) -> bool:
    """一侧只是 Apple 扣款（不含订阅平台词），另一侧是订阅平台的订单。"""
    is_apple_charge = PLATFORM_APPLE in payment and not (payment & APP_STORE_SUBSCRIPTIONS)
    return is_apple_charge and bool(order & APP_STORE_SUBSCRIPTIONS)
