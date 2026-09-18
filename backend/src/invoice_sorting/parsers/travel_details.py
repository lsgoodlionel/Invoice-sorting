"""差旅票解析结果的 travel → InvoiceData.details（date、from、to、vehicle、number、passenger）。"""

from invoice_sorting.parsers.base import ParsedInvoice

VEHICLE_BY_PARSER: dict[str, str] = {"rail_ticket": "train", "air_itinerary": "flight"}


def travel_details(parsed: ParsedInvoice) -> dict[str, str]:
    """交通票发票的结构化信息；非交通票（无 travel 或无法判断交通工具）返回 {}。"""
    travel = parsed.travel or {}
    vehicle = travel.get("vehicle") or VEHICLE_BY_PARSER.get(parsed.parser, "")
    if not travel or not vehicle:
        return {}
    values = {
        "date": travel.get("date", ""),
        "from": travel.get("from", ""),
        "to": travel.get("to", ""),
        "vehicle": vehicle,
        "number": travel.get("number") or travel.get("train_or_flight", ""),
        "passenger": travel.get("passenger", ""),
    }
    return {key: value for key, value in values.items() if value}
