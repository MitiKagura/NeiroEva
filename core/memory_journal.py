import sqlite3
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class MemoryJournal:
    def __init__(self, db_path: Path, diary_dir: Path):
        self.db_path = db_path
        self.diary_dir = diary_dir
        self.diary_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # Создаём таблицы с user_id
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
            # Добавляем колонку user_id, если её нет
            try:
                conn.execute("ALTER TABLE daily_memory ADD COLUMN user_id INTEGER")
            except sqlite3.OperationalError:
                pass  # колонка уже есть
            try:
                conn.execute("ALTER TABLE conversation_context ADD COLUMN user_id INTEGER")
            except sqlite3.OperationalError:
                pass  # колонка уже есть
            # Индексы
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON conversation_context(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON daily_memory(date)")
        logger.info("База данных инициализирована с поддержкой user_id")

    async def add_diary_entry(self, content: str, emotion: str):
        today = datetime.now().strftime("%Y-%m-%d")
        diary_file = self.diary_dir / f"{today}.md"
        timestamp = datetime.now().strftime("%H:%M")
        entry = f"- **{timestamp}** — {content}\n"
        if not diary_file.exists():
            with open(diary_file, 'w', encoding='utf-8') as f:
                f.write(f"# Дневник Евы\n\n## {today}\n\n")
        with open(diary_file, 'a', encoding='utf-8') as f:
            f.write(entry)
        logger.info(f"Запись в дневник: {content[:50]}...")

    async def generate_diary_note(self, llm_engine, mood_engine, recent_context: str = ""):
        mood_desc = mood_engine.get_mood_description()
        emotion = mood_engine.emotion
        prompt = f"""Ты ведёшь личный дневник. Сейчас ты {mood_desc}. Твоё настроение: {emotion}.
Напиши одну короткую, искреннюю запись (2-3 предложения) от первого лица о том, что ты чувствуешь, о чём думаешь, может быть, о прошедших событиях или воспоминаниях. Пиши как обычный человек.
Не упоминай, что ты ИИ. Не используй звёздочки. Без эмодзи.
Вот что было недавно: {recent_context}
Запись в дневнике:"""
        note = await llm_engine.generate(prompt, max_tokens=130, temperature=0.7)
        note = note.strip()
        await self.add_diary_entry(note, emotion)

    async def add_conversation_turn(self, user_id: int, role: str, content: str, mood_context: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO conversation_context (user_id, role, content, mood_context) VALUES (?, ?, ?, ?)",
                (user_id, role, content, mood_context)
            )

    async def get_conversation_history(self, user_id: int, limit: int = 20) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT role, content, mood_context, timestamp FROM conversation_context WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit)
            )
            rows = cur.fetchall()
        history = []
        for role, content, mood, ts in reversed(rows):
            history.append({"role": role, "content": content, "mood": mood, "time": ts})
        return history

    async def get_last_n_days_context(self, user_id: int, n: int = 5) -> str:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT date, summary, mood_score FROM daily_memory WHERE user_id = ? ORDER BY date DESC LIMIT ?",
                (user_id, n)
            )
            rows = cur.fetchall()
        if not rows:
            return "Нет воспоминаний."
        return "\n".join([f"- {r[0]}: {r[1][:80]}" for r in rows])

    async def save_day_summary(self, user_id: int, date: datetime, summary: str, key_facts: List[str], mood_score: float):
        date_str = date.strftime("%Y-%m-%d")
        key_facts_json = json.dumps(key_facts, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO daily_memory (date, user_id, summary, key_facts, mood_score)
                VALUES (?, ?, ?, ?, ?)
            """, (date_str, user_id, summary, key_facts_json, mood_score))
        await self._prune_old_records()

    async def get_day_summary(self, user_id: int, date: datetime) -> Dict[str, Any]:
        date_str = date.strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT summary, key_facts, mood_score FROM daily_memory WHERE date = ? AND user_id = ?",
                (date_str, user_id)
            )
            row = cur.fetchone()
        if row:
            return {"summary": row[0], "key_facts": json.loads(row[1]), "mood_score": row[2]}
        return None

    async def archive_auto(self, user_id: int, llm_engine, mood_engine):
        today = datetime.now()
        history = await self.get_conversation_history(user_id, limit=50)
        if not history:
            return
        prompt = "Ты ведёшь личный дневник. Опиши кратко, что сегодня происходило, какие эмоции, важные события. Пиши от первого лица."
        summary = await llm_engine.generate(prompt, max_tokens=150)
        key_facts = []
        mood_score = mood_engine.mood_score
        await self.save_day_summary(user_id, today, summary, key_facts, mood_score)

    async def _prune_old_records(self):
        cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM daily_memory WHERE date < ?", (cutoff,))
