import os
import json
import time
import logging
import asyncio
from typing import Optional
from flask import Flask, request
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
from config import CATEGORIES, COMMANDS

# Импортируем обработчики из handlers.py
from handlers import (
    AMOUNT, CATEGORY, DESCRIPTION,
    start_command, help_command,
    add_expense_start, process_amount, process_category, process_description, cancel,
    show_stats, show_today_expenses, show_month_expenses,
    clear_expenses_start, clear_expenses_confirm, handle_message
)

# Импортируем базу данных из database_postgres.py
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

# Глобальная переменная для бота с аннотацией типа
telegram_app: Optional[Application] = None
bot_is_initialized_flag = False  # Флаг инициализации бота


# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
def init_bot() -> bool:
    """Инициализация Telegram бота"""
    global telegram_app, bot_is_initialized_flag

    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "your_bot_token_here":
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN не установлен")
        return False

    try:
        telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

        # ========== НАСТРОЙКА ОБРАБОТЧИКОВ ==========
        # ConversationHandler для добавления расхода
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('add', add_expense_start),
                MessageHandler(filters.Text(['➕ Добавить расход']), add_expense_start)
            ],
            states={
                AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_amount)],
                CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_category)],
                DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_description)]
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                MessageHandler(filters.Text(['↩️ Назад', 'Отмена', 'cancel']), cancel)
            ]
        )

        # Добавляем ConversationHandler первым
        telegram_app.add_handler(conv_handler)

        # Остальные обработчики команд из handlers.py
        telegram_app.add_handler(CommandHandler("start", start_command))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CommandHandler("stats", show_stats))
        telegram_app.add_handler(CommandHandler("today", show_today_expenses))
        telegram_app.add_handler(CommandHandler("month", show_month_expenses))
        telegram_app.add_handler(CommandHandler("clear", clear_expenses_start))

        # Обработчик команды /categories
        async def categories_command(update: Update, _context: CallbackContext) -> None:
            """Обработчик команды /categories"""
            categories_text = "📋 Доступные категории:\n" + "\n".join(
                f"• {cat}" for cat in CATEGORIES
            )
            await update.message.reply_text(categories_text)
            logger.info(f"Categories requested by {update.effective_user.id}")

        telegram_app.add_handler(CommandHandler("categories", categories_command))

        # Обработчик кнопок подтверждения очистки
        telegram_app.add_handler(MessageHandler(
            filters.Text(['✅ Да, удалить все', '❌ Нет, отмена']),
            clear_expenses_confirm
        ))

        # Обработчик текстовых сообщений (для кнопок главного меню)
        telegram_app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND &
            ~filters.Text(['✅ Да, удалить все', '❌ Нет, отмена']),
            handle_message
        ))

        # Настройка меню команд бота
        async def set_bot_commands():
            commands_list = [BotCommand(cmd, desc) for cmd, desc in COMMANDS]
            await telegram_app.bot.set_my_commands(commands_list)

        # Выполняем настройку
        setup_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(setup_loop)
        try:
            setup_loop.run_until_complete(set_bot_commands())
            logger.info("✅ Меню команд бота настроено")
        finally:
            setup_loop.close()

        # ✅ ИНИЦИАЛИЗИРУЕМ приложение сразу при старте
        try:
            init_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(init_loop)
            init_loop.run_until_complete(telegram_app.initialize())
            init_loop.close()
            bot_is_initialized_flag = True
            logger.info("✅ Telegram приложение инициализировано")
        except Exception as init_error:
            logger.error(f"❌ Ошибка инициализации приложения: {init_error}")
            telegram_app = None
            bot_is_initialized_flag = False
            return False

        logger.info(f"✅ Telegram бот инициализирован успешно")
        logger.info(f"✅ Тип базы данных: {type(db).__name__}")

        return True

    except Exception as bot_init_error:
        logger.error(f"❌ Ошибка инициализации бота: {bot_init_error}")
        telegram_app = None
        bot_is_initialized_flag = False
        return False


# Инициализируем бота при запуске
bot_initialized = init_bot()


def ensure_bot_initialized() -> bool:
    """
    Убедиться, что Telegram приложение инициализировано.
    На Render при перезагрузке приложение может потерять состояние.
    """
    global telegram_app, bot_is_initialized_flag

    if telegram_app is None:
        logger.error("❌ Telegram приложение не создано")
        return reinitialize_bot()

    if not bot_is_initialized_flag:
        logger.warning("⚠️ Приложение не инициализировано, переинициализируем")
        return reinitialize_bot()

    return True


