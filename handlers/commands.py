from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError
import logging
import random
import asyncio
from utils.config import CREATOR_ID

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"Привет, {user.first_name}! Я Ева, твоя нейроЕва. Готова болтать и делиться настроением 💜")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я умею:\n"
        "- Разговаривать как человек\n"
        "- Менять настроение сама по себе\n"
        "- Вести дневник (365 дней)\n"
        "- Генерировать селфи по команде /photo\n"
        "- Показывать подруг: /show_agnes (Агнес Такион) и /show_violet (Виолетта)\n"
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
    await update.message.reply_text("📸 Ева делает селфи... Подожди до 4 минут.")
    mood_engine = context.bot_data.get("mood_engine")
    generator = context.bot_data.get("anime_gen")
    llm_engine = context.bot_data.get("llm_engine")
    compute_lock = context.bot_data.get("compute_lock")
    location_manager = context.bot_data.get("location")
    if not generator or not llm_engine:
        await update.message.reply_text("Генератор изображений или языковая модель не загружены.")
        return

    mood_score = mood_engine.mood_score
    horny = mood_engine.horny_level

    quality_tags = "masterpiece, best quality, anime screencap"
    character_tags = "1girl, purple hair, brown eyes, solo, looking at viewer"
    if mood_score > 0.7:
        mood_tag = "smile, happy, blush"
    elif mood_score < 0.3:
        mood_tag = "sad, crying, tears"
    else:
        mood_tag = "neutral expression, straight face"
    if horny > 0.6:
        mood_tag += ", playful, seductive smile"
    random_tag = ""
    if random.random() > 0.7:
        random_tag = f", {random.choice(['from side', 'close-up', 'upper body', 'sitting', 'standing'])}"
    prompt = f"{quality_tags}, {character_tags}, {mood_tag}{random_tag}"

    try:
        loc = location_manager.current_location if location_manager else "неизвестно"
        async with compute_lock:
            image_path = await generator.generate_selfie(prompt, loc, reference_key="eva")
        # Генерация подписи
        mood_desc = mood_engine.get_mood_description()
        caption_prompt = f"""Ты только что сделала селфи. Твоё текущее настроение: {mood_desc}. 
Напиши короткую подпись к этому селфи (1 предложение, с эмодзи, как живой человек). 
Не упоминай, что ты ИИ. Не пиши "вот так я выгляжу". Ответ:"""
        caption = await llm_engine.generate(caption_prompt, max_tokens=50, temperature=0.7)
        if not caption or len(caption) < 5:
            caption = "✨ Момент для истории ✨"
        caption = caption.strip().strip('"')

        # Отправка фото
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
        await update.message.reply_text("Не получилось сделать селфи, попробуй позже.")

# --- Показ подруг через отдельные команды ---
async def show_agnes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Показываю Агнес...")
    generator = context.bot_data.get("anime_gen")
    compute_lock = context.bot_data.get("compute_lock")
    location_manager = context.bot_data.get("location")
    if not generator:
        await update.message.reply_text("Генератор не загружен.")
        return
    loc = location_manager.current_location if location_manager else "неизвестно"
    
    prompt = (
        "masterpiece, best quality, anime style, highres, detailed face,"
        "1girl, agnes tachyon, horse_girl, horse ears, horse tail, upper body,"
        "short messy brown hair, ahoge, red eyes, empty eyes,"
        "single earring, labcoat, sleeves past fingers, yellow sweater vest,"
        "black shirt, black necktie, pantyhose, white high heels,"
        "looking at viewer"
    )
    negative_prompt = (
        "cat ears, cat tail, pink hair, purple hair, school uniform, pink eyes, "
        "realistic horse, quadruped, animal, horse standing, horse beside, "
        "extra limbs, bad anatomy, bad hands, blurry, low quality"
    )
    lora_path = "/home/rbur/NeiroEva/models/agnes_lora.safetensors"
    
    try:
        async with compute_lock:
            image_path = await generator.generate_selfie(prompt, loc, reference_key="agnes", lora_path=lora_path, negative_prompt=negative_prompt)
        with open(image_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption="🐴 Агнес Такион")
    except Exception as e:
        logger.error(f"Ошибка генерации Агнес: {e}", exc_info=True)
        await update.message.reply_text("Не получилось показать Агнес.")

async def show_violet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Команда /show_violet")
    await update.message.reply_text("🔍 Показываю Виолетту...")
    generator = context.bot_data.get("anime_gen")
    compute_lock = context.bot_data.get("compute_lock")
    location_manager = context.bot_data.get("location")
    if not generator:
        await update.message.reply_text("Генератор не загружен.")
        return
    loc = location_manager.current_location if location_manager else "неизвестно"
    prompt = (
        "masterpiece, best quality, anime style, highres, detailed face, elegant, "
        "1girl, cat girl, long purple hair, black cat ears, black cat tail, gothic lolita dress, "
        "pale skin, red eyes, mysterious, waist up"
    )
    negative_prompt = (
    "pink hair, pink eyes, horse ears, horse tail, lab coat, "
    "full body, long shot, distant, low quality, worst quality, bad anatomy, "
    "bad hands, extra fingers, fewer fingers, mutated hands, ugly, deformed"
)
    try:
        async with compute_lock:
            image_path = await generator.generate_selfie(prompt, loc, reference_key="violet", negative_prompt=negative_prompt)
        with open(image_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption="🐱 Виолетта (готическая кошка)")
    except Exception as e:
        logger.error(f"Ошибка генерации Виолетты: {e}", exc_info=True)
        await update.message.reply_text("Не получилось показать Виолетту.")
