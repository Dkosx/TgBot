import os
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)


class DatabaseInterface:
    """Абстрактный интерфейс для базы данных"""

    def connect(self):
        raise NotImplementedError

    def execute_query(self, query, params=None):
        raise NotImplementedError

    def get_database_info(self):
        raise NotImplementedError


class PostgreSQLDatabase(DatabaseInterface):
    """Класс для работы с PostgreSQL (используется на Render)"""

    def __init__(self):
        self.database_url = os.environ.get('DATABASE_URL')
        self.conn = None
        self.connect()
        self.create_tables()

    def connect(self):
        """Подключение к PostgreSQL"""
        try:
            import psycopg2
            self.conn = psycopg2.connect(self.database_url, sslmode='require')
            logger.info("✅ Подключено к PostgreSQL")
        except ImportError:
            logger.error("❌ psycopg2 не установлен")
            self.conn = None
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
            self.conn = None

    def create_tables(self):
        """Создание таблиц в PostgreSQL"""
        if not self.conn:
            return

        try:
            cursor = self.conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    registered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

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
            logger.info("✅ Таблицы PostgreSQL созданы/проверены")
        except Exception as e:
            logger.error(f"❌ Ошибка создания таблиц PostgreSQL: {e}")

    def execute_query(self, query, params=None):
        """Выполнение SQL запроса для PostgreSQL"""
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
            logger.error(f"❌ Ошибка выполнения запроса PostgreSQL: {e}")
            if self.conn:
                self.conn.rollback()
            return None

    def get_database_info(self):
        """Информация о базе данных"""
        return {
            "type": "PostgreSQL",
            "status": "connected" if self.conn else "disconnected",
            "environment": "Render/Production",
            "timestamp": datetime.now().isoformat()
        }

    def close(self):
        """Закрытие соединения"""
        if self.conn:
            self.conn.close()
            logger.info("✅ Соединение PostgreSQL закрыто")


class SQLiteDatabase(DatabaseInterface):
    """Класс для работы с SQLite (используется локально)"""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'expenses.db')

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
        logger.info(f"✅ SQLite база данных создана: {db_path}")

    def create_tables(self):
        """Создание таблиц в SQLite"""
        try:
            cursor = self.conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    registered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

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
            logger.info("✅ Таблицы SQLite созданы/проверены")
        except Exception as e:
            logger.error(f"❌ Ошибка создания таблиц SQLite: {e}")

    def execute_query(self, query, params=None):
        """Выполнение SQL запроса для SQLite"""
        try:
            cursor = self.conn.cursor()

            # Адаптируем запрос для SQLite
            adapted_query = self._adapt_query_for_sqlite(query)

            if params:
                cursor.execute(adapted_query, params)
            else:
                cursor.execute(adapted_query)

            if adapted_query.strip().upper().startswith('SELECT'):
                result = cursor.fetchall()
            else:
                self.conn.commit()
                result = cursor.rowcount

            cursor.close()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения запроса SQLite: {e}")
            return None

    @staticmethod
    def _adapt_query_for_sqlite(query):
        """Адаптация запроса под SQLite синтаксис (статический метод)"""
        # Заменяем %s на ? для параметров
        adapted_query = query.replace('%s', '?')

        # PostgreSQL INTERVAL на SQLite datetime
        adapted_query = adapted_query.replace(
            "CURRENT_TIMESTAMP - INTERVAL '%s days'",
            "datetime('now', '-? days')"
        )
        adapted_query = adapted_query.replace(
            "CURRENT_TIMESTAMP - INTERVAL",
            "datetime('now', '-"
        )

        # EXTRACT на strftime
        adapted_query = adapted_query.replace(
            "EXTRACT(YEAR FROM date)",
            "strftime('%Y', date)"
        )
        adapted_query = adapted_query.replace(
            "EXTRACT(MONTH FROM date)",
            "strftime('%m', date)"
        )
        adapted_query = adapted_query.replace(
            "EXTRACT(DAY FROM date)",
            "strftime('%d', date)"
        )

        # CURRENT_DATE на date('now')
        adapted_query = adapted_query.replace(
            "CURRENT_DATE",
            "date('now')"
        )

        # Удаляем ON CONFLICT для INSERT (будет отдельная обработка)
        adapted_query = adapted_query.replace(
            "ON CONFLICT (user_id) DO NOTHING",
            ""
        )

        return adapted_query

    def get_database_info(self):
        """Информация о базе данных"""
        return {
            "type": "SQLite",
            "status": "connected",
            "environment": "Local development",
            "path": self.db_path,
            "timestamp": datetime.now().isoformat()
        }

    def close(self):
        """Закрытие соединения"""
        if self.conn:
            self.conn.close()
            logger.info("✅ Соединение SQLite закрыто")


