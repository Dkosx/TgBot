from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database_postgres import (
    add_user,
    add_expense,
    get_categories_stats,
    get_today_expenses,
    get_month_expenses,
    clear_user_expenses
)
from keyboards import *
from utils import *
from config import CATEGORIES

# Состояния для ConversationHandler
AMOUNT, CATEGORY, DESCRIPTION = range(3)


async def start_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user

    # Используем новую функцию add_user
    add_user(user.id, user.username, user.first_name, user.last_name)

    welcome_text = f"""
👋 Привет, {user.first_name}!

Я помогу вам вести учет расходов.
Вот что я умею:

➕ *Добавить расход* - записать новую трату
📊 *Статистика* - посмотреть расходы по категориям
📈 *За сегодня* - расходы за текущий день
📅 *За месяц* - расходы за текущий месяц
🗑️ *Очистить все* - удалить все записи
❓ *Помощь* - показать это сообщение

Просто нажмите на кнопку внизу или используйте команды!
    """

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )


async def help_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📋 *Доступные команды:*

/start - Начать работу
/add - Добавить расход
/stats - Статистика по категориям
/today - Расходы за сегодня
/month - Расходы за месяц
/clear - Удалить все записи
/help - Эта справка

Или используйте кнопки внизу 👇
    """
    await update.message.reply_text(
        help_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )


async def add_expense_start(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса добавления расхода"""
    await update.message.reply_text(
        "💸 Введите сумму расхода (например: 1500 или 99.99):",
        reply_markup=get_back_keyboard()
    )
    return AMOUNT


async def process_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введенной суммы"""
    text = update.message.text

    if text == '↩️ Назад':
        await update.message.reply_text(
            "Действие отменено.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    is_valid, result = validate_amount(text)

    if not is_valid:
        await update.message.reply_text(result)
        return AMOUNT

    context.user_data['amount'] = result

    await update.message.reply_text(
        "📂 Выберите категорию:",
        reply_markup=get_categories_keyboard()
    )
    return CATEGORY


async def process_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбранной категории"""
    category = update.message.text

    if category == '↩️ Назад':
        await update.message.reply_text(
            "💸 Введите сумму расхода (например: 1500 или 99.99):",
            reply_markup=get_back_keyboard()
        )
        return AMOUNT

    if category not in CATEGORIES:
        await update.message.reply_text("Пожалуйста, выберите категорию из списка.")
        return CATEGORY

    context.user_data['category'] = category

    await update.message.reply_text(
        "📝 Введите описание (или нажмите 'Пропустить'):",
        reply_markup=ReplyKeyboardMarkup([['Пропустить', '↩️ Назад']], resize_keyboard=True)
    )
    return DESCRIPTION


async def process_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка описания и сохранение расхода"""
    description = update.message.text

    if description == '↩️ Назад':
        await update.message.reply_text(
            "📂 Выберите категорию:",
            reply_markup=get_categories_keyboard()
        )
        return CATEGORY

    if description == 'Пропустить':
        description = ""

    user_id = update.effective_user.id
    amount = context.user_data['amount']
    category = context.user_data['category']

    # Сохраняем в базу данных с помощью новой функции
    expense_id = add_expense(user_id, amount, category, description)

    if expense_id:
        response = f"""
✅ Расход успешно добавлен!

💵 Сумма: {format_amount(amount)}
📂 Категория: {category}
📝 Описание: {description if description else "нет"}
🕐 Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}
        """
    else:
        response = "❌ Произошла ошибка при сохранении расхода."

    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard()
    )

    # Очищаем временные данные
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=get_main_keyboard()
    )
    _context.user_data.clear()
    return ConversationHandler.END


async def show_stats(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику по категориям"""
    user_id = update.effective_user.id

    # Используем новую функцию get_categories_stats
    expenses_data = get_categories_stats(user_id, days=30)

    if not expenses_data:
        await update.message.reply_text(
            "📊 За последние 30 дней расходов нет.",
            reply_markup=get_main_keyboard()
        )
        return

    # Формат данных: [(категория, сумма, количество), ...]
    total = sum(amount for _, amount, _ in expenses_data)
    stats_text = f"📊 *Статистика за 30 дней*\n\n"

    for category, amount, count in expenses_data:
        percentage = (amount / total) * 100 if total > 0 else 0
        bar_length = int(percentage / 5)  # 5% на один символ
        bar = "█" * bar_length + "░" * (20 - bar_length)
        stats_text += f"{category} ({count} записей):\n"
        stats_text += f"{bar} {percentage:.1f}%\n"
        stats_text += f"Сумма: {format_amount(amount)}\n\n"

    stats_text += f"💰 *Общая сумма: {format_amount(total)}*"

    await update.message.reply_text(
        stats_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )


async def show_today_expenses(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Показать расходы за сегодня"""
    user_id = update.effective_user.id

    # Используем новую функцию get_today_expenses
    expenses = get_today_expenses(user_id)

    if not expenses:
        await update.message.reply_text(
            "📈 Сегодня ещё нет расходов.",
            reply_markup=get_main_keyboard()
        )
        return

    today = datetime.now().strftime('%d.%m.%Y')
    stats_text = f"📈 *Расходы за сегодня ({today})*\n\n"
    stats_text += format_expense_list(expenses)

    await update.message.reply_text(
        stats_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )


async def show_month_expenses(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Показать расходы за текущий месяц"""
    user_id = update.effective_user.id

    # Используем новую функцию get_month_expenses
    expenses = get_month_expenses(user_id)

    if not expenses:
        await update.message.reply_text(
            "📅 В этом месяце ещё нет расходов.",
            reply_markup=get_main_keyboard()
        )
        return

    month = get_current_month()
    year = datetime.now().year
    stats_text = f"📅 *Расходы за {month} {year}*\n\n"
    stats_text += format_expense_list(expenses)

    await update.message.reply_text(
        stats_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )


async def clear_expenses_start(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса очистки расходов"""
    await update.message.reply_text(
        "⚠️ *Внимание!* Это удалит ВСЕ ваши записи о расходах.\n"
        "Действие необратимо!\n\n"
        "Вы уверены, что хотите продолжить?",
        reply_markup=get_confirm_keyboard(),
        parse_mode='Markdown'
    )


async def clear_expenses_confirm(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение очистки расходов"""
    text = update.message.text

    if text == '✅ Да, удалить все':
        user_id = update.effective_user.id

        # Используем новую функцию clear_user_expenses
        deleted_count = clear_user_expenses(user_id)

        await update.message.reply_text(
            f"🗑️ Удалено {deleted_count} записей.",
            reply_markup=get_main_keyboard()
        )
    elif text == '❌ Нет, отмена':
        await update.message.reply_text(
            "Очистка отменена.",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки для ответа.",
            reply_markup=get_confirm_keyboard()
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (для кнопок)"""
    text = update.message.text

    if text == '➕ Добавить расход':
        return await add_expense_start(update, context)
    elif text == '📊 Статистика':
        return await show_stats(update, context)
    elif text == '📈 За сегодня':
        return await show_today_expenses(update, context)
    elif text == '📅 За месяц':
        return await show_month_expenses(update, context)
    elif text == '🗑️ Очистить все':
        return await clear_expenses_start(update, context)
    elif text == '❓ Помощь':
        return await help_command(update, context)
    else:
        await update.message.reply_text(
            "Используйте кнопки или команды для навигации.",
            reply_markup=get_main_keyboard()
        )
    return None