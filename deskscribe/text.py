"""Text correction rules for completed transcripts."""

import re


class ReplacementRuleError(ValueError):
    """Raised when a replacement dictionary line is malformed."""


def parse_replacement_rules(value: str) -> list[tuple[str, str]]:
    """Parse ``source => replacement`` rules from a multiline string."""
    rules: list[tuple[str, str]] = []
    for line_number, raw_line in enumerate(value.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" not in line:
            raise ReplacementRuleError(
                f"{line_number}行目は「誤変換 => 正しい表記」の形式で入力してください。"
            )
        source, replacement = (part.strip() for part in line.split("=>", 1))
        if not source:
            raise ReplacementRuleError(f"{line_number}行目の変換前文字列が空です。")
        rules.append((source, replacement))
    return rules


def apply_replacements(text: str, rules: list[tuple[str, str]]) -> str:
    """Replace against the original text, preferring longer source phrases."""
    replacements = {source: replacement for source, replacement in rules if source}
    if not replacements:
        return text
    sources = sorted(replacements, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(source) for source in sources))
    return pattern.sub(lambda match: replacements[match.group(0)], text)
