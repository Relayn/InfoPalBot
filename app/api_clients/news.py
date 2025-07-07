"""Модуль для взаимодействия с NewsAPI для получения новостей.

Предоставляет асинхронные функции для получения главных новостей по странам
и для поиска статей по ключевым словам. Модуль инкапсулирует логику
HTTP-запросов, обработку ключей API и разбор ответов, включая ошибки.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

import httpx
from httpx import HTTPStatusError, RequestError

from app.config import settings

logger = logging.getLogger(__name__)


async def get_top_headlines(
    country: str = "us",
    category: Optional[str] = None,
    page_size: int = 10,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """Получает главные новости для указанной страны и категории.

    Args:
        country: Двухбуквенный код страны (ISO 3166-1). По умолчанию 'us'.
        category: Категория новостей (например, 'technology', 'sports').
        page_size: Количество возвращаемых результатов.

    Returns:
        Список словарей, где каждый словарь представляет статью, в случае успеха.
        Словарь с информацией об ошибке в случае сбоя.
    """
    if not settings.NEWS_API_KEY:
        logger.error("Ключ NEWS_API_KEY не настроен.")
        return {"error": True, "message": "Ключ API для новостей не настроен."}

    base_url = "https://newsapi.org/v2/top-headlines"
    params = {
        "country": country,
        "pageSize": page_size,
        "apiKey": settings.NEWS_API_KEY,
    }
    if category:
        params["category"] = category

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "ok":
                articles = data.get("articles", [])
                logger.info(
                    f"Успешно получено {len(articles)} новостей для '{country}' "
                    f"(категория: {category or 'any'})."
                )
                return articles
            else:
                error_message = data.get("message", "Неизвестная ошибка NewsAPI")
                logger.warning(f"API NewsAPI вернул ошибку: {error_message}")
                return {"error": True, "message": error_message}

    except HTTPStatusError as e:
        logger.error(
            f"Ошибка HTTP {e.response.status_code} при запросе новостей: {e.response.text}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": f"Ошибка сервера новостей (статус {e.response.status_code}).",
            "status_code": e.response.status_code,
        }
    except RequestError as e:
        logger.error(f"Сетевая ошибка при запросе новостей: {e}", exc_info=True)
        return {"error": True, "message": "Ошибка сети при запросе новостей."}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении новостей: {e}", exc_info=True)
        return {"error": True, "message": "Произошла непредвиденная ошибка."}


async def get_latest_news(
    query: str,
    from_date: Optional[datetime] = None,
    page_size: int = 10,
    language: str = "ru",
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """Ищет статьи по ключевому слову за определенный период.

    Args:
        query: Ключевое слово или фраза для поиска.
        from_date: Самая ранняя дата для поиска статей. Если не указана,
            используется значение "24 часа назад".
        page_size: Количество возвращаемых результатов.
        language: Язык статей (например, 'ru', 'en').

    Returns:
        Список словарей, где каждый словарь представляет статью, в случае успеха.
        Словарь с информацией об ошибке в случае сбоя.
    """
    if not settings.NEWS_API_KEY:
        logger.error("Ключ NEWS_API_KEY не настроен.")
        return {"error": True, "message": "Ключ API для новостей не настроен."}

    base_url = "https://newsapi.org/v2/everything"
    if from_date is None:
        from_date = datetime.now(timezone.utc) - timedelta(days=1)

    params = {
        "q": query,
        "from": from_date.isoformat(),
        "pageSize": page_size,
        "language": language,
        "sortBy": "publishedAt",
        "apiKey": settings.NEWS_API_KEY,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "ok":
                articles = data.get("articles", [])
                logger.info(
                    f"Успешно получено {len(articles)} новостей по запросу '{query}'."
                )
                return articles
            else:
                error_message = data.get("message", "Неизвестная ошибка NewsAPI")
                logger.warning(f"API NewsAPI вернул ошибку: {error_message}")
                return {"error": True, "message": error_message}

    except HTTPStatusError as e:
        logger.error(
            f"Ошибка HTTP {e.response.status_code} при запросе новостей: {e.response.text}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": f"Ошибка сервера новостей (статус {e.response.status_code}).",
            "status_code": e.response.status_code,
        }
    except RequestError as e:
        logger.error(f"Сетевая ошибка при запросе новостей: {e}", exc_info=True)
        return {"error": True, "message": "Ошибка сети при запросе новостей."}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении новостей: {e}", exc_info=True)
        return {"error": True, "message": "Произошла непредвиденная ошибка."}