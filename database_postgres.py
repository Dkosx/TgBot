# database_postgres.py
import psycopg2
import psycopg2.extras
import os
import logging
import time
from typing import List, Tuple, Dict
from psycopg2 import pool

logger = logging.getLogger(__name__)


class PostgreSQLDatabase:
    def __init__(self):
        self.connection_pool = None
        self.max_retries = 3
        self.retry_delay = 2
        self.connect()

    def connect(self):
        """Устанавливаем подключение к базе данных"""
        for attempt in range(self.max_retries):
            try:
                database_url = os.environ.get('DATABASE_URL')

                if not database_url:
                    logger.warning("⚠️ DATABASE_URL не установлен, используем локальные параметры")
                    database_url = f"postgresql://{os.environ.get('PGUSER', 'postgres')}:{os.environ.get('PGPASSWORD', '')}@{os.environ.get('PGHOST', 'localhost')}:{os.environ.get('PGPORT', '5432')}/{os.environ.get('PGDATABASE', 'expense_tracker')}"

                # Для Render необходимо SSL
                if 'render.com' in database_url or 'onrender.com' in database_url:
                    # Добавляем параметры SSL
                    if '?' not in database_url:
                        database_url += '?sslmode=require'
                    elif 'sslmode' not in database_url:
                        database_url += '&sslmode=require'

                logger.info(f"🔄 Попытка подключения к БД (попытка {attempt + 1}/{self.max_retries})...")

                # Создаем пул подключений
                self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                    1,  # минимальное количество подключений
                    10,  # максимальное количество подключений
                    database_url
                )

                # Проверяем подключение
                conn = self.connection_pool.getconn()
                cursor = conn.cursor()
                cursor.execute("SELECT version();")
                version = cursor.fetchone()
                cursor.close()
                self.connection_pool.putconn(conn)

                logger.info(f"✅ Подключение к PostgreSQL установлено: {version[0]}")
                self.create_tables()
                return

            except Exception as e:
                logger.error(f"❌ Ошибка подключения к PostgreSQL (попытка {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    logger.info(f"⏳ Ждем {self.retry_delay} секунд перед следующей попыткой...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("❌ Не удалось подключиться к базе данных после всех попыток")
                    self.connection_pool = None

    def get_connection(self):
        """Получаем соединение из пула"""
        if not self.connection_pool:
            logger.warning("⚠️ Пул подключений не инициализирован, пытаемся переподключиться...")
            self.connect()

        try:
            conn = self.connection_pool.getconn()
            # Проверяем, что соединение рабочее
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return conn
        except Exception as e:
            logger.error(f"❌ Ошибка получения соединения: {e}")
            # Пробуем переподключиться
            self.connect()
            if self.connection_pool:
                return self.connection_pool.getconn()
            return None

    def return_connection(self, conn):
        """Возвращаем соединение в пул"""
        if self.connection_pool and conn:
            try:
                self.connection_pool.putconn(conn)
            except Exception as e:
                logger.error(f"❌ Ошибка возврата соединения: {e}")

    def create_tables(self):
        """Создание таблиц, если они не существуют"""
        conn = self.get_connection()
        if not conn:
            logger.error("❌ Нет подключения к БД для создания таблиц")
            return

        try:
            with conn.cursor() as cursor:
                # Таблица пользователей
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username VARCHAR(100),
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        language_code VARCHAR(10),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Таблица расходов
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS expenses (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        amount DECIMAL(10, 2) NOT NULL,
                        category VARCHAR(50) NOT NULL,
                        description TEXT,
                        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT fk_user FOREIGN KEY (user_id) 
                        REFERENCES users(user_id) ON DELETE CASCADE
                    )
                """)

                # Создаем индекс для быстрого поиска по пользователю и дате
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_expenses_user_date 
                    ON expenses(user_id, date DESC)
                """)

                # Создаем индекс по категории
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_expenses_category 
                    ON expenses(category)
                """)

                conn.commit()
                logger.info("✅ Таблицы созданы/проверены")

        except Exception as e:
            logger.error(f"❌ Ошибка создания таблиц: {e}")
            conn.rollback()
        finally:
            self.return_connection(conn)

    # === БАЗОВЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С ДАННЫМИ ===

    def add_user(self, user_id: int, username: str = None, first_name: str = None,
                 last_name: str = None, language_code: str = None) -> bool:
        """Добавление пользователя"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name, language_code)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        language_code = EXCLUDED.language_code
                """, (user_id, username, first_name, last_name, language_code))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def add_expense(self, user_id: int, amount: float, category: str, description: str = None) -> bool:
        """Добавление расхода"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            # Сначала убедимся, что пользователь существует
            self.add_user(user_id)

            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO expenses (user_id, amount, category, description)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, amount, category, description))
                conn.commit()
                logger.info(f"✅ Расход добавлен: {amount} руб. для пользователя {user_id}")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления расхода: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def get_today_expenses(self, user_id: int) -> List[Tuple]:
        """Получение расходов за сегодня"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, amount, category, description, date 
                    FROM expenses 
                    WHERE user_id = %s AND date::date = CURRENT_DATE
                    ORDER BY date DESC
                """, (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Ошибка получения расходов за сегодня: {e}")
            return []
        finally:
            self.return_connection(conn)

    def get_month_expenses(self, user_id: int) -> List[Tuple]:
        """Получение расходов за текущий месяц"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, amount, category, description, date 
                    FROM expenses 
                    WHERE user_id = %s AND EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM CURRENT_DATE)
                    AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE)
                    ORDER BY date DESC
                """, (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Ошибка получения расходов за месяц: {e}")
            return []
        finally:
            self.return_connection(conn)

    def get_expenses_by_category(self, user_id: int) -> Dict[str, float]:
        """Получение статистики по категориям"""
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cursor:
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
            self.return_connection(conn)

    def clear_user_expenses(self, user_id: int) -> bool:
        """Очистка всех расходов пользователя"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM expenses WHERE user_id = %s", (user_id,))
                conn.commit()
                logger.info(f"✅ Расходы пользователя {user_id} очищены")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка очистки расходов: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def get_total_expenses(self, user_id: int) -> float:
        """Общая сумма расходов пользователя"""
        conn = self.get_connection()
        if not conn:
            return 0.0

        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = %s", (user_id,))
                result = cursor.fetchone()
                return float(result[0]) if result else 0.0
        except Exception as e:
            logger.error(f"❌ Ошибка получения общей суммы: {e}")
            return 0.0
        finally:
            self.return_connection(conn)

    def close(self):
        """Закрытие всех соединений"""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("✅ Пул подключений закрыт")


# Создаем глобальный экземпляр базы данных
db = PostgreSQLDatabase()