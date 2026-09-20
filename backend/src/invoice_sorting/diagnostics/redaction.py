"""脱敏与残留自检（设计《日志与故障上报》4 脱敏）。

本机留存的诊断包与上传的诊断包走**同一条**脱敏链路，避免“本地包没脱敏被误发”。
`redact_text` 是幂等的：对已脱敏文本再跑一次结果不变。
"""

from invoice_sorting.diagnostics.redaction_rules import (
    PLACEHOLDER_SQL_VALUE,
    RESIDUE_CHECKS,
    RULES,
    SECRET_RULES,
    SQL_KEYWORD_PATTERN,
    SQL_LITERAL_PATTERN,
)


def redact_text(text: str) -> str:
    """按规则表依次替换；顺序见 redaction_rules.RULES 的注释。"""
    if not text:
        return ""
    cleaned = text
    for pattern, replacement in RULES:
        cleaned = pattern.sub(replacement, cleaned)
    return _redact_sql_literals(cleaned)


def scrub_secrets(text: str) -> str:
    """只抹掉密钥、令牌与密码：运行日志实时过滤用，保留其余文案便于排查。"""
    cleaned = text
    for pattern, replacement in SECRET_RULES:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def _redact_sql_literals(text: str) -> str:
    """SQL 只保留结构：语句里的字符串字面量换成占位符，表名、列名与关键字保留。"""
    if SQL_KEYWORD_PATTERN.search(text) is None:
        return text
    lines = (
        SQL_LITERAL_PATTERN.sub(PLACEHOLDER_SQL_VALUE, line)
        if SQL_KEYWORD_PATTERN.search(line)
        else line
        for line in text.split("\n")
    )
    return "\n".join(lines)


def find_residue(text: str) -> tuple[str, ...]:
    """扫描脱敏后的文本，返回仍然残留的敏感类型名（为空表示通过自检）。"""
    return tuple(name for name, pattern in RESIDUE_CHECKS if pattern.search(text) is not None)


def redact_mapping(parts: dict[str, str]) -> dict[str, str]:
    """整体脱敏一组文本，返回新字典（不修改入参）。"""
    return {name: redact_text(content) for name, content in parts.items()}


def residue_in_mapping(parts: dict[str, str]) -> tuple[str, ...]:
    """对一组文本做残留自检，返回去重后的类型名。"""
    found: list[str] = []
    for content in parts.values():
        for name in find_residue(content):
            if name not in found:
                found.append(name)
    return tuple(found)
