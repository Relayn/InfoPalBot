from typing import Dict

"""
Модуль для хранения констант, используемых в приложении бота.
"""

# Константы для типов информации, на которые можно подписаться
INFO_TYPE_WEATHER: str = "weather"
INFO_TYPE_NEWS: str = "news"
INFO_TYPE_EVENTS: str = "events"

# Словарь для сопоставления названий городов (в нижнем регистре) с их slug'ами для KudaGo API.
# Используется для команды /events и рассылки событий.
KUDAGO_LOCATION_SLUGS: Dict[str, str] = {
    "москва": "msk",
    "мск": "msk",
    "moscow": "msk",
    "санкт-петербург": "spb",
    "спб": "spb",
    "питер": "spb",
    "saint petersburg": "spb",
    "новосибирск": "nsk",
    "нск": "nsk",
    "екатеринбург": "ekb",
    "екб": "ekb",
    "казань": "kzn",
    "нижний новгород": "nnv",
    # Добавьте другие города по мере необходимости, если KudaGo их поддерживает
}