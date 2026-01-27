import os
from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters
)
from handlers import *

# Загрузка переменных окружения
load_dotenv()

# Получение токена из переменных окружения
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')


def main():
    """Основная функция запуска бота"""

    # Создаем приложение
    application = ApplicationBuilder().token(TOKEN).build()

    # НАСТРОЙКА КОМАНД БОТА - ЯВНЫЙ СПОСОБ
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("add", add_expense_start))  # ← Исправлено!
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("today", show_today_expenses))
    application.add_handler(CommandHandler("month", show_month_expenses))
    application.add_handler(CommandHandler("clear", clear_expenses_start))
    application.add_handler(CommandHandler("help", help_command))

    # ConversationHandler для добавления расходов
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('add', add_expense_start),
            MessageHandler(filters.Regex('^➕ Добавить расход$'), add_expense_start)
        ],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_amount)],
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_category)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_description)]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(filters.Regex('^↩️ Назад$'), cancel)
        ]
    )

    application.add_handler(conv_handler)

    # Обработка кнопки очистки расходов
    application.add_handler(MessageHandler(
        filters.Regex('^(✅ Да, удалить все|❌ Нет, отмена)$'),
        clear_expenses_confirm
    ))

    # Обработка остальных текстовых сообщений
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))

    # Запуск бота
    print("🤖 Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()