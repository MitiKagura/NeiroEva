import sqlite3
import json
from datetime import datetime
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
            conn.execute("CREATE TABLE IF NOT EXISTS daily_memory (date TEXT PRIMARY KEY, summary TEXT, key_facts TEXT, mood_score REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS conversation_context (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, role TEXT, content TEXT, mood_context TEXT)")
        logger.info("База данных инициализирована")

    async def add_diary_entry(self, content: str, emotion: str):
        today = datetime.now().strftime("%Y-%m-%d")
        diary_file = self.diary_dir / f"{today}.md"
        timestamp = datetime.now().strftime("%H:%M")
        if not diary_file.exists():
            with open(diary_file, 'w', encoding='utf-8') as f:
                f.write(f"# Дневник Евы\n\n## {today}\n\n")
        with open(diary_file, 'a', encoding='utf-8') as f:
            f.write(f"- **{timestamp}** — {content}\n")
        logger.info(f"Запись в дневник: {content[:60]}...")

    async def generate_diary_note(self, llm_engine, mood_engine, recent_context: str = ""):
        mood_desc = mood_engine.get_mood_description()
        emotion = mood_engine.emotion
        prompt = f"""Ты — Ева. Ты ведёшь личный дневник ТОЛЬКО от своего имени. Запрещено писать от имени Миши или других людей. Используй местоимения "я", "мне", "меня" только для себя. Если хочешь упомянуть Мишу, пиши о нём в третьем лице: "Миша сделал то-то". Не пиши фразы вроде "я (Миша) проснулся". Твоё настроение: {mood_desc}, эмоция: {emotion}.
    Напиши одну короткую искреннюю запись (2-3 предложения) о том, что ты чувствуешь, что произошло, о чём думаешь. Пиши только от первого лица Евы.
    Вот что было недавно: {recent_context}
    Запись в дневнике (от первого лица Евы):"""
        note = await llm_engine.generate(prompt, max_tokens=130, temperature=0.7)
        note = note.strip()
        # Постобработка: удаляем явные указания на Мишу в первом лице
        import re
        note = re.sub(r'\b(я проснулся|я лежал|я увидел|мой живот|я сказал|я думал|я был|я подумал|я почувствовал)\b', '', note, flags=re.IGNORECASE)
        note = re.sub(r'\s+', ' ', note).strip()
        if not note or len(note) < 5:
            note = "Сегодня был хороший день."
        await self.add_diary_entry(note, emotion)

    async def add_conversation_turn(self, role: str, content: str, mood_context: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO conversation_context (role, content, mood_context) VALUES (?, ?, ?)", (role, content, mood_context))

    async def get_conversation_history(self, limit: int = 20) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT role, content, mood_context, timestamp FROM conversation_context ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
        history = []
        for role, content, mood, ts in reversed(rows):
            history.append({"role": role, "content": content, "mood": mood, "time": ts})
        return history

    async def get_last_n_days_context(self, n: int = 5) -> str:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT date, summary, mood_score FROM daily_memory ORDER BY date DESC LIMIT ?", (n,))
            rows = cur.fetchall()
        if not rows:
            return "Нет воспоминаний."
        return "\n".join([f"- {r[0]}: {r[1][:80]}" for r in rows])
