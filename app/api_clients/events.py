"""
Модуль для взаимодействия с публичным API KudaGo.

Предоставляет асинхронную функцию `get_kudago_events` для получения
информации о событиях в различных городах России.

Этот модуль использует публичный API KudaGo для получения информации о событиях
в различных городах России. API не требует ключа для доступа.

Основные возможности:
- Получение актуальных событий для указанного города
- Фильтрация по категориям событий
- Выбор конкретных полей для получения
- Поддержка русского языка
- Обработка различных типов ошибок (HTTP, сетевые, API)
- Логирование всех запросов и ошибок

Пример использования:
    # Получение концертов в Москве
    events = await get_kudago_events(location="msk", categories="concert")
    if events and not isinstance(events, dict):  # Проверка на ошибку
        for event in events:
            print(f"{event['title']}: {event['site_url']}")

Поддерживаемые города:
    - msk: Москва
    - spb: Санкт-Петербург
    - nsk: Новосибирск
    - ekb: Екатеринбург
    - kzn: Казань
    - nnv: Нижний Новгород

Поддерживаемые категории:
    - concert: Концерты
    - exhibition: Выставки
    - festival: Фестивали
    - theater: Театр
    - cinema: Кино
    - party: Вечеринки
    - education: Образование
    - sport: Спорт
    - night: Ночная жизнь
    - kids: Детям
    - other: Другое
"""

import httpx
from typing import Optional, List, Dict, Any  # Для аннотаций типов
import logging
import time  # Для получения текущего времени в Unix timestamp

# Настройка логгера для модуля
logger = logging.getLogger(__name__)

# Базовый URL и версия публичного API KudaGo
BASE_KUDAGO_API_URL: str = "https://kudago.com/public-api/v1.4"


async def get_kudago_events(
    location: str,
    page_size: int = 5,
    fields: str = "id,title,description,dates,place,images,site_url",
    categories: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Асинхронно запрашивает список актуальных событий из KudaGo API.

    Args:
        location (str): Код города (напр., 'msk', 'spb').
        page_size (int): Количество событий для возврата.
        fields (str): Запрашиваемые поля данных, перечисленные через запятую.
        categories (Optional[str]): Категории событий ('concert', 'exhibition' и др.).

    Returns:
        Optional[List[Dict[str, Any]]]:
            - В случае успеха возвращает список событий.
            - В случае ошибки возвращает словарь с информацией об ошибке.
    """
    # Получаем текущее время в формате Unix timestamp.
    # Используется для фильтрации событий, которые актуальны с текущего момента.
    current_timestamp: int = int(time.time())

    api_url: str = f"{BASE_KUDAGO_API_URL}/events/"  # Эндпоинт для событий
    params: Dict[str, Any] = {
        "location": location,
        "page_size": page_size,
        "fields": fields,
        "actual_since": current_timestamp,  # Фильтр по времени (актуальные с текущего момента)
        "text_format": "text",  # Запрашиваем описание в виде простого текста (без HTML-тегов)
        "order_by": "dates",  # Сортировка событий по дате начала
    }
    # Добавляем категории в параметры запроса, если они указаны
    if categories:
        params["categories"] = categories

    logger.debug(f"Запрос к KudaGo API: URL={api_url}, Params={params}")

    try:
        # Используем асинхронный HTTP клиент httpx для выполнения запроса
        async with httpx.AsyncClient() as client:
            # Устанавливаем заголовок Accept-Language для получения русскоязычных ответов (если доступно)
            headers: Dict[str, str] = {"Accept-Language": "ru-RU,ru;q=0.9"}
            response = await client.get(api_url, params=params, headers=headers)
            # Вызовет исключение httpx.HTTPStatusError для HTTP ошибок (4xx или 5xx)
            response.raise_for_status()
            response_data: Dict[str, Any] = response.json()  # Парсим JSON ответ от API

            # KudaGo API возвращает список событий под ключом "results"
            events: Optional[List[Dict[str, Any]]] = response_data.get("results")

            if (
                events is not None
            ):  # Проверяем, что ключ "results" существует и содержит список
                logger.info(
                    f"Успешно получено {len(events)} событий KudaGo для города '{location}'."
                )
                return events
            else:
                # Если ключ "results" отсутствует, это указывает на некорректный формат ответа от API
                logger.error(
                    f"Ошибка от KudaGo API для города '{location}': отсутствует ключ 'results'. Ответ: {response_data}",
                    exc_info=True,
                )
                return {
                    "error": True,
                    "message": "Некорректный формат ответа от KudaGo API.",
                    "source": "KudaGo API Format",
                }

    except httpx.HTTPStatusError as e:
        # Обработка HTTP ошибок (например, 404 Not Found, 500 Internal Server Error)
        logger.error(
            f"Ошибка HTTP при запросе событий KudaGo для '{location}': {e.response.status_code} - {e.response.text}",
            exc_info=True,
        )
        # Попытка извлечь более детальное сообщение об ошибке из поля "detail" (часто используется KudaGo)
        error_detail: str = "Неизвестная HTTP ошибка."
        try:
            error_data: Dict[str, Any] = e.response.json()
            if "detail" in error_data:
                error_detail = error_data["detail"]
            elif isinstance(
                error_data, dict
            ):  # Если нет "detail", но есть другие поля в JSON
                error_detail = str(error_data)
        except Exception:  # Если ответ не является валидным JSON
            error_detail = e.response.text or error_detail

        return {
            "error": True,
            "message": error_detail,
            "status_code": e.response.status_code,
            "source": "KudaGo HTTP",
        }
    except httpx.RequestError as e:
        # Обработка сетевых ошибок (например, проблемы с подключением, DNS-ошибки)
        logger.error(
            f"Ошибка сети при запросе событий KudaGo для '{location}': {e}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": "Сетевая ошибка при запросе к сервису событий.",
            "source": "Network",
        }
    except Exception as e:
        # Обработка любых других непредвиденных исключений (например, ошибок парсинга JSON)
        logger.error(
            f"Непредвиденная ошибка при запросе событий KudaGo для '{location}': {e}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": "Неизвестная ошибка при получении событий.",
            "source": "Unknown",
        }
