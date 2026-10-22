from app.ai.llm import llm
from app.ai.prompts import INGREDIENT_EXPLANATION_PROMPT, SWAP_EXPLANATION_PROMPT
from app.ai.output_parser import parse_ingredient_explanation, parse_swap_explanation
from app.cache.explanation_cache import get_cached, set_cached
from app.core.logging_config import logger
from app.core.exceptions import LLMUnavailableError
from app.schemas.explain import (
    IngredientExplanationRequest, IngredientExplanationResponse,
    SwapExplanationRequest, SwapExplanationResponse,
)

# ---------------------------------------------------------------------------
# Ingredient Explanation Chain
# ---------------------------------------------------------------------------
ingredient_explanation_chain = INGREDIENT_EXPLANATION_PROMPT | llm


def explain_ingredient(request: IngredientExplanationRequest) -> IngredientExplanationResponse:
    cached = get_cached("ingredient", request.ingredient_name)
    if cached:
        logger.info(f"CACHE HIT | ingredient='{request.ingredient_name}'")
        return IngredientExplanationResponse(**cached)

    logger.info(f"CACHE MISS | ingredient='{request.ingredient_name}' | calling LLM")
    try:
        response = ingredient_explanation_chain.invoke({"ingredient_name": request.ingredient_name})
    except Exception as e:
        raise LLMUnavailableError(f"Ollama call failed for ingredient explanation: {e}") from e

    explanation = parse_ingredient_explanation(response.content)
    result = IngredientExplanationResponse(
        ingredient_name=request.ingredient_name,
        explanation=explanation,
    )
    set_cached(result.model_dump(), "ingredient", request.ingredient_name)
    return result


# ---------------------------------------------------------------------------
# Swap Explanation Chain — handles both 'scan' and 'craving' entry points
# ---------------------------------------------------------------------------
swap_explanation_chain = SWAP_EXPLANATION_PROMPT | llm


def _build_context_line(request: SwapExplanationRequest) -> str:
    if request.entry_point == "craving":
        return f'User craving: "{request.craving_query}"'
    return f"Original food: {request.original_food}"


def explain_swap(request: SwapExplanationRequest) -> SwapExplanationResponse:
    cache_key_context = request.craving_query if request.entry_point == "craving" else request.original_food
    cached = get_cached("swap", request.entry_point, cache_key_context, request.recommended_food)
    if cached:
        logger.info(f"CACHE HIT | swap | entry_point='{request.entry_point}'")
        cached["entry_point"] = request.entry_point
        return SwapExplanationResponse(**cached)

    logger.info(f"CACHE MISS | swap | entry_point='{request.entry_point}' | calling LLM")
    context_line = _build_context_line(request)
    try:
        response = swap_explanation_chain.invoke({
            "context_line": context_line,
            "recommended_food": request.recommended_food,
        })
    except Exception as e:
        raise LLMUnavailableError(f"Ollama call failed for swap explanation: {e}") from e

    explanation = parse_swap_explanation(response.content)
    result = SwapExplanationResponse(
        recommended_food=request.recommended_food,
        original_food=request.original_food,
        craving_query=request.craving_query,
        explanation=explanation,
        entry_point=request.entry_point,
    )
    set_cached(result.model_dump(), "swap", request.entry_point, cache_key_context, request.recommended_food)
    return result