"""合并导入的纯函数：ledger.json 解析、占位用户名、批次来源后缀、报告明细上限、导入记录路径。"""

import json

import pytest

from invoice_sorting.common.errors import AppError
from invoice_sorting.migration.ledger import LedgerInfo, LedgerScope, LedgerSource, parse_ledger
from invoice_sorting.migration.merge_apply import IMPORTED_EXPORTS_DIRNAME, imported_export_path
from invoice_sorting.migration.merge_index import compact, expense_key, rule_key
from invoice_sorting.migration.merge_plan_batches import BATCH_NAME_MAX, with_source
from invoice_sorting.migration.placeholders import placeholder_username
from invoice_sorting.migration.report import ACTION_ADDED, ACTION_CONFLICT, SectionBuilder


def _raw(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode()


def test_ledger_round_trips_through_json():
    info = LedgerInfo(
        source=LedgerSource("saas", "虚构客户甲", "虚构管理员", "0.2.1"),
        scope=LedgerScope(3, 5, 1, "2026-01-01", "2026-09-21"),
    )

    assert parse_ledger(info.to_bytes()) == info


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "tenant"},
        {"kind": "ledger", "source": "不是对象"},
        {"kind": "ledger", "scope": {"records": -1}},
        {"kind": "ledger", "scope": {"records": True}},
        {"kind": "ledger", "source": {"tenant": 123}},
        ["ledger"],
    ],
)
def test_malformed_ledger_is_rejected(payload):
    with pytest.raises(AppError) as excinfo:
        parse_ledger(_raw(payload))

    assert "ledger.json" in excinfo.value.message


def test_ledger_text_is_cleaned_and_truncated():
    raw = _raw({"kind": "ledger", "source": {"tenant": "虚构\x00客户\n" + "甲" * 300}})

    tenant = parse_ledger(raw).source.tenant

    assert "\x00" not in tenant and "\n" not in tenant
    assert len(tenant) == 100


def test_broken_ledger_bytes_are_rejected():
    with pytest.raises(AppError):
        parse_ledger(b"\xff\xfe not json")


def test_placeholder_username_prefers_original_then_suffixes():
    taken = {"zhang", "zhang.imp"}

    assert placeholder_username("Li", lambda name: False) == "imported"  # 过短时用兜底名
    assert placeholder_username("wang", taken.__contains__) == "wang"
    assert placeholder_username("zhang", taken.__contains__) == "zhang.imp2"
    long_name = placeholder_username("a" * 40, lambda name: not name.endswith(".imp"))
    assert long_name.endswith(".imp") and len(long_name) == 32


def test_placeholder_username_drops_illegal_characters():
    assert placeholder_username("张三 zhang/san", lambda name: False) == "zhangsan"


def test_batch_suffix_keeps_source_visible_when_name_is_long():
    name = with_source("批" * 200, "虚构客户甲", 2)

    assert name.endswith("（来自 虚构客户甲 2）")
    assert len(name) == BATCH_NAME_MAX


def test_section_builder_counts_everything_but_caps_details():
    builder = SectionBuilder(limit=2)
    for index in range(5):
        builder.add(ACTION_ADDED, f"第{index}条")
    builder.add(ACTION_CONFLICT, "冲突项", "保留本地")

    section = builder.build()

    assert (section.added, section.conflicts, len(section.items), section.truncated) == (5, 1, 2, 4)


def test_imported_export_path_never_reuses_package_path():
    first = imported_export_path("资料包/虚构批次/资料包.zip")
    evil = imported_export_path("../../etc/passwd")

    assert first.startswith(f"资料包/{IMPORTED_EXPORTS_DIRNAME}/") and first.endswith("_资料包.zip")
    assert ".." not in evil and evil.startswith(f"资料包/{IMPORTED_EXPORTS_DIRNAME}/")
    assert imported_export_path("资料包/虚构批次/资料包.zip") != first


def test_comparison_keys_ignore_whitespace_and_condition_order():
    assert compact(" 虚构 专项 ") == "虚构专项"
    assert expense_key(100, None, "虚构 商家") == expense_key(100, None, "虚构商家")
    assert rule_key(1, "contract", {"a": 1, "b": 2}) == rule_key(1, "contract", {"b": 2, "a": 1})
