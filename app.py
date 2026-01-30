import os
import json
import time
import logging
import asyncio
import atexit
from typing import Optional
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler

# Импортируем обработчики из handlers.py
from handlers import (
    AMOUNT, CATEGORY, DESCRIPTION,
    start_command, help_command,
    add_expense_start, process_amount, process_category, process_description,
    cancel,
    show_stats, show_today_expenses, show_month_expenses,
    clear_expenses_start,
    show_categories,
  # для отладки если нужно
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

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
telegram_app: Optional[Application] = None


def run_async_safe(coro):
    """Безопасный запуск асинхронной функции"""
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
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
        return False

    try:
        logger.info("🔄 Создаем приложение бота...")

        # 1. Создаем приложение
        telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("✅ Приложение бота создано")

        # ========== СНАЧАЛА CONVERSATIONHANDLER ==========

        # ConversationHandler для добавления расхода
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('add', add_expense_start)],
            states={
                AMOUNT: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        process_amount
                    )
                ],
                CATEGORY: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        process_category
                    )
                ],
                DESCRIPTION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        process_description
                    ),
                    # Команда "skip" как текст, а не как команда
                    MessageHandler(
                        filters.Regex(r'^(skip|пропустить|без описания)$') & ~filters.COMMAND,
                        process_description
                    )
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
        logger.info("✅ ConversationHandler добавлен")

        # ========== ЗАТЕМ ОСТАЛЬНЫЕ КОМАНДЫ ==========

        # ОСНОВНЫЕ КОМАНДЫ
        telegram_app.add_handler(CommandHandler("start", start_command))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CommandHandler("categories", show_categories))

        # КОМАНДЫ ПРОСМОТРА
        telegram_app.add_handler(CommandHandler("today", show_today_expenses))
        telegram_app.add_handler(CommandHandler("month", show_month_expenses))
        telegram_app.add_handler(CommandHandler("stats", show_stats))

        # КОМАНДА ОЧИСТКИ
        telegram_app.add_handler(CommandHandler("clear", clear_expenses_start))

        # НЕ ДОБАВЛЯЕМ CommandHandler("cancel", cancel) - он уже в fallbacks!

        # ========== ДЛЯ ОТЛАДКИ (опционально) ==========
        # Раскомментируйте если нужно видеть все сообщения:
        # telegram_app.add_handler(MessageHandler(
        #     filters.TEXT & ~filters.COMMAND,
        #     echo_debug
        # ))

        logger.info("✅ Все обработчики добавлены")

        # Инициализируем приложение
        await telegram_app.initialize()
        logger.info("✅ Приложение бота инициализировано")

        return True

    except Exception as bot_init_error:
        logger.error(f"❌ Ошибка инициализации бота: {bot_init_error}", exc_info=True)
        telegram_app = None
        return False


def create_and_initialize_bot() -> bool:
    """Создание и инициализация приложения бота (синхронная обертка)"""
    return run_async_safe(async_create_and_initialize_bot())


# ========== WEBHOOK МАРШРУТЫ ==========

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Обработчик вебхука от Telegram"""

    if telegram_app is None:
        logger.error("❌ Бот не инициализирован!")
        return 'Bot not initialized', 500

    if request.headers.get('Content-Type') != 'application/json':
        logger.error("❌ Неверный тип контента")
        return 'Invalid content type', 400

    try:
        data = json.loads(request.data.decode('utf-8'))
        update = Update.de_json(data, telegram_app.bot)

        # Логируем входящее сообщение
        if update.message:
            user_id = update.effective_user.id
            text = update.message.text or "(без текста)"
            logger.info(f"📨 [{user_id}]: '{text}'")

        # Обрабатываем обновление
        run_async_safe(telegram_app.process_update(update))
        return 'OK', 200

    except Exception as webhook_error:
        logger.error(f"❌ Ошибка webhook: {webhook_error}", exc_info=True)
        return 'Internal error', 500


@app.route('/set_webhook', methods=['GET'])
def set_webhook_handler():
    """Установка вебхука для бота"""

    if telegram_app is None:
        return """
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; padding: 20px;">
            <h1>❌ Telegram бот не инициализирован</h1>
            <p>Перезапустите приложение</p>
        </body>
        </html>
        """, 500

    try:
        webhook_url = f"https://{request.host}/webhook"
        logger.info(f"🔗 Устанавливаем webhook на {webhook_url}")

        # 1. Удаляем старый вебхук с очисткой кеша
        delete_result = run_async_safe(
            telegram_app.bot.delete_webhook(drop_pending_updates=True)
        )
        logger.info(f"🗑️  Старый webhook удален: {delete_result}")

        # 2. Удаляем команды меню
        run_async_safe(telegram_app.bot.delete_my_commands())
        logger.info("🗑️  Команды меню удалены")

        # 3. Устанавливаем новый вебхук
        set_result = run_async_safe(
            telegram_app.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"]
            )
        )
        logger.info(f"✅ Новый webhook установлен: {set_result}")

        # 4. Даем время Telegram обновиться
        time.sleep(2)

        return f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; padding: 20px;">
            <h1>✅ Вебхук установлен!</h1>
            <p><strong>URL:</strong> {webhook_url}</p>
            <p><strong>Старый кеш очищен:</strong> Да</p>
            <p><strong>Команды удалены:</strong> Да</p>
            <p><a href="/">На главную</a> | <a href="tg://resolve?domain=YOUR_BOT_USERNAME">Открыть бота</a></p>
            <hr>
            <p>Теперь отправьте /start боту в Telegram</p>
        </body>
        </html>
        """

    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")
        return f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; padding: 20px;">
            <h1>❌ Ошибка установки вебхука</h1>
            <pre>{str(e)}</pre>
        </body>
        </html>
        """, 500


@app.route('/delete_webhook', methods=['GET'])
def delete_webhook_handler():
    """Удаление вебхука (для сброса)"""
    if telegram_app is None:
        return "Бот не инициализирован", 500

    try:
        result = run_async_safe(
            telegram_app.bot.delete_webhook(drop_pending_updates=True)
        )
        return f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; padding: 20px;">
            <h1>🗑️ Вебхук удален</h1>
            <p><strong>Результат:</strong> {result}</p>
            <p><a href="/set_webhook">Установить вебхук заново</a></p>
        </body>
        </html>
        """
    except Exception as e:
        return f"Ошибка: {e}", 500


