from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError
import logging
import random
import asyncio
from utils.config import CREATOR_ID, LORA_AGNES_PATH
from handlers.messages import build_selfie_prompt
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    memory = context.bot_data.get("memory")
    mood_engine = context.bot_data.get("mood_engine")

    if not memory:
        await update.message.reply_text("Привет! Я Ева, но пока не могу запомнить твоё имя...")
        return

    await memory.ensure_user(user_id,
                             username=user.username,
                             first_name=user.first_name,
                             last_name=user.last_name)

    user_name = await memory.get_user_full_name(user_id)
    if not user_name:
        context.user_data['waiting_for_name'] = True
        await update.message.reply_text(
            "Привет! Я Ева. 😊 А как мне тебя называть? Напиши своё имя."
        )
        return

    await update.message.reply_text(
        f"Привет, {user_name}! Рада снова тебя видеть. 💜 Как твои дела?"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я умею:\n"
        "- Разговаривать как человек\n"
        "- Менять настроение сама по себе\n"
        "- Вести дневник (365 дней)\n"
        "- Генерировать селфи по команде /photo\n"
        "- Писать первой, когда скучаю\n"
        "Просто пиши мне."
    )

async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mood_engine = context.bot_data.get("mood_engine")
    if mood_engine:
        desc = mood_engine.get_mood_description()
        await update.message.reply_text(f"Моё настроение: {desc}")
    else:
        await update.message.reply_text("Не могу определить настроение :(")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == CREATOR_ID:
        await update.message.reply_text("Хозяин, я не могу вас заблокировать, как бы вы меня ни бесили 😤")
        return
    await update.message.reply_text("Ты не можешь меня заблокировать.")

async def location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location_manager = context.bot_data.get("location")
    if location_manager:
        loc = location_manager.current_location
        await update.message.reply_text(f"📍 Я сейчас: {loc}")
    else:
        await update.message.reply_text("Местоположение не определено.")

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id is None:
        user_id = 0
    await update.message.reply_text("📸 Ева делает селфи... Подожди до 4 минут.")
    mood_engine = context.bot_data.get("mood_engine")
    generator = context.bot_data.get("anime_gen")
    llm_engine = context.bot_data.get("llm_engine")
    compute_lock = context.bot_data.get("compute_lock")
    location_manager = context.bot_data.get("location")
    memory = context.bot_data.get("memory")
    if not generator or not llm_engine:
        await update.message.reply_text("Генератор изображений или языковая модель не загружены.")
        return

    if memory:
        await memory.ensure_user(user_id,
                                 username=update.effective_user.username,
                                 first_name=update.effective_user.first_name,
                                 last_name=update.effective_user.last_name)
        await memory.add_conversation_turn(user_id, "user", "/photo", mood_engine.get_mood_description())

    loc = location_manager.get_full_location() if location_manager else "неизвестно"
    prompt_selfie = await build_selfie_prompt(mood_engine, loc)

    try:
        async with compute_lock:
            image_path = await generator.generate_selfie(prompt_selfie, loc, reference_key="eva")
        mood_desc = mood_engine.get_mood_description()
        caption_prompt = f"""Ты только что сделала селфи. Твоё текущее настроение: {mood_desc}.
Напиши короткую подпись к этому селфи (1 предложение, с эмодзи, как живой человек).
Не упоминай, что ты ИИ. Не пиши "вот так я выгляжу". Ответ:"""
        caption = await llm_engine.generate(caption_prompt, max_tokens=50, temperature=0.7)
        if not caption or len(caption) < 5:
            caption = "✨ Момент для истории ✨"
        caption = caption.strip().strip('"')
        if memory:
            await memory.add_conversation_turn(user_id, "eva", caption, mood_desc)

        max_retries = 5
        for attempt in range(max_retries):
            try:
                with open(image_path, 'rb') as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption=caption,
                        read_timeout=300,
                        write_timeout=300,
                        connect_timeout=300,
                        pool_timeout=300
                    )
                break
            except (TimedOut, NetworkError) as e:
                logger.warning(f"Ошибка отправки (попытка {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error("Не удалось отправить фото после нескольких попыток.")
                    await update.message.reply_text("Не получилось отправить селфи, но оно сохранено на сервере.")
                else:
                    await asyncio.sleep(3)
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}", exc_info=True)
        try:
            async with compute_lock:
                image_path = await generator.generate_selfie(prompt_selfie, loc, reference_key="eva")
            mood_desc = mood_engine.get_mood_description()
            caption_prompt = f"""Ты только что сделала селфи. Твоё текущее настроение: {mood_desc}.
Напиши короткую подпись к этому селфи (1 предложение, с эмодзи, как живой человек).
Не упоминай, что ты ИИ. Не пиши "вот так я выгляжу". Ответ:"""
            caption = await llm_engine.generate(caption_prompt, max_tokens=50, temperature=0.7)
            if not caption or len(caption) < 5:
                caption = "✨ Момент для истории ✨"
            caption = caption.strip().strip('"')
            if memory:
                await memory.add_conversation_turn(user_id, "eva", caption, mood_desc)

            max_retries = 5
            for attempt in range(max_retries):
                try:
                    with open(image_path, 'rb') as f:
                        await update.message.reply_photo(
                            photo=f,
                            caption=caption,
                            read_timeout=300,
                            write_timeout=300,
                            connect_timeout=300,
                            pool_timeout=300
                        )
                    break
                except (TimedOut, NetworkError) as e2:
                    logger.warning(f"Ошибка отправки (попытка {attempt+1}/{max_retries}): {e2}")
                    if attempt == max_retries - 1:
                        logger.error("Не удалось отправить фото после нескольких попыток.")
                        await update.message.reply_text("Не получилось отправить селфи, но оно сохранено на сервере.")
                    else:
                        await asyncio.sleep(3)
        except Exception as e2:
            logger.error(f"Повторная ошибка генерации: {e2}", exc_info=True)
            await update.message.reply_text("Не получилось сделать селфи, попробуй позже.")
            if memory:
                await memory.add_conversation_turn(user_id, "eva", "Не получилось сделать селфи", mood_engine.get_mood_description())

