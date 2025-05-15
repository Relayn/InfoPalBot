import httpx
from typing import Optional, List, Dict, Any
import logging
import time # Для получения текущего времени в Unix timestamp

logger = logging.getLogger(__name__)

# Базовый URL и версия API KudaGo
BASE_KUDAGO_API_URL = "https://kudago.com/public-api/v1.4"

async def get_kudago_events(location: str,
                            page_size: int = 5,
                            fields: str = "id,title,description,dates,place,images,site_url",
                            categories: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Получает список актуальных событий из KudaGo API для указанного города.

    Args:
        location (str): Код города (например, 'msk', 'spb').
        page_size (int): Количество событий на странице.
        fields (str): Запрашиваемые поля через запятую.
        categories (Optional[str]): Фильтр по категориям через запятую
                                     (например, 'concert,exhibition').

    Returns:
        Optional[List[Dict[str, Any]]]: Список словарей с событиями или
                                         словарь с информацией об ошибке.
    """
    # Получаем текущее время в формате Unix timestamp для фильтрации прошлых событий
    current_timestamp = int(time.time())

    api_url = f"{BASE_KUDAGO_API_URL}/events/"
    params = {
        "location": location,
        "page_size": page_size,
        "fields": fields,
        "actual_since": current_timestamp, # Запрашиваем события, актуальные с текущего момента
        "text_format": "text", # Запрашиваем описание в виде простого текста, а не HTML
        "order_by": "dates", # Сортируем по дате начала (можно изменить)
    }
    if categories:
        params["categories"] = categories

    logger.debug(f"Запрос к KudaGo API: URL={api_url}, Params={params}")

    try:
        async with httpx.AsyncClient() as client:
            # Устанавливаем заголовок Accept-Language, чтобы KudaGo возвращал
            # названия и описания на русском (если возможно)
            headers = {"Accept-Language": "ru-RU,ru;q=0.9"}
            response = await client.get(api_url, params=params, headers=headers)
            response.raise_for_status() # Проверяем на HTTP ошибки (4xx, 5xx)
            response_data = response.json()

            # KudaGo API в ответе содержит ключ "results" со списком событий
            events = response_data.get("results")

            if events is not None: # Проверяем, что ключ "results" существует
                logger.info(f"Успешно получено {len(events)} событий KudaGo для города '{location}'.")
                return events
            else:
                # Если ключ "results" отсутствует, возможно, это ошибка API KudaGo
                logger.error(f"Ошибка от KudaGo API для города '{location}': отсутствует ключ 'results'. Ответ: {response_data}")
                return {"error": True, "message": "Некорректный формат ответа от KudaGo API.", "source": "KudaGo API Format"}

    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка HTTP при запросе событий KudaGo для '{location}': {e.response.status_code} - {e.response.text}", exc_info=True)
        # Попытка извлечь detail из ответа KudaGo, если он есть (их ошибки часто в поле detail)
        error_detail = "Неизвестная HTTP ошибка."
        try:
             error_data = e.response.json()
             if "detail" in error_data:
                 error_detail = error_data["detail"]
             elif isinstance(error_data, dict): # Если нет detail, но есть другие поля
                 error_detail = str(error_data)

        except Exception:
            error_detail = e.response.text or error_detail

        return {"error": True, "message": error_detail, "status_code": e.response.status_code, "source": "KudaGo HTTP"}
    except httpx.RequestError as e:
        logger.error(f"Ошибка сети при запросе событий KudaGo для '{location}': {e}", exc_info=True)
        return {"error": True, "message": "Сетевая ошибка при запросе к сервису событий.", "source": "Network"}
    except Exception as e: # Включая JSONDecodeError
        logger.error(f"Непредвиденная ошибка при запросе событий KudaGo для '{location}': {e}", exc_info=True)
        return {"error": True, "message": "Неизвестная ошибка при получении событий.", "source": "Unknown"}


# Пример использования
async def main_test_kudago_api():
    location = "msk" # Москва
    print(f"Запрашиваем события для города: {location}")
    events_result = await get_kudago_events(location=location, page_size=3)

    print(f"Ответ от get_kudago_events: {events_result}")

    if isinstance(events_result, list) and events_result:
        print(f"\nНайденные события:")
        for i, event in enumerate(events_result):
            print(f"  {i+1}. {event.get('title')}")
            place = event.get('place')
            place_name = place.get('title') if place else "Место не указано"
            print(f"     Место: {place_name}")
            # Можно добавить вывод дат, описания и т.д.
            print("-" * 20)
    elif isinstance(events_result, dict) and events_result.get("error"):
        print(f"Ошибка получения событий: {events_result.get('message')} (Источник: {events_result.get('source')})")
    elif isinstance(events_result, list) and not events_result:
        print("Актуальных событий не найдено.")
    else:
        print("Не удалось получить события или формат ответа неизвестен.")

if __name__ == "__main__":
    import asyncio
    # Настройки здесь не нужны, т.к. нет ключа API
    asyncio.run(main_test_kudago_api())