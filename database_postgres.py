import os
import logging
import sqlite3

logger = logging.getLogger(__name__)


# Проверяем, доступен ли PostgreSQL
def is_postgresql_available():
    """
    Автоматически выбирает базу данных:
    - PostgreSQL если есть DATABASE_URL и установлен psycopg2 (на Render)
    - SQLite для локальной разработки без PostgreSQL
    """
    # Проверяем наличие DATABASE_URL (есть на Render)
    if os.environ.get('DATABASE_URL'):
        try:
            # Пробуем импортировать psycopg2
            import psycopg2
            return True
        except ImportError:
            logger.warning("⚠️ psycopg2 не установлен, используем SQLite")
            return False
    return False


class PostgreSQLDatabase:
    """Класс для работы с PostgreSQL (используется на Render)"""

    def __init__(self):
        self.database_url = os.environ.get('DATABASE_URL')
        self.conn = None
        self.connect()

    def connect(self):
        """Подключение к PostgreSQL"""
        try:
            import psycopg2
            self.conn = psycopg2.connect(self.database_url, sslmode='require')
            self.create_tables()
            logger.info("✅ Подключено к PostgreSQL")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
            self.conn = None

    def create_tables(self):
        """Создание таблиц в PostgreSQL"""
        if not self.conn:
            return

        cursor = self.conn.cursor()

        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                registered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица расходов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount DECIMAL(10, 2),
                category VARCHAR(100),
                description TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        self.conn.commit()
        cursor.close()

    def execute_query(self, query, params=None):
        """Выполнение SQL запроса"""
        if not self.conn:
            return None

        try:
            cursor = self.conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if query.strip().upper().startswith('SELECT'):
                result = cursor.fetchall()
            else:
                self.conn.commit()
                result = cursor.rowcount

            cursor.close()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения запроса: {e}")
            return None

    @staticmethod
    def get_database_info():
        """Информация о базе данных (статический метод)"""
        return {
            "type": "PostgreSQL",
            "status": "connected",
            "environment": "Render"
        }


class SQLiteDatabase:
    """Класс для работы с SQLite (используется локально)"""

    def __init__(self):
        # Используем файловую базу вместо in-memory для сохранения данных
        db_path = os.path.join(os.path.dirname(__file__), 'expenses.db')
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_tables()
        logger.info(f"✅ SQLite база данных создана: {db_path}")

    def create_tables(self):
        """Создание таблиц в SQLite"""
        cursor = self.conn.cursor()

        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица расходов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                category TEXT,
                description TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        self.conn.commit()
        cursor.close()

    def execute_query(self, query, params=None):
        """Выполнение SQL запроса"""
        try:
            cursor = self.conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if query.strip().upper().startswith('SELECT'):
                result = cursor.fetchall()
            else:
                self.conn.commit()
                result = cursor.rowcount

            cursor.close()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения запроса: {e}")
            return None

    @staticmethod
    def get_database_info():
        """Информация о базе данных (статический метод)"""
        return {
            "type": "SQLite",
            "status": "connected",
            "environment": "Local development"
        }


# ========== ФАБРИЧНЫЙ МЕТОД ДЛЯ СОЗДАНИЯ БАЗЫ ДАННЫХ ==========
def create_database_instance():
    """
    Фабричный метод для создания экземпляра базы данных.
    Автоматически выбирает PostgreSQL или SQLite.
    """
    if is_postgresql_available():
        logger.info("🔍 Выбрана PostgreSQL база данных")
        return PostgreSQLDatabase()
    else:
        logger.info("🔍 Выбрана SQLite база данных")
        return SQLiteDatabase()


# Создаем экземпляр базы данных при импорте
db = create_database_instance()


# ========== УНИВЕРСАЛЬНЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С БАЗОЙ ==========
def add_user(user_id, username, first_name, last_name):
    """Добавление пользователя"""
    query = '''
        INSERT INTO users (user_id, username, first_name, last_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
    '''
    return db.execute_query(query, (user_id, username, first_name, last_name))


def add_expense(user_id, amount, category, description):
    """Добавление расхода"""
    query = '''
        INSERT INTO expenses (user_id, amount, category, description)
        VALUES (%s, %s, %s, %s)
    '''
    return db.execute_query(query, (user_id, amount, category, description))


def get_user_expenses(user_id, days=30):
    """Получение расходов пользователя за указанное количество дней"""
    query = '''
        SELECT amount, category, description, date
        FROM expenses
        WHERE user_id = %s AND date >= CURRENT_TIMESTAMP - INTERVAL '%s days'
        ORDER BY date DESC
    '''
    return db.execute_query(query, (user_id, days))


def get_today_expenses(user_id):
    """Получение расходов пользователя за сегодня"""
    query = '''
        SELECT amount, category, description, date
        FROM expenses
        WHERE user_id = %s AND DATE(date) = CURRENT_DATE
        ORDER BY date DESC
    '''
    return db.execute_query(query, (user_id,))


def get_month_expenses(user_id):
    """Получение расходов пользователя за текущий месяц"""
    query = '''
        SELECT amount, category, description, date
        FROM expenses
        WHERE user_id = %s 
          AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE)
          AND EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM CURRENT_DATE)
        ORDER BY date DESC
    '''
    return db.execute_query(query, (user_id,))


def clear_user_expenses(user_id):
    """Удаление всех расходов пользователя"""
    query = 'DELETE FROM expenses WHERE user_id = %s'
    return db.execute_query(query, (user_id,))


def get_categories_stats(user_id, days=30):
    """Статистика по категориям за указанное количество дней"""
    query = '''
        SELECT category, SUM(amount) as total, COUNT(*) as count
        FROM expenses
        WHERE user_id = %s AND date >= CURRENT_TIMESTAMP - INTERVAL '%s days'
        GROUP BY category
        ORDER BY total DESC
    '''
    return db.execute_query(query, (user_id, days))


if __name__ == '__main__':
    # Тестирование базы данных
    print(f"Тип базы данных: {type(db).__name__}")
    print(f"Информация о БД: {db.get_database_info()}")

    # Тестовые операции
    add_user(123456, "test_user", "Test", "User")
    add_expense(123456, 100.50, "Food", "Lunch")

    expenses = get_user_expenses(123456)
    print(f"Тестовые расходы: {expenses}")