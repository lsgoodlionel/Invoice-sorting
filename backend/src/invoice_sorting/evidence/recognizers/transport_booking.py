"""交通凭证订单（12306 车票、航司/携程/飞猪机票、汽车票、船票）：行程与票价。"""

from invoice_sorting.evidence.base import DOC_ITINERARY, RecognizedEvidence
from invoice_sorting.evidence.lines import EvidenceText
from invoice_sorting.evidence.parsing import Money, find_money
from invoice_sorting.evidence.recognizers.common import (
    NO_ANCHOR_CAP,
    Features,
    build,
    feature_score,
    first_reference,
    money_fields,
)
from invoice_sorting.evidence.recognizers.transport_fields import (
    Route,
    number_of,
    passenger_value,
    route_of,
    travel_date,
    vehicle_of,
)
from invoice_sorting.evidence.recognizers.travel_text import (
    compact_details,
    first_labeled,
    person_name,
    platform_of,
)

NAME = "transport_booking"
PLATFORMS = (
    (r"12306|中国铁路", "铁路12306"),
    (r"携程|ctrip", "携程"),
    (r"飞猪|fliggy", "飞猪"),
    (r"去哪儿|qunar", "去哪儿"),
    (r"同程", "同程"),
    (r"智行", "智行"),
    (r"航旅纵横", "航旅纵横"),
    (r"巴士管家", "巴士管家"),
    (r"东方航空|东航", "东方航空"),
    (r"南方航空|南航", "南方航空"),
    (r"中国国际航空|国航", "中国国际航空"),
    (r"海南航空|海航", "海南航空"),
    (r"春秋航空", "春秋航空"),
    (r"吉祥航空", "吉祥航空"),
    (r"厦门航空", "厦门航空"),
    (r"深圳航空", "深圳航空"),
    (r"四川航空", "四川航空"),
)
FEATURES = Features(
    groups=(
        ("订单号", "订单编号", "取票号", "订单"),
        ("车次", "航班", "班次", "船名", "航次"),
        ("发车", "起飞", "出发", "开航", "开船"),
        ("到达", "到站", "抵达", "目的地", "→"),
        ("乘车人", "乘机人", "乘客", "旅客", "乘船人", "出行人"),
        ("席别", "座", "舱", "卧"),
        ("票价", "票款", "订单总额", "订单金额", "实付", "支付金额", "总价", "合计"),
        ("12306", "铁路", "航空", "客运", "码头", "机场", "巴士", "车站"),
        ("检票", "登机", "候车", "登船", "已支付", "出票"),
        ("火车票", "机票", "汽车票", "船票", "车票"),
    ),
    needed=5,
    anchors=(
        ("车次", "航班", "班次", "船名", "航次", "乘机人", "发车时间", "起飞")
        + ("客运站", "码头", "12306", "船票", "汽车票", "机票", "火车票")
    ),
)
ORDER_LABELS = (r"订单号码|订单编号|订单号|取票号",)
AMOUNT_LABELS = (r"票价|票款|订单总额|订单金额|实付金额|实付款|实付|支付金额|总价|合计|总计",)


def _amount(doc: EvidenceText) -> Money | None:
    return find_money(first_labeled(doc, AMOUNT_LABELS)) or find_money(doc.text)


def _item_name(route: Route, number: str) -> str:
    path = "-".join(part for part in (route.origin, route.destination) if part)
    return " ".join(part for part in (path, number) if part)


def recognize(doc: EvidenceText) -> RecognizedEvidence | None:
    score = feature_score(doc, FEATURES)
    if score <= NO_ANCHOR_CAP:  # 缺少车次/航班等锚点或特征太少：不是交通凭证
        return None
    vehicle = vehicle_of(doc.compact)
    route = route_of(doc, vehicle)
    number = number_of(doc, vehicle, route)
    departed = travel_date(doc)
    details = compact_details(
        {
            "date": departed.isoformat() if departed else "",
            "from": route.origin,
            "to": route.destination,
            "vehicle": vehicle,
            "number": number,
            "passenger": person_name(passenger_value(doc)),
        }
    )
    return build(
        NAME,
        DOC_ITINERARY,
        score,
        occurred_on=departed,
        merchant=platform_of(doc.text, PLATFORMS),
        item_name=_item_name(route, number),
        order_no=first_reference(first_labeled(doc, ORDER_LABELS)),
        details=details,
        **money_fields(_amount(doc)),
    )
