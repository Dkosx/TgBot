from telegram import ReplyKeyboardMarkup
from config import CATEGORIES

def get_main_keyboard():
    """Основная клавиатура"""
    keyboard = [
        ['➕ Добавить расход', '📊 Статистика'],
        ['📈 За сегодня', '📅 За месяц'],
        ['🗑️ Очистить все', '❓ Помощь']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_categories_keyboard():
    """Клавиатура с категориями расходов"""
    # Разбиваем категории на строки по 2-3 кнопки
    keyboard = []
    for i in range(0, len(CATEGORIES), 3):
        keyboard.append(CATEGORIES[i:i+3])
    keyboard.append(['↩️ Назад'])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_confirm_keyboard():
    """Клавиатура для подтверждения действий"""
    keyboard = [
        ['✅ Да, удалить все', '❌ Нет, отмена']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_keyboard():
    """Простая кнопка "Назад" """
    return ReplyKeyboardMarkup([['↩️ Назад']], resize_keyboard=True)