@app.route('/')
def home_handler():
    """Главная страница"""
    token_set = bool(TELEGRAM_TOKEN and TELEGRAM_TOKEN != "your_bot_token_here")
    token_preview = TELEGRAM_TOKEN[:10] + "..." if token_set else "Не установлен"
    bot_status = "✅ ИНИЦИАЛИЗИРОВАН" if telegram_app else "❌ НЕ ИНИЦИАЛИЗИРОВАН"
    db_status = "✅ ПОДКЛЮЧЕНА" if db else "❌ НЕ ПОДКЛЮЧЕНА"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 TgBot - Учет расходов</title>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; max-width: 800px; margin: 0 auto; }}
            h1 {{ color: #333; }}
            .status {{ padding: 10px; margin: 10px 0; border-radius: 5px; }}
            .ok {{ background-color: #d4edda; color: #155724; }}
            .error {{ background-color: #f8d7da; color: #721c24; }}
            .actions {{ margin: 20px 0; }}
            .actions a {{ display: inline-block; margin-right: 10px; padding: 10px 15px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
            .actions a:hover {{ background: #0056b3; }}
        </style>
    </head>
    <body>
        <h1>🤖 TgBot - Учет расходов</h1>

        <div class="status {'ok' if telegram_app else 'error'}">
            <strong>Статус бота:</strong> {bot_status}
        </div>

        <div class="status {'ok' if token_set else 'error'}">
            <strong>Токен:</strong> {token_preview}
        </div>

        <div class="status {'ok' if db else 'error'}">
            <strong>База данных:</strong> {db_status}
        </div>

        <hr>

        <div class="actions">
            <a href="/set_webhook">🔗 Установить вебхук (очистить кеш)</a>
            <a href="/delete_webhook">🗑️ Удалить вебхук</a>
            <a href="/healthz">🩺 Health Check</a>
        </div>

        <hr>

        <h3>Инструкция:</h3>
        <ol>
            <li>Нажмите "Установить вебхук" для очистки кеша Telegram</li>
            <li>Откройте бота в Telegram и отправьте /start</li>
            <li>Используйте /add для добавления расходов</li>
        </ol>

        <hr>

        <p><small>Время: {time.strftime('%Y-%m-%d %H:%M:%S')} | <a href="https://render.com" target="_blank">Render</a></small></p>
    </body>
    </html>
    """


@app.route('/healthz')
def health_check_handler():
    """Health check для Render - ВАЖНЫЙ МАРШРУТ!"""
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "telegram-expense-bot",
        "bot_initialized": bool(telegram_app),
        "database_initialized": db is not None,
        "token_configured": TELEGRAM_TOKEN is not None and TELEGRAM_TOKEN != "your_bot_token_here",
        "version": "1.0.0",
        "uptime": time.time() - start_time if 'start_time' in globals() else 0
    }

    # Определяем общий статус
    if health_status["bot_initialized"] and health_status["database_initialized"] and health_status["token_configured"]:
        health_status["overall"] = "healthy"
        status_code = 200
    else:
        health_status["overall"] = "degraded"
        health_status["message"] = "Некоторые компоненты не инициализированы"
        status_code = 503

    return jsonify(health_status), status_code


# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
start_time = time.time()


@atexit.register
def cleanup():
    """Очистка при завершении"""
    if telegram_app:
        logger.info("🧹 Очистка ресурсов бота...")
        run_async_safe(telegram_app.shutdown())


if __name__ == '__main__':
    logger.info("🚀 Запуск TgBot сервера...")

    # Инициализируем бота
    logger.info("🔄 Инициализация бота...")
    success = create_and_initialize_bot()

    if not success:
        logger.error("❌ Не удалось инициализировать бота!")
        exit(1)

    logger.info("✅ Бот успешно инициализирован")

    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Запуск Flask на порту {port}")

    print("=" * 50)
    print("🚀 TgBot запущен!")
    print(f"📌 Порт: {port}")
    print(f"🤖 Бот: {'✅' if telegram_app else '❌'}")
    print(f"🗄️  БД: {'✅' if db else '❌'}")
    print(f"🔗 Webhook: https://your-app.onrender.com/set_webhook")
    print(f"🩺 Health check: https://your-app.onrender.com/healthz")
    print("=" * 50)

    app.run(host='0.0.0.0', port=port, debug=False)