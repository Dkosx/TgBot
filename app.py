import os
import json
import time
import logging
import asyncio
from typing import Optional
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler

# Импортируем обработчики из handlers.py
from handlers import (
    AMOUNT, CATEGORY, DESCRIPTION,
    start_command, help_command,
    add_expense_start, process_amount, process_category, process_description,
    cancel,
    show_stats, show_today_expenses, show_month_expenses,
    clear_expenses_start, handle_message,
    show_categories
)

from database_postgres import db

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
app = Flask(__name__)


def run_async_safe(coro):
    """Безопасный запуск асинхронной функции"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"Ошибка в асинхронной функции: {e}")
        return None


async def async_create_and_initialize_bot() -> bool:
    """Асинхронное создание и инициализация приложения бота"""
    global telegram_app

    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "your_bot_token_here":
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN не установлен")
        return False

    try:
        logger.info(f"🔄 Начинаем инициализацию бота с токеном: {TELEGRAM_TOKEN[:10]}...")

        # 1. Создаем приложение
        telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("✅ Приложение бота создано")

        # ========== КРИТИЧЕСКИ ВАЖНЫЙ ПОРЯДОК ==========

        # 1. ConversationHandler для добавления расхода - САМЫЙ ПЕРВЫЙ
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('add', add_expense_start)],
            states={
                AMOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, process_amount)
                ],
                CATEGORY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, process_category)
                ],
                DESCRIPTION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, process_description),
                    CommandHandler('skip', process_description)
                ]
            },
            fallbacks=[
                CommandHandler('cancel', cancel)
            ],
            name="add_expense",
            persistent=False,
            allow_reentry=True
        )

        telegram_app.add_handler(conv_handler)

        # 2. Обычные команды
        telegram_app.add_handler(CommandHandler("start", start_command))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CommandHandler("stats", show_stats))
        telegram_app.add_handler(CommandHandler("today", show_today_expenses))
        telegram_app.add_handler(CommandHandler("month", show_month_expenses))
        telegram_app.add_handler(CommandHandler("categories", show_categories))
        telegram_app.add_handler(CommandHandler("clear", clear_expenses_start))
        telegram_app.add_handler(CommandHandler("cancel", cancel))

        # 3. ОБЩИЙ ОБРАБОТЧИК - но ТОЛЬКО для сообщений, которые не начинаются с /
        telegram_app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^/'),
            handle_message
        ))

        # 4. ИНИЦИАЛИЗИРУЕМ приложение
        logger.info("🔄 Инициализируем приложение бота...")
        await telegram_app.initialize()
        logger.info("✅ Приложение бота инициализировано")

        logger.info("✅ Telegram бот инициализирован успешно")
        logger.info(f"✅ Тип базы данных: {type(db).__name__}")

        return True

    except Exception as bot_init_error:
        logger.error(f"❌ Ошибка инициализации бота: {bot_init_error}", exc_info=True)
        telegram_app = None
        return False


# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
telegram_app: Optional[Application] = None


def create_and_initialize_bot() -> bool:
    """Создание и инициализация приложения бота (синхронная обертка)"""
    return run_async_safe(async_create_and_initialize_bot())


# ========== WEBHOOK МАРШРУТЫ ==========
@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Обработчик вебхука от Telegram"""
    global telegram_app

    logger.info(f"📨 Получен webhook запрос, telegram_app: {telegram_app is not None}")

    if not telegram_app:
        logger.warning("⚠️ Бот не инициализирован, пытаемся инициализировать...")
        if not create_and_initialize_bot():
            logger.error("❌ Не удалось инициализировать бота для webhook")
            return 'Bot initialization failed', 500

    if db is None:
        logger.error("❌ База данных не инициализирована")
        return 'Database not initialized', 500

    if request.headers.get('Content-Type') != 'application/json':
        logger.error("❌ Неверный тип контента")
        return 'Invalid content type', 400

    try:
        data = json.loads(request.data.decode('utf-8'))
        logger.debug(f"📦 Данные webhook: {data}")

        if telegram_app is None:
            logger.error("❌ telegram_app все еще None")
            return 'Bot not initialized', 500

        update = Update.de_json(data, telegram_app.bot)
        logger.info(f"📨 Получено обновление: {update.update_id}")

        run_async_safe(telegram_app.process_update(update))
        logger.info(f"✅ Обработано обновление: {update.update_id}")
        return 'OK', 200

    except Exception as webhook_error:
        logger.error(f"❌ Ошибка webhook: {webhook_error}", exc_info=True)
        telegram_app = None
        return 'Internal error', 500


