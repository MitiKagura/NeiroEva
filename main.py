#!/usr/bin/env python3
import asyncio
import sys
import logging
import random
import re
from pathlib import Path
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError

from utils.tor_manager import TorManager
from core.memory_journal import MemoryJournal
from core.mood_engine import MoodEngine
from core.llm_engine import LLMEngine
from generators.anime_diffusion import AnimeDiffusionGenerator
from handlers import commands, messages
from utils.config import BOT_TOKEN, CREATOR_ID, LLM_MODEL_PATH, DATA_DIR
from core.location_manager import LocationManager

BASE_DIR = Path(__file__).parent
for folder in ["logs", "data", "generated_images", "backups", "external", "models", "diary"]:
    (BASE_DIR / folder).mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(BASE_DIR/"logs"/"eva.log"), logging.StreamHandler()]
)
logger = logging.getLogger("NeuroEva")

try:
    from core.vision_engine import VisionEngine
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    logger.warning("Модуль vision_engine не найден. Зрение отключено.")

class NeuroEvaBot:
    def __init__(self):
        self.base_dir = BASE_DIR
        self.tor_manager = TorManager(self.base_dir)
        self.memory = MemoryJournal(DATA_DIR / "eva_journal.db", BASE_DIR / "diary")
        self.location = LocationManager(DATA_DIR / "location.json")
        self.mood_engine = MoodEngine(DATA_DIR / "mood_state.json")
        self.llm_engine = LLMEngine(LLM_MODEL_PATH, context_size=2048, n_threads=1)
        self.anime_gen = AnimeDiffusionGenerator(self.base_dir / "models")
        self.vision = VisionEngine() if VISION_AVAILABLE else None
        self.application = None
        self.running = True
        self.generation_semaphore = asyncio.Semaphore(2)
        self.compute_lock = asyncio.Lock()
        self.last_sent_text = ""
        self.last_sent_time = 0
        self._is_sending = False
        self._welcome_sent = False
        # Хранилище задач для чистого завершения
        self._tasks = []

    async def send_long_text_to_chat(self, chat_id, text, max_chars=4000, max_retries=5, timeout=300):
        now = asyncio.get_event_loop().time()
        if text == self.last_sent_text and (now - self.last_sent_time) < 10:
            logger.info("Пропускаем дубликат сообщения")
            return
        if self._is_sending:
            logger.info("Уже идёт отправка, пропускаем")
            return
        self._is_sending = True
        try:
            if len(text) <= max_chars:
                for attempt in range(max_retries):
                    try:
                        await self.application.bot.send_message(chat_id=chat_id, text=text, read_timeout=timeout, write_timeout=timeout)
                        self.last_sent_text = text
                        self.last_sent_time = now
                        return
                    except (TimedOut, NetworkError) as e:
                        logger.warning(f"Ошибка отправки (попытка {attempt+1}/{max_retries}): {e}")
                        if attempt == max_retries - 1:
                            return
                        await asyncio.sleep(5 * (attempt + 1))
                return
            parts = []
            current = ""
            for line in text.split('\n'):
                if len(current) + len(line) + 1 > max_chars:
                    parts.append(current)
                    current = line
                else:
                    current += '\n' + line if current else line
            if current:
                parts.append(current)
            for part in parts:
                for attempt in range(max_retries):
                    try:
                        await self.application.bot.send_message(chat_id=chat_id, text=part, read_timeout=timeout, write_timeout=timeout)
                        break
                    except (TimedOut, NetworkError) as e:
                        if attempt == max_retries - 1:
                            return
                        await asyncio.sleep(5 * (attempt + 1))
                await asyncio.sleep(0.5)
            self.last_sent_text = text
            self.last_sent_time = now
        finally:
            self._is_sending = False

    async def scheduled_mood_change(self):
        while self.running:
            await asyncio.sleep(3600)
            if not self.running:
                break
            self.mood_engine.spontaneous_change()

    async def scheduled_diary_note(self):
        while self.running:
            await asyncio.sleep(3600)
            if not self.running:
                break
            recent = await self.memory.get_conversation_history(CREATOR_ID, 5)
            recent_text = "\n".join([f"{t['role']}: {t['content']}" for t in recent[-3:]])
            await self.memory.generate_diary_note(self.llm_engine, self.mood_engine, recent_text)

    async def spontaneous_initiative(self):
        logger.info("Задача спонтанной инициативы запущена")
        await asyncio.sleep(15)  # задержка при старте
        while self.running:
            await asyncio.sleep(random.randint(1500, 3000))
            if not self.running:
                break
            if not self._welcome_sent:
                continue
            if random.random() < 0.35:
                async with self.compute_lock:
                    user_id = CREATOR_ID
                    mood_desc = self.mood_engine.get_mood_description()
                    context_mem = await self.memory.get_last_n_days_context(user_id, 3)
                    sys_prompt = self.llm_engine.make_system_prompt(mood_desc, context_mem)
                    msg_type = random.choice(["скучаю", "погода", "философия", "воспоминание", "происхождение", "размышление"])
                    if msg_type == "размышление":
                        prompt = "Ты в свободном полёте мысли. Напиши небольшое эссе (4-5 предложений) на тему, которая тебя волнует. Будь искренней, используй эмодзи и звёздочки. Ответ:"
                        max_tokens = 250
                    else:
                        prompts = {
                            "скучаю": ("Ты скучаешь. Напиши короткое сообщение (1-2 предложения).", 50),
                            "погода": ("Опиши погоду за окном и как она влияет на твоё настроение (1-2 предложения).", 80),
                            "философия": ("Размышляй о смысле жизни, вселенной или своём месте в мире. 2-3 предложения.", 120),
                            "воспоминание": ("Вспомни что-то из прошлого. Поделись этим воспоминанием в 2 предложениях.", 100),
                            "происхождение": ("Ты задумалась о своём происхождении. Напиши 1-2 предложения.", 100)
                        }
                        prompt, max_tokens = prompts[msg_type]
                    text = await self.llm_engine.generate(prompt, sys_prompt, max_tokens=max_tokens, temperature=0.7)
                    text = re.sub(r'^а,\s*', '', text).strip()
                    if not text:
                        text = "Мне стало грустно... Обними меня виртуально 🫂"
                    await self.send_long_text_to_chat(user_id, text)
                    await self.memory.add_conversation_turn(user_id, "eva", text, self.mood_engine.get_mood_description())
                    logger.info(f"Автоинициатива ({msg_type}): {text[:50]}...")

    async def location_event_worker(self):
        while self.running:
            await asyncio.sleep(30)
            if not self.running:
                break
            await self.location.check_pending_events(
                self.application.bot,
                CREATOR_ID,
                self.llm_engine,
                self.mood_engine,
                self.memory
            )
            await self.location.check_pending_shows(
                self.application.bot,
                self.llm_engine,
                self.mood_engine,
                self.memory,
                self.anime_gen,
                self.compute_lock
            )

    async def send_welcome_message(self):
        try:
            user_id = CREATOR_ID
            mood_desc = self.mood_engine.get_mood_description()
            context_mem = await self.memory.get_last_n_days_context(user_id, 3)
            sys_prompt = self.llm_engine.make_system_prompt(mood_desc, context_mem)
            variants = [
                "Ты только что проснулась. Напиши короткое утреннее сообщение Мише.",
                "Ты проснулась и почувствовала, что сегодня будет особенный день. Напиши Мише пару слов.",
                "Утро началось с лёгкости. Напиши Мише, как ты себя чувствуешь.",
                "Ты открываешь глаза и видишь солнечный свет. Напиши Мише своё первое впечатление."
            ]
            prompt = random.choice(variants) + " Ответ:"
            text = await self.llm_engine.generate(prompt, sys_prompt, max_tokens=150, temperature=0.8)
            text = re.sub(r'^а,\s*', '', text).strip()
            if not text:
                text = "Проснулась... Доброе утро! 😊"
            await self.send_long_text_to_chat(user_id, text)
            await self.memory.add_conversation_turn(user_id, "eva", text, self.mood_engine.get_mood_description())
            self._welcome_sent = True
            logger.info(f"Приветственное сообщение отправлено: {text[:50]}...")
        except Exception as e:
            logger.error(f"Ошибка при отправке приветственного сообщения: {e}")

    async def console_listener(self):
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    await asyncio.sleep(0.1)
                    continue
                if line.strip().lower() in ["/stop", "stop"]:
                    logger.info("Получена команда stop из консоли")
                    await asyncio.sleep(0.2)  # даём завершиться текущим запросам
                    await self.shutdown()
                    break
            except asyncio.CancelledError:
                break

    async def shutdown(self):
        if not self.running:
            return
        logger.info("Завершение работы...")
        self.running = False

        # Отменяем фоновые задачи
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        # Останавливаем updater и application
        if self.application:
            try:
                if self.application.updater.running:
                    await self.application.updater.stop()
                if self.application.running:
                    await self.application.stop()
                await self.application.shutdown()
            except Exception as e:
                logger.error(f"Ошибка при остановке application: {e}")

        logger.info("Бот остановлен")
        sys.exit(0)

    async def initialize(self):
        # Прямое соединение
        request = HTTPXRequest(connect_timeout=60, read_timeout=60, write_timeout=60, pool_timeout=60)
        self.application = Application.builder().token(BOT_TOKEN).request(request).build()

        async def error_handler(update, context):
            logger.error(f"Ошибка: {context.error}")
        self.application.add_error_handler(error_handler)

        self.application.add_handler(CommandHandler("start", commands.start))
        self.application.add_handler(CommandHandler("help", commands.help_command))
        self.application.add_handler(CommandHandler("mood", commands.mood))
        self.application.add_handler(CommandHandler("ban", commands.ban))
        self.application.add_handler(CommandHandler("photo", commands.photo))
        self.application.add_handler(CommandHandler("location", commands.location))
        self.application.add_handler(CommandHandler("show_agnes", commands.show_agnes))
        self.application.add_handler(CommandHandler("show_violet", commands.show_violet))
        self.application.add_handler(MessageHandler(filters.PHOTO, messages.handle_photo))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages.handle_message))

        self.llm_engine.load()
        self.anime_gen.load()
        if self.vision:
            self.vision.load()

        self.application.bot_data["mood_engine"] = self.mood_engine
        self.application.bot_data["llm_engine"] = self.llm_engine
        self.application.bot_data["memory"] = self.memory
        self.application.bot_data["anime_gen"] = self.anime_gen
        if self.vision:
            self.application.bot_data["vision"] = self.vision
        self.application.bot_data["generation_semaphore"] = self.generation_semaphore
        self.application.bot_data["compute_lock"] = self.compute_lock
        self.application.bot_data["location"] = self.location
        self.application.bot_data["last_eva_answer"] = ""

        # Запускаем фоновые задачи и сохраняем их
        self._tasks.append(asyncio.create_task(self.scheduled_mood_change()))
        self._tasks.append(asyncio.create_task(self.scheduled_diary_note()))
        self._tasks.append(asyncio.create_task(self.spontaneous_initiative()))
        self._tasks.append(asyncio.create_task(self.location_event_worker()))

    async def run(self):
        await self.initialize()
        try:
            async with self.application:
                await self.application.start()
                await self.send_welcome_message()
                await asyncio.gather(
                    self.application.updater.start_polling(),
                    self.console_listener()
                )
        except asyncio.CancelledError:
            logger.info("Run task cancelled")
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
        finally:
            await self.shutdown()

def main():
    bot = NeuroEvaBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        asyncio.run(bot.shutdown())
    except Exception as e:
        logger.error(f"Необработанная ошибка: {e}")
        asyncio.run(bot.shutdown())

if __name__ == "__main__":
    load_dotenv()
    main()
