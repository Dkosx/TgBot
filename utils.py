from datetime import datetime


def format_amount(amount):
    """Форматирование суммы"""
    try:
        amount = float(amount)
        return f"{amount:.2f} ₽"
    except (ValueError, TypeError):
        return "0.00 ₽"


def format_expense_list(expenses):
    """Форматирование списка расходов"""
    if not expenses:
        return "Записи отсутствуют."

    result = ""
    total = 0
    for category, sum_amount, count in expenses:
        total += sum_amount
        result += f"{category}: {format_amount(sum_amount)} ({count} записей)\n"

    result += f"\n💰 Итого: {format_amount(total)}"
    return result


def validate_amount(text):
    """Проверка, что введена корректная сумма"""
    try:
        amount = float(text.replace(',', '.'))
        if amount <= 0:
            return False, "Сумма должна быть больше нуля!"
        return True, amount
    except ValueError:
        return False, "Пожалуйста, введите число (например: 1500 или 99.99)"


def get_current_month():
    """Получение названия текущего месяца"""
    months = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    return months[datetime.now().month - 1]