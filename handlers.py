import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database_postgres import db
from config import CATEGORIES

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
AMOUNT, CATEGORY, DESCRIPTION = range(3)


# Вспомогательные функции
def get_main_keyboard():
    """Клавиатура основного меню"""
    keyboard = [
        ['➕ Добавить расход', '📊 Статистика'],
        ['📅 Сегодня', '📈 За месяц'],
        ['🗑️ Очистить', '❓ Помощь']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_categories_keyboard():
    """Клавиатура выбора категорий"""
    # Создаем клавиатуру из категорий, по 2 в строке
    keyboard = []
    for i in range(0, len(CATEGORIES), 2):
        row = CATEGORIES[i:i + 2]
        keyboard.append(row)
    keyboard.append(['↩️ Назад'])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_confirm_keyboard():
    """Клавиатура подтверждения"""
    keyboard = [['✅ Да, удалить все', '❌ Нет, отмена']]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def validate_amount(text):
    """Проверка корректности суммы"""
    try:
        # Заменяем запятую на точку для корректного преобразования
        text = text.replace(',', '.').strip()

        # Проверяем, что текст - это число
        amount = float(text)

        if amount <= 0:
            return False, "❌ Сумма должна быть больше 0."

        # Проверяем, что не слишком много знаков после запятой
        if '.' in text:
            decimal_part = text.split('.')[1]
            if len(decimal_part) > 2:
                return False, "❌ Сумма не может содержать больше 2 знаков после запятой."

        return True, amount

    except ValueError:
        return False, "❌ Неверный формат суммы. Введите число, например: 1500 или 1500.50"


def format_amount(amount):
    """Форматирование суммы с символом рубля"""
    return f"{amount:.2f} ₽"


def get_current_month():
    """Получение названия текущего месяца"""
    months = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ]
    return months[datetime.now().month - 1]


def format_expense_list(expenses):
    """Форматирование списка расходов"""
    total = 0
    text = ""

    for expense in expenses:
        # Предполагаемая структура: (id, amount, category, description, date)
        if len(expense) >= 5:
            _, amount, category, description, date = expense[:5]
            total += amount

            time_str = date.strftime("%H:%M") if isinstance(date, datetime) else str(date)
            desc_text = f" - {description}" if description else ""

            text += f"• {format_amount(amount)} - {category}{desc_text}\n"
            text += f"  ⏰ {time_str}\n\n"
        else:
            # Если структура другая, попробуем обработать
            amount = expense[1] if len(expense) > 1 else 0
            category = expense[2] if len(expense) > 2 else "Неизвестно"
            total += amount
            text += f"• {format_amount(amount)} - {category}\n\n"

    text += f"\n💰 *Итого:* {format_amount(total)}"
    return text


async def start_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user

    # Используем новую функцию add_user
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

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
        reply_markup=ReplyKeyboardMarkup([['↩️ Назад']], resize_keyboard=True)
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
        f"✅ Сумма: {format_amount(result)}\n\n📂 Выберите категорию:",
        reply_markup=get_categories_keyboard()
    )
    return CATEGORY


async def process_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбранной категории"""
    category = update.message.text

    if category == '↩️ Назад':
        await update.message.reply_text(
            "💸 Введите сумму расхода (например: 1500 или 99.99):",
            reply_markup=ReplyKeyboardMarkup([['↩️ Назад']], resize_keyboard=True)
        )
        return AMOUNT

    if category not in CATEGORIES:
        await update.message.reply_text(
            "❌ Пожалуйста, выберите категорию из списка.",
            reply_markup=get_categories_keyboard()
        )
        return CATEGORY

    context.user_data['category'] = category

    await update.message.reply_text(
        f"✅ Категория: {category}\n\n📝 Введите описание (или нажмите 'Пропустить'):",
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
        description = None

    user_id = update.effective_user.id
    amount = context.user_data.get('amount')
    category = context.user_data.get('category')

    # Проверяем, что данные есть
    if not amount or not category:
        await update.message.reply_text(
            "❌ Ошибка: данные потеряны. Начните заново.",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Сохраняем в базу данных
    success = db.add_expense(user_id, amount, category, description)

    if success:
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


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=get_main_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END


async def show_stats(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику по категориям"""
    user_id = update.effective_user.id

    # Получаем статистику по категориям
    category_stats = db.get_expenses_by_category(user_id)

    if not category_stats:
        await update.message.reply_text(
            "📊 Ещё нет статистики. Добавьте первый расход с помощью /add",
            reply_markup=get_main_keyboard()
        )
        return

    # Рассчитываем общую сумму
    total = sum(category_stats.values())

    # Форматируем сообщение
    stats_text = "📊 *Статистика расходов*\n\n"

    for category, amount in category_stats.items():
        percentage = (amount / total * 100) if total > 0 else 0
        bar_length = int(percentage / 5)  # 5% на один символ
        bar = "█" * bar_length + "░" * (20 - bar_length)
        stats_text += f"*{category}:*\n"
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

    # Получаем расходы за сегодня
    expenses = db.get_today_expenses(user_id)

    if not expenses:
        await update.message.reply_text(
            "📈 Сегодня ещё нет расходов. Добавьте первый с помощью /add",
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

    # Получаем расходы за месяц
    expenses = db.get_month_expenses(user_id)

    if not expenses:
        await update.message.reply_text(
            "📅 В этом месяце ещё нет расходов. Добавьте первый с помощью /add",
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
    user_id = update.effective_user.id

    # Проверяем, есть ли расходы для очистки
    total = db.get_total_expenses(user_id)

    if total == 0:
        await update.message.reply_text(
            "🗑️ У вас ещё нет расходов для очистки.",
            reply_markup=get_main_keyboard()
        )
        return

    await update.message.reply_text(
        f"⚠️ *Внимание!* Это удалит ВСЕ ваши записи о расходах.\n"
        f"💰 Всего записей на сумму: {format_amount(total)}\n"
        f"Действие необратимо!\n\n"
        f"Вы уверены, что хотите продолжить?",
        reply_markup=get_confirm_keyboard(),
        parse_mode='Markdown'
    )


async def clear_expenses_confirm(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение очистки расходов"""
    text = update.message.text

    if text == '✅ Да, удалить все':
        user_id = update.effective_user.id

        # Очищаем расходы пользователя
        success = db.clear_user_expenses(user_id)

        if success:
            await update.message.reply_text(
                f"🗑️ Все расходы успешно удалены!",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Не удалось удалить расходы. Попробуйте позже.",
                reply_markup=get_main_keyboard()
            )

    elif text == '❌ Нет, отмена':
        await update.message.reply_text(
            "✅ Очистка отменена.",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки для ответа.",
            reply_markup=get_confirm_keyboard()
        )


async def handle_message(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (для кнопок)"""
    text = update.message.text

    if text == '➕ Добавить расход':
        await add_expense_start(update, _context)
    elif text == '📊 Статистика':
        await show_stats(update, _context)
    elif text == '📅 Сегодня':
        await show_today_expenses(update, _context)
    elif text == '📈 За месяц':
        await show_month_expenses(update, _context)
    elif text == '🗑️ Очистить':
        await clear_expenses_start(update, _context)
    elif text == '❓ Помощь':
        await help_command(update, _context)
    else:
        await update.message.reply_text(
            "🤔 Я не понял ваше сообщение.\n"
            "Используйте кнопки ниже или команды:\n"
            "/help - для справки",
            reply_markup=get_main_keyboard()
        )