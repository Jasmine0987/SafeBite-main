from typing import Optional
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Ingredient Explanation
# ---------------------------------------------------------------------------
class IngredientExplanationRequest(BaseModel):
    ingredient_name: str = Field(..., min_length=1, max_length=100)


class IngredientExplanationResponse(BaseModel):
    ingredient_name: str
    explanation: str


# ---------------------------------------------------------------------------
# Swap Explanation — supports both 'scan' and 'craving' entry points
# ---------------------------------------------------------------------------
class SwapExplanationRequest(BaseModel):
    recommended_food: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="The recommendation engine's (or VAE model's) chosen food.",
    )
    original_food: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Required when entry_point='scan'. The flagged product being swapped away from.",
    )
    craving_query: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Required when entry_point='craving'. The user's raw craving text.",
    )
    entry_point: str = Field(
        default="scan",
        description="'scan' (from a flagged Verdict) or 'craving' (from Craving Search).",
    )

    @model_validator(mode="after")
    def check_context_matches_entry_point(self):
        if self.entry_point == "scan" and not self.original_food:
            raise ValueError("original_food is required when entry_point='scan'")
        if self.entry_point == "craving" and not self.craving_query:
            raise ValueError("craving_query is required when entry_point='craving'")
        return self


class SwapExplanationResponse(BaseModel):
    recommended_food: str
    original_food: Optional[str] = None
    craving_query: Optional[str] = None
    explanation: str
    entry_point: str