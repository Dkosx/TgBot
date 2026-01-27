import os
import sys
import time
from threading import Thread
from flask import Flask
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def run_simple_bot():
    """Простой запуск бота без сложной асинхронной логики"""
    while True:
        try:
            print(f"[{time.strftime('%H:%M:%S')}] 🤖 Инициализация бота...")

            # Добавляем путь для импортов
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))

            # Импортируем ваш оригинальный бот
            from main import main

            print(f"[{time.strftime('%H:%M:%S')}] 🚀 Запускаю основную функцию...")
            main()  # Просто запускаем вашу функцию из main.py

        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] ❌ Ошибка: {e}")
            print(f"[{time.strftime('%H:%M:%S')}] 🔄 Перезапуск через 10 секунд...")
            time.sleep(10)


@app.route('/')
@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 TgBot</title>  # ← ИЗМЕНИЛИ ЗДЕСЬ
        <meta charset="utf-8">
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: linear-gradient(to right, #4CAF50, #2196F3);
                color: white;
            }
            .container {
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
                max-width: 600px;
                margin: 0 auto;
            }
            h1 { font-size: 2.5em; margin-bottom: 10px; }
            .status {
                background: #4CAF50;
                padding: 10px 20px;
                border-radius: 20px;
                display: inline-block;
                margin: 20px 0;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 TgBot</h1>  # ← ИЗМЕНИЛИ ЗДЕСЬ
            <div class="status">✅ РАБОТАЕТ</div>
            <p>Бот для учета расходов запущен и работает 24/7</p>
            <p>👉 Найти в Telegram: @ваш_бот</p>
            <p>Команды: /start, /add, /stats, /help</p>
            <hr>
            <div style="margin-top: 20px;">
                <a href="/health" style="color: white; margin: 0 10px;">Health Check</a>
                <a href="/ping" style="color: white; margin: 0 10px;">Ping</a>
                <a href="/status" style="color: white; margin: 0 10px;">Status</a>
            </div>
            <p style="margin-top: 20px;"><small>Размещено на Render.com</small></p>
        </div>
    </body>
    </html>
    """


@app.route('/health')
def health():
    return {"status": "healthy", "timestamp": time.time()}


@app.route('/ping')
def ping():
    return "pong"


@app.route('/status')
def status():
    return {
        "service": "telegram-finance-bot",
        "status": "running",
        "uptime": time.time() - app_start_time,
        "version": "1.0.0"
    }


if __name__ == '__main__':
    # Запоминаем время старта
    app_start_time = time.time()

    # Запускаем бота в отдельном потоке
    print("=" * 50)
    print("🚀 ЗАПУСК СИСТЕМЫ")
    print("=" * 50)

    bot_thread = Thread(target=run_simple_bot, daemon=True)
    bot_thread.start()
    print("✅ Бот запущен в фоновом режиме")

    # Запускаем веб-сервер
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Веб-сервер запущен на порту {port}")
    print(f"📡 Откройте: http://localhost:{port}")
    print("=" * 50)

    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)