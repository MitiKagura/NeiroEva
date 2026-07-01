#!/usr/bin/env python3
import subprocess
import sys
import os
import platform
from pathlib import Path
import shutil

def run_cmd(cmd, check=True, capture=True):
    print(f">>> {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if check and result.returncode != 0:
        if capture:
            print(result.stderr)
        sys.exit(1)
    return result

def get_shell():
    shell = os.environ.get('SHELL', '')
    if 'fish' in shell:
        return 'fish'
    return 'bash'

def install_system_deps():
    print("=== Установка системных зависимостей (требуется sudo) ===")
    run_cmd(["sudo", "pacman", "-Syu", "--noconfirm"])
    run_cmd(["sudo", "pacman", "-S", "--noconfirm",
        "python", "python-pip", "git", "base-devel", "cmake", "git-lfs",
        "gtk3", "gobject-introspection", "cairo", "pango", "libgirepository",
        "gcc", "make", "pkg-config", "mesa-utils"
    ])
    print("Системные зависимости установлены.")

def create_project_structure():
    base = Path(__file__).parent
    dirs = ["core", "generators", "handlers", "utils", "models", "data", "logs", "generated_images", "backups", "diary", "launcher"]
    for d in dirs:
        (base / d).mkdir(exist_ok=True)
        if d in ["core", "generators", "handlers", "utils"]:
            init_file = base / d / "__init__.py"
            if not init_file.exists():
                init_file.touch()
    print("Структура проекта создана.")

def create_requirements():
    req_file = Path(__file__).parent / "requirements.txt"
    if not req_file.exists() or True:
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
pygobject>=3.42.0
""".strip())
        print("Файл requirements.txt обновлён (добавлен pygobject).")

def setup_virtualenv():
    base = Path(__file__).parent
    venv_path = base / "evavenv"
    if venv_path.exists():
        print("Виртуальное окружение уже существует.")
        return venv_path

    print("Создание виртуального окружения...")
    run_cmd([sys.executable, "-m", "venv", str(venv_path)])
    print("Виртуальное окружение создано.")
    return venv_path

def install_python_packages(venv_path):
    print("Установка Python-пакетов в виртуальное окружение...")
    pip_path = venv_path / "bin" / "pip"
    run_cmd([str(pip_path), "install", "--upgrade", "pip"])
    run_cmd([str(pip_path), "install", "-r", "requirements.txt"])
    print("Пакеты установлены.")

def create_desktop_entry():
    print("=== Создание ярлыка на рабочем столе ===")
    home = Path.home()
    desktop_dir = home / "Desktop"
    if not desktop_dir.exists():
        desktop_dir = home / "Рабочий стол"
    if not desktop_dir.exists():
        print("⚠️ Папка рабочего стола не найдена, ярлык не создан.")
        return

    base = Path(__file__).parent
    icon_path = base / "launcher" / "icon.png"
    if not icon_path.exists():
        # Создаём заглушку
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import Image
            img = Image.new('RGBA', (128, 128), color=(180, 80, 255, 255))
            img.save(icon_path)
            print("⚠️ Иконка не найдена, создана заглушка.")
        except ImportError:
            print("⚠️ Библиотека PIL не установлена, иконка не создана.")

    desktop_file = desktop_dir / "NeuroEva-Launcher.desktop"
    venv_python = base / "evavenv" / "bin" / "python3"
    launcher_script = base / "launcher" / "eva_launcher.py"

    content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=NeuroEva Лаунчер
Comment=Запуск и управление НейроЕвой
Exec={venv_python} {launcher_script}
Icon={icon_path}
Terminal=false
Categories=Utility;Development;
StartupNotify=true
"""
    desktop_file.write_text(content)
    desktop_file.chmod(0o755)
    print(f"✅ Ярлык создан: {desktop_file}")

def main():
    print("=== Установка NeuroEva ===\n")
    install_system_deps()
    create_project_structure()
    create_requirements()
    venv_path = setup_virtualenv()
    install_python_packages(venv_path)
    ensure_env_file()
    create_desktop_entry()

    shell = get_shell()
    if shell == "fish":
        activate_cmd = f"source {venv_path}/bin/activate.fish"
    else:
        activate_cmd = f"source {venv_path}/bin/activate"

    print("\n✅ Установка завершена!")
    print(f"Для активации окружения выполните:")
    print(f"  {activate_cmd}")
    print("Для запуска бота:")
    print("  python3 main.py         # Colab-режим (если включён в .env)")
    print("  python3 main_local.py   # локальный режим")
    print("Для запуска лаунчера:")
    print("  python3 launcher/eva_launcher.py")
    print("Также создан ярлык на рабочем столе.")

if __name__ == "__main__":
    main()

def ensure_env_file():
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        print("Файл .env не найден. Создаю шаблон...")
        env_file.write_text("""
BOT_TOKEN=ваш_токен_от_BotFather
CREATOR_ID=ваш_telegram_id
USE_COLAB=false
COLAB_URL=https://your-ngrok.ngrok-free.dev
NGROK_TOKEN=ваш_ngrok_токен_если_нужен
""".strip())
        print("Создан .env. Отредактируйте его и укажите свои данные.")
    else:
        print(".env уже существует.")

    # Создаём .env.example для репозитория
    example_file = Path(__file__).parent / ".env.example"
    if not example_file.exists():
        example_file.write_text("""
BOT_TOKEN=ваш_токен_от_BotFather
CREATOR_ID=ваш_telegram_id
USE_COLAB=false
COLAB_URL=https://your-ngrok.ngrok-free.dev
NGROK_TOKEN=ваш_ngrok_токен_если_нужен
""".strip())
        print("Создан .env.example для репозитория.")