def reinitialize_bot() -> bool:
    """Переинициализировать бота"""
    global telegram_app, bot_is_initialized_flag

    try:
        if telegram_app is None:
            return init_bot()

        # Пытаемся инициализировать существующее приложение
        init_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(init_loop)
        try:
            init_loop.run_until_complete(telegram_app.initialize())
        finally:
            init_loop.close()

        bot_is_initialized_flag = True
        logger.info("✅ Приложение переинициализировано")
        return True

    except (RuntimeError, ConnectionError, asyncio.TimeoutError) as e:
        logger.error(f"❌ Ошибка переинициализации: {e}")

        # Пробуем создать приложение заново
        try:
            telegram_app = None
            bot_is_initialized_flag = False
            return init_bot()
        except Exception as reinit_error:
            logger.error(f"❌ Критическая ошибка переинициализации: {reinit_error}")
            return False


# ========== WEBHOOK РОУТЫ ==========
@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Обработчик вебхука от Telegram"""
    global bot_is_initialized_flag

    # ✅ Убедимся, что бот инициализирован перед обработкой
    if not ensure_bot_initialized():
        logger.error("❌ Не удалось инициализировать бота")
        return 'Bot not initialized', 500

    if db is None:
        logger.error("❌ База данных не инициализирована")
        return 'Database not initialized', 500

    if request.headers.get('Content-Type') != 'application/json':
        logger.error("❌ Неверный тип контента")
        return 'Invalid content type', 400

    try:
        data = json.loads(request.data.decode('utf-8'))
        update = Update.de_json(data, telegram_app.bot)
        logger.info(f"📨 Получено обновление: {update.update_id}")

        # Создаем новую event loop для обработки обновления
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Двойная проверка инициализации
            if not bot_is_initialized_flag:
                logger.warning("⚠️ Бот не инициализирован в webhook, инициализируем...")
                loop.run_until_complete(telegram_app.initialize())
                bot_is_initialized_flag = True
                logger.info("✅ Бот инициализирован в webhook")

            # Обрабатываем обновление
            loop.run_until_complete(telegram_app.process_update(update))
            logger.info(f"✅ Обработано обновление: {update.update_id}")
            return 'OK', 200

        except RuntimeError as init_error:
            if "not initialized" in str(init_error):
                logger.warning("⚠️ Приложение требует инициализации, инициализируем...")
                loop.run_until_complete(telegram_app.initialize())
                bot_is_initialized_flag = True
                # Пробуем еще раз
                loop.run_until_complete(telegram_app.process_update(update))
                logger.info(f"✅ Обработано обновление после инициализации: {update.update_id}")
                return 'OK', 200
            else:
                logger.error(f"❌ RuntimeError в webhook: {init_error}")
                raise init_error
        except Exception as process_error:
            logger.error(f"❌ Ошибка обработки обновления: {process_error}")
            raise process_error
        finally:
            loop.close()

    except (json.JSONDecodeError, KeyError, ValueError) as parse_error:
        logger.error(f"❌ Ошибка парсинга JSON: {parse_error}")
        return 'Invalid JSON data', 400
    except (ConnectionError, asyncio.TimeoutError) as connection_error:
        logger.error(f"❌ Ошибка соединения: {connection_error}")
        return 'Connection error', 502
    except Exception as webhook_error:
        logger.error(f"❌ Ошибка webhook: {webhook_error}", exc_info=True)
        return f'Internal error: {str(webhook_error)}', 500


@app.route('/set_webhook', methods=['GET'])
def set_webhook_handler():
    """Установка вебхука для бота"""
    if not ensure_bot_initialized():
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Ошибка</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>❌ Telegram бот не инициализирован</h1>
            <p>Добавьте переменную окружения в .env файл:</p>
            <p><strong>TELEGRAM_BOT_TOKEN = ваш_токен_бота</strong></p>
            <p><a href="/">На главную</a></p>
        </body>
        </html>
        """

    try:
        webhook_url = f"https://{request.host}/webhook"

        set_webhook_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(set_webhook_loop)
        result = set_webhook_loop.run_until_complete(
            telegram_app.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True
            )
        )
        set_webhook_loop.close()

        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Webhook Set</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>✅ Вебхук установлен</h1>
            <p><strong>URL:</strong> {webhook_url}</p>
            <p><strong>Результат:</strong> {result}</p>
            <p><a href="/">На главную</a> | <a href="/get_webhook_info">Информация</a></p>
        </body>
        </html>
        """
    except Exception as set_webhook_error:
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
    if not ensure_bot_initialized():
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Ошибка</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>❌ Telegram бот не инициализирован</h1>
            <p>Требуется TELEGRAM_BOT_TOKEN</p>
            <p><a href="/">На главную</a></p>
        </body>
        </html>
        """

    try:
        webhook_info_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(webhook_info_loop)
        info = webhook_info_loop.run_until_complete(telegram_app.bot.get_webhook_info())
        webhook_info_loop.close()

        info_json = json.dumps(info.to_dict(), indent=2, ensure_ascii=False)

        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Webhook Info</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>📊 Информация о вебхуке</h1>
            <pre>{info_json}</pre>
            <p><a href="/">На главную</a> | <a href="/set_webhook">Установить</a></p>
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


