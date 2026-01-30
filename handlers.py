import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from config import CATEGORIES
from database_postgres import db

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
AMOUNT, CATEGORY, DESCRIPTION = range(3)
CONFIRM_STATE = 10  # Числовое состояние для подтверждения очистки


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
    # Разбиваем категории на строки по 2-3 штуки
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

    # Используем context для очистки данных
    context.user_data.clear()

    # Добавляем пользователя в базу
    try:
        db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code
        )
    except Exception as e:
        logger.error(f"Error adding user to DB: {e}")

    welcome_text = f"""
    👋 Привет, {user.first_name}!

    🤖 Я бот для учёта расходов.

    📌 **Доступные команды:**
    • Используйте кнопки ниже для быстрого доступа
    • Или команды: /add, /today, /month, /stats, /clear

    🚀 Начните с добавления расхода!
    """

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def help_command(update: Update, context: CallbackContext) -> int:
    """Команда помощи /help"""
    user_id = update.effective_user.id
    logger.info(f"Help command from user {user_id}")

    # Используем context для логирования данных
    logger.info(f"Context user data: {context.user_data}")

    help_text = """
    📚 **Справка по командам:**

    **Основные команды:**
    /start - Запустить бота
    /help - Показать эту справку

    **Управление расходами:**
    /add - Добавить новый расход
    /today - Показать расходы за сегодня
    /month - Показать расходы за текущий месяц
    /stats - Статистика по категориям
    /categories - Список всех категорий
    /clear - Удалить все расходы

    **Как добавить расход:**
    1. Нажмите "➕ Добавить расход"
    2. Введите сумму (например: 1500 или 1500.50)
    3. Выберите категорию из списка
    4. Добавьте описание (необязательно)

    💡 **Совет:** Используйте кнопки внизу для быстрого доступа к функциям!
    """

    await update.message.reply_text(
        help_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


# ========== КОМАНДЫ РАСХОДОВ ==========
async def add_expense_start(update: Update, context: CallbackContext) -> int:
    """Начало добавления расхода"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} starting to add expense")

    # Очищаем user_data при начале диалога
    context.user_data.clear()
    # Сохраняем информацию о начале диалога
    context.user_data['adding_expense'] = True

    await update.message.reply_text(
        "💸 **Введите сумму расхода:**\n"
        "Например: 1500 или 1500.50",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )

    return AMOUNT


async def process_amount(update: Update, context: CallbackContext) -> int:
    """Обработка введенной суммы"""
    user_id = update.effective_user.id
    text = update.message.text

    try:
        # Пробуем преобразовать в число
        amount = float(text.replace(',', '.'))

        if amount <= 0:
            await update.message.reply_text(
                "❌ Сумма должна быть больше 0. Попробуйте еще раз:"
            )
            return AMOUNT

        # Сохраняем сумму в контексте
        context.user_data['amount'] = amount
        # Сохраняем состояние
        context.user_data['conversation_state'] = 'amount_processed'

        logger.info(f"User {user_id} entered amount: {amount}")

        await update.message.reply_text(
            f"✅ Сумма: {amount:.2f} руб.\n\n"
            "📋 **Теперь выберите категорию:**",
            reply_markup=get_categories_keyboard(),
            parse_mode='Markdown'
        )

        return CATEGORY

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат суммы. Введите число, например: 1500 или 1500.50"
        )
        return AMOUNT


async def process_category(update: Update, context: CallbackContext) -> int:
    """Обработка выбранной категории"""
    user_id = update.effective_user.id
    category = update.message.text

    # Проверяем, что категория из списка
    if category not in CATEGORIES and category != '↩️ Назад':
        await update.message.reply_text(
            "❌ Пожалуйста, выберите категорию из списка ниже:",
            reply_markup=get_categories_keyboard()
        )
        return CATEGORY

    if category == '↩️ Назад':
        await update.message.reply_text(
            "🚫 Добавление расхода отменено.",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Сохраняем категорию
    context.user_data['category'] = category
    # Сохраняем состояние
    context.user_data['conversation_state'] = 'category_selected'

    logger.info(f"User {user_id} selected category: {category}")

    await update.message.reply_text(
        f"✅ Категория: {category}\n\n"
        "📝 **Введите описание (необязательно):**\n"
        "Нажмите /skip чтобы пропустить",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )

    return DESCRIPTION


async def process_description(update: Update, context: CallbackContext) -> int:
    """Обработка описания"""
    user_id = update.effective_user.id
    description = update.message.text

    # Пропускаем, если это команда skip
    if description == '/skip':
        return await skip_description(update, context)

    # Получаем сохраненные данные
    amount = context.user_data.get('amount')
    category = context.user_data.get('category')

    if not amount or not category:
        await update.message.reply_text(
            "❌ Ошибка: данные потеряны. Начните заново.",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Сохраняем расход в базу
    try:
        success = db.add_expense(
            user_id=user_id,
            amount=amount,
            category=category,
            description=description
        )
    except Exception as e:
        logger.error(f"Error adding expense: {e}")
        success = False

    if success:
        response_text = (
            f"✅ **Расход успешно добавлен!**\n\n"
            f"💰 Сумма: {amount:.2f} руб.\n"
            f"📂 Категория: {category}\n"
        )
        if description:
            response_text += f"📝 Описание: {description}\n"

        response_text += "\n📊 Используйте /stats чтобы увидеть статистику."

    else:
        response_text = "❌ Не удалось сохранить расход. Попробуйте позже."

    # Очищаем временные данные
    context.user_data.clear()

    await update.message.reply_text(
        response_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

    return ConversationHandler.END


async def skip_description(update: Update, context: CallbackContext) -> int:
    """Пропуск описания"""
    user_id = update.effective_user.id

    amount = context.user_data.get('amount')
    category = context.user_data.get('category')

    if not amount or not category:
        await update.message.reply_text(
            "❌ Ошибка: данные потеряны. Начните заново.",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Сохраняем расход без описания
    try:
        success = db.add_expense(
            user_id=user_id,
            amount=amount,
            category=category,
            description=None
        )
    except Exception as e:
        logger.error(f"Error adding expense: {e}")
        success = False

    if success:
        response_text = (
            f"✅ **Расход успешно добавлен!**\n\n"
            f"💰 Сумма: {amount:.2f} руб.\n"
            f"📂 Категория: {category}\n\n"
            f"📊 Используйте /stats чтобы увидеть статистику."
        )
    else:
        response_text = "❌ Не удалось сохранить расход. Попробуйте позже."

    # Очищаем временные данные
    context.user_data.clear()

    await update.message.reply_text(
        response_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

    return ConversationHandler.END


async def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена добавления расхода"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} cancelled adding expense")

    # Очищаем временные данные
    context.user_data.clear()

    await update.message.reply_text(
        "🚫 Добавление расхода отменено.",
        reply_markup=get_main_keyboard()
    )

    return ConversationHandler.END


# ========== КОМАНДЫ ДЛЯ ПРОСМОТРА ==========
async def show_today_expenses(update: Update, context: CallbackContext) -> int:
    """Показать расходы за сегодня"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested today's expenses")

    # Используем context для логирования состояния
    logger.info(f"Context data for today expenses: {context.user_data}")

    try:
        expenses = db.get_today_expenses(user_id)
    except Exception as e:
        logger.error(f"Error getting today expenses: {e}")
        await update.message.reply_text(
            "❌ Ошибка получения данных. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    if not expenses:
        await update.message.reply_text(
            "📅 **Сегодня ещё нет расходов.**\n\n"
            "Начните с добавления расхода с помощью /add",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Формируем сообщение
    total = 0
    message = "📅 **Расходы за сегодня:**\n\n"

    for exp in expenses:
        exp_id, amount, category, description, date = exp
        total += amount
        time_str = date.strftime("%H:%M")

        message += f"• **{amount:.2f} руб.** - {category}\n"
        if description:
            message += f"  📝 {description}\n"
        message += f"  ⏰ {time_str}\n\n"

    message += f"💰 **Итого за день:** {total:.2f} руб."

    await update.message.reply_text(
        message,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def show_month_expenses(update: Update, context: CallbackContext) -> int:
    """Показать расходы за текущий месяц"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested month's expenses")

    # Используем context для логирования
    logger.info(f"Month expenses context: {context.user_data}")

    try:
        expenses = db.get_month_expenses(user_id)
    except Exception as e:
        logger.error(f"Error getting month expenses: {e}")
        await update.message.reply_text(
            "❌ Ошибка получения данных. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    if not expenses:
        await update.message.reply_text(
            "📈 **В этом месяце ещё нет расходов.**\n\n"
            "Начните с добавления расхода с помощью /add",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Формируем сообщение
    total = 0
    message = "📈 **Расходы за текущий месяц:**\n\n"

    for exp in expenses:
        exp_id, amount, category, description, date = exp
        total += amount
        date_str = date.strftime("%d.%m")

        message += f"• **{amount:.2f} руб.** - {category}\n"
        if description:
            message += f"  📝 {description}\n"
        message += f"  📅 {date_str}\n\n"

    message += f"💰 **Итого за месяц:** {total:.2f} руб."

    await update.message.reply_text(
        message,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def show_stats(update: Update, context: CallbackContext) -> int:
    """Показать статистику по категориям"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested statistics")

    # Используем context для логирования
    logger.info(f"Stats context data: {context.user_data}")

    try:
        category_stats = db.get_expenses_by_category(user_id)
        total_expenses = db.get_total_expenses(user_id)
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        await update.message.reply_text(
            "❌ Ошибка получения данных. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    if not category_stats:
        await update.message.reply_text(
            "📊 **Ещё нет статистики.**\n\n"
            "Начните с добавления расхода с помощью /add",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Формируем сообщение
    message = "📊 **Статистика расходов:**\n\n"

    for category, amount in category_stats.items():
        percentage = (amount / total_expenses * 100) if total_expenses > 0 else 0
        message += f"• **{category}:** {amount:.2f} руб. ({percentage:.1f}%)\n"

    message += f"\n💰 **Общая сумма:** {total_expenses:.2f} руб."

    await update.message.reply_text(
        message,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def show_categories(update: Update, context: CallbackContext) -> int:
    """Показать список категорий"""
    user_id = update.effective_user.id
    logger.info(f"Categories command from user {user_id}")

    # Используем context для логирования
    logger.info(f"Categories context: {context.user_data}")

    categories_text = "📋 **Доступные категории:**\n" + "\n".join(f"• {cat}" for cat in CATEGORIES)
    await update.message.reply_text(
        categories_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


# ========== ОЧИСТКА РАСХОДОВ ==========
async def clear_expenses_start(update: Update, context: CallbackContext) -> int:
    """Начало очистки расходов"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} starting to clear expenses")

    # Используем context для отслеживания состояния
    context.user_data['clearing_expenses'] = True

    try:
        total = db.get_total_expenses(user_id)
    except Exception as e:
        logger.error(f"Error getting total expenses: {e}")
        await update.message.reply_text(
            "❌ Ошибка получения данных. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    if total == 0:
        context.user_data.clear()
        await update.message.reply_text(
            "🗑️ **У вас ещё нет расходов для очистки.**",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    keyboard = [['✅ Да, удалить все', '❌ Нет, отмена']]

    await update.message.reply_text(
        f"⚠️ **Вы уверены, что хотите удалить ВСЕ расходы?**\n\n"
        f"💰 Всего записей на сумму: {total:.2f} руб.\n\n"
        f"❌ **Это действие нельзя отменить!**",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

    return CONFIRM_STATE


async def clear_expenses_confirm(update: Update, context: CallbackContext) -> int:
    """Подтверждение очистки расходов"""
    user_id = update.effective_user.id
    choice = update.message.text

    if choice == '❌ Нет, отмена':
        context.user_data.clear()
        await update.message.reply_text(
            "✅ Очистка отменена.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    elif choice == '✅ Да, удалить все':
        try:
            success = db.clear_user_expenses(user_id)
        except Exception as e:
            logger.error(f"Error clearing expenses: {e}")
            success = False

        context.user_data.clear()

        if success:
            await update.message.reply_text(
                "✅ **Все расходы успешно удалены!**",
                reply_markup=get_main_keyboard(),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ Не удалось удалить расходы. Попробуйте позже.",
                reply_markup=get_main_keyboard()
            )

        return ConversationHandler.END

    else:
        await update.message.reply_text(
            "❌ Пожалуйста, используйте кнопки для подтверждения.",
            reply_markup=get_main_keyboard()
        )
        return CONFIRM_STATE


# ========== УПРОЩЕННЫЙ ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: CallbackContext) -> int:
    """Обработка текстовых сообщений (для кнопок)"""
    text = update.message.text
    user_id = update.effective_user.id

    logger.info(f"User {user_id} sent text: {text}")
    # Используем context для логирования
    logger.info(f"handle_message context data: {context.user_data}")

    # Если это команда (начинается с /), пропускаем - команды обрабатываются отдельно
    if text.startswith('/'):
        return ConversationHandler.END

    # Обрабатываем нажатия на кнопки главного меню
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

    else:
        # Если сообщение не распознано как команда и пользователь не в ConversationHandler
        # Просто игнорируем или показываем основную клавиатуру
        return ConversationHandler.END