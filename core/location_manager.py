import json
import asyncio
import logging
import random
import re
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class LocationManager:
    def __init__(self, data_path: Path):
        self.data_path = data_path
        self.current_location = "родной дом"  # главная локация
        self.sub_location = ""  # дополнительная локация (кухня, кровать и т.д.)
        self.pending_events = []
        self.pending_shows = []
        self._load()

    def _load(self):
        if self.data_path.exists():
            try:
                with open(self.data_path, 'r') as f:
                    data = json.load(f)
                self.current_location = data.get("current_location", "родной дом")
                self.sub_location = data.get("sub_location", "")
                self.pending_events = data.get("pending_events", [])
                self.pending_shows = data.get("pending_shows", [])
                logger.info(f"Локация загружена: {self.current_location}, {self.sub_location}")
            except Exception as e:
                logger.error(f"Ошибка загрузки локации: {e}")

    def save(self):
        try:
            with open(self.data_path, 'w') as f:
                json.dump({
                    "current_location": self.current_location,
                    "sub_location": self.sub_location,
                    "pending_events": self.pending_events,
                    "pending_shows": self.pending_shows,
                    "last_update": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения локации: {e}")

    async def set_location(self, main_location: str, sub_location: str = "", source: str = "context"):
        old_main = self.current_location
        old_sub = self.sub_location
        self.current_location = main_location
        self.sub_location = sub_location
        self.save()
        logger.info(f"Локация изменена: {old_main}/{old_sub} -> {main_location}/{sub_location} (источник: {source})")

    async def set_sub_location(self, sub_location: str, source: str = "context"):
        old_sub = self.sub_location
        self.sub_location = sub_location
        self.save()
        logger.info(f"Дополнительная локация изменена: {old_sub} -> {sub_location} (источник: {source})")

    def get_full_location(self) -> str:
        if self.sub_location:
            return f"{self.current_location}, {self.sub_location}"
        return self.current_location

    async def add_pending_call(self, delay_seconds: int, location: str):
        event = {
            "type": "call",
            "time": asyncio.get_event_loop().time() + delay_seconds,
            "location": location,
            "done": False
        }
        self.pending_events.append(event)
        self.save()
        logger.info(f"Запланирован звонок через {delay_seconds} сек из {location}")

    async def add_pending_show(self, person: str, chat_id: int, request_text: str):
        event = {
            "person": person,
            "chat_id": chat_id,
            "request_text": request_text,
            "done": False,
            "created": datetime.now().isoformat()
        }
        self.pending_shows.append(event)
        self.save()
        logger.info(f"Добавлено обещание показать {person}")

    async def check_pending_events(self, bot, chat_id, llm_engine, mood_engine, memory):
        now = asyncio.get_event_loop().time()
        for event in self.pending_events[:]:
            if event["type"] == "call" and event["time"] <= now and not event.get("done", False):
                mood_desc = mood_engine.get_mood_description()
                prompt = f"""Ты находишься в {event['location']}. Ты обещала позвонить Мише, чтобы он тебя забрал.
Твоё настроение: {mood_desc}. Напиши короткое сообщение (1-2 предложения, с эмодзи и звёздочками) – как бы ты позвонила и сказала, что ты готова, чтобы тебя забрали. Ответ:"""
                text = await llm_engine.generate(prompt, max_tokens=80, temperature=0.7)
                text = text.strip()
                if not text:
                    text = "*звонит* Я на месте, забери меня!"
                try:
                    await bot.send_message(chat_id=chat_id, text=text)
                    await memory.add_conversation_turn(chat_id, "eva", text, mood_engine.get_mood_description())
                    event["done"] = True
                    self.save()
                    logger.info(f"Отложенный звонок выполнен из {event['location']}")
                except Exception as e:
                    logger.error(f"Ошибка отправки звонка: {e}")

    async def check_pending_shows(self, bot, llm_engine, mood_engine, memory, anime_gen, compute_lock):
        for req in self.pending_shows[:]:
            if req.get("done", False):
                continue
            person = req["person"]
            if person == "violet":
                can = self.current_location in ["родной дом", "дом Виолетты", "город"]
            elif person == "agnes":
                can = self.current_location in ["родной дом", "дом Агнес", "город"]
            else:
                can = False
            if can:
                chat_id = req["chat_id"]
                mood_desc = mood_engine.get_mood_description()
                prompt = f"""Твоё настроение: {mood_desc}. Ты обещала показать {person} пользователю, и теперь вы находитесь в подходящем месте ({self.current_location}).
Напиши короткое сообщение (1-2 предложения), что ты выполняешь обещание, и покажи фото."""
                text = await llm_engine.generate(prompt, max_tokens=80, temperature=0.7)
                try:
                    await bot.send_message(chat_id=chat_id, text=text)
                    await memory.add_conversation_turn(chat_id, "eva", text, mood_engine.get_mood_description())
                except Exception as e:
                    logger.error(f"Ошибка отправки сообщения о выполнении обещания: {e}")
                    continue
                try:
                    if person == "agnes":
                        prompt_img = "masterpiece, best quality, anime style, highres, detailed face, 1girl, horse girl, horse ears, horse tail, upper body, short messy brown hair, ahoge, red eyes, empty eyes, single earring, labcoat, sleeves past fingers, yellow sweater vest, black shirt, black necktie, pantyhose, white high heels, looking at viewer"
                        lora_path = "/home/rbur/NeiroEva/models/agnes_lora.safetensors"
                        ref_key = "agnes"
                    else:
                        prompt_img = "masterpiece, best quality, anime style, highres, detailed face, elegant, 1girl, cat girl, long purple hair, black cat ears, black cat tail, gothic lolita dress, pale skin, red eyes, mysterious, upper body, looking at viewer"
                        lora_path = None
                        ref_key = "violet"
                    full_loc = self.get_full_location()
                    async with compute_lock:
                        image_path = await anime_gen.generate_selfie(prompt_img, full_loc, reference_key=ref_key, lora_path=lora_path)
                    with open(image_path, 'rb') as f:
                        await bot.send_photo(chat_id=chat_id, photo=f, caption=f"Вот {person}!")
                    await memory.add_conversation_turn(chat_id, "eva", f"[Фото {person}]", mood_engine.get_mood_description())
                except Exception as e:
                    logger.error(f"Ошибка генерации фото при выполнении обещания: {e}")
                req["done"] = True
                self.save()
                logger.info(f"Обещание показать {person} выполнено")

    async def update_from_dialogue(self, text: str, is_eva: bool = False):
        if not is_eva:
            return
        lowered = text.lower()

        # Сопоставление ключевых фраз с локациями (главная + дополнительная)
        location_rules = [
            # Главные локации
            (r'родной дом|мой дом|домой|к тебе', "родной дом", ""),
            (r'дом миши|к мише', "дом Миши", ""),
            (r'дом агнес|лаборатория агнес|к агнес', "дом Агнес", ""),
            (r'дом виолетты|к виолетте', "дом Виолетты", ""),
            # Дополнительные локации
            (r'кухня|на кухне', "", "кухня"),
            (r'кровать|лежу|лежать|в кровати', "", "кровать"),
            (r'подоконник|на подоконнике', "", "подоконник"),
            (r'гостиная|комната', "", "гостиная"),
            (r'парк|в парке', "парк", ""),
            (r'лес|в лесу', "лес", ""),
            (r'город|в городе', "город", ""),
            (r'кафе|в кафе', "кафе", ""),
            (r'пляж|на пляже', "пляж", ""),
            (r'автобус|в автобусе', "автобус", ""),
            (r'гости|в гостях', "гости", ""),
            (r'улица|на улице', "улица", ""),
            (r'деревня|в деревне', "деревня", ""),
        ]

        for pattern, main_loc, sub_loc in location_rules:
            if re.search(pattern, lowered):
                if main_loc:
                    await self.set_location(main_loc, sub_loc, source="диалог (упоминание)")
                else:
                    # только дополнительная локация
                    await self.set_sub_location(sub_loc, source="диалог (упоминание)")
                logger.info(f"Локация обновлена из диалога: {main_loc}/{sub_loc}")
                return

        # Движение с указанием места
        if re.search(r'\b(поехали|едем|отправляемся|направляемся|поеду|еду|приехали|добрались|идём|пойдём|поехали\s+в|едем\s+в|отправились\s+в)\b', lowered):
            match = re.search(r'(в\s+[а-яА-ЯёЁ]+|на\s+[а-яА-ЯёЁ]+|к\s+[а-яА-ЯёЁ]+)', lowered)
            if match:
                dest = match.group(0).replace('в ', '').replace('на ', '').replace('к ', '').strip()
                await self.set_location(dest, "", source="диалог (движение)")
            else:
                await self.set_location("в пути", "", source="диалог (движение)")
            return

        # Движение без указания места
        if re.search(r'\b(поеду|еду|отправляюсь|направляюсь|выхожу|ухожу|уезжаю)\b', lowered):
            await self.set_location("в пути", "", source="диалог (движение)")
            return

        # Прибытие
        if re.search(r'\b(приехала|добралась|на месте|в\s+[а-яА-ЯёЁ]+\b)', lowered):
            match = re.search(r'(в|на)\s+([а-яА-ЯёЁa-zA-Z]+)', lowered)
            if match:
                new_loc = match.group(2)
            else:
                new_loc = "неизвестном месте"
            await self.set_location(new_loc, "", source="диалог (прибытие)")
            await self.add_pending_call(random.randint(120, 300), new_loc)
            return

        # Прощание
        if re.search(r'\b(прощай|пока|до свидания|ухожу|выхожу|уезжаю)\b', lowered):
            await self.set_location("в пути, вышла из поля зрения", "", source="прощание")
            return
