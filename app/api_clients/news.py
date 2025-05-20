import httpx
from typing import Optional, List, Dict, Any
from app.config import settings
import logging
from datetime import datetime, timedelta, timezone # Добавляем для from_date, если решим использовать

logger = logging.getLogger(__name__)

BASE_NEWSAPI_EVERYTHING_URL = "https://newsapi.org/v2/everything"
BASE_NEWSAPI_TOP_HEADLINES_URL = "https://newsapi.org/v2/top-headlines"

async def get_latest_news(query: str = "технологии",
                          language: str = "ru",
                          page_size: int = 5,
                          sort_by: str = "publishedAt",
                          use_from_date: bool = True) -> Optional[List[Dict[str, Any]]]: # Добавил use_from_date
    """
    Получает новости по заданному запросу из NewsAPI.org (эндпоинт /everything).
    """
    if not settings.NEWS_API_KEY:
        logger.error("NEWS_API_KEY не установлен в настройках.")
        return None

    params = {
        "q": query,
        "language": language,
        "pageSize": page_size,
        "sortBy": sort_by,
        "apiKey": settings.NEWS_API_KEY,
    }
    if use_from_date: # Используем параметр для управления from_date
        from_date_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        params["from"] = from_date_str

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BASE_NEWSAPI_EVERYTHING_URL, params=params)
            response_data = response.json()

            if response.status_code == 200 and response_data.get("status") == "ok":
                articles = response_data.get("articles", [])
                logger.info(f"(/everything) Успешно получено {len(articles)} новостей по запросу '{query}'.")
                if not articles and use_from_date: # Уточняем лог
                    logger.info(f"(/everything) По запросу '{query}' не найдено статей за последние 24 часа.")
                elif not articles:
                    logger.info(f"(/everything) По запросу '{query}' не найдено статей.")
                return articles
            else: # Ошибки, которые NewsAPI возвращает в JSON
                error_code = response_data.get("code", str(response.status_code))
                error_message = response_data.get("message", "Неизвестная ошибка от NewsAPI или HTTP.")
                logger.error(f"(/everything) Ошибка от NewsAPI/HTTP при запросе '{query}': Код - {error_code}, Сообщение - {error_message}, Ответ: {response_data}")
                return {"error": True, "code": error_code, "message": error_message, "source": "NewsAPI/HTTP"}

    except httpx.HTTPStatusError as e: # Ловим HTTPStatusError явно
        logger.error(f"(/everything) Ошибка HTTP при запросе новостей '{query}': {e.response.status_code} - {e.response.text}", exc_info=True)
        return {"error": True, "message": f"Ошибка HTTP: {e.response.status_code}", "status_code": e.response.status_code, "source": "HTTP"}
    except httpx.RequestError as e: # Сетевые ошибки
        logger.error(f"(/everything) Ошибка сети при запросе новостей '{query}': {e}", exc_info=True)
        return {"error": True, "message": "Сетевая ошибка при запросе к сервису новостей.", "source": "Network"}
    except Exception as e: # Другие ошибки, включая JSONDecodeError
        logger.error(f"(/everything) Непредвиденная ошибка при запросе новостей '{query}': {e}", exc_info=True)
        return {"error": True, "message": "Неизвестная ошибка при получении новостей.", "source": "Unknown"}


