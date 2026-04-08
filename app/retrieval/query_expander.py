"""Expand a user query into multiple search queries for better retrieval coverage.

Broad queries like "гражданское право Казахстана" map to a single point in
embedding space and miss relevant chunks about specific sub-topics. Multi-query
expansion generates diverse sub-queries so the retrieval covers more ground.
"""

import logging

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_EXPAND_PROMPT = (
    "Ты помогаешь улучшить поиск по базе научных статей казахстанских журналов.\n"
    "Преобразуй вопрос пользователя в 3 конкретных поисковых запроса для поиска В ТЕКСТЕ научных статей.\n\n"
    "Важные правила:\n"
    "- Запросы должны описывать СОДЕРЖАНИЕ искомых статей, а не спрашивать о базе данных.\n"
    "- Каждый запрос — это фраза которая может ВСТРЕТИТЬСЯ в тексте научной статьи.\n"
    "- Покрывай разные аспекты темы.\n"
    "- Язык запросов = язык вопроса.\n"
    "- Верни ТОЛЬКО запросы, по одному на строку, без нумерации.\n\n"
    "Пример: если вопрос 'какие данные есть про право', запросы должны быть типа:\n"
    "правовое регулирование в Республике Казахстан\n"
    "нормы законодательства РК\n"
    "судебная практика правоприменение"
)

# Reuse Qwen thinking-mode disable flag
_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}


def expand_query(question: str) -> list[str]:
    """Return [original_query, sub_query_1, sub_query_2, sub_query_3].

    Falls back to [original_query] if the LLM call fails or is disabled.
    """
    if not settings.query_expansion_enabled or not settings.llm_api_key:
        return [question]

    try:
        client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": _EXPAND_PROMPT},
                {"role": "user", "content": question},
            ],
            max_tokens=200,
            temperature=0.7,
            extra_body=_EXTRA_BODY,
        )

        content = response.choices[0].message.content
        if not content:
            return [question]

        sub_queries = [line.strip() for line in content.strip().splitlines() if line.strip()]
        sub_queries = sub_queries[:3]

        logger.info(
            "Query expansion: '%s' → +%d sub-queries: %s",
            question[:60], len(sub_queries), sub_queries,
        )
        return [question] + sub_queries

    except Exception as exc:
        logger.warning("Query expansion failed, using original query: %s", exc)
        return [question]