@app.route('/set_webhook', methods=['GET'])
def set_webhook_handler():
    """Установка вебхука для бота"""
    global telegram_app

    logger.info(f"🔄 Запрос на установку webhook, telegram_app: {telegram_app is not None}")

    if not telegram_app:
        logger.warning("⚠️ Бот не инициализирован, пытаемся инициализировать...")
        if not create_and_initialize_bot():
            return """
            <!DOCTYPE html>
            <html>
            <head><title>Ошибка</title></head>
            <body style="font-family: Arial; padding: 20px;">
                <h1>❌ Telegram бот не инициализирован</h1>
                <p>Проверьте TELEGRAM_BOT_TOKEN в переменных окружения</p>
                <p>Токен установлен: Да</p>
                <p>Попробуйте перезапустить приложение</p>
            </body>
            </html>
            """, 500

    try:
        webhook_url = f"https://{request.host}/webhook"
        logger.info(f"🔗 Устанавливаем webhook на URL: {webhook_url}")

        if telegram_app is None:
            return """
            <!DOCTYPE html>
            <html>
            <head><title>Ошибка</title></head>
            <body style="font-family: Arial; padding: 20px;">
                <h1>❌ Telegram бот не доступен</h1>
            </body>
            </html>
            """, 500

        result = run_async_safe(
            telegram_app.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True
            )
        )

        logger.info(f"✅ Webhook установлен: {result}")

        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Webhook Set</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>✅ Вебхук установлен</h1>
            <p><strong>URL:</strong> {webhook_url}</p>
            <p><strong>Результат:</strong> {result}</p>
            <p><strong>Статус бота:</strong> Инициализирован ✅</p>
            <p><a href="/">На главную</a></p>
        </body>
        </html>
        """

    except Exception as set_webhook_error:
        logger.error(f"❌ Ошибка установки webhook: {set_webhook_error}", exc_info=True)
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Ошибка</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>❌ Ошибка установки вебхука</h1>
            <pre>{str(set_webhook_error)}</pre>
            <p><a href="/">На главную</a></p>
        </body>
        </html>
        """, 500


@app.route('/get_webhook_info', methods=['GET'])
def get_webhook_info_handler():
    """Получение информации о вебхуке"""
    global telegram_app

    if not telegram_app:
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Ошибка</title></head>
            <body style="font-family: Arial; padding: 20px;">
            <h1>❌ Telegram бот не инициализирован</h1>
        </body>
        </html>
        """, 500

    try:
        if telegram_app is None:
            info_json = "Бот не доступен"
        else:
            info = run_async_safe(telegram_app.bot.get_webhook_info())
            info_json = json.dumps(info.to_dict(), indent=2, ensure_ascii=False)

        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Webhook Info</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>📊 Информация о вебхуке</h1>
            <pre>{info_json}</pre>
            <p><a href="/">На главную</a></p>
        </body>
        </html>
        """

    except Exception as get_webhook_error:
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Ошибка</title></head>
            <body style="font-family: Arial; padding: 20px;">
            <h1>❌ Ошибка получения информации</h1>
            <pre>{str(get_webhook_error)}</pre>
            <p><a href="/">На главную</a></p>
        </body>
        </html>
        """, 500


# ========== ПРОСТЫЕ СТРАНИЦЫ ==========
@app.route('/')
def home_handler():
    """Главная страница"""
    token_status = "✅ УСТАНОВЛЕН" if TELEGRAM_TOKEN and TELEGRAM_TOKEN != "your_bot_token_here" else "❌ ОТСУТСТВУЕТ"
    token_preview = TELEGRAM_TOKEN[
                        :10] + "..." if TELEGRAM_TOKEN and TELEGRAM_TOKEN != "your_bot_token_here" else "Не установлен"
    bot_status = "✅ ИНИЦИАЛИЗИРОВАН" if telegram_app else "❌ НЕ ИНИЦИАЛИЗИРОВАН"

    if db is None:
        db_status = "❌ НЕ ИНИЦИАЛИЗИРОВАНА"
        database_type_info = "Неизвестно"
    else:
        database_type_info = type(db).__name__
        db_status = "✅ PostgreSQL" if database_type_info == 'PostgreSQLDatabase' else "💻 SQLite"

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>🤖 TgBot - Учет расходов</title></head>
    <body style="font-family: Arial; padding: 20px;">
        <h1>🤖 TgBot - Учет расходов</h1>
        <p><strong>Telegram бот:</strong> {bot_status}</p>
        <p><strong>Токен бота:</strong> {token_status}</p>
        <p><strong>Токен (первые 10 символов):</strong> {token_preview}</p>
        <p><strong>База данных:</strong> {db_status}</p>
        <p><strong>Тип базы данных:</strong> {database_type_info}</p>
        <p><a href="/set_webhook">🔗 Установить вебхук</a></p>
        <p><a href="/healthz">🩺 Health Check</a></p>
        <hr>
        <p><small>Время: {time.strftime('%Y-%m-%d %H:%M:%S')}</small></p>
    </body>
    </html>
    """


@app.route('/healthz')
def health_check_handler():
    """Health check для Render - ОБЯЗАТЕЛЬНО ДОЛЖЕН БЫТЬ!"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "bot_initialized": bool(telegram_app),
        "database_initialized": db is not None,
        "token_configured": TELEGRAM_TOKEN is not None and TELEGRAM_TOKEN != "your_bot_token_here",
    }, 200


# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print("=" * 50)
    print("🚀 Запуск TgBot сервера")
    print(f"📌 Порт: {port}")
    print(f"🔑 TELEGRAM_TOKEN установлен: {bool(TELEGRAM_TOKEN and TELEGRAM_TOKEN != 'your_bot_token_here')}")
    print(f"🤖 Бот инициализирован: {telegram_app is not None}")
    print(f"💾 База данных: {'✅' if db else '❌'} {type(db).__name__ if db else 'Не инициализирована'}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False)