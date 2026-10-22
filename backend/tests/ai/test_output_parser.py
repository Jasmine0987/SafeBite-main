from app.ai.output_parser import (
    parse_ingredient_explanation,
    parse_swap_explanation,
    FALLBACK_INGREDIENT_EXPLANATION,
    FALLBACK_SWAP_EXPLANATION,
)


def test_clean_text_passes_through_unchanged():
    result = parse_ingredient_explanation("Casein is a protein naturally found in milk.")
    assert result == "Casein is a protein naturally found in milk."


def test_strips_common_preamble():
    result = parse_ingredient_explanation("Sure, here's the explanation: Casein is a milk protein.")
    assert not result.lower().startswith("sure")
    assert "Casein" in result


def test_falls_back_on_forbidden_word_ingredient():
    result = parse_ingredient_explanation("Casein is safe for most people.")
    assert result == FALLBACK_INGREDIENT_EXPLANATION


def test_falls_back_on_forbidden_word_swap():
    result = parse_swap_explanation("This is a much healthier and safer choice.")
    assert result == FALLBACK_SWAP_EXPLANATION


def test_falls_back_on_empty_output():
    result = parse_ingredient_explanation("")
    assert result == FALLBACK_INGREDIENT_EXPLANATION


def test_strips_surrounding_quotes():
    result = parse_swap_explanation('"Roasted makhana offers a similar crunch."')
    assert not result.startswith('"')
    assert not result.endswith('"')