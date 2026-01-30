import os
import json
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


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
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

        # ========== КРИТИЧЕСКИ ВАЖНО: УПРОЩЕННЫЙ ПОРЯДОК ==========

        # 1. Сначала ConversationHandler - САМЫЙ ВАЖНЫЙ
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

        # Добавляем ConversationHandler ПЕРВЫМ
        telegram_app.add_handler(conv_handler)

        # 2. Затем ВСЕ обычные команды
        telegram_app.add_handler(CommandHandler("start", start_command))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CommandHandler("stats", show_stats))
        telegram_app.add_handler(CommandHandler("today", show_today_expenses))
        telegram_app.add_handler(CommandHandler("month", show_month_expenses))
        telegram_app.add_handler(CommandHandler("categories", show_categories))
        telegram_app.add_handler(CommandHandler("clear", clear_expenses_start))

        # 3. Обработчик /cancel отдельно (должен быть ПОСЛЕ ConversationHandler)
        telegram_app.add_handler(CommandHandler("cancel", cancel))

        # 4. ОБЩИЙ обработчик сообщений - только для случайных текстов
        # Фильтр: ТОЛЬКО текст, НЕ команда, НЕ начинается с /
        telegram_app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))

        # 5. ИНИЦИАЛИЗИРУЕМ приложение
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


# Остальной код оставляем БЕЗ ИЗМЕНЕНИЙ...
# [webhook handlers, routes и т.д. из предыдущего кода]

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


# [ВСТАВЬТЕ СЮДА ВЕСЬ ОСТАЛЬНОЙ КОД ИЗ ПРЕДЫДУЩЕГО ФАЙЛА app.py]
# set_webhook_handler, get_webhook_info_handler, home_handler, health_check_handler
# и все остальные маршруты оставьте БЕЗ ИЗМЕНЕНИЙ

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