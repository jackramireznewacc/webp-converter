#!/bin/bash
# Скрипт запуска WebP Converter

cd "$(dirname "$0")"

# Проверяем наличие venv
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Запускаем приложение
python3 webp_converter.py
