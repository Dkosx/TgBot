import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_name='finance.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        """Создание таблиц в базе данных"""
        # Таблица пользователей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_date TIMESTAMP
            )
        ''')

        # Таблица расходов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        self.conn.commit()

    def add_user(self, user_id, username, first_name, last_name):
        """Добавление нового пользователя"""
        try:
            self.cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registered_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, datetime.now()))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error adding user: {e}")
            return False

    def add_expense(self, user_id, amount, category, description=""):
        """Добавление расхода"""
        try:
            self.cursor.execute('''
                INSERT INTO expenses (user_id, amount, category, description, date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, amount, category, description, datetime.now()))
            self.conn.commit()
            return self.cursor.lastrowid
        except Exception as e:
            print(f"Error adding expense: {e}")
            return None

    def get_today_expenses(self, user_id):
        """Получение расходов за сегодня"""
        self.cursor.execute('''
            SELECT category, SUM(amount), COUNT(*)
            FROM expenses 
            WHERE user_id = ? AND DATE(date) = DATE('now')
            GROUP BY category
        ''', (user_id,))
        return self.cursor.fetchall()

    def get_month_expenses(self, user_id):
        """Получение расходов за текущий месяц"""
        self.cursor.execute('''
            SELECT category, SUM(amount), COUNT(*)
            FROM expenses 
            WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            GROUP BY category
        ''', (user_id,))
        return self.cursor.fetchall()

    def get_total_by_category(self, user_id, days=30):
        """Получение расходов по категориям за указанное количество дней"""
        self.cursor.execute('''
            SELECT category, SUM(amount)
            FROM expenses 
            WHERE user_id = ? AND date >= datetime('now', ?)
            GROUP BY category
            ORDER BY SUM(amount) DESC
        ''', (user_id, f'-{days} days'))
        return self.cursor.fetchall()

    def clear_all_expenses(self, user_id):
        """Удаление всех записей пользователя"""
        self.cursor.execute('DELETE FROM expenses WHERE user_id = ?', (user_id,))
        self.conn.commit()
        return self.cursor.rowcount

    def close(self):
        """Закрытие соединения с БД"""
        self.conn.close()


# Глобальный экземпляр базы данных
db = Database()