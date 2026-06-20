#!/bin/bash
# Установщик NeuroEva для Arch Linux / CachyOS
# Запуск: chmod +x install.sh && ./install.sh

set -e  # прерывать при ошибках

echo "=== NeuroEva Installer ==="
echo "Система: Arch Linux / CachyOS"

# Проверка наличия Python
if ! command -v python &> /dev/null; then
    echo "Ошибка: Python не найден. Установите python."
    exit 1
fi

# 1. Системные зависимости
echo "[1/5] Установка системных пакетов (требуется sudo)..."
sudo pacman -Syu --noconfirm
sudo pacman -S --noconfirm python python-pip git base-devel cmake git-lfs

# 2. Создание виртуального окружения
echo "[2/5] Создание виртуального окружения evavenv..."
python -m venv evavenv

# 3. Активация и установка Python-пакетов
echo "[3/5] Установка Python-зависимостей..."
source evavenv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Проверка наличия .env
echo "[4/5] Проверка .env файла..."
if [ ! -f .env ]; then
    echo "Внимание: Файл .env не найден."
    echo "Создайте его вручную, добавив:"
    echo "  BOT_TOKEN=ваш_токен_от_BotFather"
    echo "  CREATOR_ID=ваш_telegram_id"
    echo "Или скопируйте .env.example, если он есть."
fi

# 5. Проверка и скачивание модели NablaThetaA5
echo "[5/5] Проверка модели NablaThetaA5..."
if [ ! -d "models/NablaThetaA5" ] || [ -z "$(ls -A models/NablaThetaA5 2>/dev/null)" ]; then
    echo "Модель NablaThetaA5 не найдена. Скачиваем..."
    mkdir -p models
    pip install huggingface-hub
    # Пробуем через hf (новая команда)
    if command -v hf &> /dev/null; then
        hf download eienmojiki/NablaThetaA5-v1.0 --local-dir models/NablaThetaA5
    else
        # Запасной вариант через Python
        python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='eienmojiki/NablaThetaA5-v1.0', local_dir='models/NablaThetaA5')"
    fi
else
    echo "Модель NablaThetaA5 уже есть."
fi

echo ""
echo "=== Установка завершена ==="
echo "Для запуска бота выполните:"
echo "  source evavenv/bin/activate"
echo "  python main.py"
