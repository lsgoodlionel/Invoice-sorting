"""首次启动时写入默认分类与凭证清单模板（蓝图 4.1 / 4.2）。已有数据时不重复写入。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import Category, ChecklistRule

YUAN = 100

DEFAULT_CATEGORIES: list[dict] = [
    {
        "name": "办公用品",
        "color": "blue",
        "keywords": [
            "文件夹",
            "签字笔",
            "中性笔",
            "便利贴",
            "打印纸",
            "复印纸",
            "文具",
            "办公用品",
        ],
        "route_hint": "办公用品不在设备与实验室平台填报，走日常报销。",
    },
    {
        "name": "易耗品",
        "color": "teal",
        "keywords": [
            "鼠标",
            "键盘",
            "硒鼓",
            "墨盒",
            "电池",
            "网线",
            "手套",
            "内存",
            "读卡器",
            "摄像头",
            "插线板",
            "计算机配套产品",
        ],
        "route_hint": "公共数据库 → 设备与实验室 → 报账管理 → 材料易耗品低值品报账 → "
        "新增报账单 → 审批后打印验收单；报销金额填“材料费”。",
    },
    {
        "name": "低值品",
        "color": "cyan",
        "keywords": ["移动硬盘", "U盘", "优盘", "录音笔", "工具"],
        "route_hint": "同易耗品路径：材料易耗品低值品报账，审批后打印验收单。",
    },
    {
        "name": "设备",
        "color": "indigo",
        "keywords": ["笔记本电脑", "计算机", "显示器", "打印机", "服务器", "仪器"],
        "route_hint": "单价≥1000元设备先申购报账，再到财务“资产业务”；申购时间须早于购买时间。",
    },
    {
        "name": "材料",
        "color": "green",
        "keywords": ["试剂", "材料", "耗材"],
        "route_hint": "材料易耗品低值品报账，审批后打印验收单；金额填“材料费”。",
    },
    {
        "name": "软件服务",
        "color": "violet",
        "keywords": ["会员", "网盘", "腾讯会议", "问卷星", "订阅", "软件", "信息技术服务"],
        "route_hint": "无形资产软件报账，审批后打印验收单；金额填“委托其他业务费”。",
    },
    {
        "name": "印刷快递",
        "color": "orange",
        "keywords": ["印刷", "打印费", "复印费", "快递", "邮政", "物流"],
        "route_hint": "打印费需附明细或票面已开明细。",
    },
    {
        "name": "差旅交通",
        "color": "yellow",
        "keywords": ["铁路", "客票", "航空", "机票", "住宿", "出行", "打车", "滴滴", "客运"],
        "route_hint": "选择国内差旅费；市内交通附发票及行程单，个人出行与节假日不报。",
    },
    {
        "name": "餐饮会议",
        "color": "red",
        "keywords": ["餐饮", "餐费", "会议费", "会务"],
        "route_hint": "工作餐附工作餐单（50元/人/餐）；"
        "会议附预算决算表、申请流程、签到表、通知或议程。",
    },
    {"name": "其他", "color": "gray", "keywords": [], "route_hint": ""},
]

# (分类名 或 None=通用, 附件类型, 级别, 条件, 提示)
DEFAULT_RULES: list[tuple[str | None, str, str, dict, str]] = [
    (None, "invoice", "required", {}, "报销需附发票原件"),
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
    ("印刷快递", "order", "suggested", {}, "打印费附明细（票面已开明细可免）"),
    ("差旅交通", "itinerary", "required", {}, "附行程单，需与出差单对应"),
    ("餐饮会议", "meal_form", "suggested", {}, "工作餐附工作餐单，50元/人/餐"),
    ("餐饮会议", "meeting", "suggested", {}, "会议附预算决算表、签到表、通知或议程"),
]


def seed_defaults(session: Session) -> None:
    if session.scalar(select(Category.id).limit(1)) is not None:
        return
    by_name: dict[str, Category] = {}
    for index, data in enumerate(DEFAULT_CATEGORIES):
        category = Category(sort=index, **data)
        session.add(category)
        by_name[category.name] = category
    session.flush()
    for cat_name, kind, level, condition, hint in DEFAULT_RULES:
        session.add(
            ChecklistRule(
                category_id=by_name[cat_name].id if cat_name else None,
                attachment_kind=kind,
                level=level,
                condition=condition,
                hint=hint,
            )
        )
    session.commit()
