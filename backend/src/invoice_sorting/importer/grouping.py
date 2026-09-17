"""本次上传内分组（设计 5.1）：并查集依次按以下条件连接。

L1 订单号 → L2 文件名键 → L3 金额+日期+商家 → L4 境外订单↔银行交易。

约束：每组最多一张发票；两组各自带有不同订单号（发票/订单类凭证）时不合并。纯函数，无数据库依赖。
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.importer.items import ORDER_LIKE_KINDS, EvidenceItem
from invoice_sorting.importer.merchants import merchants_overlap
from invoice_sorting.importer.platforms import platforms_compatible

MAX_LINK_DAYS = 3
REASON_ORDER_NO = "订单号一致"
REASON_FILE_KEY = "文件名一致"
REASON_AMOUNT_DATE = "金额与日期一致"
REASON_FOREIGN = "境外订单与银行交易日期一致"
REASON_CARD = "卡号末四位一致"

Link = tuple[int, int, tuple[str, ...]]


@dataclass(frozen=True)
class ItemGroup:
    items: tuple[EvidenceItem, ...]
    link_reasons: tuple[str, ...] = ()


class _UnionFind:
    def __init__(self, items: Sequence[EvidenceItem]) -> None:
        self._items = items
        self._parent = list(range(len(items)))
        self._reasons: dict[int, list[str]] = {index: [] for index in range(len(items))}

    def find(self, index: int) -> int:
        while self._parent[index] != index:
            self._parent[index] = self._parent[self._parent[index]]
            index = self._parent[index]
        return index

    def members(self, root: int) -> list[EvidenceItem]:
        return [item for index, item in enumerate(self._items) if self.find(index) == root]

    def _conflicts(self, first: int, second: int) -> bool:
        merged = self.members(first) + self.members(second)
        if sum(1 for item in merged if item.is_invoice) > 1:
            return True
        return _order_keys_disjoint(self.members(first), self.members(second))

    def union(self, first: int, second: int, reasons: tuple[str, ...]) -> bool:
        left, right = self.find(first), self.find(second)
        if left == right or self._conflicts(left, right):
            return False
        root, child = min(left, right), max(left, right)
        self._parent[child] = root
        combined = self._reasons[root] + self._reasons.pop(child) + list(reasons)
        self._reasons[root] = list(dict.fromkeys(combined))
        return True

    def groups(self) -> list[ItemGroup]:
        roots = dict.fromkeys(self.find(index) for index in range(len(self._items)))
        return [ItemGroup(tuple(self.members(root)), tuple(self._reasons[root])) for root in roots]


# 收据/账单上的收据号、账单号彼此不同，不代表不同订单，不参与冲突判断
NON_CONFLICTING_RECOGNIZERS = frozenset({"receipt"})


def _order_keys(items: list[EvidenceItem]) -> set[str]:
    return {
        item.order_key
        for item in items
        if item.kind in ORDER_LIKE_KINDS
        and item.order_key
        and item.recognizer not in NON_CONFLICTING_RECOGNIZERS
    }


def _order_keys_disjoint(first: list[EvidenceItem], second: list[EvidenceItem]) -> bool:
    left, right = _order_keys(first), _order_keys(second)
    return bool(left) and bool(right) and not (left & right)


def _pairs(items: Sequence[EvidenceItem]) -> Iterator[tuple[int, int]]:
    for first in range(len(items)):
        for second in range(first + 1, len(items)):
            yield first, second


def _day_gap(first: EvidenceItem, second: EvidenceItem) -> int | None:
    if first.occurred_on is None or second.occurred_on is None:
        return None
    return abs((first.occurred_on - second.occurred_on).days)


def _same_value_links(items: Sequence[EvidenceItem], attr: str, reason: str) -> list[Link]:
    links: list[Link] = []
    for first, second in _pairs(items):
        value = getattr(items[first], attr)
        if value and value == getattr(items[second], attr):
            links.append((first, second, (reason,)))
    return links


def _amount_date_linked(first: EvidenceItem, second: EvidenceItem) -> bool:
    gap = _day_gap(first, second)
    if first.kind == second.kind or gap is None or gap > MAX_LINK_DAYS:
        return False
    if first.cny_cents is None or first.cny_cents != second.cny_cents:
        return False
    for payment in (first, second):
        if payment.kind == AttachmentKind.PAYMENT and not payment.merchant:
            return True
    return merchants_overlap(first.merchant, first.platforms, second.merchant, second.platforms)


def amount_date_links(items: Sequence[EvidenceItem]) -> list[Link]:
    """L3：按日期差从小到大连接，避免远的先占位。"""
    pairs = [pair for pair in _pairs(items) if _amount_date_linked(items[pair[0]], items[pair[1]])]
    pairs.sort(key=lambda pair: (_day_gap(items[pair[0]], items[pair[1]]), pair))
    return [(first, second, (REASON_AMOUNT_DATE,)) for first, second in pairs]


def _is_foreign_order(item: EvidenceItem) -> bool:
    return item.kind == AttachmentKind.ORDER and item.is_foreign_currency


def _is_foreign_payment(item: EvidenceItem) -> bool:
    return item.kind == AttachmentKind.PAYMENT and (item.is_foreign or item.is_foreign_currency)


def _foreign_compatible(order: EvidenceItem, payment: EvidenceItem) -> bool:
    gap = _day_gap(order, payment)
    if gap is None or gap > MAX_LINK_DAYS:
        return False
    return platforms_compatible(order.platforms, payment.platforms)


def _narrow(order: EvidenceItem, candidates: list[int], items: Sequence[EvidenceItem]) -> list[int]:
    """多个候选时依次用原币金额、卡号末四位唯一化（筛选结果为空则不采用该条件）。"""
    tests = (
        lambda p: (
            p.amount_cents is not None
            and (p.amount_cents, p.currency) == (order.amount_cents, order.currency)
        ),
        lambda p: bool(order.card_last4) and p.card_last4 == order.card_last4,
    )
    for test in tests:
        if len(candidates) <= 1:
            break
        narrowed = [index for index in candidates if test(items[index])]
        candidates = narrowed or candidates
    return candidates


def foreign_links(items: Sequence[EvidenceItem]) -> list[Link]:
    """L4：境外外币订单 ↔ 境外银行交易，双方候选都唯一才连接。"""
    payments = [index for index, item in enumerate(items) if _is_foreign_payment(item)]
    chosen: dict[int, int] = {}
    for index, order in enumerate(items):
        if not _is_foreign_order(order):
            continue
        candidates = [p for p in payments if _foreign_compatible(order, items[p])]
        candidates = _narrow(order, candidates, items)
        if len(candidates) == 1:
            chosen[index] = candidates[0]
    claimed = list(chosen.values())
    links: list[Link] = []
    for order_index, payment_index in chosen.items():
        if claimed.count(payment_index) != 1:
            continue
        order, payment = items[order_index], items[payment_index]
        same_card = bool(order.card_last4) and order.card_last4 == payment.card_last4
        reasons = (REASON_FOREIGN, REASON_CARD) if same_card else (REASON_FOREIGN,)
        links.append((order_index, payment_index, reasons))
    return links


def group_items(items: Sequence[EvidenceItem]) -> list[ItemGroup]:
    """按优先级依次尝试连接；返回的组按组内第一个凭证在输入中的顺序排列。"""
    finder = _UnionFind(items)
    levels = (
        _same_value_links(items, "order_key", REASON_ORDER_NO),
        _same_value_links(items, "usable_file_key", REASON_FILE_KEY),
        amount_date_links(items),
        foreign_links(items),
    )
    for links in levels:
        for first, second, reasons in links:
            finder.union(first, second, reasons)
    return finder.groups()
