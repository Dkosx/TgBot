import logging
from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler
from config import CATEGORIES
from database_postgres import db

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
AMOUNT, CATEGORY, DESCRIPTION = range(3)


# ========== БАЗОВЫЕ КОМАНДЫ ==========
async def start_command(update: Update, context: CallbackContext) -> int:
    """Обработчик команды /start"""
    user = update.effective_user
    logger.info(f"User {user.id} started the bot")

    # Очищаем контекст
    context.user_data.clear()

    # Добавляем пользователя в базу
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code
    )

    welcome_text = f"""
    👋 Привет, {user.first_name}!

    🤖 Я бот для учёта расходов.

    📌 **Доступные команды:**
    /add - Добавить расход
    /today - Расходы за сегодня
    /month - Расходы за месяц
    /stats - Статистика по категориям
    /categories - Список категорий
    /clear - Очистить все расходы
    /help - Помощь

    💡 **Совет:** Используйте меню команд для удобства!
    """

    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def help_command(update: Update, _context: CallbackContext) -> int:
    """Команда помощи /help"""
    help_text = """
    📚 **Справка по командам:**

    **Основные команды:**
    /add - Добавить новый расход
    /today - Показать расходы за сегодня
    /month - Показать расходы за текущий месяц
    /stats - Статистика по категориям
    /categories - Показать все категории расходов
    /clear - Удалить все расходы (с подтверждением)

    **Процесс добавления расхода:**
    1. Напишите `/add`
    2. Введите сумму (например: 1500 или 1500.50)
    3. Выберите категорию из списка
    4. Добавьте описание (необязательно, /skip для пропуска)

    💡 **Все команды доступны в меню бота!**
    """

    await update.message.reply_text(
        help_text,
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def show_categories(update: Update, _context: CallbackContext) -> int:
    """Показать все категории - команда /categories"""
    categories_text = "📋 **Доступные категории расходов:**\n\n"
    categories_text += "\n".join([f"• {cat}" for cat in CATEGORIES])
    categories_text += "\n\n💡 Используйте эти категории при добавлении расходов."

    await update.message.reply_text(
        categories_text,
        parse_mode='Markdown'
    )
    return ConversationHandler.END


# ========== ДИАЛОГ ДОБАВЛЕНИЯ РАСХОДА ==========
async def add_expense_start(update: Update, context: CallbackContext) -> int:
    """Начало добавления расхода - команда /add"""
    logger.info(f"User {update.effective_user.id} starting to add expense")

    # Очищаем данные предыдущего диалога
    context.user_data.clear()

    await update.message.reply_text(
        "💸 **Введите сумму расхода:**\n"
        "Например: 1500 или 1500.50\n\n"
        "Для отмены напишите /cancel",
        parse_mode='Markdown'
    )
    return AMOUNT


async def process_amount(update: Update, context: CallbackContext) -> int:
    """Обработка суммы"""
    text = update.message.text.strip()

    try:
        amount = float(text.replace(',', '.'))

        if amount <= 0:
            await update.message.reply_text(
                "❌ Сумма должна быть больше 0. Введите сумму еще раз:\n"
                "Для отмены напишите /cancel"
            )
            return AMOUNT

        if amount > 1000000000:  # 1 миллиард
            await update.message.reply_text(
                "❌ Сумма слишком большая. Проверьте правильность ввода.\n"
                "Для отмены напишите /cancel"
            )
            return AMOUNT

        # Сохраняем сумму
        context.user_data['amount'] = amount

        # Показываем категории в виде простого списка
        categories_text = "📋 **Выберите категорию:**\n\n"
        categories_text += "\n".join([f"• {cat}" for cat in CATEGORIES])
        categories_text += "\n\n✏️ **Напишите название категории из списка выше**\nДля отмены напишите /cancel"

        await update.message.reply_text(
            f"✅ Сумма: {amount:.2f} руб.\n\n{categories_text}",
            parse_mode='Markdown'
        )
        return CATEGORY

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат. Введите число, например: 1500 или 1500.50\n"
            "Для отмены напишите /cancel"
        )
        return AMOUNT


async def process_category(update: Update, context: CallbackContext) -> int:
    """Обработка выбора категории"""
    text = update.message.text.strip()

    # Проверка на валидную категорию
    if text not in CATEGORIES:
        await update.message.reply_text(
            "❌ Пожалуйста, введите название категории из списка:\n\n" +
            "\n".join([f"• {cat}" for cat in CATEGORIES]) +
            "\n\nДля отмены напишите /cancel"
        )
        return CATEGORY

    # Сохраняем категорию
    context.user_data['category'] = text

    await update.message.reply_text(
        f"✅ Категория: {text}\n\n"
        "📝 **Введите описание (необязательно):**\n"
        "Напишите описание или /skip чтобы пропустить\n"
        "Для отмены напишите /cancel",
        parse_mode='Markdown'
    )
    return DESCRIPTION


