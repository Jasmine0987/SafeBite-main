from app.core.logging_config import logger

# Words that must NEVER appear in AI-generated explanations, per the
# "AI only explains, never decides" rule.
FORBIDDEN_WORDS = [
    "safe", "unsafe", "allergen", "allergy", "allergic",
    "avoid", "dangerous", "harmful", "healthy", "unhealthy",
    "best", "better than", "recommend",
]

FALLBACK_INGREDIENT_EXPLANATION = "This is a common food ingredient."
FALLBACK_SWAP_EXPLANATION = "This alternative offers a similar taste and texture."


def _strip_preamble(text: str) -> str:
    preambles = [
        "sure, here's the explanation:", "sure! here's the explanation:",
        "here's the explanation:", "explanation:",
    ]
    cleaned = text.strip()
    lowered = cleaned.lower()
    for phrase in preambles:
        if lowered.startswith(phrase):
            cleaned = cleaned[len(phrase):].strip()
            break
    return cleaned.strip('"').strip()


def _contains_forbidden_word(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in FORBIDDEN_WORDS)


def parse_ingredient_explanation(raw_text: str) -> str:
    cleaned = _strip_preamble(raw_text)

    if _contains_forbidden_word(cleaned):
        logger.warning(f"PARSER FALLBACK (ingredient) | forbidden word in: '{cleaned}'")
        return FALLBACK_INGREDIENT_EXPLANATION

    if not cleaned:
        logger.warning("PARSER FALLBACK (ingredient) | empty output after cleanup")
        return FALLBACK_INGREDIENT_EXPLANATION

    return cleaned


def parse_swap_explanation(raw_text: str) -> str:
    cleaned = _strip_preamble(raw_text)

    if _contains_forbidden_word(cleaned):
        logger.warning(f"PARSER FALLBACK (swap) | forbidden word in: '{cleaned}'")
        return FALLBACK_SWAP_EXPLANATION

    if not cleaned:
        logger.warning("PARSER FALLBACK (swap) | empty output after cleanup")
        return FALLBACK_SWAP_EXPLANATION

    return cleaned