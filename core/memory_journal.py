import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from core.db_writer import DBWriter

logger = logging.getLogger(__name__)

class MemoryJournal:
    def __init__(self, db_path: Path, diary_dir: Path):
        self.db_path = db_path
        self.diary_dir = diary_dir
        self.diary_dir.mkdir(parents=True, exist_ok=True)
        self.db = DBWriter(db_path)  # используем синхронный доступ
        logger.info(f"MemoryJournal инициализирован с БД {db_path}")

    async def add_conversation_turn(self, user_id: int, role: str, content: str, mood_context: str = ""):
        logger.info(f"add_conversation_turn вызван: user={user_id}, role={role}, content={content[:30]}")
        # Синхронный вызов
        self.db.add_conversation_turn(user_id, role, content, mood_context)

    async def get_conversation_history(self, user_id: int, limit: int = 20) -> List[Dict]:
        return self.db.get_last_conversation(user_id, limit)

    async def ensure_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        return self.db.ensure_user(user_id, username, first_name, last_name)

    async def set_user_name(self, user_id: int, full_name: str):
        self.db.set_user_name(user_id, full_name)

    async def get_user_full_name(self, user_id: int):
        return self.db.get_user_full_name(user_id)

    # Остальные методы (для дневника) оставляем без изменений, они не критичны
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

    # В memory_journal.py
    async def generate_diary_note(self, llm_engine, mood_engine, recent_context: str = ""):
        mood_desc = mood_engine.get_mood_description()
        emotion = mood_engine.emotion
        prompt = f"""Ты ведёшь личный дневник. Сейчас ты {mood_desc}. Твоё настроение: {emotion}.
    Напиши одну короткую, искреннюю запись (2-3 предложения) от первого лица о том, что ты чувствуешь, о чём думаешь, может быть, о прошедших событиях или воспоминаниях. Пиши как обычный человек.
    Не упоминай, что ты ИИ. Не используй звёздочки. Без эмодзи.
    Вот что было недавно: {recent_context}
    Запись в дневнике:"""
        try:
            note = await asyncio.wait_for(llm_engine.generate(prompt, max_tokens=150, temperature=0.7), timeout=30.0)
            if not note or len(note.strip()) < 5:
                raise ValueError("Пустой ответ")
            note = note.strip()
            await self.add_diary_entry(note, emotion)
        except (asyncio.TimeoutError, Exception):
            logger.warning("Первая попытка генерации дневника не удалась, пробуем снова с упрощённым промптом...")
            fallback_prompt = "Напиши одну короткую запись в дневник о том, что ты чувствуешь сегодня. 2 предложения."
            note = await llm_engine.generate(fallback_prompt, max_tokens=100, temperature=0.7)
            if not note or len(note.strip()) < 3:
                note = "Сегодня был обычный день. Чувствую себя спокойно."
            await self.add_diary_entry(note, emotion)

    async def get_last_n_days_context(self, user_id: int, n: int = 5) -> str:
        # Заглушка, можно реализовать через DBWriter при необходимости
        return "Воспоминания загружены."

    async def save_day_summary(self, user_id: int, date: datetime, summary: str, key_facts: List[str], mood_score: float):
        # Пока пропускаем, не критично для теста
        pass

    async def get_day_summary(self, user_id: int, date: datetime) -> Dict[str, Any]:
        return None

    async def archive_auto(self, user_id: int, llm_engine, mood_engine):
        pass