async def get_top_headlines(country: str = "ru",
                            category: Optional[str] = None,
                            page_size: int = 5) -> Optional[List[Dict[str, Any]]]:
    """
    Получает главные новости для страны (и опционально категории) из NewsAPI.org.
    """
    if not settings.NEWS_API_KEY:
        logger.error("NEWS_API_KEY не установлен в настройках.")
        return None

    params = { "country": country, "pageSize": page_size, "apiKey": settings.NEWS_API_KEY }
    if category:
        params["category"] = category

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BASE_NEWSAPI_TOP_HEADLINES_URL, params=params)
            response_data = response.json()

            if response.status_code == 200 and response_data.get("status") == "ok":
                articles = response_data.get("articles", [])
                logger.info(f"(/top-headlines) Успешно получено {len(articles)} новостей для страны '{country}' (категория: {category}).")
                if not articles:
                    logger.info(f"(/top-headlines) Не найдено главных новостей для страны '{country}' (категория: {category}).")
                return articles
            else:
                error_code = response_data.get("code", str(response.status_code))
                error_message = response_data.get("message", "Неизвестная ошибка от NewsAPI или HTTP.")
                logger.error(f"(/top-headlines) Ошибка от NewsAPI/HTTP для страны '{country}': Код - {error_code}, Сообщение - {error_message}, Ответ: {response_data}")
                return {"error": True, "code": error_code, "message": error_message, "source": "NewsAPI/HTTP"}

    except httpx.HTTPStatusError as e: # Ловим HTTPStatusError явно
        logger.error(f"(/top-headlines) Ошибка HTTP при запросе новостей для страны '{country}': {e.response.status_code} - {e.response.text}", exc_info=True)
        return {"error": True, "message": f"Ошибка HTTP: {e.response.status_code}", "status_code": e.response.status_code, "source": "HTTP"}
    except httpx.RequestError as e:
        logger.error(f"(/top-headlines) Ошибка сети при запросе новостей для страны '{country}': {e}", exc_info=True)
        return {"error": True, "message": "Сетевая ошибка при запросе к сервису новостей.", "source": "Network"}
    except Exception as e:
        logger.error(f"(/top-headlines) Непредвиденная ошибка при запросе новостей для страны '{country}': {e}", exc_info=True)
        return {"error": True, "message": "Неизвестная ошибка при получении новостей.", "source": "Unknown"}

# Пример использования (оставляем для возможности ручного теста)
async def main_test_news_api():
    print(f"--- Тест /everything (с ограничением по дате) ---")
    query_ru_ai = "искусственный интеллект"
    print(f"Запрашиваем новости по запросу: '{query_ru_ai}' (русский, с датой)...")
    raw_result_ru_ai_dated = await get_latest_news(query=query_ru_ai, language="ru", page_size=3, use_from_date=True)
    print(f"Ответ (/everything, ru, AI, dated): {raw_result_ru_ai_dated}")
    if isinstance(raw_result_ru_ai_dated, list) and raw_result_ru_ai_dated:
        for i, article in enumerate(raw_result_ru_ai_dated): print(f"  RU-AI-Dated-{i+1}. {article.get('title')}")
    elif isinstance(raw_result_ru_ai_dated, dict) and raw_result_ru_ai_dated.get("error"): print(f"Ошибка: {raw_result_ru_ai_dated.get('message')}")
    else: print(f"Статей не найдено.")
    print("-" * 30)

    print(f"--- Тест /everything (без ограничения по дате) ---")
    query_en_tech = "technology"
    print(f"Запрашиваем новости по запросу: '{query_en_tech}' (английский, без даты)...")
    raw_result_en_tech_nodate = await get_latest_news(query=query_en_tech, language="en", page_size=3, use_from_date=False)
    print(f"Ответ (/everything, en, tech, no date): {raw_result_en_tech_nodate}")
    if isinstance(raw_result_en_tech_nodate, list) and raw_result_en_tech_nodate:
        for i, article in enumerate(raw_result_en_tech_nodate): print(f"  EN-Tech-NoDate-{i+1}. {article.get('title')}")
    elif isinstance(raw_result_en_tech_nodate, dict) and raw_result_en_tech_nodate.get("error"): print(f"Ошибка: {raw_result_en_tech_nodate.get('message')}")
    else: print(f"Статей не найдено.")
    print("-" * 30)

    print(f"--- Тест /top-headlines (Россия, без категории) ---")
    raw_result_top_ru = await get_top_headlines(country="ru", page_size=3)
    print(f"Ответ (/top-headlines, ru): {raw_result_top_ru}")
    if isinstance(raw_result_top_ru, list) and raw_result_top_ru:
        for i, article in enumerate(raw_result_top_ru): print(f"  RU-Top-{i+1}. {article.get('title')}")
    elif isinstance(raw_result_top_ru, dict) and raw_result_top_ru.get("error"): print(f"Ошибка: {raw_result_top_ru.get('message')}")
    else: print(f"Статей не найдено.")

if __name__ == "__main__":
    import asyncio
    # from app.config import settings # Уже импортирован глобально
    if not settings.NEWS_API_KEY:
        print("Переменная NEWS_API_KEY не найдена в .env файле или пуста.")
    else:
        print(f"Используется NEWS_API_KEY: ...{settings.NEWS_API_KEY[-4:]}")
        asyncio.run(main_test_news_api())