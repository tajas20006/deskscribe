import pytest

from deskscribe.text import (
    ReplacementRuleError,
    apply_replacements,
    parse_replacement_rules,
)


def test_parse_replacement_rules_ignores_comments_and_blank_lines() -> None:
    rules = parse_replacement_rules(
        """
        # よくある誤変換
        Open AI => OpenAI

        机上書記 => DeskScribe
        """
    )

    assert rules == [("Open AI", "OpenAI"), ("机上書記", "DeskScribe")]


def test_parse_replacement_rules_reports_the_invalid_line() -> None:
    with pytest.raises(ReplacementRuleError, match="2行目"):
        parse_replacement_rules("正常 => 正式\n区切りなし")


def test_apply_replacements_prefers_longer_source_phrases() -> None:
    text = apply_replacements(
        "Open AI と AI",
        [("AI", "エーアイ"), ("Open AI", "OpenAI")],
    )

    assert text == "OpenAI と エーアイ"