async def show_agnes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Команда /show_agnes")
    user_id = update.effective_user.id
    if user_id is None:
        user_id = 0
    await update.message.reply_text("🔍 Показываю Агнес...")
    generator = context.bot_data.get("anime_gen")
    compute_lock = context.bot_data.get("compute_lock")
    location_manager = context.bot_data.get("location")
    memory = context.bot_data.get("memory")
    mood_engine = context.bot_data.get("mood_engine")
    if not generator:
        await update.message.reply_text("Генератор не загружен.")
        return
    if memory:
        await memory.ensure_user(user_id,
                                 username=update.effective_user.username,
                                 first_name=update.effective_user.first_name,
                                 last_name=update.effective_user.last_name)
        await memory.add_conversation_turn(user_id, "user", "/show_agnes", mood_engine.get_mood_description())
    loc = location_manager.current_location if location_manager else "неизвестно"
    prompt = (
        "masterpiece, best quality, anime style, highres, detailed face, "
        "1girl, horse girl, horse ears, horse tail, short messy brown hair, ahoge, hair between eyes, "
        "red eyes, single earring, white lab coat, yellow sweater vest, black collared shirt, black necktie, "
        "waist up, upper body, science lab background, "
        "confident expression, holding a test tube, detailed clothing"
    )
    negative_prompt = "cat ears, cat tail, pink hair, purple hair, school uniform, pink eyes, extra horse, two horses, multiple horses, duplicate horse, background horse, full body, legs, feet, shoes, deformed, bad anatomy"
    lora_path = LORA_AGNES_PATH if LORA_AGNES_PATH.exists() else None
    try:
        async with compute_lock:
            image_path = await generator.generate_selfie(prompt, loc, reference_key="agnes", lora_path=lora_path, negative_prompt=negative_prompt)
        with open(image_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption="🐴 Агнес Такион")
        if memory:
            await memory.add_conversation_turn(user_id, "eva", "[Фото Агнес]", mood_engine.get_mood_description())
    except Exception as e:
        logger.error(f"Ошибка генерации Агнес: {e}", exc_info=True)
        await update.message.reply_text("Не получилось показать Агнес.")
        if memory:
            await memory.add_conversation_turn(user_id, "eva", "Не получилось показать Агнес", mood_engine.get_mood_description())

