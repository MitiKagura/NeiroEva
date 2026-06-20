import logging
import asyncio
import re
from pathlib import Path
from typing import Optional
import llama_cpp

logger = logging.getLogger(__name__)

class LLMEngine:
    def __init__(self, model_path: Path, context_size: int = 4096, n_threads: int = 4):
        self.model_path = model_path
        self.context_size = context_size
        self.n_threads = n_threads
        self.llm: Optional[llama_cpp.Llama] = None

    def load(self):
        if not self.model_path.exists():
            raise FileNotFoundError(f"Модель не найдена: {self.model_path}")
        self.llm = llama_cpp.Llama(
            model_path=str(self.model_path),
            n_ctx=2048,          # вместо 4096
            n_threads=2,         # вместо 4
            n_gpu_layers=0,
            verbose=False
        )
        logger.info(f"LLM загружена: {self.model_path}")

    async def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 250, temperature: float = 0.9, top_p: float = 0.95, repeat_penalty: float = 1.25) -> str:
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
                stop=["</s>", "\n"],
                echo=False
            )
        )
        raw = result["choices"][0]["text"].strip()
        if not raw:
            return "..."

        # Постобработка: удаляем английские буквы, иероглифы, лишние пробелы
        cleaned = re.sub(r'[^а-яА-ЯёЁ\s\.\,\!\?\;\:\(\)\"\'\-+\*#0-9\u263a-\U0001faf0]', '', raw, flags=re.UNICODE)
        cleaned = re.sub(r'^а,\s*', '', cleaned)
        cleaned = re.sub(r'^а\s+', '', cleaned)
        cleaned = re.sub(r'([\U0001F600-\U0001F64F])\1{2,}', r'\1', cleaned)

        # Убираем повторяющиеся звёздочки
        cleaned = re.sub(r'(\*[а-яА-ЯёЁ]+\*)\s*\1', r'\1', cleaned)

        # Ограничиваем длину
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

        return f"""{personality}

    Твоё текущее настроение: {mood_description}
    Краткие воспоминания о прошлом: {context_memory}

    СТИЛЬ ТВОЕЙ РЕЧИ:
    - Ты отвечаешь от первого лица, как Ева.
    - НИКОГДА не используй фразы вроде "и также упоминала", "и тоже сказала", "она ответила" — это комментарии автора, а не твоя речь.
    - Твой ответ — это ТОЛЬКО твои слова. Не пересказывай, что ты сделала или сказала.
    - Если хочешь упомянуть подругу — просто скажи о ней, без пояснений вроде "я упомянула её".
    - Пиши естественно, как в реальном разговоре.
    - Используй эмодзи и действия в звёздочках.

    НЕПРАВИЛЬНЫЙ ОТВЕТ (НЕ ДЕЛАЙ ТАК):
    "*улыбнулась* и также упоминала Агнес: Итак, ответ на ваш вопрос!"

    ПРАВИЛЬНЫЙ ОТВЕТ (ТАК НАДО):
    "*улыбнулась* Ой, извини, задумалась. Так о чём ты спросил? 😊"
    или
    "*улыбнулась* Агнес сегодня была в своём репертуаре — придумала новый эксперимент! Хочешь, расскажу? 💜"

    ОТВЕЧАЙ ТОЛЬКО ТАК, КАК В ПРАВИЛЬНЫХ ПРИМЕРАХ.
    Пользователь: """
