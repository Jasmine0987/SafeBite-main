import pytest
from pydantic import ValidationError
from app.schemas.explain import IngredientExplanationRequest, SwapExplanationRequest


def test_ingredient_request_rejects_empty_string():
    with pytest.raises(ValidationError):
        IngredientExplanationRequest(ingredient_name="")


def test_ingredient_request_accepts_valid_input():
    req = IngredientExplanationRequest(ingredient_name="casein")
    assert req.ingredient_name == "casein"


def test_swap_request_scan_requires_original_food():
    with pytest.raises(ValidationError):
        SwapExplanationRequest(recommended_food="Roasted Makhana", entry_point="scan")


def test_swap_request_craving_requires_craving_query():
    with pytest.raises(ValidationError):
        SwapExplanationRequest(recommended_food="Roasted Makhana", entry_point="craving")


def test_swap_request_scan_valid():
    req = SwapExplanationRequest(
        original_food="Potato Chips", recommended_food="Roasted Makhana", entry_point="scan"
    )
    assert req.original_food == "Potato Chips"


def test_swap_request_craving_valid():
    req = SwapExplanationRequest(
        craving_query="something crunchy and salty",
        recommended_food="Roasted Makhana",
        entry_point="craving",
    )
    assert req.craving_query == "something crunchy and salty"