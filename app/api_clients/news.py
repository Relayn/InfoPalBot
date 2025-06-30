"""
Модуль для взаимодействия с NewsAPI для получения новостей.
"""

import logging
from typing import Optional, List, Dict, Any, Union
# ИЗМЕНЕНО: импортируем timezone
from datetime import datetime, timedelta, timezone

import httpx
from httpx import RequestError, HTTPStatusError

from app.config import settings

logger = logging.getLogger(__name__)


async def get_top_headlines(
    country: str = "us",
    category: Optional[str] = None,
    page_size: int = 10,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    # ... (код без изменений) ...
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
                    f"(/top-headlines) Успешно получено {len(articles)} новостей для страны '{country}' (категория: {category})."
                )
                if not articles:
                    logger.info(
                        f"(/top-headlines) Не найдено главных новостей для страны '{country}' (категория: {category})."
                    )
                return articles
            else:
                error_message = data.get("message", "Неизвестная ошибка от NewsAPI")
                logger.warning(
                    f"(/top-headlines) API NewsAPI вернул ошибку: {error_message}"
                )
                return {"error": True, "message": error_message}

    except HTTPStatusError as e:
        logger.error(
            f"(/top-headlines) Ошибка HTTP {e.response.status_code} при запросе к NewsAPI: {e.response.text}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": f"Ошибка сервера новостей (статус {e.response.status_code}).",
            "status_code": e.response.status_code,
        }
    except RequestError as e:
        logger.error(
            f"(/top-headlines) Ошибка сети при запросе к NewsAPI: {e}", exc_info=True
        )
        return {"error": True, "message": "Ошибка сети при запросе новостей."}
    except Exception as e:
        logger.error(
            f"(/top-headlines) Непредвиденная ошибка при получении новостей: {e}",
            exc_info=True,
        )
        return {"error": True, "message": "Произошла непредвиденная ошибка."}


async def get_latest_news(
    query: str,
    from_date: Optional[datetime] = None,
    page_size: int = 10,
    language: str = "ru",
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Получает последние новости по ключевому запросу.
    """
    if not settings.NEWS_API_KEY:
        logger.error("Ключ NEWS_API_KEY не настроен.")
        return {"error": True, "message": "Ключ API для новостей не настроен."}

    base_url = "https://newsapi.org/v2/everything"
    if from_date is None:
        # ИЗМЕНЕНО: используем timezone-aware datetime
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
                    f"(/everything) Успешно получено {len(articles)} новостей по запросу '{query}'."
                )
                if not articles:
                    logger.info(
                        f"(/everything) Не найдено новостей по запросу '{query}'."
                    )
                return articles
            else:
                error_message = data.get("message", "Неизвестная ошибка от NewsAPI")
                logger.warning(
                    f"(/everything) API NewsAPI вернул ошибку: {error_message}"
                )
                return {"error": True, "message": error_message}

    except HTTPStatusError as e:
        logger.error(
            f"(/everything) Ошибка HTTP {e.response.status_code} при запросе к NewsAPI: {e.response.text}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": f"Ошибка сервера новостей (статус {e.response.status_code}).",
            "status_code": e.response.status_code,
        }
    except RequestError as e:
        logger.error(
            f"(/everything) Ошибка сети при запросе к NewsAPI: {e}", exc_info=True
        )
        return {"error": True, "message": "Ошибка сети при запросе новостей."}
    except Exception as e:
        logger.error(
            f"(/everything) Непредвиденная ошибка при получении новостей: {e}",
            exc_info=True,
        )
        return {"error": True, "message": "Произошла непредвиденная ошибка."}