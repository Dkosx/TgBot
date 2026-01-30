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
    logger.info(f"🔄 Пользователь {update.effective_user.id} начал добавление расхода")
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
        logger.info(f"💰 Получена сумма: {amount}")

        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0. Введите снова:")
            return AMOUNT

        context.user_data['amount'] = amount
        logger.info(f"✅ Сумма сохранена: {amount}")

        categories = "\n".join([f"• {cat}" for cat in CATEGORIES])

        await update.message.reply_text(
            f"✅ Сумма: {amount:.2f} руб.\n\n"
            f"📋 **Выберите категорию:**\n\n{categories}\n\n"
            "✏️ **Введите название категории из списка выше**",
            parse_mode='Markdown'
        )
        return CATEGORY

    except ValueError:
        logger.warning(f"❌ Неверный формат суммы: '{update.message.text}'")
        await update.message.reply_text("❌ Неверный формат. Введите число:")
        return AMOUNT


async def process_category(update: Update, context: CallbackContext) -> int:
    """Обработка выбора категории"""
    text = update.message.text.strip()
    logger.info(f"📂 Получена категория: '{text}'")

    if text in CATEGORIES:
        context.user_data['category'] = text
        logger.info(f"✅ Категория сохранена: {text}")

        await update.message.reply_text(
            f"✅ Категория: {text}\n\n"
            "📝 **Введите описание (необязательно):**\n"
            "Напишите описание или /skip чтобы пропустить\n"
            "/cancel для отмены",
            parse_mode='Markdown'
        )
        return DESCRIPTION
    else:
        logger.warning(f"❌ Категория не найдена: '{text}'")
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

    logger.info(f"📝 Получено описание: '{text}'")

    # Обработка skip команды (текст, а не команда)
    if text.lower() in ['skip', 'пропустить', 'без описания']:
        text = None
        logger.info("⏭️  Описание пропущено")

    amount = context.user_data.get('amount')
    category = context.user_data.get('category')

    if not amount or not category:
        logger.error("❌ Ошибка: потеряны данные amount или category")
        await update.message.reply_text("❌ Ошибка: данные потеряны.")
        context.user_data.clear()
        return ConversationHandler.END

    success = db.add_expense(user_id, amount, category, text)

    if success:
        response = f"✅ **Расход добавлен!**\n\n💰 {amount:.2f} руб. - {category}"
        if text:
            response += f"\n📝 {text}"
        logger.info(f"✅ Расход добавлен для пользователя {user_id}: {amount} руб. - {category}")
    else:
        response = "❌ Ошибка сохранения"
        logger.error(f"❌ Ошибка сохранения для пользователя {user_id}")

    context.user_data.clear()
    await update.message.reply_text(response, parse_mode='Markdown')
    return ConversationHandler.END


async def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена диалога"""
    user_id = update.effective_user.id
    logger.info(f"🚫 Отмена пользователем {user_id}")
    context.user_data.clear()
    await update.message.reply_text("🚫 Операция отменена.")
    return ConversationHandler.END


# ========== КОМАНДЫ ПРОСМОТРА ==========
async def show_today_expenses(update: Update, context: CallbackContext) -> int:
    """Расходы за сегодня"""
    context.user_data.clear()
    user_id = update.effective_user.id
    logger.info(f"📅 Запрос расходов за сегодня от {user_id}")
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

    logger.info(f"📊 Показаны расходы за сегодня: {total:.2f} руб.")

    await update.message.reply_text(message, parse_mode='Markdown')
    return ConversationHandler.END


async def show_month_expenses(update: Update, context: CallbackContext) -> int:
    """Расходы за месяц"""
    context.user_data.clear()
    user_id = update.effective_user.id
    logger.info(f"📈 Запрос расходов за месяц от {user_id}")
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

    logger.info(f"📊 Показаны расходы за месяц: {total:.2f} руб.")

    await update.message.reply_text(message, parse_mode='Markdown')
    return ConversationHandler.END


async def show_stats(update: Update, context: CallbackContext) -> int:
    """Статистика"""
    context.user_data.clear()
    user_id = update.effective_user.id
    logger.info(f"📊 Запрос статистики от {user_id}")
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

    logger.info(f"📊 Показана статистика: {total:.2f} руб. по {len(stats)} категориям")

    await update.message.reply_text(message, parse_mode='Markdown')
    return ConversationHandler.END


# ========== УПРОЩЕННАЯ КОМАНДА ОЧИСТКИ ==========
async def clear_expenses_start(update: Update, context: CallbackContext) -> int:
    """Очистка расходов (без подтверждения)"""
    context.user_data.clear()
    user_id = update.effective_user.id

    # Получаем сумму перед удалением
    total = db.get_total_expenses(user_id)

    if total == 0:
        await update.message.reply_text("🗑️ **Нет расходов для очистки.**")
        logger.info(f"🔄 Попытка очистки при нулевых расходах от {user_id}")
        return ConversationHandler.END

    # Сразу удаляем
    success = db.clear_user_expenses(user_id)

    if success:
        await update.message.reply_text(
            f"✅ **Все расходы ({total:.2f} руб.) удалены!**\n\n"
            "⚠️ Это действие нельзя отменить.",
            parse_mode='Markdown'
        )
        logger.info(f"🗑️  Расходы ({total:.2f} руб.) очищены для пользователя {user_id}")
    else:
        await update.message.reply_text("❌ Ошибка при удалении расходов.")
        logger.error(f"❌ Ошибка очистки расходов для {user_id}")

    return ConversationHandler.END


# ========== ФУНКЦИЯ ДЛЯ ОТЛАДКИ ==========
async def echo_debug(update: Update, context: CallbackContext) -> int:
    """Функция для отладки - показывает что получил бот"""
    user_id = update.effective_user.id
    text = update.message.text or "(без текста)"

    logger.info(f"🔍 DEBUG: Пользователь {user_id} отправил: '{text}'")
    logger.info(f"🔍 DEBUG: user_data = {context.user_data}")

    await update.message.reply_text(
        f"🔍 **Отладка:**\n\n"
        f"User ID: `{user_id}`\n"
        f"Текст: `{text}`\n"
        f"user_data: `{context.user_data}`\n\n"
        f"Используйте /add для добавления расхода",
        parse_mode='Markdown'
    )
    return ConversationHandler.END