async def show_violet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Команда /show_violet")
    user_id = update.effective_user.id
    if user_id is None:
        user_id = 0
    await update.message.reply_text("🔍 Показываю Виолетту...")
    generator = context.bot_data.get("anime_gen")
    compute_lock = context.bot_data.get("compute_lock")
    location_manager = context.bot_data.get("location")
    memory = context.bot_data.get("memory")
    mood_engine = context.bot_data.get("mood_engine")
    if not generator:
        await update.message.reply_text("Генератор не загружен.")
        return
    if memory:
        await memory.ensure_user(user_id,
                                 username=update.effective_user.username,
                                 first_name=update.effective_user.first_name,
                                 last_name=update.effective_user.last_name)
        await memory.add_conversation_turn(user_id, "user", "/show_violet", mood_engine.get_mood_description())
    loc = location_manager.current_location if location_manager else "неизвестно"
    prompt = (
        "masterpiece, best quality, anime style, highres, detailed face, elegant, "
        "1girl, cat girl, long purple hair, black cat ears, black cat tail, gothic lolita dress, "
        "pale skin, red eyes, mysterious, waist up, upper body, dark gothic room, candles, books, "
        "detailed lace, elegant pose, looking at viewer with a calm expression"
    )
    negative_prompt = "pink hair, school uniform, pink eyes, horse ears, horse tail, lab coat, full body, legs, feet, shoes, extra limbs, deformed, bad anatomy"
    try:
        async with compute_lock:
            image_path = await generator.generate_selfie(prompt, loc, reference_key="violet", negative_prompt=negative_prompt)
        with open(image_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption="🐱 Виолетта (готическая кошка)")
        if memory:
            await memory.add_conversation_turn(user_id, "eva", "[Фото Виолетты]", mood_engine.get_mood_description())
    except Exception as e:
        logger.error(f"Ошибка генерации Виолетты: {e}", exc_info=True)
        await update.message.reply_text("Не получилось показать Виолетту.")
        if memory:
            await memory.add_conversation_turn(user_id, "eva", "Не получилось показать Виолетту", mood_engine.get_mood_description())

# ---------- СЕКРЕТНАЯ КОМАНДА ДЛЯ СОЗДАТЕЛЯ ----------
async def badabadad_secret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Секретная команда — только для создателя."""
    user_id = update.effective_user.id
    if user_id != CREATOR_ID:
        await update.message.reply_text("Ой, это секретная команда! Только для Миши 💜")
        return

    logger.info("Команда /badabadad_secre (секретная Виолетта)")
    await update.message.reply_text("🔮 Открываю секретную дверь...")

    generator = context.bot_data.get("anime_gen")
    compute_lock = context.bot_data.get("compute_lock")
    location_manager = context.bot_data.get("location")
    memory = context.bot_data.get("memory")
    mood_engine = context.bot_data.get("mood_engine")

    if not generator:
        await update.message.reply_text("Генератор не загружен.")
        return
    if memory:
        await memory.ensure_user(user_id,
                                 username=update.effective_user.username,
                                 first_name=update.effective_user.first_name,
                                 last_name=update.effective_user.last_name)
        await memory.add_conversation_turn(user_id, "user", "/badabadad_secret", mood_engine.get_mood_description())
    loc = location_manager.current_location if location_manager else "неизвестно"
    prompt = (
        "(masterpiece, best quality:1.2), 1girl, cat girl, pink hair, pink cat ears, pink cat tail, pink eyes, (sitting on couch:1.2), (leaning forward:1.3), (upper body lowered toward viewer:1.4), (from below angle:1.3), (face close to viewer:1.2), (predatory smile:1.5), (dangerous smirk:1.4), (sharp fangs visible:1.3), (hungry, lustful gaze:1.4), (intense eye contact:1.3), (black lace lingerie, revealing:1.3), (messy pink hair falling forward:1.2), (one hand gripping couch arm, other hand reaching toward viewer:1.3), (intimate bedroom setting, dim warm lighting, candles, soft shadows, plush couch, velvet pillows:1.2), (dominant, aggressive, seductive:1.4), (waist up, upper body:1.2)"
    )
    negative_prompt = (
        "EasyNegative, (worst quality, low quality:1.4), (bad anatomy, deformed:1.3), (extra limbs, extra fingers:1.3), (blurry, ugly:1.2), (horse ears, horse tail:1.3), (legs, feet, shoes:1.4), (full body:1.3), (innocent, cute, shy, blushing:1.4), (looking away, closed eyes:1.3), (second person, multiple girls, duo:1.5)"
    )
    try:
        async with compute_lock:
            image_path = await generator.generate_selfie(prompt, loc, reference_key="eva", negative_prompt=negative_prompt)
        with open(image_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption="🐱 Секретная Виолетта")
        if memory:
            await memory.add_conversation_turn(user_id, "eva", "[Фото Секрет]", mood_engine.get_mood_description())
    except Exception as e:
        logger.error(f"Ошибка генерации секретной картинки: {e}", exc_info=True)
        await update.message.reply_text("Не получилось показать секрет.")
        if memory:
            await memory.add_conversation_turn(user_id, "eva", "Не получилось показать секрет", mood_engine.get_mood_description())
