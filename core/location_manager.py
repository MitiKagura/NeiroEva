import json
import asyncio
import logging
import re
import random
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class LocationManager:
    def __init__(self, data_path: Path):
        self.data_path = data_path
        self.current_location = "лес, родной дом"
        self.pending_events = []
        # Создаём папку, если её нет
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.data_path.exists():
            self.save()   # создаст файл с дефолтными значениями
        else:
            self._load()

    def _load(self):
        if self.data_path.exists():
            try:
                with open(self.data_path, 'r') as f:
                    data = json.load(f)
                self.current_location = data.get("current_location", "лес, родной дом")
                self.pending_events = data.get("pending_events", [])
                logger.info(f"Локация загружена: {self.current_location}")
            except Exception as e:
                logger.error(f"Ошибка загрузки локации: {e}")

    def save(self):
        try:
            with open(self.data_path, 'w') as f:
                json.dump({
                    "current_location": self.current_location,
                    "pending_events": self.pending_events,
                    "last_update": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения локации: {e}")

    async def set_location(self, new_location: str, source: str = "context"):
        old = self.current_location
        self.current_location = new_location
        self.save()
        logger.info(f"Локация изменена: {old} -> {new_location} (источник: {source})")

    async def add_pending_call(self, delay_seconds: int, location: str):
        """Планирует звонок через delay_seconds из указанной локации."""
        event = {
            "type": "call",
            "time": asyncio.get_event_loop().time() + delay_seconds,
            "location": location,
            "done": False
        }
        self.pending_events.append(event)
        self.save()

    async def update_from_dialogue(self, text: str, is_eva: bool = False):
        """
        Анализирует ответ Евы и обновляет локацию на основе ключевых фраз.
        """
        if not is_eva:
            return
        lowered = text.lower()
        # 1. Обещание позвонить – планируем звонок
        if re.search(r'\b(позвоню|наберу|свяжусь|звякну)\b', lowered):
            delay = random.randint(600, 1800)  # 10–30 минут
            loc = self.current_location
            await self.add_pending_call(delay, loc)
            logger.info(f"Запланирован звонок через {delay} сек из {loc}")
            return
        # 2. Движение
        if re.search(r'\b(поеду|еду|отправляюсь|направляюсь|выхожу|ухожу)\b', lowered):
            match = re.search(r'(в|на|к)\s+([а-яА-ЯёЁa-zA-Z]+)', lowered)
            if match:
                dest = match.group(2)
                new_loc = f"в пути к {dest}"
            else:
                new_loc = "в пути"
            await self.set_location(new_loc, source="диалог (движение)")
            return
        # 3. Прибытие
        if re.search(r'\b(приехала|добралась|на месте|в\s+[а-яА-ЯёЁ]+\b)', lowered):
            match = re.search(r'(в|на)\s+([а-яА-ЯёЁa-zA-Z]+)', lowered)
            if match:
                new_loc = match.group(2)
            else:
                new_loc = "неизвестном месте"
            await self.set_location(new_loc, source="диалог (прибытие)")
            # после прибытия – автоматически позвонить через 2-5 минут
            await self.add_pending_call(random.randint(120, 300), new_loc)
            return
        # 4. Прощание (выход из поля зрения)
        if re.search(r'\b(прощай|пока|до свидания|ухожу|выхожу)\b', lowered):
            await self.set_location("в пути, вышла из поля зрения", source="прощание")
            return

    async def check_events(self, bot, chat_id, llm_engine, mood_engine, memory):
        """Проверяет и выполняет отложенные события (звонки)."""
        now = asyncio.get_event_loop().time()
        for event in self.pending_events[:]:
            if event["type"] == "call" and event["time"] <= now and not event.get("done", False):
                # Генерируем текст звонка
                mood_desc = mood_engine.get_mood_description()
                prompt = f"""Ты находишься в {event['location']}. Ты обещала позвонить Мише, чтобы он тебя забрал.
Твоё настроение: {mood_desc}. Напиши короткое сообщение (1-2 предложения, с эмодзи и звёздочками) – как бы ты позвонила и сказала, что ты готова, чтобы тебя забрали. Ответ:"""
                text = await llm_engine.generate(prompt, max_tokens=80, temperature=0.7)
                text = text.strip()
                if not text:
                    text = "*звонит* Я на месте, забери меня!"
                await bot.send_message(chat_id=chat_id, text=text)
                await memory.add_conversation_turn("eva", text, mood_engine.get_mood_description())
                event["done"] = True
                self.save()
                logger.info(f"Отложенный звонок выполнен из {event['location']}")
