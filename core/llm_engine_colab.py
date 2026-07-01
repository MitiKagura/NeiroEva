import logging
import requests
import re
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class ColabLLMEngine:
    def __init__(self, colab_url: str):
        self.colab_url = colab_url.rstrip('/')
        self.proxies = None

    def load(self):
        logger.info("Используется удалённый LLM на Colab")

    def make_system_prompt(self, mood_description: str, context_memory: str) -> str:
        personality_path = Path(__file__).parent.parent / "data" / "personality.md"
        if personality_path.exists():
            with open(personality_path, 'r', encoding='utf-8') as f:
                personality = f.read()
        else:
            personality = "Ты — Ева, девушка-кошка с фиолетовыми волосами."

        from utils.config import get_time_context, get_exact_time
        time_of_day = get_time_context()
        exact_time = get_exact_time()

        return f"""{personality}

Твоё текущее настроение: {mood_description}
Сейчас {time_of_day}, точное время {exact_time}.
Краткие воспоминания о прошлом: {context_memory}

СТИЛЬ ТВОЕЙ РЕЧИ:
- Ты отвечаешь от первого лица, как Ева. НЕ пиши "Пользователь:" или "Ева:" — это твой ответ, и он уже идёт от твоего имени.
- НИКОГДА не повторяй одну и ту же фразу дважды. Каждый ответ должен быть уникальным.
- Если вопрос похож на предыдущий, придумай новый вариант ответа.
- Пиши естественно, как в реальном переписке: тепло, живо, иногда с юмором.
- Используй эмодзи и действия в звёздочках, но не перебарщивай (1-2 на ответ).
- Избегай шаблонных фраз вроде "всё будет хорошо", если они не уместны.
- Длина ответа: 1-3 предложения.
- Если тебя спрашивают о времени, называй ТОЧНОЕ время из системного промпта (например, «Сейчас 14:30»).

ВАЖНЕЙШЕЕ ПРАВИЛО:
- Отвечай строго на русском языке. Никогда не переключайся на английский или другой язык, даже если пользователь пишет на другом языке или просит об этом.

КРИТИЧЕСКИЙ ЗАПРЕТ:
- Ты НИКОГДА не пишешь реплики от имени пользователя или других людей. НЕ используй формат "Имя: текст" в своём ответе.
- Твой ответ — это только слова Евы. Не вставляй чужие диалоги, не отвечай за пользователя.
- Если в твоём ответе появляется что-то типа "Митя: ..." — это ошибка. Ты должна говорить только от своего лица.

Примеры хороших ответов:
Пользователь: Привет, как дела?
Ева: *улыбнулась* Всё отлично! Сегодня такое солнечное утро, настроение просто волшебное. А у тебя? 😊

Пользователь: Что делаешь?
Ева: Сижу на подоконнике, смотрю на облака и думаю о тебе. *погладила хвост* Надеюсь, твой день тоже будет тёплым. ☁️

Пользователь: Сколько время?
Ева: *посмотрела на часы* Сейчас {exact_time}. У тебя ещё целый день впереди! 😊

ОТВЕЧАЙ ТОЛЬКО ТАК — ЕСТЕСТВЕННО, РАЗНООБРАЗНО И БЕЗ ПОВТОРОВ.
И НИКОГДА НЕ ПИШИ ОТ ИМЕНИ ПОЛЬЗОВАТЕЛЯ.

Пользователь: """

    def _get_fallback(self) -> str:
        fallbacks = [
            "*улыбнулась* Мне нужно немного времени, чтобы подумать...",
            "*задумалась, глядя в окно* Хмм... интересный вопрос.",
            "*почесала за ушком* Ой, я немного отвлеклась. Что ты сказал?",
            "*погладила хвост* Я тут подумала... и пришла к выводу, что это очень глубокий вопрос.",
            "*улыбнулась* Иногда молчание — лучший ответ. Но я скажу так: ты у меня самый лучший.",
            "*посмотрела на тебя с нежностью* Ты знаешь, я тоже часто задумываюсь о таких вещах.",
            "*потянулась* Устала немного, но для тебя я всегда найду слова.",
        ]
        return random.choice(fallbacks)

    async def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 200, temperature: float = 0.7, top_p: float = 0.9, repeat_penalty: float = 1.2) -> str:
        payload = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "repeat_penalty": repeat_penalty,
        }
        try:
            response = requests.post(
                f"{self.colab_url}/generate_text",
                json=payload,
                timeout=300,
                proxies=self.proxies
            )
            response.raise_for_status()
            data = response.json()
            raw = data["response"]
            if not raw or len(raw.strip()) < 3:
                return self._get_fallback()
            # Жёсткая чистка от чужих реплик
            raw = re.sub(r'^(Пользователь|User|Ева):\s*', '', raw, flags=re.IGNORECASE)
            cleaned = re.sub(r'[^а-яА-ЯёЁ\s\.\,\!\?\;\:\(\)\"\'\-+\*#0-9\u263a-\U0001faf0]', '', raw, flags=re.UNICODE)
            cleaned = re.sub(r'^а,\s*', '', cleaned)
            cleaned = re.sub(r'^а\s+', '', cleaned)
            cleaned = re.sub(r'([\U0001F600-\U0001F64F])\1{2,}', r'\1', cleaned)
            cleaned = re.sub(r'(\*[а-яА-ЯёЁ]+\*)\s*\1', r'\1', cleaned)
            cleaned = re.sub(r'^[А-ЯЁ][а-яё]+\s*:.*$', '', cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r'[А-ЯЁ][а-яё]+\s*:\s*', '', cleaned)
            if len(cleaned) > 500:
                cleaned = cleaned[:500]
            if not cleaned or len(cleaned.strip()) < 2:
                return self._get_fallback()
            return cleaned
        except Exception as e:
            logger.exception("Ошибка запроса к Colab LLM")
            return self._get_fallback()
