# config.py
# Конфигурация проекта. Значения берутся из переменных окружения (на Render
# их задают в разделе Environment), а если переменной нет, используется заглушка.

import os

# Токен бота от @BotFather
TOKEN = "8835589329:AAHaCjR4OSjz4PrsR0uKM83Nz5iF5pVHg_U"

# Telegram ID администратора (получает карточки новых заказов)
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

# Путь к файлу SQLite.
# На Render для сохранности данных задайте DB_PATH=/var/data/restaurant.db
# (путь на подключённом Persistent Disk).
DB_PATH = os.getenv("DB_PATH", "restaurant.db")

# Публичный адрес приложения. Render сам задаёт RENDER_EXTERNAL_URL
# после деплоя (сразу с https://), локально используется localhost.
WEB_APP_URL = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")