from fastapi import APIRouter

from app.ai.chains import explain_ingredient, explain_swap
from app.schemas.explain import (
    IngredientExplanationRequest, IngredientExplanationResponse,
    SwapExplanationRequest, SwapExplanationResponse,
)

router = APIRouter()


@router.post("/explain-ingredient", response_model=IngredientExplanationResponse)
def explain_ingredient_route(request: IngredientExplanationRequest) -> IngredientExplanationResponse:
    """
    Consumed by: Person B's Ingredient Detail page.
    Takes an ingredient name, returns a plain-English explanation.
    Deterministic allergen decisions happen elsewhere — this route only explains.
    """
    return explain_ingredient(request)


@router.post("/explain-swap", response_model=SwapExplanationResponse)
def explain_swap_route(request: SwapExplanationRequest) -> SwapExplanationResponse:
    """
    Consumed by: YOUR Swap Results + Craving Search pages (one endpoint, two entry points).
    Takes the recommendation engine's already-decided swap, returns an explanation.
    This route never re-evaluates or ranks the swap — it only explains it.
    """
    return explain_swap(request)