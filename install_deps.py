#!/usr/bin/env python3
import subprocess
import sys
import os
from pathlib import Path

def run_cmd(cmd, check=True):
    print(f">>> {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(result.stderr)
        sys.exit(1)
    return result

def install_system_deps():
    """Устанавливает системные пакеты для Arch/CachyOS."""
    print("Установка системных зависимостей (требуется sudo)...")
    run_cmd(["sudo", "pacman", "-Syu", "--noconfirm"])
    run_cmd(["sudo", "pacman", "-S", "--noconfirm",
        "python", "python-pip", "git", "base-devel", "cmake", "git-lfs"
    ])

def create_project_structure():
    base = Path(__file__).parent
    dirs = ["core", "generators", "handlers", "utils", "models", "data", "logs", "generated_images", "backups", "diary"]
    for d in dirs:
        (base / d).mkdir(exist_ok=True)
        if d in ["core", "generators", "handlers", "utils"]:
            init_file = base / d / "__init__.py"
            if not init_file.exists():
                init_file.touch()
    print("Структура проекта создана.")

def install_python_packages():
    print("Установка Python-пакетов...")
    req_file = Path(__file__).parent / "requirements.txt"
    if not req_file.exists():
        print("requirements.txt не найден, создаём...")
        req_file.write_text("""
python-telegram-bot[job-queue]>=20.0
llama-cpp-python
torch
torchvision
transformers
sentencepiece
opencv-python
numpy
Pillow
diffusers>=0.26.3
accelerate
safetensors
aiohttp
aiohttp-socks
aiosqlite
python-dotenv
schedule
sentence-transformers
huggingface-hub
""".strip())
    run_cmd([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run_cmd([sys.executable, "-m", "pip", "install", "-r", str(req_file)])

def ensure_env_file():
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        print("Файл .env не найден. Создайте его вручную с содержимым:")
        print("BOT_TOKEN=ваш_токен_от_BotFather")
        print("CREATOR_ID=ваш_telegram_id")
        print("(или просто скопируйте .env.example)")

def main():
    print("=== Установка NeuroEva ===\n")
    install_system_deps()
    create_project_structure()
    install_python_packages()
    ensure_env_file()
    # Проверка модели NablaThetaA5
    model_dir = Path("models/NablaThetaA5")
    if not model_dir.exists() or not any(model_dir.iterdir()):
        print("Модель NablaThetaA5 не найдена. Скачиваем...")
        run_cmd([sys.executable, "-m", "pip", "install", "huggingface-hub"])
        run_cmd([sys.executable, "-m", "huggingface_hub.commands.huggingface_cli",
                "download", "eienmojiki/NablaThetaA5-v1.0", "--local-dir", str(model_dir)])
    else:
        print("Модель NablaThetaA5 уже есть.")
    print("\nУстановка завершена.")
    print("Запустите: source evavenv/bin/activate && python main.py")

if __name__ == "__main__":
    main()
