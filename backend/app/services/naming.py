import re
from typing import Any

_GEO_RE = re.compile(r"^[A-Z]{2}$")


def apply_prefix(name: str, prefix: str) -> str:
    """'campaign1' -> '<CAMPAIGN_PREFIX>campaign1'. Префикс не дублируется."""
    name = name.strip()
    if prefix and name.lower().startswith(prefix.lower()):
        name = name[len(prefix):]
    if not name:
        raise ValueError("Название кампании пустое после префикса")
    return f"{prefix}{name}"


def parse_geo(value: Any) -> list[str]:
    """'mx, AU;ro' / ['MX','au'] -> ['MX', 'AU', 'RO'] (без дублей, порядок сохранён)."""
    if isinstance(value, str):
        parts = re.split(r"[\s,;]+", value)
    elif isinstance(value, (list, tuple)):
        parts = [str(p) for p in value]
    else:
        raise ValueError("Гео должно быть строкой вида 'MX,AU,RO' или списком")

    result: list[str] = []
    bad: list[str] = []
    for part in parts:
        code = part.strip().upper()
        if not code:
            continue
        if not _GEO_RE.match(code):
            bad.append(part.strip())
        elif code not in result:
            result.append(code)
    if bad:
        raise ValueError(f"Некорректные коды стран (нужен ISO 3166-1 alpha-2): {', '.join(bad)}")
    if not result:
        raise ValueError("Укажите хотя бы одну страну")
    return result


def distribute_evenly(count: int, total: int = 100) -> list[int]:
    """Целые доли, сумма ровно total: 3 -> [34, 33, 33]."""
    if count <= 0:
        return []
    base, rest = divmod(total, count)
    return [base + (1 if i < rest else 0) for i in range(count)]