def create_database_instance():
    """
    Фабричный метод для создания экземпляра базы данных.
    Автоматически выбирает PostgreSQL или SQLite.
    """
    database_url = os.environ.get('DATABASE_URL')

    if database_url and 'postgresql' in database_url:
        try:
            import psycopg2
            logger.info("🔍 Выбрана PostgreSQL база данных")
            return PostgreSQLDatabase()
        except ImportError:
            logger.warning("⚠️ psycopg2 не установлен, используем SQLite")

    logger.info("🔍 Выбрана SQLite база данных")
    return SQLiteDatabase()


# Создаем экземпляр базы данных
db = create_database_instance()


# ========== УНИВЕРСАЛЬНЫЕ МЕТОДЫ С АДАПТАЦИЕЙ ==========
def add_user(user_id, username, first_name, last_name):
    """Добавление пользователя"""
    if isinstance(db, PostgreSQLDatabase):
        query = '''
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        '''
        params = (user_id, username, first_name, last_name)
    else:
        # SQLite не поддерживает ON CONFLICT напрямую
        query = '''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        '''
        params = (user_id, username, first_name, last_name)

    return db.execute_query(query, params)


def add_expense(user_id, amount, category, description):
    """Добавление расхода"""
    if isinstance(db, PostgreSQLDatabase):
        query = '''
            INSERT INTO expenses (user_id, amount, category, description)
            VALUES (%s, %s, %s, %s)
        '''
        params = (user_id, amount, category, description)
    else:
        query = '''
            INSERT INTO expenses (user_id, amount, category, description)
            VALUES (?, ?, ?, ?)
        '''
        params = (user_id, amount, category, description)

    return db.execute_query(query, params)


def get_user_expenses(user_id, days=30):
    """Получение расходов пользователя за указанное количество дней"""
    if isinstance(db, PostgreSQLDatabase):
        query = '''
            SELECT amount, category, description, date
            FROM expenses
            WHERE user_id = %s AND date >= CURRENT_TIMESTAMP - INTERVAL '%s days'
            ORDER BY date DESC
        '''
        params = (user_id, days)
    else:
        query = '''
            SELECT amount, category, description, date
            FROM expenses
            WHERE user_id = ? AND date >= datetime('now', '-? days')
            ORDER BY date DESC
        '''
        params = (user_id, days)

    return db.execute_query(query, params)


def get_today_expenses(user_id):
    """Получение расходов пользователя за сегодня"""
    if isinstance(db, PostgreSQLDatabase):
        query = '''
            SELECT amount, category, description, date
            FROM expenses
            WHERE user_id = %s AND DATE(date) = CURRENT_DATE
            ORDER BY date DESC
        '''
        params = (user_id,)
    else:
        query = '''
            SELECT amount, category, description, date
            FROM expenses
            WHERE user_id = ? AND date(date) = date('now')
            ORDER BY date DESC
        '''
        params = (user_id,)

    return db.execute_query(query, params)


