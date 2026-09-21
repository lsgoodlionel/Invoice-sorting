"""合并导入报告：预览（dry-run）与真正导入返回同一结构。

每一部分（记录、附件、分类……）给出新增/跳过/冲突/失败的精确数量，
明细最多列 MAX_ITEMS 条（超出部分只计数），报告不含任何令牌、密码或本机绝对路径。
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

ACTION_ADDED = "added"
ACTION_SKIPPED = "skipped"
ACTION_CONFLICT = "conflict"
ACTION_FAILED = "failed"
ACTIONS = (ACTION_ADDED, ACTION_SKIPPED, ACTION_CONFLICT, ACTION_FAILED)

MAX_ITEMS = 500

SECTION_USERS = "users"
SECTION_CATEGORIES = "categories"
SECTION_PROJECTS = "projects"
SECTION_RULES = "rules"
SECTION_MEMORIES = "memories"
SECTION_BATCHES = "batches"
SECTION_EXPORTS = "exports"
SECTION_RECORDS = "records"
SECTION_ATTACHMENTS = "attachments"

# 报告中各部分的顺序与中文名
SECTION_LABELS: Mapping[str, str] = MappingProxyType(
    {
        SECTION_RECORDS: "记录",
        SECTION_ATTACHMENTS: "附件",
        SECTION_BATCHES: "批次",
        SECTION_EXPORTS: "资料包生成记录",
        SECTION_CATEGORIES: "分类",
        SECTION_PROJECTS: "经费项目",
        SECTION_RULES: "凭证规则",
        SECTION_MEMORIES: "分类记忆",
        SECTION_USERS: "用户",
    }
)


@dataclass(frozen=True)
class ReportItem:
    """一条明细：动作、对象说明与原因。"""

    action: str
    label: str
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action, "label": self.label, "reason": self.reason}


@dataclass(frozen=True)
class SectionReport:
    added: int = 0
    skipped: int = 0
    conflicts: int = 0
    failed: int = 0
    items: tuple[ReportItem, ...] = ()
    truncated: int = 0  # 超出明细上限、只计数未列出的条数

    def to_dict(self, key: str) -> dict[str, object]:
        return {
            "key": key,
            "label": SECTION_LABELS.get(key, key),
            "added": self.added,
            "skipped": self.skipped,
            "conflicts": self.conflicts,
            "failed": self.failed,
            "details": [item.to_dict() for item in self.items],
            "truncated": self.truncated,
        }


class SectionBuilder:
    """规划阶段逐条登记，最后产出不可变的 SectionReport。"""

    def __init__(self, limit: int = MAX_ITEMS) -> None:
        self._counts = dict.fromkeys(ACTIONS, 0)
        self._items: list[ReportItem] = []
        self._limit = limit

    def add(self, action: str, label: str, reason: str = "") -> None:
        self._counts[action] += 1
        if len(self._items) < self._limit:
            self._items.append(ReportItem(action=action, label=label, reason=reason))

    def build(self) -> SectionReport:
        total = sum(self._counts.values())
        return SectionReport(
            added=self._counts[ACTION_ADDED],
            skipped=self._counts[ACTION_SKIPPED],
            conflicts=self._counts[ACTION_CONFLICT],
            failed=self._counts[ACTION_FAILED],
            items=tuple(self._items),
            truncated=total - len(self._items),
        )


@dataclass(frozen=True)
class MergeReport:
    """合并导入报告。is_dry_run=True 为预览：数量是“将要”发生的，未写入任何数据。"""

    slug: str
    is_dry_run: bool
    package: Mapping[str, object]
    sections: Mapping[str, SectionReport]
    warnings: tuple[str, ...] = field(default=())
    mode: str = "merge"

    def section(self, key: str) -> SectionReport:
        return self.sections.get(key, SectionReport())

    @property
    def total_added(self) -> int:
        return sum(section.added for section in self.sections.values())

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "slug": self.slug,
            "is_dry_run": self.is_dry_run,
            "source": dict(self.package),
            "total_added": self.total_added,
            "items": [self.section(key).to_dict(key) for key in SECTION_LABELS],
            "warnings": list(self.warnings),
        }


def freeze_sections(sections: Mapping[str, SectionReport]) -> Mapping[str, SectionReport]:
    return MappingProxyType(dict(sections))
