import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")

CREATOR_ID = int(os.getenv("CREATOR_ID", "0"))

# Пути
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
IMAGES_DIR = BASE_DIR / "generated_images"
BACKUPS_DIR = BASE_DIR / "backups"

# Путь к LoRA для Агнес (если есть)
LORA_AGNES_PATH = MODELS_DIR / "agnes_tachion_lora.safetensors"

# Настройки LLM
LLM_MODEL_PATH = MODELS_DIR / "qwen2.5-7b-instruct-q4_k_m.gguf"  # старый для совместимости
LLM_MODEL_PATH_LOCAL = MODELS_DIR / "Qwen3.5-9B-Q4_K_M.gguf"      # новый для локального запуска
LLM_CONTEXT_SIZE = 2048
LLM_MAX_TOKENS = 150
LLM_TEMPERATURE = 0.75

# Настройки аниме-генерации
ANIMEGAN_WEIGHTS_PATH = MODELS_DIR / "animegan" / "face_paint_512_v2.pt"
WAFU2X_PATH = MODELS_DIR / "waifu2x"

# Прокси
TOR_SOCKS_PORT = 9050

def get_time_context() -> str:
    """Возвращает строку с текущим временем суток."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "утро"
    elif 12 <= hour < 17:
        return "день"
    elif 17 <= hour < 22:
        return "вечер"
    else:
        return "ночь"

def get_exact_time() -> str:
    """Возвращает текущее время в формате ЧЧ:ММ."""
    return datetime.now().strftime("%H:%M")
