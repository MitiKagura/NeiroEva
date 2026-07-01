import json
import asyncio
import logging
import random
import re
from pathlib import Path
from datetime import datetime
from utils.config import LORA_AGNES_PATH

logger = logging.getLogger(__name__)

class LocationManager:
    # Список допустимых главных локаций (совпадает с location_map в генераторах)
    ALLOWED_LOCATIONS = {
        "родной дом", "дом Миши", "дом Агнес", "дом Виолетты",
        "подоконник", "кровать", "кухня", "парк", "лес", "город",
        "кафе", "пляж", "автобус", "гости", "улица", "деревня",
        "в пути"
    }
    # Дополнительные локации (сублокации)
    ALLOWED_SUB_LOCATIONS = {"кухня", "кровать", "подоконник", "гостиная"}

    def __init__(self, data_path: Path):
        self.data_path = data_path
        self.current_location = "родной дом"  # главная локация
        self.sub_location = ""  # дополнительная локация
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
                # Проверяем, что загруженная локация допустима
                if self.current_location not in self.ALLOWED_LOCATIONS:
                    logger.warning(f"Загружена недопустимая локация: {self.current_location}, сбрасываем на 'родной дом'")
                    self.current_location = "родной дом"
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
        # Проверка допустимости
        if main_location not in self.ALLOWED_LOCATIONS:
            logger.warning(f"Попытка установить недопустимую локацию: {main_location}, игнорируем")
            return
        if sub_location and sub_location not in self.ALLOWED_SUB_LOCATIONS:
            logger.warning(f"Попытка установить недопустимую сублокацию: {sub_location}, игнорируем")
            sub_location = ""
        old_main = self.current_location
        old_sub = self.sub_location
        self.current_location = main_location
        self.sub_location = sub_location
        self.save()
        logger.info(f"Локация изменена: {old_main}/{old_sub} -> {main_location}/{sub_location} (источник: {source})")

    async def set_sub_location(self, sub_location: str, source: str = "context"):
        if sub_location not in self.ALLOWED_SUB_LOCATIONS:
            logger.warning(f"Попытка установить недопустимую сублокацию: {sub_location}, игнорируем")
            return
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
                        lora_path = str(LORA_AGNES_PATH) if LORA_AGNES_PATH.exists() else None
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

        # Сначала проверяем явные упоминания локаций из белого списка
        for loc in self.ALLOWED_LOCATIONS:
            if loc in lowered:
                # Проверяем, не является ли это частью другой фразы (например, "дом" в "домой" может быть частью)
                # Для простоты используем границы слова
                if re.search(rf'\b{re.escape(loc)}\b', lowered):
                    await self.set_location(loc, "", source="диалог (упоминание)")
                    logger.info(f"Локация обновлена из диалога: {loc}")
                    return

        # Проверяем сублокации (они могут быть частью главной локации)
        for sub in self.ALLOWED_SUB_LOCATIONS:
            if sub in lowered and re.search(rf'\b{re.escape(sub)}\b', lowered):
                await self.set_sub_location(sub, source="диалог (упоминание)")
                logger.info(f"Сублокация обновлена из диалога: {sub}")
                return

        # Движение с указанием места (извлекаем только из белого списка)
        if re.search(r'\b(поехали|едем|отправляемся|направляемся|поеду|еду|приехали|добрались|идём|пойдём|поехали\s+в|едем\s+в|отправились\s+в)\b', lowered):
            # Ищем совпадение с одной из допустимых локаций после предлога
            for loc in self.ALLOWED_LOCATIONS:
                if re.search(rf'(в|на|к)\s+{re.escape(loc)}', lowered):
                    await self.set_location(loc, "", source="диалог (движение)")
                    logger.info(f"Локация обновлена из диалога (движение): {loc}")
                    return
            # Если не нашли, но есть движение — устанавливаем "в пути"
            await self.set_location("в пути", "", source="диалог (движение)")
            return

        # Прибытие
        if re.search(r'\b(приехала|добралась|на месте|в\s+[а-яА-ЯёЁa-zA-Z]+\b)', lowered):
            # Ищем совпадение с локацией после предлога "в" или "на"
            for loc in self.ALLOWED_LOCATIONS:
                if re.search(rf'(в|на)\s+{re.escape(loc)}', lowered):
                    await self.set_location(loc, "", source="диалог (прибытие)")
                    # Запланировать звонок через случайное время
                    await self.add_pending_call(random.randint(120, 300), loc)
                    return
            # Если не нашли конкретную локацию, но прибыла — оставляем текущую или ставим "неизвестно"
            # Но лучше оставить текущую, чтобы не создавать мусор
            logger.info("Прибытие без указания конкретной локации, оставляем текущую")
            return

        # Прощание
        if re.search(r'\b(прощай|пока|до свидания|ухожу|выхожу|уезжаю)\b', lowered):
            await self.set_location("в пути", "", source="прощание")
            return

        # Если ничего не сработало — ничего не меняем
