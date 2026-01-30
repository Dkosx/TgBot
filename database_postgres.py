import os
import psycopg2
import logging

logger = logging.getLogger(__name__)


class PostgreSQLDatabase:
    def __init__(self):
        self.connection_string = os.environ.get('DATABASE_URL')

        # Добавляем параметры SSL для Render
        if self.connection_string:
            logger.info(f"Original connection string: {self.connection_string[:50]}...")

            # Обязательно добавляем sslmode=require для Render
            if 'postgresql://' in self.connection_string:
                if '?' not in self.connection_string:
                    self.connection_string += '?sslmode=require'
                elif 'sslmode' not in self.connection_string:
                    self.connection_string += '&sslmode=require'

            logger.info(f"Updated connection string: {self.connection_string[:50]}...")

        self.connection_pool = None
        self.create_tables()

    def get_connection(self):
        """Получение соединения с БД"""
        try:
            if not self.connection_string:
                logger.error("❌ DATABASE_URL не установлен")
                return None

            # Создаем новое соединение каждый раз
            connection = psycopg2.connect(
                self.connection_string,
                connect_timeout=10
            )
            connection.autocommit = True
            return connection
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            return None

    def create_tables(self):
        """Создание таблиц в базе данных"""
        connection = self.get_connection()
        if not connection:
            logger.error("❌ Не удалось подключиться к БД для создания таблиц")
            return False

        try:
            with connection.cursor() as cursor:
                # Таблица пользователей
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username VARCHAR(100),
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        language_code VARCHAR(10),
                        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Таблица расходов
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS expenses (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                        amount DECIMAL(10, 2) NOT NULL,
                        category VARCHAR(50) NOT NULL,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

            logger.info("✅ Таблицы созданы успешно")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка создания таблиц: {e}")
            return False
        finally:
            connection.close()

    def add_user(self, user_id, username=None, first_name=None, last_name=None, language_code=None):
        """Добавление пользователя"""
        connection = self.get_connection()
        if not connection:
            return False

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name, language_code)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id, username, first_name, last_name, language_code))
            logger.info(f"✅ Пользователь {user_id} добавлен")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя: {e}")
            return False
        finally:
            connection.close()

    def add_expense(self, user_id, amount, category, description=None):
        """Добавление расхода"""
        connection = self.get_connection()
        if not connection:
            return False

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO expenses (user_id, amount, category, description)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, amount, category, description))
            logger.info(f"✅ Расход {amount} руб. добавлен для пользователя {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления расхода: {e}")
            return False
        finally:
            connection.close()

    def get_today_expenses(self, user_id):
        """Получение расходов за сегодня"""
        connection = self.get_connection()
        if not connection:
            return []

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, amount, category, description, created_at 
                    FROM expenses 
                    WHERE user_id = %s 
                    AND DATE(created_at) = CURRENT_DATE
                    ORDER BY created_at DESC
                """, (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Ошибка получения расходов за сегодня: {e}")
            return []
        finally:
            connection.close()

    def get_month_expenses(self, user_id):
        """Получение расходов за текущий месяц"""
        connection = self.get_connection()
        if not connection:
            return []

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, amount, category, description, created_at 
                    FROM expenses 
                    WHERE user_id = %s 
                    AND EXTRACT(MONTH FROM created_at) = EXTRACT(MONTH FROM CURRENT_DATE)
                    AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                    ORDER BY created_at DESC
                """, (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Ошибка получения расходов за месяц: {e}")
            return []
        finally:
            connection.close()

    def get_expenses_by_category(self, user_id):
        """Получение статистики по категориям"""
        connection = self.get_connection()
        if not connection:
            return {}

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT category, SUM(amount) as total
                    FROM expenses 
                    WHERE user_id = %s
                    GROUP BY category
                    ORDER BY total DESC
                """, (user_id,))
                result = cursor.fetchall()
                return {row[0]: float(row[1]) for row in result}
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}
        finally:
            connection.close()

    def get_total_expenses(self, user_id):
        """Получение общей суммы расходов"""
        connection = self.get_connection()
        if not connection:
            return 0

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COALESCE(SUM(amount), 0)
                    FROM expenses 
                    WHERE user_id = %s
                """, (user_id,))
                result = cursor.fetchone()
                return float(result[0]) if result else 0
        except Exception as e:
            logger.error(f"❌ Ошибка получения общей суммы: {e}")
            return 0
        finally:
            connection.close()

    def clear_user_expenses(self, user_id):
        """Очистка всех расходов пользователя"""
        connection = self.get_connection()
        if not connection:
            return False

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM expenses 
                    WHERE user_id = %s
                """, (user_id,))
            logger.info(f"✅ Расходы пользователя {user_id} очищены")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка очистки расходов: {e}")
            return False
        finally:
            connection.close()


# Создаем глобальный экземпляр базы данных
db = PostgreSQLDatabase()