import sqlite3
from datetime import datetime
import logging

# Настройка логирования
logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_name=':memory:'):
        """
        Инициализация базы данных.
        """
        try:
            self.conn = sqlite3.connect(db_name, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self.create_tables()
            logger.info(f"✅ Database initialized: {db_name}")
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error initializing database: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error initializing database: {e}")
            raise

    def create_tables(self):
        """Создание таблиц в базе данных"""
        try:
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

            # Индексы для быстрого поиска
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, date)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)')

            self.conn.commit()
            logger.info("✅ Database tables created successfully")
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error creating tables: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error creating tables: {e}")
            raise

    def add_user(self, user_id, username, first_name, last_name):
        """Добавление нового пользователя"""
        try:
            self.cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registered_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, datetime.now()))
            self.conn.commit()

            if self.cursor.rowcount > 0:
                logger.info(f"✅ New user registered: {user_id} ({username})")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"❌ Integrity error adding user {user_id}: {e}")
            return False
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error adding user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error adding user {user_id}: {e}")
            return False

    def add_expense(self, user_id, amount, category, description=""):
        """Добавление расхода"""
        try:
            # Проверка валидности данных
            if amount <= 0:
                logger.warning(f"⚠️  Invalid amount {amount} for user {user_id}")
                return None

            # Проверяем, существует ли пользователь
            self.cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
            if not self.cursor.fetchone():
                logger.warning(f"⚠️  User {user_id} not found in database")
                return None

            self.cursor.execute('''
                INSERT INTO expenses (user_id, amount, category, description, date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, amount, category, description, datetime.now()))
            self.conn.commit()

            expense_id = self.cursor.lastrowid
            logger.info(f"✅ Expense added: id={expense_id}, user={user_id}, amount={amount}, category={category}")
            return expense_id
        except sqlite3.IntegrityError as e:
            logger.error(f"❌ Integrity error adding expense for user {user_id}: {e}")
            return None
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error adding expense for user {user_id}: {e}")
            return None
        except ValueError as e:
            logger.error(f"❌ Value error adding expense for user {user_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error adding expense for user {user_id}: {e}")
            return None

    def get_today_expenses(self, user_id):
        """Получение расходов за сегодня"""
        try:
            self.cursor.execute('''
                SELECT category, SUM(amount) as total, COUNT(*) as count
                FROM expenses 
                WHERE user_id = ? AND DATE(date) = DATE('now')
                GROUP BY category
                ORDER BY total DESC
            ''', (user_id,))
            result = self.cursor.fetchall()
            logger.debug(f"📊 Today expenses for user {user_id}: {len(result)} categories")
            return result
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error getting today expenses for user {user_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error getting today expenses for user {user_id}: {e}")
            return []

    def get_month_expenses(self, user_id):
        """Получение расходов за текущий месяц"""
        try:
            self.cursor.execute('''
                SELECT category, SUM(amount) as total, COUNT(*) as count
                FROM expenses 
                WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
                GROUP BY category
                ORDER BY total DESC
            ''', (user_id,))
            result = self.cursor.fetchall()
            logger.debug(f"📊 Month expenses for user {user_id}: {len(result)} categories")
            return result
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error getting month expenses for user {user_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error getting month expenses for user {user_id}: {e}")
            return []

    def get_total_by_category(self, user_id, days=30):
        """Получение расходов по категориям за указанное количество дней"""
        try:
            self.cursor.execute('''
                SELECT category, SUM(amount) as total
                FROM expenses 
                WHERE user_id = ? AND date >= datetime('now', ?)
                GROUP BY category
                ORDER BY total DESC
            ''', (user_id, f'-{days} days'))
            result = self.cursor.fetchall()
            logger.debug(f"📊 {days}-day expenses for user {user_id}: {len(result)} categories")
            return result
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error getting {days}-day expenses for user {user_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error getting {days}-day expenses for user {user_id}: {e}")
            return []

    def get_all_expenses(self, user_id, limit=50):
        """Получение всех расходов пользователя (последние N записей)"""
        try:
            self.cursor.execute('''
                SELECT id, amount, category, description, date
                FROM expenses 
                WHERE user_id = ?
                ORDER BY date DESC
                LIMIT ?
            ''', (user_id, limit))
            result = self.cursor.fetchall()
            logger.debug(f"📊 All expenses for user {user_id}: {len(result)} records")
            return result
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error getting all expenses for user {user_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error getting all expenses for user {user_id}: {e}")
            return []

    def get_user_stats(self, user_id):
        """Получение общей статистики пользователя"""
        try:
            # Общая сумма расходов
            self.cursor.execute('SELECT SUM(amount) FROM expenses WHERE user_id = ?', (user_id,))
            total_spent_result = self.cursor.fetchone()
            total_spent = total_spent_result[0] if total_spent_result[0] else 0

            # Количество записей
            self.cursor.execute('SELECT COUNT(*) FROM expenses WHERE user_id = ?', (user_id,))
            total_records_result = self.cursor.fetchone()
            total_records = total_records_result[0] if total_records_result[0] else 0

            # Первая запись
            self.cursor.execute('SELECT MIN(date) FROM expenses WHERE user_id = ?', (user_id,))
            first_record_result = self.cursor.fetchone()
            first_record = first_record_result[0] if first_record_result[0] else None

            # Рассчет средней за день (если есть данные)
            avg_per_day = 0
            if total_records > 0 and first_record:
                # Примерный расчет: общая сумма / количество дней с первой записи
                try:
                    first_date = datetime.fromisoformat(first_record.replace('Z', '+00:00'))
                    days_since_first = (datetime.now() - first_date).days
                    avg_per_day = total_spent / max(days_since_first, 1)
                except (ValueError, AttributeError) as e:
                    logger.debug(f"⚠️  Could not calculate avg per day: {e}")
                    avg_per_day = total_spent / 30  # fallback

            stats = {
                'total_spent': round(total_spent, 2),
                'total_records': total_records,
                'first_record': first_record,
                'avg_per_day': round(avg_per_day, 2)
            }

            logger.debug(f"📊 Stats for user {user_id}: {stats}")
            return stats
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error getting stats for user {user_id}: {e}")
            return {}
        except Exception as e:
            logger.error(f"❌ Unexpected error getting stats for user {user_id}: {e}")
            return {}

    def clear_all_expenses(self, user_id):
        """Удаление всех записей пользователя"""
        try:
            # Получаем количество записей ДО удаления для логирования
            self.cursor.execute('SELECT COUNT(*) FROM expenses WHERE user_id = ?', (user_id,))
            count_result = self.cursor.fetchone()
            count_before = count_result[0] if count_result[0] else 0

            if count_before == 0:
                logger.info(f"📝 No expenses to clear for user {user_id}")
                return 0

            self.cursor.execute('DELETE FROM expenses WHERE user_id = ?', (user_id,))
            self.conn.commit()

            deleted_count = self.cursor.rowcount
            logger.warning(f"🗑️  Cleared {deleted_count} expenses for user {user_id} (had {count_before})")
            return deleted_count
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error clearing expenses for user {user_id}: {e}")
            return 0
        except Exception as e:
            logger.error(f"❌ Unexpected error clearing expenses for user {user_id}: {e}")
            return 0

    def close(self):
        """Закрытие соединения с БД"""
        try:
            self.conn.close()
            logger.info("✅ Database connection closed")
        except sqlite3.Error as e:
            logger.error(f"❌ SQLite error closing database: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error closing database: {e}")


# Глобальный экземпляр базы данных
db = Database(':memory:')