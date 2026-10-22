import os
from langchain_ollama import ChatOllama

# Read the model name from .env so switching models later doesn't require code changes
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

llm = ChatOllama(
    model=OLLAMA_MODEL,
    temperature=0.2,      # low temperature = consistent, factual output, not creative variation
    timeout=15,           # seconds — fail fast rather than hang if Ollama is slow/unresponsive
)