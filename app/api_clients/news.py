import httpx
from typing import Optional, List, Dict, Any
from app.config import settings
import logging
# from datetime import datetime, timedelta, timezone # Убираем, т.к. не используем from_date в этом тесте

logger = logging.getLogger(__name__)

BASE_NEWSAPI_EVERYTHING_URL = "https://newsapi.org/v2/everything"
BASE_NEWSAPI_TOP_HEADLINES_URL = "https://newsapi.org/v2/top-headlines" # Добавляем URL для top-headlines


# Оставляем оригинальную функцию get_latest_news (можно будет ее доработать или удалить позже)
async def get_latest_news(query: str = "технологии",
                          language: str = "ru",
                          page_size: int = 5,
                          sort_by: str = "publishedAt") -> Optional[List[Dict[str, Any]]]:
    if not settings.NEWS_API_KEY:
        logger.error("NEWS_API_KEY не установлен в настройках.")
        return None

    # Убираем from_date для теста
    # from_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')

    params = {
        "q": query,
        "language": language,
        "pageSize": page_size,
        "sortBy": sort_by,
        "apiKey": settings.NEWS_API_KEY,
        # "from": from_date, # Убрали ограничение по дате
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BASE_NEWSAPI_EVERYTHING_URL, params=params)
            response_data = response.json()

            if response.status_code == 200 and response_data.get("status") == "ok":
                articles = response_data.get("articles", [])
                logger.info(f"(/everything) Успешно получено {len(articles)} новостей по запросу '{query}'.")
                if not articles:
                    logger.info(f"(/everything) По запросу '{query}' не найдено статей.")
                return articles
            else:
                error_code = response_data.get("code", str(response.status_code))
                error_message = response_data.get("message", "Неизвестная ошибка от NewsAPI или HTTP.")
                logger.error(f"(/everything) Ошибка от NewsAPI/HTTP при запросе '{query}': Код - {error_code}, Сообщение - {error_message}, Ответ: {response_data}")
                return {"error": True, "code": error_code, "message": error_message, "source": "NewsAPI/HTTP"}

    except httpx.RequestError as e:
        logger.error(f"(/everything) Ошибка сети при запросе новостей '{query}': {e}", exc_info=True)
        return {"error": True, "message": "Сетевая ошибка при запросе к сервису новостей.", "source": "Network"}
    except Exception as e:
        logger.error(f"(/everything) Непредвиденная ошибка при запросе новостей '{query}': {e}", exc_info=True)
        return {"error": True, "message": "Неизвестная ошибка при получении новостей.", "source": "Unknown"}


# Новая функция для top-headlines
async def get_top_headlines(country: str = "ru",
                            category: Optional[str] = None,
                            page_size: int = 5) -> Optional[List[Dict[str, Any]]]:
    """
    Получает главные новости для страны (и опционально категории) из NewsAPI.org.

    Args:
        country (str): Код страны (ISO 3166-1 alpha-2). По умолчанию "ru".
        category (Optional[str]): Категория новостей (business, entertainment, general,
                                  health, science, sports, technology).
        page_size (int): Количество статей.

    Returns:
        Optional[List[Dict[str, Any]]]: Список статей или словарь с ошибкой.
    """
    if not settings.NEWS_API_KEY:
        logger.error("NEWS_API_KEY не установлен в настройках.")
        return None

    params = {
        "country": country,
        "pageSize": page_size,
        "apiKey": settings.NEWS_API_KEY,
    }
    if category:
        params["category"] = category

    # В запросе к /top-headlines нельзя указывать country/category вместе с sources.
    # Мы используем country/category.

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

    except httpx.RequestError as e:
        logger.error(f"(/top-headlines) Ошибка сети при запросе новостей для страны '{country}': {e}", exc_info=True)
        return {"error": True, "message": "Сетевая ошибка при запросе к сервису новостей.", "source": "Network"}
    except Exception as e:
        logger.error(f"(/top-headlines) Непредвиденная ошибка при запросе новостей для страны '{country}': {e}", exc_info=True)
        return {"error": True, "message": "Неизвестная ошибка при получении новостей.", "source": "Unknown"}


# Обновленный тестовый блок
async def main_test_news_api():
    print(f"--- Тест /everything (без ограничения по дате) ---")
    query_en = "technology"
    print(f"Запрашиваем новости по запросу: '{query_en}' (английский)...")
    raw_result_en = await get_latest_news(query=query_en, language="en", page_size=3)
    print(f"Ответ (/everything, en): {raw_result_en}")
    if isinstance(raw_result_en, list) and raw_result_en:
        for i, article in enumerate(raw_result_en): print(f"  EN-{i+1}. {article.get('title')}")
    elif isinstance(raw_result_en, dict) and raw_result_en.get("error"): print(f"Ошибка (/everything, en): {raw_result_en.get('message')}")
    else: print(f"Статей не найдено (/everything, en).")
    print("-" * 30)

    print(f"--- Тест /top-headlines (Россия, без категории) ---")
    raw_result_top_ru = await get_top_headlines(country="ru", page_size=3)
    print(f"Ответ (/top-headlines, ru): {raw_result_top_ru}")
    if isinstance(raw_result_top_ru, list) and raw_result_top_ru:
        for i, article in enumerate(raw_result_top_ru): print(f"  RU-Top-{i+1}. {article.get('title')}")
    elif isinstance(raw_result_top_ru, dict) and raw_result_top_ru.get("error"): print(f"Ошибка (/top-headlines, ru): {raw_result_top_ru.get('message')}")
    else: print(f"Статей не найдено (/top-headlines, ru).")
    print("-" * 30)

    print(f"--- Тест /top-headlines (США, технология) ---")
    raw_result_top_us_tech = await get_top_headlines(country="us", category="technology", page_size=3)
    print(f"Ответ (/top-headlines, us, tech): {raw_result_top_us_tech}")
    if isinstance(raw_result_top_us_tech, list) and raw_result_top_us_tech:
        for i, article in enumerate(raw_result_top_us_tech): print(f"  US-Tech-{i+1}. {article.get('title')}")
    elif isinstance(raw_result_top_us_tech, dict) and raw_result_top_us_tech.get("error"): print(f"Ошибка (/top-headlines, us, tech): {raw_result_top_us_tech.get('message')}")
    else: print(f"Статей не найдено (/top-headlines, us, tech).")

if __name__ == "__main__":
    import asyncio
    from app.config import settings
    if not settings.NEWS_API_KEY:
        print("Переменная NEWS_API_KEY не найдена в .env файле или пуста.")
        print("Пожалуйста, добавьте NEWS_API_KEY='ВАШ_КЛЮЧ' в .env")
    else:
        print(f"Используется NEWS_API_KEY: ...{settings.NEWS_API_KEY[-4:]}")
        asyncio.run(main_test_news_api())