def get_month_expenses(user_id):
    """Получение расходов пользователя за текущий месяц"""
    if isinstance(db, PostgreSQLDatabase):
        query = '''
            SELECT amount, category, description, date
            FROM expenses
            WHERE user_id = %s 
              AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE)
              AND EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM CURRENT_DATE)
            ORDER BY date DESC
        '''
        params = (user_id,)
    else:
        query = '''
            SELECT amount, category, description, date
            FROM expenses
            WHERE user_id = ?
              AND strftime('%Y', date) = strftime('%Y', 'now')
              AND strftime('%m', date) = strftime('%m', 'now')
            ORDER BY date DESC
        '''
        params = (user_id,)

    return db.execute_query(query, params)


def clear_user_expenses(user_id):
    """Удаление всех расходов пользователя"""
    if isinstance(db, PostgreSQLDatabase):
        query = 'DELETE FROM expenses WHERE user_id = %s'
        params = (user_id,)
    else:
        query = 'DELETE FROM expenses WHERE user_id = ?'
        params = (user_id,)

    return db.execute_query(query, params)


def get_categories_stats(user_id, days=30):
    """Статистика по категориям за указанное количество дней"""
    if isinstance(db, PostgreSQLDatabase):
        query = '''
            SELECT category, SUM(amount) as total, COUNT(*) as count
            FROM expenses
            WHERE user_id = %s AND date >= CURRENT_TIMESTAMP - INTERVAL '%s days'
            GROUP BY category
            ORDER BY total DESC
        '''
        params = (user_id, days)
    else:
        query = '''
            SELECT category, SUM(amount) as total, COUNT(*) as count
            FROM expenses
            WHERE user_id = ? AND date >= datetime('now', '-? days')
            GROUP BY category
            ORDER BY total DESC
        '''
        params = (user_id, days)

    return db.execute_query(query, params)


def get_user_info(user_id):
    """Получение информации о пользователе"""
    if isinstance(db, PostgreSQLDatabase):
        query = 'SELECT * FROM users WHERE user_id = %s'
        params = (user_id,)
    else:
        query = 'SELECT * FROM users WHERE user_id = ?'
        params = (user_id,)

    result = db.execute_query(query, params)
    return result[0] if result else None


def get_total_expenses_count():
    """Получение общего количества записей о расходах"""
    query = 'SELECT COUNT(*) FROM expenses'
    result = db.execute_query(query)
    return result[0][0] if result else 0


def get_total_users_count():
    """Получение общего количества пользователей"""
    query = 'SELECT COUNT(*) FROM users'
    result = db.execute_query(query)
    return result[0][0] if result else 0


if __name__ == '__main__':
    # Тестирование базы данных
    print("=" * 50)
    print("🔧 Тестирование базы данных")
    print("=" * 50)

    print(f"Тип базы данных: {type(db).__name__}")
    print(f"Информация о БД: {db.get_database_info()}")

    # Тестовые данные
    print("\n📝 Тестовые операции:")
    add_user(123456, "test_user", "Test", "User")
    add_expense(123456, 100.50, "Food", "Lunch")
    add_expense(123456, 500, "Transport", "Taxi")
    add_expense(123456, 1200, "Food", "Dinner")

    print("✅ Тестовые данные добавлены")

    # Получение расходов
    expenses = get_user_expenses(123456)
    print(f"\n📊 Расходы пользователя: {len(expenses)} записей")
    for expense in expenses[:3]:  # Показать первые 3 записи
        print(f"  - {expense}")

    # Статистика
    stats = get_categories_stats(123456, 30)
    print(f"\n📈 Статистика по категориям:")
    for stat in stats:
        print(f"  - {stat[0]}: ${stat[1]} ({stat[2]} записей)")

    # Количества
    total_expenses = get_total_expenses_count()
    total_users = get_total_users_count()
    print(f"\n📋 Общая статистика:")
    print(f"  - Пользователей: {total_users}")
    print(f"  - Записей о расходах: {total_expenses}")

    # Закрытие соединения
    if hasattr(db, 'close'):
        db.close()
        print("✅ Соединение с БД закрыто")

    print("\n" + "=" * 50)
    print("✅ Тестирование завершено успешно")
    print("=" * 50)