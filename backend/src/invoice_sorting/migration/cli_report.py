"""命令行导入报告的文本输出：各部分数量一行一条，只展开冲突与失败的明细。"""

from collections.abc import Callable, Mapping
from typing import Any

from invoice_sorting.migration.accounts_report import SECTION_ACCOUNTS
from invoice_sorting.migration.report import ACTION_CONFLICT, ACTION_FAILED, ACTION_UPDATED

ACTION_TAGS: Mapping[str, str] = {
    ACTION_UPDATED: "以包为准",
    ACTION_CONFLICT: "冲突",
    ACTION_FAILED: "失败",
}
HEADER_MERGE = "合并{what}：账套 {slug} ← 来源「{source}」"
HEADER_REPLACE = "覆盖{what}：账套 {slug} ← 来源「{source}」"


def _what(report: Mapping[str, Any]) -> str:
    return "预览（未写入任何数据）" if report.get("is_dry_run") else "导入完成"


def _counts(item: Mapping[str, Any], is_replace: bool) -> str:
    if is_replace and item.get("key") == SECTION_ACCOUNTS:
        return f"新建 {item['added']}、更新 {item.get('updated', 0)}、不变或保留 {item['skipped']}"
    if is_replace:
        return f"包内 {item['added']}"
    return (
        f"新增 {item['added']}、更新 {item.get('updated', 0)}、跳过 {item['skipped']}、"
        f"冲突 {item['conflicts']}、失败 {item['failed']}"
    )


def report_lines(report: Mapping[str, Any]) -> list[str]:
    """把 preview_import / run_import 返回的字典转成终端文本。"""
    is_replace = report.get("mode") == "replace"
    header = HEADER_REPLACE if is_replace else HEADER_MERGE
    source = report.get("source") or {}
    lines = [
        header.format(
            what=_what(report), slug=report.get("slug", ""), source=source.get("tenant", "")
        )
    ]
    items = report.get("items") or []
    lines.extend(f"  {item['label']}：{_counts(item, is_replace)}" for item in items)
    if report.get("backup_file"):
        lines.append(f"  覆盖前已备份现有数据：{report['backup_file']}")
    accounts = report.get("accounts") or {}
    if accounts.get("note"):
        lines.append(f"账号：{accounts['note']}")
    lines.extend(f"提示：{warning}" for warning in report.get("warnings") or [])
    lines.extend(_detail_lines(items))
    return lines


def _detail_lines(items: list[Mapping[str, Any]]) -> list[str]:
    details = [
        f"  [{ACTION_TAGS[row['action']]}] {item['label']} {row['label']}：{row['reason']}"
        for item in items
        for row in item.get("details") or []
        if row["action"] in ACTION_TAGS
    ]
    return ["需要留意的明细：", *details] if details else []


def print_report(report: Mapping[str, Any], out: Callable[[str], None] = print) -> None:
    for line in report_lines(report):
        out(line)
