# main.py
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher

# Импортируем настройки, базу данных и обработчики, которые создал Клод
from config import TOKEN
from database import init_db
from handlers import router

# Настройка асинхронного управления жизненным циклом сервера (lifespan)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Действия при СТАРТЕ сервера
    logging.basicConfig(level=logging.INFO)
    logging.info("Инициализация базы данных...")
    await init_db()
    
    logging.info("Запуск Telegram-бота Grand Bistro...")
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    # Очищаем старые скопившиеся сообщения, чтобы бот не спамил при включении
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем чтение сообщений (polling) бота в фоновом режиме параллельно сайту
    polling_task = asyncio.create_task(dp.start_polling(bot))
    
    yield
    
    # Действия при ОСТАНОВКЕ сервера
    logging.info("Остановка сервера и закрытие сессии бота...")
    polling_task.cancel()
    await bot.session.close()

# Инициализируем FastAPI
app = FastAPI(lifespan=lifespan)

# Эндпоинт, который будет автономно выдавать наш Mini App прямо из папки templates
@app.get("/", response_class=HTMLResponse)
async def serve_mini_app():
    html_path = Path(__file__).parent / "templates" / "index.html"
    with open(html_path, "r", encoding="utf-8") as file:
        return file.read()

# Запуск локального сервера (пригодится для тестов, хостинг Render перезапишет команду на свою)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
