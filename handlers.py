import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from config import CATEGORIES
from database_postgres import db

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler - ДОБАВЛЕН CONFIRM_STATE
AMOUNT, CATEGORY, DESCRIPTION, CONFIRM_STATE = range(4)


# Базовая клавиатура
def get_main_keyboard():
    keyboard = [
        ['➕ Добавить расход', '📊 Статистика'],
        ['📅 Сегодня', '📈 За месяц'],
        ['🗑️ Очистить', '❓ Помощь']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# Клавиатура для выбора категории
def get_categories_keyboard():
    categories = CATEGORIES
    keyboard = []
    for i in range(0, len(categories), 2):
        row = categories[i:i + 2]
        keyboard.append(row)
    keyboard.append(['↩️ Назад'])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


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

    📌 Используйте кнопки ниже для управления расходами.
    """

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def help_command(update: Update, _context: CallbackContext) -> int:
    """Команда помощи /help"""
    help_text = """
    📚 **Справка:**

    **Как добавить расход:**
    1. Нажмите "➕ Добавить расход"
    2. Введите сумму (например: 1500 или 1500.50)
    3. Выберите категорию из списка
    4. Добавьте описание (необязательно)

    **Другие функции:**
    • 📊 Статистика - статистика по категориям
    • 📅 Сегодня - расходы за сегодня
    • 📈 За месяц - расходы за текущий месяц
    • 🗑️ Очистить - удалить все расходы

    💡 **Совет:** Используйте кнопки внизу для быстрого доступа!
    """

    await update.message.reply_text(
        help_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


# ========== ПРОСТОЙ ДИАЛОГ ДОБАВЛЕНИЯ РАСХОДА ==========
async def add_expense_start(update: Update, context: CallbackContext) -> int:
    """Начало добавления расхода"""
    logger.info(f"User {update.effective_user.id} starting to add expense")

    # Очищаем данные предыдущего диалога
    context.user_data.clear()

    await update.message.reply_text(
        "💸 **Введите сумму расхода:**\n"
        "Например: 1500 или 1500.50",
        reply_markup=ReplyKeyboardRemove(),
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
                "❌ Сумма должна быть больше 0. Введите сумму еще раз:"
            )
            return AMOUNT

        # Сохраняем сумму
        context.user_data['amount'] = amount

        await update.message.reply_text(
            f"✅ Сумма: {amount:.2f} руб.\n\n"
            "📋 **Выберите категорию:**",
            reply_markup=get_categories_keyboard(),
            parse_mode='Markdown'
        )
        return CATEGORY

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат. Введите число, например: 1500 или 1500.50"
        )
        return AMOUNT


async def process_category(update: Update, context: CallbackContext) -> int:
    """Обработка выбора категории"""
    category = update.message.text.strip()

    # Проверка на отмену
    if category == '↩️ Назад':
        context.user_data.clear()
        await update.message.reply_text(
            "🚫 Добавление расхода отменено.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    # Проверка на валидную категорию
    if category not in CATEGORIES:
        await update.message.reply_text(
            "❌ Пожалуйста, выберите категорию из списка:",
            reply_markup=get_categories_keyboard()
        )
        return CATEGORY

    # Сохраняем категорию
    context.user_data['category'] = category

    await update.message.reply_text(
        f"✅ Категория: {category}\n\n"
        "📝 **Введите описание (необязательно):**\n"
        "Или напишите /skip чтобы пропустить",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    return DESCRIPTION


async def process_description(update: Update, context: CallbackContext) -> int:
    """Обработка описания"""
    description = update.message.text.strip()
    user_id = update.effective_user.id

    # Пропуск описания
    if description == '/skip':
        description = None

    # Получаем сохраненные данные
    amount = context.user_data.get('amount')
    category = context.user_data.get('category')

    if not amount or not category:
        await update.message.reply_text(
            "❌ Ошибка: данные потеряны. Начните заново.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    # Сохраняем в БД
    success = db.add_expense(
        user_id=user_id,
        amount=amount,
        category=category,
        description=description
    )

    if success:
        response = (
            f"✅ **Расход добавлен!**\n\n"
            f"💰 Сумма: {amount:.2f} руб.\n"
            f"📂 Категория: {category}\n"
        )
        if description:
            response += f"📝 Описание: {description}\n"
    else:
        response = "❌ Ошибка сохранения. Попробуйте позже."

    # Очищаем данные
    context.user_data.clear()

    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def skip_description(update: Update, context: CallbackContext) -> int:
    """Пропуск описания"""
    return await process_description(update, context)


async def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена диалога"""
    context.user_data.clear()
    await update.message.reply_text(
        "🚫 Операция отменена.",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END


# ========== КОМАНДЫ ПРОСМОТРА ==========
async def show_today_expenses(update: Update, _context: CallbackContext) -> int:
    """Расходы за сегодня"""
    user_id = update.effective_user.id
    expenses = db.get_today_expenses(user_id)

    if not expenses:
        await update.message.reply_text(
            "📅 **Сегодня еще нет расходов.**\n"
            "Добавьте первый расход с помощью ➕ Добавить расход",
            reply_markup=get_main_keyboard(),
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
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def show_month_expenses(update: Update, _context: CallbackContext) -> int:
    """Расходы за месяц"""
    user_id = update.effective_user.id
    expenses = db.get_month_expenses(user_id)

    if not expenses:
        await update.message.reply_text(
            "📈 **В этом месяце еще нет расходов.**\n"
            "Добавьте первый расход с помощью ➕ Добавить расход",
            reply_markup=get_main_keyboard(),
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
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def show_stats(update: Update, _context: CallbackContext) -> int:
    """Статистика"""
    user_id = update.effective_user.id
    stats = db.get_expenses_by_category(user_id)
    total = db.get_total_expenses(user_id)

    if not stats:
        await update.message.reply_text(
            "📊 **Еще нет статистики.**\n"
            "Добавьте расходы для просмотра статистики.",
            reply_markup=get_main_keyboard(),
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
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def clear_expenses_start(update: Update, context: CallbackContext) -> int:
    """Начало очистки"""
    user_id = update.effective_user.id
    total = db.get_total_expenses(user_id)

    if total == 0:
        await update.message.reply_text(
            "🗑️ **Нет расходов для очистки.**",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Создаем простую клавиатуру подтверждения
    keyboard = [['✅ Да, удалить все', '❌ Нет, отмена']]

    await update.message.reply_text(
        f"⚠️ **Удалить ВСЕ расходы?**\n\n"
        f"Всего на сумму: {total:.2f} руб.\n\n"
        f"❌ **Действие необратимо!**",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
        parse_mode='Markdown'
    )

    # Устанавливаем флаг в контексте
    context.user_data['clearing'] = True
    return CONFIRM_STATE


async def handle_clear_confirmation(update: Update, context: CallbackContext) -> int:
    """Обработка подтверждения очистки"""
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if text == '❌ Нет, отмена':
        await update.message.reply_text(
            "✅ Очистка отменена.",
            reply_markup=get_main_keyboard()
        )
    elif text == '✅ Да, удалить все':
        success = db.clear_user_expenses(user_id)

        if success:
            await update.message.reply_text(
                "✅ **Все расходы удалены!**",
                reply_markup=get_main_keyboard(),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка удаления расходов.",
                reply_markup=get_main_keyboard()
            )

    # Очищаем флаг
    if 'clearing' in context.user_data:
        del context.user_data['clearing']

    return ConversationHandler.END


async def clear_expenses_confirm(update: Update, context: CallbackContext) -> int:
    """Алиас для handle_clear_confirmation"""
    return await handle_clear_confirmation(update, context)


async def show_categories(update: Update, _context: CallbackContext) -> int:
    """Показать категории"""
    categories_text = "📋 **Доступные категории:**\n\n" + "\n".join(
        [f"• {cat}" for cat in CATEGORIES]
    )

    await update.message.reply_text(
        categories_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


# ========== УПРОЩЕННЫЙ ОБРАБОТЧИК КНОПОК ==========
async def handle_message(update: Update, context: CallbackContext) -> int:
    """Обработка текстовых сообщений и кнопок"""
    text = update.message.text

    # Обработка подтверждения очистки
    if text in ['✅ Да, удалить все', '❌ Нет, отмена']:
        return await handle_clear_confirmation(update, context)

    # Обработка основных кнопок
    if text == '➕ Добавить расход':
        return await add_expense_start(update, context)
    elif text == '📊 Статистика':
        return await show_stats(update, context)
    elif text == '📅 Сегодня':
        return await show_today_expenses(update, context)
    elif text == '📈 За месяц':
        return await show_month_expenses(update, context)
    elif text == '🗑️ Очистить':
        return await clear_expenses_start(update, context)
    elif text == '❓ Помощь':
        return await help_command(update, context)

    # Если не распознано - игнорируем
    return ConversationHandler.END