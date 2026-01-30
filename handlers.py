import logging
from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler
from config import CATEGORIES
from database_postgres import db

logger = logging.getLogger(__name__)
AMOUNT, CATEGORY, DESCRIPTION = range(3)


async def start_command(update: Update, context: CallbackContext) -> int:
    """Обработчик команды /start"""
    user = update.effective_user
    context.user_data.clear()

    db.add_user(user.id, user.username, user.first_name, user.last_name, user.language_code)

    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "🤖 Я бот для учёта расходов.\n\n"
        "📌 **Команды:**\n"
        "/add - Добавить расход\n"
        "/today - Расходы за сегодня\n"
        "/month - Расходы за месяц\n"
        "/stats - Статистика\n"
        "/categories - Категории\n"
        "/clear - Очистить\n"
        "/help - Помощь",
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def help_command(update: Update, context: CallbackContext) -> int:
    """Команда помощи /help"""
    context.user_data.clear()
    await update.message.reply_text(
        "📚 **Справка:**\n\n"
        "/add - Добавить расход\n"
        "/today - Расходы за сегодня\n"
        "/month - Расходы за месяц\n"
        "/stats - Статистика\n"
        "/categories - Категории\n"
        "/clear - Очистить\n"
        "/cancel - Отмена",
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def show_categories(update: Update, context: CallbackContext) -> int:
    """Показать все категории"""
    context.user_data.clear()
    categories = "\n".join([f"• {cat}" for cat in CATEGORIES])
    await update.message.reply_text(
        f"📋 **Категории:**\n\n{categories}",
        parse_mode='Markdown'
    )
    return ConversationHandler.END


# ========== ДИАЛОГ ДОБАВЛЕНИЯ РАСХОДА ==========
async def add_expense_start(update: Update, context: CallbackContext) -> int:
    """Начало добавления расхода"""
    logger.info(f"Начало добавления расхода для пользователя {update.effective_user.id}")
    context.user_data.clear()

    await update.message.reply_text(
        "💸 **Введите сумму расхода:**\n"
        "Например: 1500 или 1500.50\n\n"
        "/cancel для отмены",
        parse_mode='Markdown'
    )
    return AMOUNT


async def process_amount(update: Update, context: CallbackContext) -> int:
    """Обработка суммы"""
    try:
        amount = float(update.message.text.replace(',', '.'))

        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0. Введите снова:")
            return AMOUNT

        context.user_data['amount'] = amount
        logger.info(f"Сумма сохранена: {amount}")

        # Показываем категории
        categories_text = "📋 **Выберите категорию:**\n\n"
        categories_text += "\n".join([f"• {cat}" for cat in CATEGORIES])
        categories_text += "\n\n✏️ **Введите название категории из списка выше**"

        await update.message.reply_text(
            f"✅ Сумма: {amount:.2f} руб.\n\n{categories_text}",
            parse_mode='Markdown'
        )
        return CATEGORY

    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Введите число:")
        return AMOUNT


async def process_category(update: Update, context: CallbackContext) -> int:
    """Обработка выбора категории"""
    text = update.message.text.strip()
    logger.info(f"Получена категория: '{text}'")

    # Проверяем, что это не команда
    if text.startswith('/'):
        return CATEGORY

    if text in CATEGORIES:
        context.user_data['category'] = text
        logger.info(f"Категория сохранена: {text}")

        await update.message.reply_text(
            f"✅ Категория: {text}\n\n"
            "📝 **Введите описание (необязательно):**\n"
            "Напишите описание или /skip чтобы пропустить\n"
            "/cancel для отмены",
            parse_mode='Markdown'
        )
        return DESCRIPTION
    else:
        categories = "\n".join([f"• {cat}" for cat in CATEGORIES])
        await update.message.reply_text(
            f"❌ Категория не найдена.\n\n**Доступные категории:**\n{categories}\n"
            "Введите категорию точно как в списке:",
            parse_mode='Markdown'
        )
        return CATEGORY


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
        await update.message.reply_text("❌ Ошибка: данные потеряны.")
        context.user_data.clear()
        return ConversationHandler.END

    # Сохраняем в БД
    success = db.add_expense(user_id, amount, category, text)

    if success:
        response = f"✅ **Расход добавлен!**\n\n💰 {amount:.2f} руб. - {category}"
        if text:
            response += f"\n📝 {text}"
        logger.info(f"Расход добавлен для пользователя {user_id}")
    else:
        response = "❌ Ошибка сохранения"
        logger.error(f"Ошибка сохранения для пользователя {user_id}")

    context.user_data.clear()
    await update.message.reply_text(response, parse_mode='Markdown')
    return ConversationHandler.END


async def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена диалога"""
    logger.info(f"Отмена пользователем {update.effective_user.id}")
    context.user_data.clear()
    await update.message.reply_text("🚫 Операция отменена.")
    return ConversationHandler.END


# ========== КОМАНДЫ ПРОСМОТРА ==========
async def show_today_expenses(update: Update, context: CallbackContext) -> int:
    """Расходы за сегодня"""
    context.user_data.clear()
    user_id = update.effective_user.id
    expenses = db.get_today_expenses(user_id)

    if not expenses:
        await update.message.reply_text("📅 **Сегодня нет расходов.**")
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

    await update.message.reply_text(message, parse_mode='Markdown')
    return ConversationHandler.END


async def show_month_expenses(update: Update, context: CallbackContext) -> int:
    """Расходы за месяц"""
    context.user_data.clear()
    user_id = update.effective_user.id
    expenses = db.get_month_expenses(user_id)

    if not expenses:
        await update.message.reply_text("📈 **В этом месяце нет расходов.**")
        return ConversationHandler.END

    total = sum(exp[1] for exp in expenses)
    message = "📈 **Расходы за месяц:**\n\n"

    for exp in expenses:
        amount, category, description, date = exp[1], exp[2], exp[3], exp[4]
        date_str = date.strftime("%d.%m")
        message += f"• **{amount:.2f} руб.** - {category}\n"
        if description:
            message += f"  📝 {description}\n"
        message += f"  📅 {date_str}\n\n"

    message += f"💰 **Итого: {total:.2f} руб.**"

    await update.message.reply_text(message, parse_mode='Markdown')
    return ConversationHandler.END


async def show_stats(update: Update, context: CallbackContext) -> int:
    """Статистика"""
    context.user_data.clear()
    user_id = update.effective_user.id
    stats = db.get_expenses_by_category(user_id)
    total = db.get_total_expenses(user_id)

    if not stats:
        await update.message.reply_text("📊 **Нет статистики.**")
        return ConversationHandler.END

    message = "📊 **Статистика:**\n\n"

    for category, amount in stats.items():
        percentage = (amount / total * 100) if total > 0 else 0
        message += f"• **{category}:** {amount:.2f} руб. ({percentage:.1f}%)\n"

    message += f"\n💰 **Всего: {total:.2f} руб.**"

    await update.message.reply_text(message, parse_mode='Markdown')
    return ConversationHandler.END


async def clear_expenses_start(update: Update, context: CallbackContext) -> int:
    """Начало очистки"""
    context.user_data.clear()
    user_id = update.effective_user.id
    total = db.get_total_expenses(user_id)

    if total == 0:
        await update.message.reply_text("🗑️ **Нет расходов для очистки.**")
        return ConversationHandler.END

    await update.message.reply_text(
        f"⚠️ **Удалить ВСЕ расходы?**\n\n"
        f"Всего: {total:.2f} руб.\n\n"
        f"Напишите **ДА** для подтверждения или /cancel для отмены.",
        parse_mode='Markdown'
    )

    context.user_data['clearing'] = True
    return ConversationHandler.END


async def handle_clear_confirmation(update: Update, context: CallbackContext) -> int:
    """Обработка подтверждения очистки"""
    text = update.message.text.strip().upper()
    user_id = update.effective_user.id

    if text == 'ДА':
        success = db.clear_user_expenses(user_id)

        if success:
            await update.message.reply_text("✅ **Все расходы удалены!**")
        else:
            await update.message.reply_text("❌ Ошибка удаления.")
    else:
        await update.message.reply_text("✅ Очистка отменена.")

    if 'clearing' in context.user_data:
        del context.user_data['clearing']

    return ConversationHandler.END


async def handle_message(update: Update, context: CallbackContext) -> int:
    """Обработка случайных сообщений"""
    text = update.message.text.strip().upper()

    # Обработка подтверждения очистки
    if context.user_data.get('clearing') and text == 'ДА':
        return await handle_clear_confirmation(update, context)

    # Если начата очистка, но введено не "ДА"
    if context.user_data.get('clearing'):
        await update.message.reply_text(
            "⚠️ Напишите **ДА** для подтверждения или /cancel для отмены."
        )
        return ConversationHandler.END

    # Для всех других сообщений
    await update.message.reply_text(
        "🤖 Используйте команды:\n"
        "/add - Добавить расход\n"
        "/today - Расходы за сегодня\n"
        "/month - Расходы за месяц\n"
        "/stats - Статистика\n"
        "/categories - Категории\n"
        "/clear - Очистить\n"
        "/help - Помощь\n"
        "/cancel - Отмена"
    )
    return ConversationHandler.END