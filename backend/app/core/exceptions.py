from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.logging_config import logger


class LLMUnavailableError(Exception):
    """Raised when the LLM (Ollama) fails to respond — connection issue or timeout."""
    pass


async def llm_unavailable_handler(request: Request, exc: LLMUnavailableError):
    logger.error(f"LLM UNAVAILABLE | path={request.url.path} | detail={exc}")
    return JSONResponse(
        status_code=503,
        content={
            "error": "ai_service_unavailable",
            "message": "The AI explanation service is temporarily unavailable. Please try again shortly.",
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"UNHANDLED ERROR | path={request.url.path} | {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Something went wrong processing your request.",
        },
    )