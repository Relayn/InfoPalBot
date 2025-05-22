"""
Модуль для взаимодействия с API NewsAPI.org.
Предоставляет функции для получения последних новостей и главных заголовков.
"""

import httpx
from typing import Optional, List, Dict, Any
from app.config import settings # Для доступа к API ключу NewsAPI
import logging
from datetime import datetime, timedelta, timezone # Для работы с датами и часовыми поясами

# Настройка логгера для модуля
logger = logging.getLogger(__name__)

# Базовые URL для различных эндпоинтов NewsAPI.org
BASE_NEWSAPI_EVERYTHING_URL: str = "https://newsapi.org/v2/everything"
BASE_NEWSAPI_TOP_HEADLINES_URL: str = "https://newsapi.org/v2/top-headlines"


async def get_latest_news(query: str = "технологии",
                          language: str = "ru",
                          page_size: int = 5,
                          sort_by: str = "publishedAt",
                          use_from_date: bool = True) -> Optional[List[Dict[str, Any]]]:
    """
    Получает последние новости по заданному запросу из NewsAPI.org (эндпоинт /everything).
    NewsAPI для /everything может иметь ограничения по дате на бесплатных тарифах.

    Args:
        query (str): Ключевые слова или фраза для поиска новостей. По умолчанию "технологии".
        language (str): Язык новостей (например, "ru", "en"). По умолчанию "ru".
        page_size (int): Количество статей для возврата. По умолчанию 5. Максимум 100 на бесплатном тарифе.
        sort_by (str): Порядок сортировки результатов. Варианты: "relevancy", "popularity", "publishedAt".
                       По умолчанию "publishedAt" (сначала новые).
        use_from_date (bool): Если True, добавляет параметр 'from' для ограничения новостей
                              последними 24 часами (рекомендуется для бесплатных ключей /everything).

    Returns:
        Optional[List[Dict[str, Any]]]: Список словарей со статьями, если запрос успешен.
                                         В случае ошибки возвращает словарь с ключом "error": True
                                         и сообщением об ошибке, иначе None (если API ключ не установлен).
    """
    if not settings.NEWS_API_KEY:
        logger.error("NEWS_API_KEY не установлен в настройках. Невозможно получить новости.")
        return None

    params: Dict[str, Any] = {
        "q": query,
        "language": language,
        "pageSize": page_size,
        "sortBy": sort_by,
        "apiKey": settings.NEWS_API_KEY,
    }
    # Добавляем ограничение по дате, если требуется
    if use_from_date:
        from_date_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        params["from"] = from_date_str

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BASE_NEWSAPI_EVERYTHING_URL, params=params)
            response_data = response.json() # Парсим JSON ответ

            # NewsAPI часто возвращает 200 OK даже при ошибках (например, неверный ключ),
            # информацию об ошибке содержит в поле "status": "error" в JSON.
            if response.status_code == 200 and response_data.get("status") == "ok":
                articles = response_data.get("articles", [])
                logger.info(f"(/everything) Успешно получено {len(articles)} новостей по запросу '{query}'.")
                if not articles and use_from_date:
                    logger.info(f"(/everything) По запросу '{query}' не найдено статей за последние 24 часа.")
                elif not articles:
                    logger.info(f"(/everything) По запросу '{query}' не найдено статей.")
                return articles
            else: # Обработка ошибок, которые NewsAPI возвращает в JSON с status="error"
                error_code = response_data.get("code", str(response.status_code))
                error_message = response_data.get("message", "Неизвестная ошибка от NewsAPI или HTTP.")
                logger.error(f"(/everything) Ошибка от NewsAPI/HTTP при запросе '{query}': Код - {error_code}, Сообщение - {error_message}, Ответ: {response_data}", exc_info=True)
                return {"error": True, "code": error_code, "message": error_message, "source": "NewsAPI/HTTP"}

    except httpx.HTTPStatusError as e:
        # Обработка HTTP ошибок (например, 4xx или 5xx), когда сервер NewsAPI возвращает не 200 OK
        logger.error(f"(/everything) Ошибка HTTP при запросе новостей '{query}': {e.response.status_code} - {e.response.text}", exc_info=True)
        return {"error": True, "message": f"Ошибка HTTP: {e.response.status_code}", "status_code": e.response.status_code, "source": "HTTP"}
    except httpx.RequestError as e:
        # Обработка сетевых ошибок или проблем с запросом
        logger.error(f"(/everything) Ошибка сети при запросе новостей '{query}': {e}", exc_info=True)
        return {"error": True, "message": "Сетевая ошибка при запросе к сервису новостей.", "source": "Network"}
    except Exception as e:
        # Обработка любых других непредвиденных исключений (например, ошибок парсинга JSON, если ответ не JSON)
        logger.error(f"(/everything) Непредвиденная ошибка при запросе новостей '{query}': {e}", exc_info=True)
        return {"error": True, "message": "Неизвестная ошибка при получении новостей.", "source": "Unknown"}


