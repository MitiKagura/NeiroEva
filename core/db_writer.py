import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class DBWriter:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        logger.info(f"DBWriter инициализирован с путём: {db_path}")
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        full_name TEXT,
                        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_context (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        role TEXT,
                        content TEXT,
                        mood_context TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS daily_memory (
                        date TEXT PRIMARY KEY,
                        user_id INTEGER,
                        summary TEXT,
                        key_facts TEXT,
                        mood_score REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON conversation_context(user_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON daily_memory(date)")
                logger.info(f"База данных {self.db_path} инициализирована")
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")

    def ensure_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if cur.fetchone() is None:
                    full_name = f"{first_name or ''} {last_name or ''}".strip()
                    conn.execute(
                        "INSERT INTO users (user_id, username, first_name, last_name, full_name) VALUES (?, ?, ?, ?, ?)",
                        (user_id, username, first_name, last_name, full_name)
                    )
                    logger.info(f"Новый пользователь добавлен: user_id={user_id}, name={full_name}")
                    return True
                else:
                    conn.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
                    return False
        except Exception as e:
            logger.error(f"Ошибка ensure_user: {e}")
            return False

    def set_user_name(self, user_id: int, full_name: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE users SET full_name = ? WHERE user_id = ?", (full_name, user_id))
                logger.info(f"Имя пользователя {user_id} обновлено на {full_name}")
        except Exception as e:
            logger.error(f"Ошибка set_user_name: {e}")

    def add_conversation_turn(self, user_id: int, role: str, content: str, mood_context: str = ""):
        if user_id is None:
            user_id = 0
        if content is None:
            content = ""
        if mood_context is None:
            mood_context = ""
        logger.debug(f"DBWriter.add_conversation_turn: user={user_id}, role={role}, content={content[:30]}")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO conversation_context (user_id, role, content, mood_context) VALUES (?, ?, ?, ?)",
                    (user_id, role, content, mood_context)
                )
                logger.info(f"✅ Запись добавлена: user={user_id}, role={role}, content={content[:30]}")
        except Exception as e:
            logger.error(f"❌ Ошибка записи диалога: {e}, user={user_id}, role={role}")

    def get_last_conversation(self, user_id: int, limit: int = 20):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(
                    "SELECT role, content, mood_context, timestamp FROM conversation_context "
                    "WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (user_id, limit)
                )
                rows = cur.fetchall()
                return [{"role": r[0], "content": r[1], "mood": r[2], "time": r[3]} for r in reversed(rows)]
        except Exception as e:
            logger.error(f"Ошибка get_last_conversation: {e}")
            return []

    def get_user_full_name(self, user_id: int) -> Optional[str]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("SELECT full_name FROM users WHERE user_id = ?", (user_id,))
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Ошибка get_user_full_name: {e}")
            return None
