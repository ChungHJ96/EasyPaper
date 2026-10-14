"""Deterministic protected-literal checks for general-document translation."""
from __future__ import annotations
import re

_URL = re.compile(r"https?://[^\s<>()\]]+")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_MULTI_UNITS = r"%|ms|MB|GB|KB|Hz|kHz|MHz|GHz|°C|mA|kg|km|cm|mm"
_NUMBER_UNIT = re.compile(
    rf"(?<![\w.])(?:[-+]?\d+(?:[.,]\d+)*\s?(?:{_MULTI_UNITS})(?!\w)|(?!\d{{4}}s\b)[-+]?\d+(?:[.,]\d+)*s(?!\w)|[-+]?\d+(?:[.,]\d+)*\s?V(?!\w)|[-+]?\d+(?:[.,]\d+)*(?:A|\s+A(?!\s+[A-Za-z]))(?!\w)|[-+]?\d+(?:[.,]\d+)*(?![%\w]|\.\d))"
)
_COMMAND = re.compile(r"(?m)^(?:\$\s*)?((?:sudo|curl|wget|npm|npx|pnpm|yarn|pip|python|docker|kubectl|git)\s+[^\n]+)$")
_PATH = re.compile(r"(?<![:/\w])(?:/(?:[\w-]+/)*[\w-]+(?:\.[\w-]+)*|[A-Za-z]:\\(?:[^\s\\]+\\)*[^\s\\]+)")


class TranslationIntegrityError(ValueError):
    pass


def protected_literals(source: str) -> list[str]:
    values = []
    for pattern in (_URL, _INLINE_CODE, _COMMAND, _PATH, _NUMBER_UNIT):
        for match in pattern.finditer(source or ""):
            value = match.group(1) if pattern in (_INLINE_CODE, _COMMAND) else match.group(0)
            value = value.rstrip(".,;:") if pattern is _URL else value
            if value and value not in values:
                values.append(value)
    return values


def validate_translation_integrity(source: str, translation: str) -> dict:
    protected = protected_literals(source)
    missing = [value for value in protected if value not in (translation or "")]
    return {"valid": not missing, "protected_count": len(protected), "missing": missing}


def assert_translation_integrity(source: str, translation: str) -> None:
    result = validate_translation_integrity(source, translation)
    if result["missing"]:
        preview = ", ".join(repr(item) for item in result["missing"][:5])
        raise TranslationIntegrityError(f"보호해야 할 코드·URL·수치가 번역에서 변경되었습니다: {preview}")
