"""首次启动时写入默认分类与凭证清单模板（蓝图 4.1 / 4.2）；默认关键词升级时合并进已有分类。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.default_keywords import (
    DEFAULT_KEYWORDS,
    KEYWORDS_REMOVED_IN,
    KEYWORDS_VERSION,
)
from invoice_sorting.db.models import AppSetting, Category, ChecklistRule

YUAN = 100
KEYWORDS_VERSION_KEY = "keywords_version"
RULES_VERSION_KEY = "rules_version"
RULES_VERSION = 4
BASE_RULES_VERSION = 1  # 未记录 rules_version 的旧库视为版本 1

BOOK_CATEGORY: dict = {
    "name": "图书",
    "color": "sienna",
    "route_hint": "单册或单套≥500元需图书馆验收后报销；<500元附购书清单或详细书名；"
    "非书店购买附供货单位电脑小票，网购书籍附送货清单；单张或累计>3万元附合同。",
}

DEFAULT_CATEGORIES: list[dict] = [
    {
        "name": "办公用品",
        "color": "blue",
        "route_hint": "办公用品不在设备与实验室平台填报，走日常报销。",
    },
    {
        "name": "易耗品",
        "color": "teal",
        "route_hint": "公共数据库 → 设备与实验室 → 报账管理 → 材料易耗品低值品报账 → "
        "新增报账单 → 审批后打印验收单；报销金额填“材料费”。",
    },
    {
        "name": "低值品",
        "color": "cyan",
        "route_hint": "同易耗品路径：材料易耗品低值品报账，审批后打印验收单。",
    },
    {
        "name": "设备",
        "color": "indigo",
        "route_hint": "单价≥1000元设备先申购报账，再到财务“资产业务”；申购时间须早于购买时间。",
    },
    {
        "name": "材料",
        "color": "green",
        "route_hint": "材料易耗品低值品报账，审批后打印验收单；金额填“材料费”。",
    },
    {
        "name": "软件服务",
        "color": "violet",
        "route_hint": "无形资产软件报账，审批后打印验收单；金额填“委托其他业务费”。",
    },
    {
        "name": "印刷快递",
        "color": "orange",
        "route_hint": "打印费需附明细或票面已开明细。",
    },
    {
        "name": "差旅交通",
        "color": "yellow",
        "route_hint": "选择国内差旅费；市内交通附发票及行程单，个人出行与节假日不报。",
    },
    {
        "name": "餐饮会议",
        "color": "red",
        "route_hint": "工作餐附工作餐单（50元/人/餐）；"
        "会议附预算决算表、申请流程、签到表、通知或议程。",
    },
    BOOK_CATEGORY,
    {"name": "其他", "color": "gray", "route_hint": ""},
]

# 分类版本 → 该版本新增的默认分类名；已有数据库升级时补上（按名称判断，已存在则跳过）
CATEGORIES_ADDED_IN: dict[int, tuple[str, ...]] = {3: ("图书",)}

RuleSpec = tuple[str | None, str, str, dict, str]

NONLOCAL_ORDER_RULE: RuleSpec = (
    None,
    "order",
    "required",
    {"is_nonlocal": True, "detail_platform": False},
    "外地发票需附网购订单截图（京东、当当、圆迈等已带明细平台可免）；"
    "非网购的外地购品需随差旅报销并说明途中购买必要性",
)

BOOK_RULES: tuple[RuleSpec, ...] = (
    (
        "图书",
        "order",
        "required",
        {},
        "附购书清单或详细书名；网购书籍附送货清单/订单，月结附结算清单",
    ),
    (
        "图书",
        "acceptance",
        "suggested",
        {"amount_gte": 500 * YUAN},
        "单册或单套≥500元需图书馆验收后报销",
    ),
)

NOT_EXEMPT: dict = {"invoice_exempt": False}
EXEMPT: dict = {"invoice_exempt": True}
INVOICE_RULE: RuleSpec = (None, "invoice", "required", NOT_EXEMPT, "报销需附发票原件")

EXEMPT_RULES: tuple[RuleSpec, ...] = (
    (
        None,
        "order",
        "required",
        EXEMPT,
        "境外消费无发票：附订单或收据（显示商品、金额、日期）",
    ),
    (None, "payment", "required", EXEMPT, "附银行卡交易明细，显示人民币入账金额"),
    (None, "statement", "suggested", EXEMPT, "说明用途及无法取得发票的原因"),
)

# (分类名 或 None=通用, 附件类型, 级别, 条件, 提示)
DEFAULT_RULES: list[RuleSpec] = [
    INVOICE_RULE,
    *EXEMPT_RULES,
    (
        None,
        "payment",
        "required",
        {"amount_gte": 1000 * YUAN},
        "单张发票≥1000元需附支付记录；同一商家累计也需注意",
    ),
    (
        None,
        "contract",
        "required",
        {"amount_gte": 30000 * YUAN},
        "一般≥3万元附合同，需职能部门盖章，不得倒签",
    ),
    NONLOCAL_ORDER_RULE,
    ("办公用品", "order", "required", {"is_online": True}, "网购办公用品需附机打订单清单"),
    ("办公用品", "order", "required", {"amount_gte": 500 * YUAN}, "≥500元需附明细清单"),
    ("易耗品", "order", "required", {}, "附订单或明细"),
    ("易耗品", "acceptance", "required", {}, "平台报账审批后打印验收单"),
    ("低值品", "order", "required", {}, "附订单或明细"),
    ("低值品", "acceptance", "required", {}, "平台报账审批后打印验收单"),
    ("材料", "order", "required", {}, "附订单或明细"),
    ("材料", "acceptance", "required", {}, "平台报账审批后打印验收单"),
    ("设备", "application", "required", {}, "单价≥1000元设备需先申购，申购日期早于购买日期"),
    ("设备", "acceptance", "required", {}, "设备验收单"),
    ("设备", "payment", "required", {}, "设备需转账付款凭证"),
    ("软件服务", "order", "required", {}, "附订单"),
    ("软件服务", "software_form", "required", {}, "附软件服务报账单"),
    ("软件服务", "acceptance", "required", {}, "审批后打印验收单"),
    *BOOK_RULES,
    ("印刷快递", "order", "suggested", {}, "打印费附明细（票面已开明细可免）"),
    ("差旅交通", "itinerary", "required", {}, "附行程单，需与出差单对应"),
    ("餐饮会议", "meal_form", "suggested", {}, "工作餐附工作餐单，50元/人/餐"),
    ("餐饮会议", "meeting", "suggested", {}, "会议附预算决算表、签到表、通知或议程"),
]

# 规则版本 → 该版本新增的默认规则；已有数据库升级时只追加这些规则
RULES_ADDED_IN: dict[int, tuple[RuleSpec, ...]] = {
    2: (NONLOCAL_ORDER_RULE,),
    3: BOOK_RULES,
    4: EXEMPT_RULES,
}
EXEMPT_CONDITION_VERSION = 4  # 该版本起通用“发票”规则只对非免发票记录触发


def seed_defaults(session: Session) -> None:
    if session.scalar(select(Category.id).limit(1)) is not None:
        return
    by_name: dict[str, Category] = {}
    for index, data in enumerate(DEFAULT_CATEGORIES):
        keywords = list(DEFAULT_KEYWORDS.get(data["name"], ()))
        category = Category(sort=index, keywords=keywords, **data)
        session.add(category)
        by_name[category.name] = category
    session.flush()
    for spec in DEFAULT_RULES:
        session.add(_rule_from(spec, by_name[spec[0]].id if spec[0] else None))
    session.merge(AppSetting(key=KEYWORDS_VERSION_KEY, value=str(KEYWORDS_VERSION)))
    session.merge(AppSetting(key=RULES_VERSION_KEY, value=str(RULES_VERSION)))
    session.commit()


def _rule_from(spec: RuleSpec, category_id: int | None) -> ChecklistRule:
    _cat_name, kind, level, condition, hint = spec
    return ChecklistRule(
        category_id=category_id,
        attachment_kind=kind,
        level=level,
        condition=dict(condition),
        hint=hint,
    )


def sync_default_keywords(session: Session) -> None:
    """默认词表版本升级时，把新增关键词追加到同名分类；同一版本只合并一次。"""
    stored = session.get(AppSetting, KEYWORDS_VERSION_KEY)
    if stored is not None and stored.value == str(KEYWORDS_VERSION):
        return
    version = int(stored.value) if stored is not None and stored.value.isdigit() else 1
    _add_missing_categories(session, version)
    for category in session.scalars(select(Category)):
        removed = _removed_keywords(category.name, version)
        existing = [kw for kw in category.keywords or [] if kw not in removed]
        additions = [kw for kw in DEFAULT_KEYWORDS.get(category.name, ()) if kw not in existing]
        if additions or len(existing) != len(category.keywords or []):
            category.keywords = existing + additions
    session.merge(AppSetting(key=KEYWORDS_VERSION_KEY, value=str(KEYWORDS_VERSION)))
    session.commit()


def _add_missing_categories(session: Session, version: int) -> None:
    names = {
        name
        for added_in, items in CATEGORIES_ADDED_IN.items()
        if added_in > version
        for name in items
    }
    existing = set(session.scalars(select(Category.name)))
    max_sort = max(session.scalars(select(Category.sort)), default=0)
    for data in DEFAULT_CATEGORIES:
        if data["name"] in names and data["name"] not in existing:
            max_sort += 1
            keywords = list(DEFAULT_KEYWORDS.get(data["name"], ()))
            session.add(Category(sort=max_sort, keywords=keywords, **data))
    session.flush()


def _removed_keywords(category_name: str, version: int) -> set[str]:
    return {
        keyword
        for removed_in, by_category in KEYWORDS_REMOVED_IN.items()
        if removed_in > version
        for keyword in by_category.get(category_name, ())
    }


def _stored_rules_version(session: Session) -> int:
    stored = session.get(AppSetting, RULES_VERSION_KEY)
    if stored is None or not stored.value.isdigit():
        return BASE_RULES_VERSION
    return int(stored.value)


def _has_rule(session: Session, category_id: int | None, kind: str, condition: dict) -> bool:
    category_filter = (
        ChecklistRule.category_id.is_(None)
        if category_id is None
        else ChecklistRule.category_id == category_id
    )
    query = select(ChecklistRule).where(category_filter, ChecklistRule.attachment_kind == kind)
    return any(dict(rule.condition or {}) == condition for rule in session.scalars(query))


def _append_rule(session: Session, spec: RuleSpec) -> None:
    cat_name, kind, _level, condition, _hint = spec
    category_id = None
    if cat_name is not None:
        category_id = session.scalar(select(Category.id).where(Category.name == cat_name))
        if category_id is None:
            return  # 用户已删除/改名该分类，不再补
    if not _has_rule(session, category_id, kind, condition):
        session.add(_rule_from(spec, category_id))
        session.flush()


def _restrict_invoice_rule(session: Session) -> None:
    """版本 4 的修改（非追加）：通用、条件为空的“发票”规则改为仅对非免发票记录触发。

    只改条件恰好为 {} 的规则；用户改过条件的规则保持不变，重复执行无副作用。
    """
    query = select(ChecklistRule).where(
        ChecklistRule.category_id.is_(None), ChecklistRule.attachment_kind == "invoice"
    )
    for rule in session.scalars(query):
        if dict(rule.condition or {}) == {}:
            rule.condition = dict(NOT_EXEMPT)
    session.flush()


def sync_default_rules(session: Session) -> None:
    """默认规则版本升级时，追加新版本引入且尚不存在的同类同条件规则；不删除用户规则。"""
    version = _stored_rules_version(session)
    if version >= RULES_VERSION:
        return
    if version < EXEMPT_CONDITION_VERSION:
        _restrict_invoice_rule(session)
    for added_in, specs in sorted(RULES_ADDED_IN.items()):
        if added_in <= version:
            continue
        for spec in specs:
            _append_rule(session, spec)
    session.merge(AppSetting(key=RULES_VERSION_KEY, value=str(RULES_VERSION)))
    session.commit()
