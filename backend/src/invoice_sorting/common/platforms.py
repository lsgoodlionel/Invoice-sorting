"""电商平台关键词：用于判断网购，以及“综合平台商家”不做商家→分类记忆（什么都卖）。"""

ONLINE_PLATFORM_KEYWORDS: tuple[str, ...] = (
    "京东", "天猫", "淘宝", "当当", "拼多多", "圆迈", "苏宁", "抖音", "亚马逊", "唯品会",
)  # fmt: skip


def is_marketplace_seller(seller_name: str | None) -> bool:
    """销售方名称含电商平台关键词（如“上海圆迈贸易有限公司”“北京京东世纪贸易有限公司”）。"""
    seller = (seller_name or "").strip()
    return bool(seller) and any(keyword in seller for keyword in ONLINE_PLATFORM_KEYWORDS)
