import logging
import asyncio
import re
from pathlib import Path
from typing import Optional
import llama_cpp
from utils.config import get_time_context, get_exact_time

logger = logging.getLogger(__name__)

class LLMEngine:
    def __init__(self, model_path: Path, context_size: int = 2048, n_threads: int = 1):
        self.model_path = model_path
        self.context_size = context_size
        self.n_threads = n_threads
        self.llm: Optional[llama_cpp.Llama] = None

    def load(self):
        if not self.model_path.exists():
            raise FileNotFoundError(f"Модель не найдена: {self.model_path}")
        self.llm = llama_cpp.Llama(
            model_path=str(self.model_path),
            n_ctx=self.context_size,
            n_threads=self.n_threads,
            n_gpu_layers=0,
            verbose=False
        )
        logger.info(f"LLM загружена: {self.model_path}")

    async def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 200, temperature: float = 0.75, top_p: float = 0.9, repeat_penalty: float = 1.2) -> str:
        if not self.llm:
            raise RuntimeError("LLM не загружена")
        full_prompt = system_prompt + "\n\n" + prompt if system_prompt else prompt
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.llm(
                full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=repeat_penalty,
                stop=["</s>", "User:", "user:", "\n\n", "<|im_end|>", '"', "'"],
                echo=False
            )
        )
        raw = result["choices"][0]["text"].strip()
        if not raw:
            return "..."
        # Убираем всё, что начинается с "Пользователь:" или "Ева:" (если модель решила их вставить)
        raw = re.sub(r'^(Пользователь|User|Ева):\s*', '', raw, flags=re.IGNORECASE)
        cleaned = re.sub(r'[^а-яА-ЯёЁ\s\.\,\!\?\;\:\(\)\"\'\-+\*#0-9\u263a-\U0001faf0]', '', raw, flags=re.UNICODE)
        cleaned = re.sub(r'^а,\s*', '', cleaned)
        cleaned = re.sub(r'^а\s+', '', cleaned)
        cleaned = re.sub(r'([\U0001F600-\U0001F64F])\1{2,}', r'\1', cleaned)
        cleaned = re.sub(r'(\*[а-яА-ЯёЁ]+\*)\s*\1', r'\1', cleaned)
        if len(cleaned) > 500:
            cleaned = cleaned[:500]
        return cleaned

    def make_system_prompt(self, mood_description: str, context_memory: str) -> str:
        personality_path = Path(__file__).parent.parent / "data" / "personality.md"
        if personality_path.exists():
            with open(personality_path, 'r', encoding='utf-8') as f:
                personality = f.read()
        else:
            personality = "Ты — Ева, девушка-кошка с фиолетовыми волосами."

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

Примеры хороших ответов:
Пользователь: Привет, как дела?
Ева: *улыбнулась* Всё отлично! Сегодня такое солнечное утро, настроение просто волшебное. А у тебя? 😊

Пользователь: Что делаешь?
Ева: Сижу на подоконнике, смотрю на облака и думаю о тебе. *погладила хвост* Надеюсь, твой день тоже будет тёплым. ☁️

Пользователь: Сколько время?
Ева: *посмотрела на часы* Сейчас {exact_time}. У тебя ещё целый день впереди! 😊

ОТВЕЧАЙ ТОЛЬКО ТАК — ЕСТЕСТВЕННО, РАЗНООБРАЗНО И БЕЗ ПОВТОРОВ.
Пользователь: """
