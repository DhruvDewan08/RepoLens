import os

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() or None
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()


def _build_prompt(question: str, context: dict) -> str:
    parts = ["You are a code assistant answering questions about a codebase.\n"]
    if context.get("function_snippets"):
        parts.append("Relevant functions:\n")
        parts.append("\n\n".join(context["function_snippets"]))
    if context.get("graph_summary"):
        parts.append("\n\nDependency graph context:\n")
        parts.append(context["graph_summary"])
    parts.append(
        f"\n\nQuestion: {question}\nAnswer clearly, citing function names and file paths where relevant."
    )
    return "\n".join(parts)


def _chat_openai_compatible(prompt: str, api_key: str, base_url: str | None, model: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


def ask_llm(question: str, context: dict) -> str:
    prompt = _build_prompt(question, context)

    if GROQ_API_KEY:
        return _chat_openai_compatible(
            prompt,
            GROQ_API_KEY,
            "https://api.groq.com/openai/v1",
            LLM_MODEL or "llama-3.1-8b-instant",
        )
    if OPENAI_API_KEY:
        return _chat_openai_compatible(
            prompt,
            OPENAI_API_KEY,
            OPENAI_BASE_URL,
            LLM_MODEL or "gpt-4o-mini",
        )

    import ollama

    response = ollama.chat(
        model=LLM_MODEL or "llama3.2",
        messages=[{"role": "user", "content": prompt}],
    )
    return response["message"]["content"]
