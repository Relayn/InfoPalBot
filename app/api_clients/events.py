"""Модуль для взаимодействия с публичным API KudaGo.

Предоставляет асинхронную функцию для получения информации о предстоящих
событиях в различных городах России. Модуль инкапсулирует логику
HTTP-запросов и обработку ответов от API KudaGo.
"""
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_KUDAGO_API_URL: str = "https://kudago.com/public-api/v1.4"


async def get_kudago_events(
    location: str,
    page_size: int = 5,
    fields: str = "id,title,description,dates,place,images,site_url",
    categories: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Асинхронно запрашивает список актуальных событий из KudaGo API.

    Функция фильтрует события, которые актуальны с текущего момента,
    и сортирует их по дате начала.

    Args:
        location: Код города (slug), например, 'msk', 'spb'.
        page_size: Количество событий для возврата.
        fields: Запрашиваемые поля данных, перечисленные через запятую.
        categories: Категории событий для фильтрации, перечисленные
            через запятую (например, 'concert,exhibition').

    Returns:
        Список словарей, где каждый словарь представляет событие,
        в случае успеха.
        Словарь с информацией об ошибке, если запрос не удался.
    """
    current_timestamp: int = int(time.time())
    api_url: str = f"{BASE_KUDAGO_API_URL}/events/"
    params: Dict[str, Any] = {
        "location": location,
        "page_size": page_size,
        "fields": fields,
        "actual_since": current_timestamp,
        "text_format": "text",
        "order_by": "dates",
    }
    if categories:
        params["categories"] = categories

    logger.debug(f"Запрос к KudaGo API: URL={api_url}, Params={params}")

    try:
        async with httpx.AsyncClient() as client:
            headers: Dict[str, str] = {"Accept-Language": "ru-RU,ru;q=0.9"}
            response = await client.get(api_url, params=params, headers=headers)
            response.raise_for_status()
            response_data: Dict[str, Any] = response.json()

            events: Optional[List[Dict[str, Any]]] = response_data.get("results")
            if events is not None:
                logger.info(
                    f"Успешно получено {len(events)} событий KudaGo для '{location}'."
                )
                return events
            else:
                logger.error(
                    f"Ошибка от KudaGo API для '{location}': "
                    f"отсутствует ключ 'results'. Ответ: {response_data}",
                )
                return {
                    "error": True,
                    "message": "Некорректный формат ответа от KudaGo API.",
                    "source": "KudaGo API Format",
                }

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Ошибка HTTP при запросе событий KudaGo для '{location}': "
            f"{e.response.status_code} - {e.response.text}",
            exc_info=True,
        )
        try:
            error_data: Dict[str, Any] = e.response.json()
            message = error_data.get("detail", str(error_data))
        except Exception:
            message = e.response.text or "Неизвестная HTTP ошибка."

        return {
            "error": True,
            "message": message,
            "status_code": e.response.status_code,
            "source": "KudaGo HTTP",
        }
    except httpx.RequestError as e:
        logger.error(
            f"Сетевая ошибка при запросе событий KudaGo для '{location}': {e}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": "Сетевая ошибка при запросе к сервису событий.",
            "source": "Network",
        }
    except Exception as e:
        logger.error(
            f"Непредвиденная ошибка при запросе событий KudaGo для '{location}': {e}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": "Неизвестная ошибка при получении событий.",
            "source": "Unknown",
        }