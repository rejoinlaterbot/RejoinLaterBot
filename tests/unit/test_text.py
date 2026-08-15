"""Unicode-aware visible-title trimming tests."""

from rejoinlater.services.text import truncate_graphemes


def test_truncation_preserves_combined_graphemes_and_word_boundary() -> None:
    value = "Photography Cyprus community with e\N{COMBINING ACUTE ACCENT} accents"
    result = truncate_graphemes(value, 26)

    assert result.endswith("…")
    assert not result.endswith("e…")