async def get_top_headlines(country: str = "ru",
                            category: Optional[str] = None,
                            page_size: int = 5) -> Optional[List[Dict[str, Any]]]:
    """
    Получает главные новости (топ-заголовки) для указанной страны (и опционально категории) из NewsAPI.org.

    Args:
        country (str): Код страны (ISO 3166-1 alpha-2). По умолчанию "ru".
        category (Optional[str]): Категория новостей (например, "business", "technology").
                                  Если None, возвращаются новости общей категории.
        page_size (int): Количество статей для возврата. По умолчанию 5.

    Returns:
        Optional[List[Dict[str, Any]]]: Список словарей со статьями, если запрос успешен.
                                         В случае ошибки возвращает словарь с ключом "error": True
                                         и сообщением об ошибке, иначе None (если API ключ не установлен).
    """
    if not settings.NEWS_API_KEY:
        logger.error("NEWS_API_KEY не установлен в настройках. Невозможно получить главные новости.")
        return None

    params: Dict[str, Any] = {
        "country": country,
        "pageSize": page_size,
        "apiKey": settings.NEWS_API_KEY,
    }
    # Добавляем категорию, если она указана
    if category:
        params["category"] = category

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BASE_NEWSAPI_TOP_HEADLINES_URL, params=params)
            response_data = response.json() # Парсим JSON ответ

            if response.status_code == 200 and response_data.get("status") == "ok":
                articles = response_data.get("articles", [])
                logger.info(f"(/top-headlines) Успешно получено {len(articles)} новостей для страны '{country}' (категория: {category}).")
                if not articles:
                    logger.info(f"(/top-headlines) Не найдено главных новостей для страны '{country}' (категория: {category}).")
                return articles
            else: # Обработка ошибок, которые NewsAPI возвращает в JSON с status="error"
                error_code = response_data.get("code", str(response.status_code))
                error_message = response_data.get("message", "Неизвестная ошибка от NewsAPI или HTTP.")
                logger.error(f"(/top-headlines) Ошибка от NewsAPI/HTTP для страны '{country}': Код - {error_code}, Сообщение - {error_message}, Ответ: {response_data}", exc_info=True)
                return {"error": True, "code": error_code, "message": error_message, "source": "NewsAPI/HTTP"}

    except httpx.HTTPStatusError as e:
        # Обработка HTTP ошибок (например, 4xx или 5xx), когда сервер NewsAPI возвращает не 200 OK
        logger.error(f"(/top-headlines) Ошибка HTTP при запросе новостей для страны '{country}': {e.response.status_code} - {e.response.text}", exc_info=True)
        return {"error": True, "message": f"Ошибка HTTP: {e.response.status_code}", "status_code": e.response.status_code, "source": "HTTP"}
    except httpx.RequestError as e:
        # Обработка сетевых ошибок или проблем с запросом
        logger.error(f"(/top-headlines) Ошибка сети при запросе новостей для страны '{country}': {e}", exc_info=True)
        return {"error": True, "message": "Сетевая ошибка при запросе к сервису новостей.", "source": "Network"}
    except Exception as e:
        # Обработка любых других непредвиденных исключений
        logger.error(f"(/top-headlines) Непредвиденная ошибка при запросе новостей для страны '{country}': {e}", exc_info=True)
        return {"error": True, "message": "Неизвестная ошибка при получении новостей.", "source": "Unknown"}