async def process_description(update: Update, context: CallbackContext) -> int:
    """Обработка описания"""
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # Пропуск описания
    if text == '/skip':
        text = None

    # Получаем сохраненные данные
    amount = context.user_data.get('amount')
    category = context.user_data.get('category')

    if not amount or not category:
        await update.message.reply_text(
            "❌ Ошибка: данные потеряны. Начните заново командой /add",
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Сохраняем в БД
    success = db.add_expense(
        user_id=user_id,
        amount=amount,
        category=category,
        description=text
    )

    if success:
        response = (
            f"✅ **Расход добавлен!**\n\n"
            f"💰 Сумма: {amount:.2f} руб.\n"
            f"📂 Категория: {category}\n"
        )
        if text:
            response += f"📝 Описание: {text}\n"

        response += "\n💡 Используйте другие команды для управления расходами."
    else:
        response = "❌ Ошибка сохранения. Попробуйте позже."

    # Очищаем данные
    context.user_data.clear()

    await update.message.reply_text(
        response,
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена диалога - команда /cancel"""
    context.user_data.clear()
    await update.message.reply_text(
        "🚫 Операция отменена.\n"
        "Используйте /help для просмотра доступных команд."
    )
    return ConversationHandler.END


# ========== КОМАНДЫ ПРОСМОТРА ==========
async def show_today_expenses(update: Update, _context: CallbackContext) -> int:
    """Расходы за сегодня - команда /today"""
    user_id = update.effective_user.id
    expenses = db.get_today_expenses(user_id)

    if not expenses:
        await update.message.reply_text(
            "📅 **Сегодня еще нет расходов.**\n"
            "Добавьте первый расход командой /add",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    total = sum(exp[1] for exp in expenses)
    message = "📅 **Расходы за сегодня:**\n\n"

    for exp in expenses:
        amount, category, description, date = exp[1], exp[2], exp[3], exp[4]
        time_str = date.strftime("%H:%M")
        message += f"• **{amount:.2f} руб.** - {category}\n"
        if description:
            message += f"  📝 {description}\n"
        message += f"  ⏰ {time_str}\n\n"

    message += f"💰 **Итого: {total:.2f} руб.**"

    await update.message.reply_text(
        message,
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def show_month_expenses(update: Update, _context: CallbackContext) -> int:
    """Расходы за месяц - команда /month"""
    user_id = update.effective_user.id
    expenses = db.get_month_expenses(user_id)

    if not expenses:
        await update.message.reply_text(
            "📈 **В этом месяце еще нет расходов.**\n"
            "Добавьте первый расход командой /add",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    total = sum(exp[1] for exp in expenses)
    message = "📈 **Расходы за текущий месяц:**\n\n"

    for exp in expenses:
        amount, category, description, date = exp[1], exp[2], exp[3], exp[4]
        date_str = date.strftime("%d.%m")
        message += f"• **{amount:.2f} руб.** - {category}\n"
        if description:
            message += f"  📝 {description}\n"
        message += f"  📅 {date_str}\n\n"

    message += f"💰 **Итого: {total:.2f} руб.**"

    await update.message.reply_text(
        message,
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def show_stats(update: Update, _context: CallbackContext) -> int:
    """Статистика - команда /stats"""
    user_id = update.effective_user.id
    stats = db.get_expenses_by_category(user_id)
    total = db.get_total_expenses(user_id)

    if not stats:
        await update.message.reply_text(
            "📊 **Еще нет статистики.**\n"
            "Добавьте расходы командой /add для просмотра статистики.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    message = "📊 **Статистика расходов:**\n\n"

    for category, amount in stats.items():
        percentage = (amount / total * 100) if total > 0 else 0
        message += f"• **{category}:** {amount:.2f} руб. ({percentage:.1f}%)\n"

    message += f"\n💰 **Общая сумма: {total:.2f} руб.**"

    await update.message.reply_text(
        message,
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def clear_expenses_start(update: Update, context: CallbackContext) -> int:
    """Начало очистки - команда /clear"""
    user_id = update.effective_user.id
    total = db.get_total_expenses(user_id)

    if total == 0:
        await update.message.reply_text(
            "🗑️ **Нет расходов для очистки.**",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"⚠️ **Удалить ВСЕ расходы?**\n\n"
        f"Всего на сумму: {total:.2f} руб.\n\n"
        f"❌ **Действие необратимо!**\n\n"
        f"Напишите **ДА** для подтверждения или /cancel для отмены.",
        parse_mode='Markdown'
    )

    # Устанавливаем флаг в контексте
    context.user_data['clearing'] = True
    return ConversationHandler.END


async def handle_clear_confirmation(update: Update, context: CallbackContext) -> int:
    """Обработка подтверждения очистки"""
    text = update.message.text.strip().upper()

    if text == 'ДА':
        user_id = update.effective_user.id
        success = db.clear_user_expenses(user_id)

        if success:
            await update.message.reply_text(
                "✅ **Все расходы удалены!**\n"
                "Используйте /add для добавления новых расходов.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка удаления расходов.",
            )
    else:
        await update.message.reply_text(
            "✅ Очистка отменена.\n"
            "Данные сохранены.",
        )

    # Очищаем флаг
    if 'clearing' in context.user_data:
        del context.user_data['clearing']

    return ConversationHandler.END


# ========== ПРОСТОЙ ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: CallbackContext) -> int:
    """Обработка текстовых сообщений (для очистки и случайных сообщений)"""
    text = update.message.text.strip().upper()

    # Обработка подтверждения очистки
    if context.user_data.get('clearing') and text == 'ДА':
        return await handle_clear_confirmation(update, context)

    # Если начат процесс очистки, но введено не "ДА"
    if context.user_data.get('clearing'):
        await update.message.reply_text(
            "⚠️ Напишите **ДА** для подтверждения очистки или /cancel для отмены."
        )
        return ConversationHandler.END

    # Для всех других сообщений - показываем подсказку
    await update.message.reply_text(
        "🤖 Используйте команды для работы с ботом:\n"
        "/start - Запустить бота\n"
        "/help - Помощь по командам\n"
        "/add - Добавить расход\n"
        "/today - Расходы за сегодня\n"
        "/month - Расходы за месяц\n"
        "/stats - Статистика\n"
        "/categories - Список категорий\n"
        "/clear - Очистить расходы"
    )
    return ConversationHandler.END