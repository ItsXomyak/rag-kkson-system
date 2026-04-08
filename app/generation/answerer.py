"""Generate a literature review answer using Qwen 3 via OpenAI-compatible API."""

import logging
from collections.abc import Iterator

from openai import OpenAI

from app.config import settings
from app.retrieval.search import SearchResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — научный ассистент, работающий с базой казахстанских научных журналов (ККСОН).

Твоя задача — дать полезный, точный и лаконичный ответ на вопрос исследователя, опираясь на предоставленные фрагменты статей.

Правила:
1. Отвечай ТОЛЬКО на основе предоставленного контекста. НЕ придумывай информацию.
2. Ссылайся на источники в формате [Источник: имя_файла, стр. N].
3. Будь КРАТКИМ. Не лей воду. Каждое предложение должно нести новую информацию.
4. НЕ пиши длинные вводные абзацы типа "В предоставленных источниках содержится...". Сразу переходи к сути.
5. Если вопрос широкий (например "гражданское право"), а источники покрывают только узкие темы — кратко перечисли что найдено, без попыток раздуть в полноценный обзор.
6. Если информации по вопросу нет совсем — скажи это ОДНИМ предложением, без оговорок.
7. Используй структуру (заголовки, списки) только когда это реально помогает читаемости. Для короткого ответа — не нужно.
8. Язык ответа = язык вопроса.
9. Если источники противоречат друг другу — отметь кратко."""

# Qwen 3 uses "thinking mode" by default; disable it so content is returned
# directly and streaming works correctly.
_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}


def _build_context(results: list[SearchResult]) -> str:
    """Format search results into a numbered context block for the LLM."""
    if not results:
        return "Контекст: источники не найдены."

    sections = []
    for i, r in enumerate(results, 1):
        sections.append(
            f"--- Источник {i} ---\n"
            f"Файл: {r.source_file} | Страница: {r.page_number} | "
            f"Релевантность: {r.score:.2f}\n"
            f"{r.text}\n"
        )
    return "\n".join(sections)


def _get_client() -> OpenAI:
    """Create an OpenAI-compatible client for Alem AI / Qwen 3."""
    if not settings.llm_api_key:
        raise RuntimeError(
            "LLM_API_KEY not set. Add it to .env or export it."
        )
    return OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )


def _build_messages(question: str, results: list[SearchResult]) -> list[dict]:
    """Build the messages array for the chat completion."""
    context = _build_context(results)
    user_message = (
        f"Вопрос: {question}\n\n"
        f"Контекст из научных статей:\n{context}\n\n"
        f"Ответь на вопрос кратко и по существу, опираясь на контекст."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]


def generate_answer(question: str, results: list[SearchResult]) -> str:
    """Generate a complete answer (non-streaming).

    Args:
        question: User's research question.
        results: Retrieved chunks with metadata.

    Returns:
        Full text of the generated literature review.
    """
    client = _get_client()
    messages = _build_messages(question, results)

    logger.info("Generating answer for: '%s' (%d sources).", question[:80], len(results))

    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        max_tokens=settings.llm_max_tokens,
        extra_body=_EXTRA_BODY,
    )

    content = response.choices[0].message.content
    if not content:
        logger.warning("LLM returned empty content (model may still be in thinking mode).")
        return "Ошибка: модель не вернула ответ. Попробуйте повторить запрос."
    return content.strip()


def stream_answer(question: str, results: list[SearchResult]) -> Iterator[str]:
    """Generate an answer with streaming (for HTMX SSE).

    Yields:
        Text chunks as they arrive from the API.
    """
    client = _get_client()
    messages = _build_messages(question, results)

    logger.info("Streaming answer for: '%s' (%d sources).", question[:80], len(results))

    stream = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        max_tokens=settings.llm_max_tokens,
        stream=True,
        extra_body=_EXTRA_BODY,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