@app.route('/database_info', methods=['GET'])
def database_info_handler():
    """Информация о базе данных"""
    if db is None:
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Ошибка</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>❌ База данных не инициализирована</h1>
            <p><a href="/">На главную</a></p>
        </body>
        </html>
        """, 500

    try:
        if hasattr(db, 'get_database_info'):
            info = db.get_database_info()
        else:
            info = {
                "type": type(db).__name__,
                "status": "connected" if hasattr(db, 'conn') and db.conn else "unknown"
            }

        info_json = json.dumps(info, indent=2, ensure_ascii=False, default=str)

        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Database Info</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>🗃️ Информация о базе данных</h1>
            <p><strong>Тип базы:</strong> {type(db).__name__}</p>
            <pre>{info_json}</pre>
            <p><a href="/">На главную</a></p>
        </body>
        </html>
        """
    except Exception as db_error:
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Ошибка</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>❌ Ошибка получения информации о БД</h1>
            <pre>{str(db_error)}</pre>
            <p><a href="/">На главную</a></p>
        </body>
        </html>
        """, 500


# ========== ГЛАВНАЯ СТРАНИЦА ==========
@app.route('/')
def home_handler():
    """Главная страница"""
    # Используем уникальное имя для локальной переменной
    bot_initialized_status = ensure_bot_initialized()
    bot_status = "✅ ИНИЦИАЛИЗИРОВАН" if bot_initialized_status else "❌ НЕ НАСТРОЕН"
    token_status = "✅ УСТАНОВЛЕН" if TELEGRAM_TOKEN and TELEGRAM_TOKEN != "your_bot_token_here" else "❌ ОТСУТСТВУЕТ"

    if db is None:
        db_status = "❌ НЕ ИНИЦИАЛИЗИРОВАНА"
        database_type = "Неизвестно"
    else:
        database_type = type(db).__name__
        if database_type == 'PostgreSQLDatabase':
            db_status = "✅ PostgreSQL"
        elif database_type == 'Database':
            db_status = "💻 SQLite"
        else:
            db_status = f"✅ {database_type}"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 TgBot - Учет расходов</title>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                padding: 20px;
                background: #f5f5f5;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .status {{ 
                padding: 10px; 
                margin: 10px 0; 
                border-radius: 5px;
                font-weight: bold;
            }}
            .status-good {{ background: #d4edda; color: #155724; }}
            .status-bad {{ background: #f8d7da; color: #721c24; }}
            .status-info {{ background: #d1ecf1; color: #0c5460; }}
            .btn {{
                display: inline-block;
                margin: 10px 5px;
                padding: 10px 20px;
                background: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
            }}
            .btn:hover {{ background: #0056b3; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 TgBot - Учет расходов</h1>

            <div class="status {'status-good' if bot_initialized_status else 'status-bad'}">
                Telegram бот: {bot_status}
            </div>

            <div class="status {'status-good' if TELEGRAM_TOKEN and TELEGRAM_TOKEN != 'your_bot_token_here' else 'status-bad'}">
                Токен бота: {token_status}
            </div>

            <div class="status status-info">
                База данных: {db_status} ({database_type})
            </div>

            <div style="margin: 30px 0;">
                <a href="/set_webhook" class="btn">🔗 Установить вебхук</a>
                <a href="/get_webhook_info" class="btn">📊 Информация о вебхуке</a>
                <a href="/database_info" class="btn">🗃️ Информация о БД</a>
                <a href="/healthz" class="btn">🩺 Health Check</a>
            </div>

            <p>Текущая база данных: <strong>{database_type}</strong></p>
            <p>Данные сохраняются {'на PostgreSQL' if database_type == 'PostgreSQLDatabase' else 'в памяти (SQLite)'}</p>
        </div>
    </body>
    </html>
    """


@app.route('/healthz')
def health_check_handler():
    """Health check для Render"""
    # Используем уникальное имя для локальной переменной
    bot_health_status = ensure_bot_initialized()
    return {
        "status": "healthy" if bot_health_status else "unhealthy",
        "service": "telegram-bot",
        "timestamp": time.time(),
        "bot_initialized": bot_health_status,
        "database": type(db).__name__ if db else None,
        "bot_is_initialized_flag": bot_is_initialized_flag
    }, 200 if bot_health_status else 503


# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))

    print("=" * 60)
    print("🚀 Запуск TgBot Webhook сервера")
    print("=" * 60)
    print(f"Порт: {port}")

    # Используем уникальное имя для локальной переменной
    bot_initialization_status = ensure_bot_initialized()
    print(f"Telegram Bot: {'✅ Инициализирован' if bot_initialization_status else '❌ Не настроен'}")

    print(f"Token: {'✅ Установлен' if TELEGRAM_TOKEN else '❌ Отсутствует'}")

    if db is not None:
        print(f"Database: ✅ {type(db).__name__}")
    else:
        print(f"Database: ❌ Не инициализирована")

    print("=" * 60)

    app.run(host='0.0.0.0', port=port, debug=False)