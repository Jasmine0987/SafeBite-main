import pytest
from app.ai.chains import explain_ingredient, explain_swap
from app.schemas.explain import IngredientExplanationRequest, SwapExplanationRequest

# Mark these as 'integration' tests so they can be skipped separately when fast
# iteration matters more than full coverage (e.g. right before a quick redeploy).
pytestmark = pytest.mark.integration


def test_explain_ingredient_returns_nonempty_string():
    result = explain_ingredient(IngredientExplanationRequest(ingredient_name="casein"))
    assert isinstance(result.explanation, str)
    assert len(result.explanation) > 0


def test_explain_swap_scan_entry_point():
    result = explain_swap(SwapExplanationRequest(
        original_food="Potato Chips", recommended_food="Roasted Makhana", entry_point="scan"
    ))
    assert isinstance(result.explanation, str)
    assert result.entry_point == "scan"


def test_explain_swap_craving_entry_point():
    result = explain_swap(SwapExplanationRequest(
        craving_query="something crunchy and salty",
        recommended_food="Roasted Makhana",
        entry_point="craving",
    ))
    assert isinstance(result.explanation, str)
    assert result.entry_point == "craving"