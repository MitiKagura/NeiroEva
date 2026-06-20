import logging
import random
import re
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError

logger = logging.getLogger(__name__)

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ОТПРАВКИ ----------
async def send_with_retry(update: Update, text: str, max_retries=5, timeout=300):
    for attempt in range(max_retries):
        try:
            await update.message.reply_text(text, read_timeout=timeout, write_timeout=timeout, connect_timeout=timeout)
            return
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Ошибка отправки текста (попытка {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                logger.error("Не удалось отправить текст после нескольких попыток")
                return
            await asyncio.sleep(5 * (attempt + 1))

async def send_photo_with_retry(update: Update, photo_path, caption, max_retries=5, timeout=300):
    for attempt in range(max_retries):
        try:
            with open(photo_path, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=caption,
                    read_timeout=timeout,
                    write_timeout=timeout,
                    connect_timeout=timeout
                )
            return
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Ошибка отправки фото (попытка {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                logger.error("Не удалось отправить фото после нескольких попыток")
                raise
            await asyncio.sleep(5 * (attempt + 1))

# ---------- ПОСТРОЕНИЕ ПРОМПТОВ ----------
async def build_selfie_prompt(mood_engine, location: str = "неизвестно") -> str:
    mood_score = mood_engine.mood_score
    horny = mood_engine.horny_level
    if mood_score > 0.7:
        mood_tag = "happy, smile"
    elif mood_score < 0.3:
        mood_tag = "sad, crying"
    else:
        mood_tag = "neutral expression"
    if horny > 0.6:
        mood_tag += ", playful"
    return f"masterpiece, best quality, 1girl, dark blue hair, dark blue eyes, cat ears, cat tail, {mood_tag}, location: {location}, anime style, highres, detailed face, looking at viewer"

async def build_friend_prompt(mood_engine, friend_type: str, location: str) -> str:
    if friend_type == "agnes":
        return (
            "masterpiece, best quality, anime style, highres, detailed face, cute\n"
            "1girl, horse girl, horse ears, horse tail, short messy brown hair, red eyes, "
            "wearing a long white lab coat, yellow sweater vest, black collared shirt, black necktie, "
            "black pantyhose, white heeled boots, standing, full body\n"
            f"location: {location}"
        )
    else:  # violet
        return (
            "masterpiece, best quality, anime style, highres, detailed face, elegant\n"
            "1girl, cat girl, long purple hair, black cat ears, black cat tail, gothic lolita dress, "
            "pale skin, red eyes, mysterious, standing, full body\n"
            f"location: {location}"
        )

async def build_scene_prompt(mood_engine, scene_type: str, location: str) -> str:
    base = "masterpiece, best quality, anime style, detailed background"
    if scene_type == "forest":
        return f"{base}, forest, tall trees, sunlight through leaves, path, mystical atmosphere, {location}"
    elif scene_type == "home":
        return f"{base}, cozy room, wooden furniture, window with view, cat toys, warm lighting, {location}"
    elif scene_type == "city":
        return f"{base}, city street, neon lights, evening, reflections, anime cityscape, {location}"
    else:
        return f"{base}, {location}, peaceful scenery, high quality"

# ---------- ОБРАБОТЧИК ФОТО ----------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Получено фото")
    mood_engine = context.bot_data.get("mood_engine")
    memory = context.bot_data.get("memory")
    vision = context.bot_data.get("vision")
    llm = context.bot_data.get("llm_engine")
    if not vision or not llm:
        await update.message.reply_text("Пока не умею смотреть фото.")
        return
    try:
        photo = update.message.photo[-1]
        for attempt in range(3):
            try:
                file = await context.bot.get_file(photo.file_id)
                image_bytes = await file.download_as_bytearray()
                break
            except (TimedOut, NetworkError) as e:
                logger.warning(f"Ошибка скачивания фото (попытка {attempt+1}/3): {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(3 * (attempt + 1))
        eng_caption = await vision.describe_image(bytes(image_bytes))
        logger.info(f"Английское описание: {eng_caption}")
        mood_desc = mood_engine.get_mood_description()
        prompt = f"""Ты Ева. Твоё настроение: {mood_desc}.
Пользователь отправил фото, которое описывается как: "{eng_caption}".
Напиши короткое (1-2 предложения) субъективное впечатление об этом фото на русском языке, как живой человек. Пиши только по-русски. Ответ:"""
        sys_prompt = "Ты говоришь только по-русски, без английских слов."
        try:
            russian_reaction = await asyncio.wait_for(
                llm.generate(prompt, sys_prompt, max_tokens=60, temperature=0.7),
                timeout=120.0
            )
        except asyncio.TimeoutError:
            logger.warning("Таймаут генерации ответа на фото")
            russian_reaction = "Интересное фото! 😊"
        if not russian_reaction or len(russian_reaction.strip()) < 3:
            russian_reaction = "Красивое фото!"
        await update.message.reply_text(f"*смотрит фото* {russian_reaction}")
        if memory:
            await memory.add_conversation_turn("user", f"[Фото: {eng_caption}]", mood_desc)
            await memory.add_conversation_turn("eva", russian_reaction, mood_engine.get_mood_description())
        return
    except Exception as e:
        logger.error(f"Ошибка фото: {e}", exc_info=True)
        await update.message.reply_text("Не получилось разобрать фото.")
        return

# ---------- ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    if not user_text:
        return
    logger.info(f"Обработка сообщения: {user_text}")

    mood_engine = context.bot_data.get("mood_engine")
    llm_engine = context.bot_data.get("llm_engine")
    memory = context.bot_data.get("memory")
    generator = context.bot_data.get("anime_gen")
    compute_lock = context.bot_data.get("compute_lock")
    location_manager = context.bot_data.get("location")

    if not mood_engine or not llm_engine:
        logger.error("Отсутствуют необходимые компоненты")
        return

    text_lower = user_text.lower()

    # ----- Прямая команда "Покажи Агнес" -----
    if user_text.lower().startswith("покажи агнес") or user_text.lower().startswith("покажи агнесс"):
        logger.info("Прямая команда: покажи Агнес")
        await send_with_retry(update, "🔍 Показываю Агнес...")
        loc = location_manager.current_location if location_manager else "неизвестно"
        prompt_friend = (
            "masterpiece, best quality, anime style, highres, detailed face, "
            "1girl, horse girl, horse ears, horse tail, short messy brown hair, red eyes, "
            "wearing a long white lab coat, yellow sweater vest, black collared shirt, black necktie, "
            "black pantyhose, white heeled boots, standing, full body"
        )
        negative = "cat ears, cat tail, pink hair, purple hair, school uniform, pink eyes"
        try:
            async with compute_lock:
                image_path = await generator.generate_selfie(prompt_friend, loc, use_reference=False, negative_prompt=negative)
            await send_photo_with_retry(update, image_path, "🐴 Агнес Такион")
        except Exception as e:
            logger.error(f"Ошибка генерации Агнес: {e}", exc_info=True)
            await send_with_retry(update, "Не получилось показать Агнес.")
        return

    # ----- Селфи -----
    if re.search(r'(покажи\s+себя|покажись|сделай\s+селфи|своё\s+фото|в\s+полный\s+рост)', text_lower):
        logger.info("Команда селфи")
        await send_with_retry(update, "📸 Сейчас сделаю селфи...")
        loc = location_manager.current_location if location_manager else "неизвестно"
        prompt_selfie = await build_selfie_prompt(mood_engine, loc)
        try:
            async with compute_lock:
                image_path = await generator.generate_selfie(prompt_selfie, loc, use_reference=True)
            await send_photo_with_retry(update, image_path, "Вот как я выгляжу 💜")
        except Exception as e:
            logger.error(f"Ошибка генерации селфи: {e}")
            await send_with_retry(update, "Не получилось сделать селфи, попробуй позже.")
        return

    # ----- Показ леса, дома, города, подруг -----
    if text_lower.startswith("покажи") and "себя" not in text_lower:
        logger.info("Блок показа окружения/подруг")
        query = text_lower[6:].strip()
        logger.info(f"Запрос после 'покажи': '{query}'")

        if "лес" in query or "деревья" in query:
            await send_with_retry(update, "🔍 Показываю лес...")
            loc = location_manager.current_location if location_manager else "неизвестно"
            prompt_scene = await build_scene_prompt(mood_engine, "forest", loc)
            try:
                async with compute_lock:
                    image_path = await generator.generate_selfie(prompt_scene, loc, use_reference=False)
                await send_photo_with_retry(update, image_path, "🌲 Лес")
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await send_with_retry(update, "Не могу показать лес.")
            return
        if "дом" in query or "комнат" in query:
            await send_with_retry(update, "🔍 Показываю дом...")
            loc = location_manager.current_location if location_manager else "неизвестно"
            prompt_scene = await build_scene_prompt(mood_engine, "home", loc)
            try:
                async with compute_lock:
                    image_path = await generator.generate_selfie(prompt_scene, loc, use_reference=False)
                await send_photo_with_retry(update, image_path, "🏠 Дом")
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await send_with_retry(update, "Не могу показать дом.")
            return
        if "город" in query or "улиц" in query:
            await send_with_retry(update, "🔍 Показываю город...")
            loc = location_manager.current_location if location_manager else "неизвестно"
            prompt_scene = await build_scene_prompt(mood_engine, "city", loc)
            try:
                async with compute_lock:
                    image_path = await generator.generate_selfie(prompt_scene, loc, use_reference=False)
                await send_photo_with_retry(update, image_path, "🌆 Город")
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await send_with_retry(update, "Не могу показать город.")
            return

        # Подруги
        friend_type = None
        caption = None
        if "виолетт" in query or "гот" in query or "фиолетов" in query or "виолетта" in query:
            friend_type = "violet"
            caption = "🐱 Виолетта"
        elif "подруг" in query or "друзей" in query or "подружек" in query:
            friend_type = random.choice(["agnes", "violet"])
            caption = "Моя подруга"

        if friend_type:
            logger.info(f"Показываем подругу: {friend_type}")
            await send_with_retry(update, f"🔍 Показываю {caption}...")
            loc = location_manager.current_location if location_manager else "неизвестно"
            prompt_friend = await build_friend_prompt(mood_engine, friend_type, loc)
            negative = "cat ears, cat tail, pink hair" if friend_type == "agnes" else ""
            try:
                async with compute_lock:
                    image_path = await generator.generate_selfie(prompt_friend, loc, use_reference=False, negative_prompt=negative)
                await send_photo_with_retry(update, image_path, caption)
            except Exception as e:
                logger.error(f"Ошибка генерации подруги: {e}", exc_info=True)
                await send_with_retry(update, "Не могу показать, попробуй позже.")
            return

        # Общая сцена
        await send_with_retry(update, "🔍 Показываю...")
        loc = location_manager.current_location if location_manager else "неизвестно"
        prompt_scene = await build_scene_prompt(mood_engine, "generic", loc)
        try:
            async with compute_lock:
                image_path = await generator.generate_selfie(prompt_scene, loc, use_reference=False)
            await send_photo_with_retry(update, image_path, "🌍 Вот что вокруг")
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await send_with_retry(update, "Не могу показать.")
        return

    # ----- Подарки / извинения (динамические) -----
    is_apology = re.search(r'\b(прости|извини|виноват|не прав|дурак|глупость)\b', text_lower)
    is_gift = re.search(r'\*?(дарит|даю|дарю|подсовывает|шоколадку|конфету|цветы|плюшевого мишку|подарок|купить|куплю|подарю)\*?', text_lower)
    if is_apology or is_gift:
        action_type = "извинение" if is_apology else "подарок"
        mood_score = mood_engine.mood_score
        emotion = mood_engine.emotion

        if action_type == "извинение":
            if emotion in ["обида", "злость", "грусть"]:
                base_chance = 0.2
            elif emotion in ["радость", "влюблённость", "игривость"]:
                base_chance = 0.8
            else:
                base_chance = 0.5
            adjusted_chance = base_chance * (0.5 + mood_score)
            adjusted_chance = min(0.95, max(0.05, adjusted_chance))
            positive = random.random() < adjusted_chance
            if positive:
                new_emotion = "радость"
                mood_delta = 0.2
                horny_delta = 0.1
                energy_delta = 0.1
            else:
                new_emotion = emotion if emotion in ["обида", "злость", "грусть"] else "обида"
                mood_delta = -0.05
                horny_delta = -0.05
                energy_delta = -0.05
        else:  # подарок
            if emotion in ["радость", "влюблённость"]:
                base_chance = 0.95
            elif emotion in ["обида", "злость", "грусть"]:
                base_chance = 0.6
            else:
                base_chance = 0.85
            positive = random.random() < base_chance
            if positive:
                new_emotion = "радость"
                mood_delta = 0.25
                horny_delta = 0.1
                energy_delta = 0.1
            else:
                new_emotion = "нейтральное"
                mood_delta = 0.05
                horny_delta = 0.0
                energy_delta = 0.0

        mood_engine.emotion = new_emotion
        mood_engine.mood_score = min(1.0, max(0.0, mood_engine.mood_score + mood_delta))
        mood_engine.horny_level = min(1.0, max(0.0, mood_engine.horny_level + horny_delta))
        mood_engine.energy = min(1.0, max(0.0, mood_engine.energy + energy_delta))
        mood_engine.save()

        mood_desc = mood_engine.get_mood_description()
        if action_type == "извинение":
            prompt = f"""Твоё текущее настроение: {mood_desc}. Пользователь извинился: "{user_text}".
Ты {'простила' if positive else 'не простила'}. Напиши короткий ответ (1-2 предложения) на русском, который отражает твоё состояние.
Если простила, можешь написать что-то вроде «Ладно, прощаю» или более тёплое. Если нет — можешь надуться, сказать «Ещё рано» или «Я обижена».
Используй эмодзи и действия в звёздочках. Ответ:"""
        else:
            prompt = f"""Твоё текущее настроение: {mood_desc}. Пользователь дарит тебе подарок: "{user_text}".
Ты {'обрадовалась' if positive else 'отреагировала нейтрально'}. Напиши короткий ответ (1-2 предложения) на русском, с эмодзи и действиями в звёздочках, который показывает твою реакцию.
Если рада — поблагодари, если нейтрально — скажи что-то вежливое. Ответ:"""

        async with compute_lock:
            answer = await llm_engine.generate(prompt, max_tokens=70, temperature=0.7)
        answer = answer.strip()
        if answer.startswith("а,"):
            answer = answer[2:].strip()
        if not answer:
            answer = "*улыбнулась* Спасибо!" if action_type == "подарок" else "*пожимает плечами* Ладно."
        await send_with_retry(update, answer)
        await memory.add_conversation_turn("user", user_text, mood_desc)
        await memory.add_conversation_turn("eva", answer, mood_engine.get_mood_description())
        return

    # ----- Анализ тональности -----
    sentiment = "neutral"
    keywords = []
    if any(w in text_lower for w in ["люблю", "обожаю", "красивая", "хорошо", "❤️"]):
        sentiment = "positive"
        keywords.append("люблю")
    elif any(w in text_lower for w in ["ненавижу", "плохо", "грустно", "ужасно"]):
        sentiment = "negative"
        keywords.append("грустно")
    if "грустно" in text_lower or "печально" in text_lower:
        keywords.append("грустно")
    if "злой" in text_lower or "бесить" in text_lower:
        keywords.append("злой")
    if "люблю" in text_lower or "обожаю" in text_lower:
        keywords.append("люблю")
    if "игривая" in text_lower or "пошлая" in text_lower:
        keywords.append("игривая")
    if "сонная" in text_lower or "устала" in text_lower:
        keywords.append("сонная")
    if "весёлая" in text_lower or "смех" in text_lower:
        keywords.append("весёлая")
    mood_engine.apply_reaction_to_user_message(sentiment, keywords)

    # ----- Обычный ответ -----
    mood_desc = mood_engine.get_mood_description()
    context_mem = await memory.get_last_n_days_context(3)
    sys_prompt = llm_engine.make_system_prompt(mood_desc, context_mem)
    history = await memory.get_conversation_history(8)
    history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history[-4:]])
    prompt = f"История диалога:\n{history_text}\n\nПользователь: {user_text}\nЕва:"

    # Получаем последний ответ Евы (если есть)
    last_eva_answer = context.bot_data.get("last_eva_answer", "")

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            temp = 0.9 + (attempt * 0.1)  # повышаем температуру при каждой попытке
            async with compute_lock:
                answer = await llm_engine.generate(
                    prompt,
                    sys_prompt,
                    max_tokens=250,
                    temperature=min(temp, 1.2),
                    repeat_penalty=1.5 + (attempt * 0.1)
                )
            # Постобработка
            # Удаляем фразы типа "и также упоминала", "и тоже сказала" и т.п.
            answer = re.sub(r'и\s+также\s+упоминала\s+[А-Яа-я]+:', '', answer)
            answer = re.sub(r'и\s+тоже\s+сказала\s+[А-Яа-я]+:', '', answer)
            answer = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', '', answer)
            answer = re.sub(r'[a-zA-Z]', '', answer)
            answer = re.sub(r'^\.{2,}\s*', '', answer)
            answer = re.sub(r'(\*[а-яА-ЯёЁ]+\*)\s*\1', r'\1', answer)
            if "поесть" in answer and not ("есть" in answer and "хочу" in answer):
                answer = re.sub(r'вижу, ты хочешь меня поесть.*?[.!?]', '', answer)
            answer = answer.strip()

            # Проверка на повтор
            if answer and last_eva_answer and (
                answer == last_eva_answer or
                answer.split('.')[0] == last_eva_answer.split('.')[0]  # совпадает первое предложение
            ):
                logger.warning(f"Обнаружен повтор ответа (попытка {attempt+1}), перегенерируем...")
                if attempt == max_attempts - 1:
                    answer = "*улыбнулась* Ты задаёшь интересные вопросы! 😊"
                continue
            break
        except Exception as e:
            logger.error(f"Ошибка при генерации: {e}")
            answer = "*улыбнулась* Всё хорошо! 😊"
            break

    # Сохраняем последний ответ
    context.bot_data["last_eva_answer"] = answer

    if not answer or len(answer) < 3:
        answer = "*улыбнулась* Всё хорошо! 😊"

    await memory.add_conversation_turn("user", user_text, mood_desc)
    await memory.add_conversation_turn("eva", answer, mood_engine.get_mood_description())
    await send_with_retry(update, answer)
