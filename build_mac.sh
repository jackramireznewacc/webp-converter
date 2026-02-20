#!/bin/bash
# Скрипт сборки WebP Converter для macOS
# Запускать из папки проекта: ./build_mac.sh

set -e

echo "🔧 Сборка WebP Converter для macOS"
echo "=================================="

# Проверяем, что мы в правильной папке
if [ ! -f "webp_converter.py" ]; then
    echo "❌ Ошибка: запустите скрипт из папки с webp_converter.py"
    exit 1
fi

# Создаём виртуальное окружение если его нет
if [ ! -d "venv" ]; then
    echo "📦 Создаю виртуальное окружение..."
    python3 -m venv venv
fi

# Активируем venv
source venv/bin/activate

# Устанавливаем зависимости
echo "📦 Устанавливаю зависимости..."
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# Создаём папку converted если её нет
mkdir -p converted

# Собираем приложение
echo "🏗️  Собираю приложение..."
pyinstaller \
    --name "WebP Converter" \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    --add-data "converted:converted" \
    --hidden-import PIL \
    --hidden-import PIL.Image \
    --hidden-import PIL.WebPImagePlugin \
    --icon NONE \
    webp_converter.py

# Копируем папку converted в бандл
echo "📁 Копирую папку converted..."
mkdir -p "dist/WebP Converter.app/Contents/MacOS/converted"

echo ""
echo "✅ Готово!"
echo ""
echo "Приложение находится в: dist/WebP Converter.app"
echo ""
echo "Для установки:"
echo "  1. Откройте папку dist/"
echo "  2. Перетащите 'WebP Converter.app' в /Applications"
echo ""
echo "Или запустите прямо сейчас:"
echo "  open \"dist/WebP Converter.app\""
