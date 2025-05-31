"""
Модуль для взаимодействия с API OpenWeatherMap.
Предоставляет функцию для получения текущего прогноза погоды.

Этот модуль использует OpenWeatherMap API для получения актуальных данных о погоде.
Для работы требуется API ключ, который должен быть установлен в настройках приложения.

Основные возможности:
- Получение текущей погоды для указанного города
- Поддержка русского языка в ответах API
- Обработка различных типов ошибок (HTTP, сетевые, API)
- Логирование всех запросов и ошибок

Пример использования:
    weather_data = await get_weather_data("Москва")
    if weather_data and not weather_data.get("error"):
        temperature = weather_data["main"]["temp"]
        description = weather_data["weather"][0]["description"]
"""

import httpx
from typing import Optional, Dict, Any  # Для аннотаций типов
from app.config import settings  # Для доступа к API ключу OpenWeatherMap
import logging

# Настройка логгера для модуля
logger = logging.getLogger(__name__)

# Базовый URL для API OpenWeatherMap (эндпоинт для текущей погоды)
BASE_OPENWEATHERMAP_URL: str = "https://api.openweathermap.org/data/2.5/weather"


async def get_weather_data(city_name: str) -> Optional[Dict[str, Any]]:
    """
    Получает данные о текущей погоде для указанного города из API OpenWeatherMap.

    Функция выполняет асинхронный HTTP запрос к OpenWeatherMap API и возвращает
    структурированные данные о погоде. В случае ошибок возвращает словарь с
    информацией об ошибке.

    Args:
        city_name (str): Название города, для которого запрашивается погода.
                        Может быть на русском или английском языке.

    Returns:
        Optional[Dict[str, Any]]: Словарь с данными о погоде в случае успеха.
                                 Структура ответа:
                                 {
                                     "main": {
                                         "temp": float,  # Температура в Цельсиях
                                         "humidity": int # Влажность в процентах
                                     },
                                     "weather": [{
                                         "description": str,  # Описание погоды на русском
                                         "icon": str         # Код иконки
                                     }],
                                     "wind": {
                                         "speed": float  # Скорость ветра в м/с
                                     }
                                 }

                                 В случае ошибки:
                                 {
                                     "error": True,
                                     "status_code": int,  # HTTP код ошибки (если есть)
                                     "message": str       # Описание ошибки
                                 }

                                 None, если API ключ не установлен.

    Raises:
        Не выбрасывает исключений, все ошибки обрабатываются внутри функции
        и возвращаются в виде словаря с ключом "error": True.

    Note:
        - Требуется установленный WEATHER_API_KEY в настройках приложения
        - Все температуры возвращаются в градусах Цельсия
        - Описания погоды возвращаются на русском языке
    """
    # Проверяем наличие API ключа перед выполнением запроса
    if not settings.WEATHER_API_KEY:
        logger.error(
            "WEATHER_API_KEY не установлен в настройках. Невозможно получить данные о погоде."
        )
        return None

    # Параметры запроса к API OpenWeatherMap
    params: Dict[str, Any] = {
        "q": city_name,  # Название города
        "appid": settings.WEATHER_API_KEY,  # Ваш API ключ
        "units": "metric",  # Единицы измерения (metric для Цельсия)
        "lang": "ru",  # Язык ответа (русский)
    }

    try:
        # Используем асинхронный HTTP клиент httpx для выполнения запроса
        async with httpx.AsyncClient() as client:
            response = await client.get(BASE_OPENWEATHERMAP_URL, params=params)
            # Вызовет исключение httpx.HTTPStatusError для HTTP ошибок (4xx или 5xx)
            response.raise_for_status()
            weather_data = response.json()  # Парсим JSON ответ от API
            logger.info(f"Успешно получены данные о погоде для города '{city_name}'.")
            return weather_data
    except httpx.HTTPStatusError as e:
        # Обработка ошибок HTTP статуса (например, 404 Not Found, 401 Unauthorized)
        logger.error(
            f"Ошибка HTTP при запросе погоды для города '{city_name}': {e.response.status_code} - {e.response.text}",
            exc_info=True,
        )
        # Попытка извлечь более детальное сообщение об ошибке из JSON ответа API
        try:
            error_details = e.response.json()
            return {
                "error": True,
                "status_code": e.response.status_code,
                "message": error_details.get("message", e.response.text),
            }
        except Exception:  # Если ответ не является валидным JSON
            return {
                "error": True,
                "status_code": e.response.status_code,
                "message": e.response.text,
            }
    except httpx.RequestError as e:
        # Обработка сетевых ошибок (например, проблемы с подключением, DNS-ошибки)
        logger.error(
            f"Ошибка сети при запросе погоды для города '{city_name}': {e}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": "Сетевая ошибка при запросе к сервису погоды.",
        }
    except Exception as e:
        # Обработка любых других непредвиденных исключений (например, ошибок парсинга JSON)
        logger.error(
            f"Непредвиденная ошибка при запросе погоды для города '{city_name}': {e}",
            exc_info=True,
        )
        return {
            "error": True,
            "message": "Неизвестная ошибка при получении данных о погоде.",
        }
