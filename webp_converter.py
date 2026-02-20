#!/usr/bin/env python3
"""
WebP Converter — локальный конвертер изображений с интерактивной обрезкой
Версия: 1.0.0
"""

import sys
import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QComboBox, QProgressBar,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox,
    QFileDialog, QMessageBox, QGroupBox, QFrame, QSplitter,
    QAbstractItemView, QSizePolicy, QLineEdit
)
from PySide6.QtCore import (
    Qt, QRect, QPoint, QSize, Signal, QThread, QSettings,
    QMimeData, QUrl
)
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush, QImage,
    QDragEnterEvent, QDropEvent, QMouseEvent, QPaintEvent,
    QResizeEvent, QCursor
)

from PIL import Image
import io


# ============================================================================
# КОНСТАНТЫ И КОНФИГУРАЦИЯ
# ============================================================================

SUPPORTED_INPUT_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
OUTPUT_FORMAT = '.webp'

QUALITY_PRESETS = {
    'SEO (70)': 70,
    'Balanced (75)': 75,
    'High (85)': 85,
}

# Пресеты соотношений сторон (ширина : высота)
ASPECT_RATIO_PRESETS = {
    'Свободно': None,
    'Обложка 8:5': (8, 5),
    'Широкий 16:9': (16, 9),
    'Стандарт 4:3': (4, 3),
    'Квадрат 1:1': (1, 1),
    'Портрет 3:4': (3, 4),
    'Портрет 9:16': (9, 16),
}

# Модификаторы для генерации имён
NAME_MODIFIERS = {
    'adjectives': [
        'beautiful', 'amazing', 'stunning', 'gorgeous', 'nice', 
        'great', 'perfect', 'lovely', 'wonderful'
    ],
    'state': [
        'new', 'fresh', 'original', 'authentic', 'unique', 
        'classic', 'modern', 'vintage', 'traditional', 'famous'
    ],
    'seo_suffixes': [
        'photo', 'image', 'picture', 'pic', 'wallpaper', 
        'background', 'cover', 'banner', 'hd', '4k', 'free', 'stock'
    ]
}

APP_NAME = "WebP Converter"
APP_VERSION = "1.0.0"
SETTINGS_FILE = "settings.json"


# ============================================================================
# ГЕНЕРАТОР ИМЁН
# ============================================================================

class NameGenerator:
    """Генератор уникальных имён файлов"""
    
    SEPARATORS = ['-', '_']
    
    def __init__(self, base_words: List[str]):
        # Очищаем и нормализуем слова
        self.base_words = [w.strip().lower() for w in base_words if w.strip()]
        
        # Собираем все модификаторы в один список
        self.all_modifiers = []
        for category in NAME_MODIFIERS.values():
            for mod in category:
                # Исключаем модификаторы, которые уже есть в базовых словах
                if mod.lower() not in self.base_words:
                    self.all_modifiers.append(mod)
        
        self._generated = set()
    
    def _get_permutations(self, words: List[str]) -> List[List[str]]:
        """Получить все перестановки списка слов"""
        from itertools import permutations
        return [list(p) for p in permutations(words)]
    
    def _join_words(self, words: List[str], separator: str) -> str:
        """Соединить слова разделителем"""
        return separator.join(words)
    
    def generate(self, count: int) -> List[str]:
        """Сгенерировать count уникальных имён"""
        names = []
        self._generated = set()
        
        # Фаза 1: Базовые перестановки с разными разделителями
        base_perms = self._get_permutations(self.base_words)
        for perm in base_perms:
            for sep in self.SEPARATORS:
                name = self._join_words(perm, sep)
                if name not in self._generated:
                    names.append(name)
                    self._generated.add(name)
                    if len(names) >= count:
                        return names
        
        # Фаза 2: Добавляем модификаторы как префикс
        for modifier in self.all_modifiers:
            for perm in base_perms:
                for sep in self.SEPARATORS:
                    name = self._join_words([modifier] + perm, sep)
                    if name not in self._generated:
                        names.append(name)
                        self._generated.add(name)
                        if len(names) >= count:
                            return names
        
        # Фаза 3: Добавляем модификаторы как суффикс
        for modifier in self.all_modifiers:
            for perm in base_perms:
                for sep in self.SEPARATORS:
                    name = self._join_words(perm + [modifier], sep)
                    if name not in self._generated:
                        names.append(name)
                        self._generated.add(name)
                        if len(names) >= count:
                            return names
        
        # Фаза 4: Два модификатора (префикс + суффикс)
        for mod1 in self.all_modifiers:
            for mod2 in self.all_modifiers:
                if mod1 != mod2:
                    for perm in base_perms:
                        for sep in self.SEPARATORS:
                            name = self._join_words([mod1] + perm + [mod2], sep)
                            if name not in self._generated:
                                names.append(name)
                                self._generated.add(name)
                                if len(names) >= count:
                                    return names
        
        # Фаза 5: Fallback на цифры
        base_name = self._join_words(self.base_words, '-')
        counter = 1
        while len(names) < count:
            name = f"{base_name}_{counter}"
            if name not in self._generated:
                names.append(name)
                self._generated.add(name)
            counter += 1
        
        return names
    
    @staticmethod
    def estimate_combinations(word_count: int) -> int:
        """Оценить количество комбинаций для N слов"""
        from math import factorial
        
        # Базовые перестановки × разделители
        base = factorial(word_count) * 2
        
        # С модификаторами
        total_modifiers = sum(len(cat) for cat in NAME_MODIFIERS.values())
        with_prefix = base * total_modifiers
        with_suffix = base * total_modifiers
        with_both = base * total_modifiers * (total_modifiers - 1)
        
        return base + with_prefix + with_suffix + with_both


# ============================================================================
# МОДЕЛИ ДАННЫХ
# ============================================================================

@dataclass
class ImageItem:
    """Элемент очереди изображений"""
    path: Path
    original_size: Tuple[int, int]
    crop_rect: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
    status: str = "pending"  # pending, processing, done, error
    output_path: Optional[Path] = None
    output_size_kb: Optional[float] = None
    output_name: Optional[str] = None  # Кастомное имя для сохранения
    
    @property
    def filename(self) -> str:
        return self.path.name
    
    @property
    def display_name(self) -> str:
        """Имя для отображения (кастомное или оригинальное)"""
        if self.output_name:
            return f"{self.output_name}.webp"
        return self.path.name
    
    @property
    def dimensions_str(self) -> str:
        if self.crop_rect:
            return f"{self.crop_rect[2]}×{self.crop_rect[3]}"
        return f"{self.original_size[0]}×{self.original_size[1]}"


# ============================================================================
# ОБРАБОТКА ИЗОБРАЖЕНИЙ
# ============================================================================

class ImageProcessor:
    """Класс для обработки изображений"""
    
    @staticmethod
    def load_image(path: Path) -> Image.Image:
        """Загрузка изображения"""
        img = Image.open(path)
        # Конвертируем в RGB если нужно (для RGBA, P и др.)
        if img.mode in ('RGBA', 'P', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        return img
    
    @staticmethod
    def crop_image(img: Image.Image, rect: Tuple[int, int, int, int]) -> Image.Image:
        """Обрезка изображения: rect = (x, y, width, height)"""
        x, y, w, h = rect
        return img.crop((x, y, x + w, y + h))
    
    @staticmethod
    def convert_to_webp(img: Image.Image, quality: int) -> bytes:
        """Конвертация в WebP, возвращает байты"""
        buffer = io.BytesIO()
        img.save(buffer, format='WEBP', quality=quality, method=6)
        return buffer.getvalue()
    
    @staticmethod
    def get_image_size(path: Path) -> Tuple[int, int]:
        """Получить размеры изображения без полной загрузки"""
        with Image.open(path) as img:
            return img.size
    
    @staticmethod
    def estimate_webp_size(img: Image.Image, quality: int) -> int:
        """Оценка размера WebP в байтах"""
        data = ImageProcessor.convert_to_webp(img, quality)
        return len(data)


# ============================================================================
# ВИДЖЕТ ИНТЕРАКТИВНОЙ ОБРЕЗКИ
# ============================================================================

class CropHandle(Enum):
    """Ручки для изменения размера области обрезки"""
    NONE = 0
    TOP_LEFT = 1
    TOP = 2
    TOP_RIGHT = 3
    RIGHT = 4
    BOTTOM_RIGHT = 5
    BOTTOM = 6
    BOTTOM_LEFT = 7
    LEFT = 8
    MOVE = 9


class CropWidget(QWidget):
    """Виджет для интерактивной обрезки изображения"""
    
    crop_changed = Signal()
    
    HANDLE_SIZE = 10
    MIN_CROP_SIZE = 50
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        
        self._pixmap: Optional[QPixmap] = None
        self._original_size: Tuple[int, int] = (0, 0)
        self._scale: float = 1.0
        self._offset: QPoint = QPoint(0, 0)
        
        # Область обрезки в координатах ОРИГИНАЛЬНОГО изображения
        self._crop_x: int = 0
        self._crop_y: int = 0
        self._crop_w: int = 0
        self._crop_h: int = 0
        
        self._active_handle: CropHandle = CropHandle.NONE
        self._drag_start: QPoint = QPoint()
        self._crop_start: Tuple[int, int, int, int] = (0, 0, 0, 0)
        
        # Фиксированное соотношение сторон (None = свободное)
        self._aspect_ratio: Optional[Tuple[int, int]] = None
        
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    def set_aspect_ratio(self, ratio: Optional[Tuple[int, int]]):
        """Установить фиксированное соотношение сторон"""
        self._aspect_ratio = ratio
        if ratio and self._pixmap:
            self._apply_aspect_ratio()
            self.update()
            self.crop_changed.emit()
    
    def _apply_aspect_ratio(self):
        """Применить соотношение сторон к текущей области"""
        if not self._aspect_ratio or not self._pixmap:
            return
        
        ratio_w, ratio_h = self._aspect_ratio
        target_ratio = ratio_w / ratio_h
        
        current_ratio = self._crop_w / self._crop_h if self._crop_h > 0 else 1
        
        # Центр текущей области
        center_x = self._crop_x + self._crop_w // 2
        center_y = self._crop_y + self._crop_h // 2
        
        if current_ratio > target_ratio:
            # Слишком широкий — уменьшаем ширину
            new_w = int(self._crop_h * target_ratio)
            new_h = self._crop_h
        else:
            # Слишком высокий — уменьшаем высоту
            new_w = self._crop_w
            new_h = int(self._crop_w / target_ratio)
        
        # Новые координаты от центра
        self._crop_w = new_w
        self._crop_h = new_h
        self._crop_x = center_x - new_w // 2
        self._crop_y = center_y - new_h // 2
        
        self._constrain_crop()
    
    def set_crop_size(self, width: int, height: int):
        """Установить размер области обрезки в пикселях оригинала"""
        if not self._pixmap:
            return
        
        # Ограничиваем размерами оригинала
        width = max(self.MIN_CROP_SIZE, min(width, self._original_size[0]))
        height = max(self.MIN_CROP_SIZE, min(height, self._original_size[1]))
        
        # Сохраняем центр
        center_x = self._crop_x + self._crop_w // 2
        center_y = self._crop_y + self._crop_h // 2
        
        self._crop_w = width
        self._crop_h = height
        self._crop_x = center_x - width // 2
        self._crop_y = center_y - height // 2
        
        self._constrain_crop()
        self.update()
        self.crop_changed.emit()
    
    def set_image(self, pixmap: QPixmap):
        """Установить изображение для обрезки"""
        self._pixmap = pixmap
        self._original_size = (pixmap.width(), pixmap.height())
        self._update_scale()
        
        # Инициализируем crop на ВСЁ изображение (точные размеры)
        self._crop_x = 0
        self._crop_y = 0
        self._crop_w = self._original_size[0]
        self._crop_h = self._original_size[1]
        
        self.update()
    
    def _update_scale(self):
        """Пересчитать масштаб и смещение"""
        if not self._pixmap:
            return
        
        widget_w = self.width()
        widget_h = self.height()
        img_w, img_h = self._original_size
        
        # Масштаб с сохранением пропорций
        scale_w = widget_w / img_w
        scale_h = widget_h / img_h
        self._scale = min(scale_w, scale_h) * 0.95  # 5% отступ
        
        # Центрирование
        scaled_w = int(img_w * self._scale)
        scaled_h = int(img_h * self._scale)
        self._offset = QPoint(
            (widget_w - scaled_w) // 2,
            (widget_h - scaled_h) // 2
        )
    
    def get_crop_rect_original(self) -> Tuple[int, int, int, int]:
        """Получить область обрезки в координатах оригинального изображения"""
        return (self._crop_x, self._crop_y, self._crop_w, self._crop_h)
    
    def _original_to_widget(self, x: int, y: int) -> QPoint:
        """Конвертировать координаты оригинала в координаты виджета"""
        return QPoint(
            int(x * self._scale + self._offset.x()),
            int(y * self._scale + self._offset.y())
        )
    
    def _widget_to_original(self, pos: QPoint) -> Tuple[int, int]:
        """Конвертировать координаты виджета в координаты оригинала"""
        x = int((pos.x() - self._offset.x()) / self._scale)
        y = int((pos.y() - self._offset.y()) / self._scale)
        return (x, y)
    
    def _get_crop_rect_widget(self) -> QRect:
        """Получить область обрезки в координатах виджета"""
        top_left = self._original_to_widget(self._crop_x, self._crop_y)
        w = int(self._crop_w * self._scale)
        h = int(self._crop_h * self._scale)
        return QRect(top_left.x(), top_left.y(), w, h)
    
    def reset_crop(self):
        """Сбросить область обрезки на всё изображение"""
        if self._pixmap:
            self._crop_x = 0
            self._crop_y = 0
            self._crop_w = self._original_size[0]
            self._crop_h = self._original_size[1]
            self.update()
            self.crop_changed.emit()
    
    def _constrain_crop(self):
        """Ограничить область обрезки границами изображения"""
        if not self._pixmap:
            return
        
        img_w, img_h = self._original_size
        
        # Минимальный размер
        self._crop_w = max(self.MIN_CROP_SIZE, self._crop_w)
        self._crop_h = max(self.MIN_CROP_SIZE, self._crop_h)
        
        # Не больше изображения
        self._crop_w = min(self._crop_w, img_w)
        self._crop_h = min(self._crop_h, img_h)
        
        # Не выходить за левый/верхний край
        self._crop_x = max(0, self._crop_x)
        self._crop_y = max(0, self._crop_y)
        
        # Не выходить за правый/нижний край
        if self._crop_x + self._crop_w > img_w:
            self._crop_x = img_w - self._crop_w
        if self._crop_y + self._crop_h > img_h:
            self._crop_y = img_h - self._crop_h
        
        # Финальная проверка
        self._crop_x = max(0, self._crop_x)
        self._crop_y = max(0, self._crop_y)
    
    def _get_handle_at(self, pos: QPoint) -> CropHandle:
        """Определить, на какой ручке находится курсор"""
        r = self._get_crop_rect_widget()
        hs = self.HANDLE_SIZE
        
        # Углы
        if QRect(r.left() - hs, r.top() - hs, hs * 2, hs * 2).contains(pos):
            return CropHandle.TOP_LEFT
        if QRect(r.right() - hs, r.top() - hs, hs * 2, hs * 2).contains(pos):
            return CropHandle.TOP_RIGHT
        if QRect(r.right() - hs, r.bottom() - hs, hs * 2, hs * 2).contains(pos):
            return CropHandle.BOTTOM_RIGHT
        if QRect(r.left() - hs, r.bottom() - hs, hs * 2, hs * 2).contains(pos):
            return CropHandle.BOTTOM_LEFT
        
        # Стороны
        if QRect(r.left() + hs, r.top() - hs, r.width() - 2 * hs, hs * 2).contains(pos):
            return CropHandle.TOP
        if QRect(r.right() - hs, r.top() + hs, hs * 2, r.height() - 2 * hs).contains(pos):
            return CropHandle.RIGHT
        if QRect(r.left() + hs, r.bottom() - hs, r.width() - 2 * hs, hs * 2).contains(pos):
            return CropHandle.BOTTOM
        if QRect(r.left() - hs, r.top() + hs, hs * 2, r.height() - 2 * hs).contains(pos):
            return CropHandle.LEFT
        
        # Внутри — перемещение
        if r.contains(pos):
            return CropHandle.MOVE
        
        return CropHandle.NONE
    
    def _get_cursor_for_handle(self, handle: CropHandle) -> Qt.CursorShape:
        """Получить курсор для ручки"""
        cursors = {
            CropHandle.TOP_LEFT: Qt.SizeFDiagCursor,
            CropHandle.TOP_RIGHT: Qt.SizeBDiagCursor,
            CropHandle.BOTTOM_LEFT: Qt.SizeBDiagCursor,
            CropHandle.BOTTOM_RIGHT: Qt.SizeFDiagCursor,
            CropHandle.TOP: Qt.SizeVerCursor,
            CropHandle.BOTTOM: Qt.SizeVerCursor,
            CropHandle.LEFT: Qt.SizeHorCursor,
            CropHandle.RIGHT: Qt.SizeHorCursor,
            CropHandle.MOVE: Qt.SizeAllCursor,
        }
        return cursors.get(handle, Qt.ArrowCursor)
    
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._active_handle = self._get_handle_at(event.pos())
            self._drag_start = event.pos()
            self._crop_start = (self._crop_x, self._crop_y, self._crop_w, self._crop_h)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        if self._active_handle == CropHandle.NONE:
            handle = self._get_handle_at(event.pos())
            self.setCursor(self._get_cursor_for_handle(handle))
            return
        
        # Дельта в координатах оригинала
        dx = int((event.pos().x() - self._drag_start.x()) / self._scale)
        dy = int((event.pos().y() - self._drag_start.y()) / self._scale)
        
        start_x, start_y, start_w, start_h = self._crop_start
        img_w, img_h = self._original_size
        
        if self._active_handle == CropHandle.MOVE:
            self._crop_x = start_x + dx
            self._crop_y = start_y + dy
            self._crop_w = start_w
            self._crop_h = start_h
        
        elif self._active_handle == CropHandle.TOP_LEFT:
            new_x = start_x + dx
            new_y = start_y + dy
            new_w = start_w - dx
            new_h = start_h - dy
            if new_w >= self.MIN_CROP_SIZE and new_h >= self.MIN_CROP_SIZE:
                self._crop_x = new_x
                self._crop_y = new_y
                self._crop_w = new_w
                self._crop_h = new_h
        
        elif self._active_handle == CropHandle.TOP:
            new_y = start_y + dy
            new_h = start_h - dy
            if new_h >= self.MIN_CROP_SIZE:
                self._crop_y = new_y
                self._crop_h = new_h
        
        elif self._active_handle == CropHandle.TOP_RIGHT:
            new_y = start_y + dy
            new_w = start_w + dx
            new_h = start_h - dy
            if new_w >= self.MIN_CROP_SIZE and new_h >= self.MIN_CROP_SIZE:
                self._crop_y = new_y
                self._crop_w = new_w
                self._crop_h = new_h
        
        elif self._active_handle == CropHandle.RIGHT:
            new_w = start_w + dx
            if new_w >= self.MIN_CROP_SIZE:
                self._crop_w = new_w
        
        elif self._active_handle == CropHandle.BOTTOM_RIGHT:
            new_w = start_w + dx
            new_h = start_h + dy
            if new_w >= self.MIN_CROP_SIZE and new_h >= self.MIN_CROP_SIZE:
                self._crop_w = new_w
                self._crop_h = new_h
        
        elif self._active_handle == CropHandle.BOTTOM:
            new_h = start_h + dy
            if new_h >= self.MIN_CROP_SIZE:
                self._crop_h = new_h
        
        elif self._active_handle == CropHandle.BOTTOM_LEFT:
            new_x = start_x + dx
            new_w = start_w - dx
            new_h = start_h + dy
            if new_w >= self.MIN_CROP_SIZE and new_h >= self.MIN_CROP_SIZE:
                self._crop_x = new_x
                self._crop_w = new_w
                self._crop_h = new_h
        
        elif self._active_handle == CropHandle.LEFT:
            new_x = start_x + dx
            new_w = start_w - dx
            if new_w >= self.MIN_CROP_SIZE:
                self._crop_x = new_x
                self._crop_w = new_w
        
        # Применяем соотношение сторон если задано
        if self._aspect_ratio and self._active_handle != CropHandle.MOVE:
            ratio_w, ratio_h = self._aspect_ratio
            target_ratio = ratio_w / ratio_h
            
            # Корректируем высоту под ширину
            self._crop_h = int(self._crop_w / target_ratio)
            if self._crop_h < self.MIN_CROP_SIZE:
                self._crop_h = self.MIN_CROP_SIZE
                self._crop_w = int(self._crop_h * target_ratio)
        
        self._constrain_crop()
        self.update()
        self.crop_changed.emit()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._active_handle = CropHandle.NONE
    
    def resizeEvent(self, event: QResizeEvent):
        self._update_scale()
        self.update()
    
    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Фон
        painter.fillRect(self.rect(), QColor(40, 40, 40))
        
        if not self._pixmap:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(self.rect(), Qt.AlignCenter, "Нет изображения")
            return
        
        # Масштабированное изображение
        scaled_w = int(self._original_size[0] * self._scale)
        scaled_h = int(self._original_size[1] * self._scale)
        scaled_pixmap = self._pixmap.scaled(
            scaled_w, scaled_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        painter.drawPixmap(self._offset, scaled_pixmap)
        
        # Область изображения в координатах виджета
        img_rect = QRect(self._offset.x(), self._offset.y(), scaled_w, scaled_h)
        
        # Область обрезки в координатах виджета
        crop_rect = self._get_crop_rect_widget()
        
        # Затемнение вне области обрезки
        overlay = QColor(0, 0, 0, 150)
        
        # Верх
        painter.fillRect(QRect(img_rect.left(), img_rect.top(),
                               img_rect.width(), crop_rect.top() - img_rect.top()), overlay)
        # Низ
        painter.fillRect(QRect(img_rect.left(), crop_rect.bottom(),
                               img_rect.width(), img_rect.bottom() - crop_rect.bottom()), overlay)
        # Лево
        painter.fillRect(QRect(img_rect.left(), crop_rect.top(),
                               crop_rect.left() - img_rect.left(), crop_rect.height()), overlay)
        # Право
        painter.fillRect(QRect(crop_rect.right(), crop_rect.top(),
                               img_rect.right() - crop_rect.right(), crop_rect.height()), overlay)
        
        # Рамка обрезки
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawRect(crop_rect)
        
        # Ручки
        handle_color = QColor(0, 120, 215)
        painter.setBrush(QBrush(handle_color))
        painter.setPen(QPen(Qt.white, 1))
        
        hs = self.HANDLE_SIZE
        r = crop_rect
        
        # Угловые ручки
        for point in [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]:
            painter.drawRect(point.x() - hs // 2, point.y() - hs // 2, hs, hs)
        
        # Боковые ручки
        painter.drawRect(r.center().x() - hs // 2, r.top() - hs // 2, hs, hs)
        painter.drawRect(r.right() - hs // 2, r.center().y() - hs // 2, hs, hs)
        painter.drawRect(r.center().x() - hs // 2, r.bottom() - hs // 2, hs, hs)
        painter.drawRect(r.left() - hs // 2, r.center().y() - hs // 2, hs, hs)
        
        # Размеры
        size_text = f"{self._crop_w} × {self._crop_h} px"
        painter.setPen(Qt.white)
        painter.drawText(crop_rect.x() + 5, crop_rect.y() + 20, size_text)


# ============================================================================
# ДИАЛОГ ОБРЕЗКИ
# ============================================================================

class CropDialog(QDialog):
    """Диалог интерактивной обрезки"""
    
    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Обрезка — {image_path.name}")
        self.setMinimumSize(900, 700)
        self.resize(1100, 800)
        
        self._image_path = image_path
        self._crop_rect: Optional[Tuple[int, int, int, int]] = None
        self._updating_fields = False  # Флаг для предотвращения рекурсии
        
        self._setup_ui()
        self._load_image()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Верхняя панель с настройками
        settings_layout = QHBoxLayout()
        
        # Пресет соотношения сторон
        settings_layout.addWidget(QLabel("Соотношение:"))
        self._ratio_combo = QComboBox()
        self._ratio_combo.addItems(ASPECT_RATIO_PRESETS.keys())
        self._ratio_combo.currentTextChanged.connect(self._on_ratio_changed)
        self._ratio_combo.setMinimumWidth(140)
        settings_layout.addWidget(self._ratio_combo)
        
        settings_layout.addSpacing(20)
        
        # Поля ввода размеров
        settings_layout.addWidget(QLabel("Ширина:"))
        self._width_input = QLineEdit()
        self._width_input.setFixedWidth(70)
        self._width_input.setAlignment(Qt.AlignRight)
        self._width_input.textChanged.connect(self._on_width_changed)
        settings_layout.addWidget(self._width_input)
        
        settings_layout.addWidget(QLabel("px"))
        settings_layout.addSpacing(10)
        
        # Кнопка связи пропорций
        self._link_btn = QPushButton("🔗")
        self._link_btn.setFixedSize(28, 28)
        self._link_btn.setCheckable(True)
        self._link_btn.setToolTip("Связать пропорции")
        self._link_btn.clicked.connect(self._on_link_toggled)
        settings_layout.addWidget(self._link_btn)
        
        settings_layout.addSpacing(10)
        settings_layout.addWidget(QLabel("Высота:"))
        self._height_input = QLineEdit()
        self._height_input.setFixedWidth(70)
        self._height_input.setAlignment(Qt.AlignRight)
        self._height_input.textChanged.connect(self._on_height_changed)
        settings_layout.addWidget(self._height_input)
        
        settings_layout.addWidget(QLabel("px"))
        
        settings_layout.addStretch()
        layout.addLayout(settings_layout)
        
        # Виджет обрезки
        self._crop_widget = CropWidget()
        self._crop_widget.crop_changed.connect(self._on_crop_changed)
        layout.addWidget(self._crop_widget, 1)
        
        # Информация
        info_layout = QHBoxLayout()
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #888; font-size: 12px;")
        info_layout.addWidget(self._info_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        # Кнопки
        btn_layout = QHBoxLayout()
        
        reset_btn = QPushButton("Сбросить")
        reset_btn.clicked.connect(self._reset_crop)
        btn_layout.addWidget(reset_btn)
        
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        apply_btn = QPushButton("Применить")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._apply)
        btn_layout.addWidget(apply_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_image(self):
        pixmap = QPixmap(str(self._image_path))
        if pixmap.isNull():
            QMessageBox.critical(self, "Ошибка", "Не удалось загрузить изображение")
            self.reject()
            return
        
        self._original_size = (pixmap.width(), pixmap.height())
        self._crop_widget.set_image(pixmap)
        self._on_crop_changed()
        self._update_info()
    
    def _on_ratio_changed(self, text: str):
        ratio = ASPECT_RATIO_PRESETS.get(text)
        self._crop_widget.set_aspect_ratio(ratio)
        
        # Если выбран пресет — автоматически связываем пропорции
        if ratio:
            self._link_btn.setChecked(True)
        else:
            self._link_btn.setChecked(False)
    
    def _on_link_toggled(self, checked: bool):
        if checked and self._ratio_combo.currentText() == 'Свободно':
            # Вычисляем текущее соотношение
            crop = self._crop_widget.get_crop_rect_original()
            if crop[2] > 0 and crop[3] > 0:
                # Устанавливаем текущее соотношение как фиксированное
                from math import gcd
                g = gcd(crop[2], crop[3])
                ratio = (crop[2] // g, crop[3] // g)
                self._crop_widget.set_aspect_ratio(ratio)
        elif not checked:
            self._crop_widget.set_aspect_ratio(None)
            self._ratio_combo.setCurrentText('Свободно')
    
    def _on_crop_changed(self):
        if self._updating_fields:
            return
        
        self._updating_fields = True
        crop = self._crop_widget.get_crop_rect_original()
        self._width_input.setText(str(crop[2]))
        self._height_input.setText(str(crop[3]))
        self._update_info()
        self._updating_fields = False
    
    def _on_width_changed(self, text: str):
        if self._updating_fields:
            return
        
        try:
            width = int(text)
            if width < 10:
                return
            
            # Ограничиваем размером оригинала
            if hasattr(self, '_original_size'):
                width = min(width, self._original_size[0])
            
            crop = self._crop_widget.get_crop_rect_original()
            height = crop[3]
            
            # Если связаны пропорции — пересчитываем высоту
            if self._link_btn.isChecked() and crop[2] > 0:
                ratio = crop[3] / crop[2]
                height = int(width * ratio)
                if hasattr(self, '_original_size'):
                    height = min(height, self._original_size[1])
                self._updating_fields = True
                self._height_input.setText(str(height))
                self._updating_fields = False
            
            self._crop_widget.set_crop_size(width, height)
            
        except ValueError:
            pass
    
    def _on_height_changed(self, text: str):
        if self._updating_fields:
            return
        
        try:
            height = int(text)
            if height < 10:
                return
            
            # Ограничиваем размером оригинала
            if hasattr(self, '_original_size'):
                height = min(height, self._original_size[1])
            
            crop = self._crop_widget.get_crop_rect_original()
            width = crop[2]
            
            # Если связаны пропорции — пересчитываем ширину
            if self._link_btn.isChecked() and crop[3] > 0:
                ratio = crop[2] / crop[3]
                width = int(height * ratio)
                if hasattr(self, '_original_size'):
                    width = min(width, self._original_size[0])
                self._updating_fields = True
                self._width_input.setText(str(width))
                self._updating_fields = False
            
            self._crop_widget.set_crop_size(width, height)
            
        except ValueError:
            pass
    
    def _update_info(self):
        crop = self._crop_widget.get_crop_rect_original()
        if hasattr(self, '_original_size'):
            orig_w, orig_h = self._original_size
            self._info_label.setText(
                f"Оригинал: {orig_w}×{orig_h} px  |  "
                f"Обрезка: {crop[2]}×{crop[3]} px  |  "
                f"Позиция: ({crop[0]}, {crop[1]})"
            )
    
    def _reset_crop(self):
        self._ratio_combo.setCurrentText('Свободно')
        self._link_btn.setChecked(False)
        self._crop_widget.set_aspect_ratio(None)
        self._crop_widget.reset_crop()
    
    def _apply(self):
        self._crop_rect = self._crop_widget.get_crop_rect_original()
        self.accept()
    
    def get_crop_rect(self) -> Optional[Tuple[int, int, int, int]]:
        return self._crop_rect


# ============================================================================
# ДИАЛОГ ПЕРЕИМЕНОВАНИЯ
# ============================================================================

class RenameDialog(QDialog):
    """Диалог для массового переименования файлов"""
    
    def __init__(self, file_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Переименовать все")
        self.setMinimumWidth(500)
        
        self._file_count = file_count
        self._generated_names: List[str] = []
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Инструкция
        info_label = QLabel(
            f"Введите ключевые слова через пробел.\n"
            f"Из них будут сгенерированы {self._file_count} уникальных имён."
        )
        info_label.setStyleSheet("color: #aaa; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Поле ввода
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Ключевые слова:"))
        
        self._keywords_input = QLineEdit()
        self._keywords_input.setPlaceholderText("например: december turkey")
        self._keywords_input.textChanged.connect(self._on_keywords_changed)
        input_layout.addWidget(self._keywords_input, 1)
        
        layout.addLayout(input_layout)
        
        # Статистика
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("color: #888; font-size: 12px; margin-top: 5px;")
        layout.addWidget(self._stats_label)
        
        # Предпросмотр
        preview_group = QGroupBox("Предпросмотр имён")
        preview_layout = QVBoxLayout(preview_group)
        
        self._preview_list = QListWidget()
        self._preview_list.setMaximumHeight(200)
        preview_layout.addWidget(self._preview_list)
        
        layout.addWidget(preview_group)
        
        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        self._apply_btn = QPushButton("Применить")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply)
        btn_layout.addWidget(self._apply_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_keywords_changed(self, text: str):
        words = text.strip().split()
        
        if len(words) < 2:
            self._stats_label.setText("Введите минимум 2 слова")
            self._preview_list.clear()
            self._apply_btn.setEnabled(False)
            self._generated_names = []
            return
        
        # Оцениваем количество комбинаций
        estimated = NameGenerator.estimate_combinations(len(words))
        
        # Генерируем имена
        generator = NameGenerator(words)
        self._generated_names = generator.generate(self._file_count)
        
        # Статистика
        if estimated >= self._file_count:
            self._stats_label.setText(
                f"✅ {len(words)} слов → ~{estimated} комбинаций (нужно {self._file_count})"
            )
            self._stats_label.setStyleSheet("color: #4caf50; font-size: 12px; margin-top: 5px;")
        else:
            self._stats_label.setText(
                f"⚠️ {len(words)} слов → ~{estimated} комбинаций. "
                f"Недостающие {self._file_count - estimated} будут с цифрами."
            )
            self._stats_label.setStyleSheet("color: #ff9800; font-size: 12px; margin-top: 5px;")
        
        # Обновляем предпросмотр
        self._preview_list.clear()
        for i, name in enumerate(self._generated_names[:20]):  # Показываем первые 20
            self._preview_list.addItem(f"{i+1}. {name}.webp")
        
        if len(self._generated_names) > 20:
            self._preview_list.addItem(f"... и ещё {len(self._generated_names) - 20}")
        
        self._apply_btn.setEnabled(True)
    
    def _apply(self):
        self.accept()
    
    def get_names(self) -> List[str]:
        return self._generated_names


# ============================================================================
# ПОТОК КОНВЕРТАЦИИ
# ============================================================================

class ConversionWorker(QThread):
    """Поток для конвертации изображений"""
    
    progress = Signal(int, str)  # real_index, status
    item_done = Signal(int, str, float)  # real_index, output_path, size_kb
    item_error = Signal(int, str)  # real_index, error_message
    finished_all = Signal()
    
    def __init__(self, items_with_indices: List[tuple], quality: int, output_dir: Path):
        """
        items_with_indices: список кортежей (real_index, ImageItem)
        """
        super().__init__()
        self._items_with_indices = items_with_indices
        self._quality = quality
        self._output_dir = output_dir
        self._cancelled = False
    
    def cancel(self):
        self._cancelled = True
    
    def run(self):
        for real_index, item in self._items_with_indices:
            if self._cancelled:
                break
            
            self.progress.emit(real_index, "processing")
            
            try:
                # Загрузка
                img = ImageProcessor.load_image(item.path)
                
                # Обрезка если задана
                if item.crop_rect:
                    img = ImageProcessor.crop_image(img, item.crop_rect)
                
                # Конвертация
                webp_data = ImageProcessor.convert_to_webp(img, self._quality)
                
                # Определяем имя файла
                if item.output_name:
                    base_name = item.output_name
                else:
                    base_name = item.path.stem
                
                output_name = base_name + OUTPUT_FORMAT
                output_path = self._output_dir / output_name
                
                # Если файл существует, добавляем номер
                counter = 1
                while output_path.exists():
                    output_name = f"{base_name}_{counter}{OUTPUT_FORMAT}"
                    output_path = self._output_dir / output_name
                    counter += 1
                
                with open(output_path, 'wb') as f:
                    f.write(webp_data)
                
                size_kb = len(webp_data) / 1024
                self.item_done.emit(real_index, str(output_path), size_kb)
                
            except Exception as e:
                self.item_error.emit(real_index, str(e))
        
        self.finished_all.emit()


# ============================================================================
# ВИДЖЕТ DRAG & DROP
# ============================================================================

class DropZone(QFrame):
    """Зона для перетаскивания файлов"""
    
    files_dropped = Signal(list)  # List[Path]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.setStyleSheet("""
            DropZone {
                background-color: #2d2d2d;
                border: 2px dashed #555;
                border-radius: 8px;
            }
            DropZone:hover {
                border-color: #0078d4;
                background-color: #363636;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        icon_label = QLabel("📁")
        icon_label.setStyleSheet("font-size: 32px;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        
        text_label = QLabel("Перетащите изображения сюда\nили нажмите для выбора")
        text_label.setStyleSheet("color: #aaa; font-size: 14px;")
        text_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(text_label)
        
        self._text_label = text_label
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._open_file_dialog()
    
    def _open_file_dialog(self):
        formats = " ".join(f"*{fmt}" for fmt in SUPPORTED_INPUT_FORMATS)
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите изображения",
            "",
            f"Изображения ({formats})"
        )
        if files:
            self.files_dropped.emit([Path(f) for f in files])
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            # Проверяем, есть ли хоть один подходящий файл
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.suffix.lower() in SUPPORTED_INPUT_FORMATS:
                        event.acceptProposedAction()
                        self.setStyleSheet("""
                            DropZone {
                                background-color: #1a3a1a;
                                border: 2px dashed #4caf50;
                                border-radius: 8px;
                            }
                        """)
                        return
    
    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            DropZone {
                background-color: #2d2d2d;
                border: 2px dashed #555;
                border-radius: 8px;
            }
            DropZone:hover {
                border-color: #0078d4;
                background-color: #363636;
            }
        """)
    
    def dropEvent(self, event: QDropEvent):
        self.dragLeaveEvent(None)
        
        files = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.suffix.lower() in SUPPORTED_INPUT_FORMATS:
                    files.append(path)
        
        if files:
            self.files_dropped.emit(files)


class ImagePreviewWidget(QWidget):
    """Виджет предпросмотра изображения"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(250)
        self.setMaximumWidth(400)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Контейнер для изображения
        self._image_container = QFrame()
        self._image_container.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
            }
        """)
        container_layout = QVBoxLayout(self._image_container)
        container_layout.setAlignment(Qt.AlignCenter)
        
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setMinimumSize(200, 150)
        self._image_label.setStyleSheet("border: none; background: transparent;")
        container_layout.addWidget(self._image_label)
        
        layout.addWidget(self._image_container, 1)
        
        # Информация о файле
        self._info_frame = QFrame()
        self._info_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        info_layout = QVBoxLayout(self._info_frame)
        info_layout.setSpacing(4)
        
        self._filename_label = QLabel("")
        self._filename_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self._filename_label.setWordWrap(True)
        info_layout.addWidget(self._filename_label)
        
        self._details_label = QLabel("")
        self._details_label.setStyleSheet("color: #888; font-size: 12px;")
        info_layout.addWidget(self._details_label)
        
        self._crop_label = QLabel("")
        self._crop_label.setStyleSheet("color: #4caf50; font-size: 12px;")
        info_layout.addWidget(self._crop_label)
        
        layout.addWidget(self._info_frame)
        
        self.clear_preview()
    
    def clear_preview(self):
        """Очистить предпросмотр"""
        self._image_label.setText("Выберите\nизображение")
        self._image_label.setStyleSheet("border: none; background: transparent; color: #666;")
        self._filename_label.setText("")
        self._details_label.setText("")
        self._crop_label.setText("")
        self._info_frame.setVisible(False)
    
    def show_preview(self, item: 'ImageItem'):
        """Показать предпросмотр для элемента"""
        # Загружаем изображение
        pixmap = QPixmap(str(item.path))
        if pixmap.isNull():
            self.clear_preview()
            return
        
        # Масштабируем для предпросмотра
        preview_size = self._image_label.size()
        scaled = pixmap.scaled(
            preview_size.width() - 20,
            preview_size.height() - 20,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self._image_label.setPixmap(scaled)
        self._image_label.setStyleSheet("border: none; background: transparent;")
        
        # Информация о файле
        if item.output_name:
            self._filename_label.setText(f"→ {item.output_name}.webp")
            self._filename_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #4caf50;")
        else:
            self._filename_label.setText(item.filename)
            self._filename_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        
        # Размер файла
        try:
            file_size = item.path.stat().st_size / 1024
            size_str = f"{file_size:.1f} KB" if file_size < 1024 else f"{file_size/1024:.2f} MB"
        except:
            size_str = "—"
        
        self._details_label.setText(
            f"Размер: {item.original_size[0]}×{item.original_size[1]} px\n"
            f"Файл: {size_str}"
        )
        
        # Информация об обрезке
        if item.crop_rect:
            self._crop_label.setText(
                f"✂️ Обрезка: {item.crop_rect[2]}×{item.crop_rect[3]} px"
            )
            self._crop_label.setStyleSheet("color: #ff9800; font-size: 12px;")
            self._crop_label.setVisible(True)
        else:
            self._crop_label.setVisible(False)
        
        # Статус конвертации
        if item.status == 'done' and item.output_size_kb:
            original_size = item.path.stat().st_size / 1024
            saving = ((original_size - item.output_size_kb) / original_size) * 100
            self._crop_label.setText(
                f"✅ WebP: {item.output_size_kb:.1f} KB (−{saving:.0f}%)"
            )
            self._crop_label.setStyleSheet("color: #4caf50; font-size: 12px;")
            self._crop_label.setVisible(True)
        
        self._info_frame.setVisible(True)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Можно обновить предпросмотр при изменении размера


# ============================================================================
# ГЛАВНОЕ ОКНО
# ============================================================================

class MainWindow(QMainWindow):
    """Главное окно приложения"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(900, 600)
        self.resize(1100, 750)
        
        self._items: List[ImageItem] = []
        self._worker: Optional[ConversionWorker] = None
        
        # Определяем папку приложения
        # Работает и при запуске из исходников, и из .app бандла
        if getattr(sys, 'frozen', False):
            # Запуск из собранного приложения
            self._app_dir = Path(sys.executable).parent
        else:
            # Запуск из исходников
            self._app_dir = Path(__file__).parent
        
        self._output_dir = self._app_dir / "converted"
        
        self._setup_ui()
        self._load_settings()
        self._ensure_output_dir()
    
    def _ensure_output_dir(self):
        """Создать папку для результатов"""
        self._output_dir.mkdir(exist_ok=True)
    
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Стили
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1084d8;
            }
            QPushButton:pressed {
                background-color: #006cbd;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #888;
            }
            QPushButton#secondary {
                background-color: #444;
            }
            QPushButton#secondary:hover {
                background-color: #555;
            }
            QPushButton#danger {
                background-color: #d32f2f;
            }
            QPushButton#danger:hover {
                background-color: #e53935;
            }
            QListWidget {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3a3a3a;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #444;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: #0078d4;
                border-radius: 3px;
            }
            QComboBox {
                background-color: #2d2d2d;
                border: 1px solid #444;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                selection-background-color: #0078d4;
            }
            QProgressBar {
                background-color: #2d2d2d;
                border: none;
                border-radius: 4px;
                height: 8px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
                border-radius: 4px;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel#info {
                color: #888;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #2d2d2d;
                border: 1px solid #444;
                padding: 4px 8px;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """)
        
        # Drop zone
        self._drop_zone = DropZone()
        self._drop_zone.files_dropped.connect(self._add_files)
        main_layout.addWidget(self._drop_zone)
        
        # Область списка файлов + предпросмотр
        content_layout = QHBoxLayout()
        
        # Левая часть — список файлов
        files_group = QGroupBox("Очередь файлов")
        files_layout = QVBoxLayout(files_group)
        
        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._file_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._file_list.itemSelectionChanged.connect(self._on_selection_changed)
        files_layout.addWidget(self._file_list)
        
        # Кнопки управления списком
        list_btn_layout = QHBoxLayout()
        
        crop_btn = QPushButton("✂️ Обрезать")
        crop_btn.setObjectName("secondary")
        crop_btn.clicked.connect(self._crop_selected)
        list_btn_layout.addWidget(crop_btn)
        
        rename_btn = QPushButton("✏️ Переименовать")
        rename_btn.setObjectName("secondary")
        rename_btn.clicked.connect(self._rename_all)
        list_btn_layout.addWidget(rename_btn)
        
        remove_btn = QPushButton("🗑️ Удалить")
        remove_btn.setObjectName("danger")
        remove_btn.clicked.connect(self._remove_selected)
        list_btn_layout.addWidget(remove_btn)
        
        clear_btn = QPushButton("Очистить всё")
        clear_btn.setObjectName("secondary")
        clear_btn.clicked.connect(self._clear_all)
        list_btn_layout.addWidget(clear_btn)
        
        list_btn_layout.addStretch()
        files_layout.addLayout(list_btn_layout)
        
        content_layout.addWidget(files_group, 1)
        
        # Правая часть — предпросмотр
        self._preview_widget = ImagePreviewWidget()
        content_layout.addWidget(self._preview_widget)
        
        main_layout.addLayout(content_layout, 1)
        
        # Настройки качества
        quality_group = QGroupBox("Качество WebP")
        quality_layout = QVBoxLayout(quality_group)
        
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Пресет:"))
        
        self._preset_combo = QComboBox()
        self._preset_combo.addItems(QUALITY_PRESETS.keys())
        self._preset_combo.addItem("Вручную")
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(self._preset_combo)
        preset_layout.addStretch()
        quality_layout.addLayout(preset_layout)
        
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(QLabel("Quality:"))
        
        self._quality_slider = QSlider(Qt.Horizontal)
        self._quality_slider.setRange(1, 100)
        self._quality_slider.setValue(75)
        self._quality_slider.valueChanged.connect(self._on_quality_changed)
        slider_layout.addWidget(self._quality_slider, 1)
        
        self._quality_label = QLabel("75")
        self._quality_label.setMinimumWidth(30)
        slider_layout.addWidget(self._quality_label)
        
        quality_layout.addLayout(slider_layout)
        main_layout.addWidget(quality_group)
        
        # Прогресс
        progress_layout = QHBoxLayout()
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        progress_layout.addWidget(self._progress_bar, 1)
        
        self._status_label = QLabel("")
        self._status_label.setObjectName("info")
        progress_layout.addWidget(self._status_label)
        
        main_layout.addLayout(progress_layout)
        
        # Кнопка конвертации
        convert_layout = QHBoxLayout()
        convert_layout.addStretch()
        
        self._open_folder_btn = QPushButton("📂 Открыть папку")
        self._open_folder_btn.setObjectName("secondary")
        self._open_folder_btn.clicked.connect(self._open_output_folder)
        convert_layout.addWidget(self._open_folder_btn)
        
        self._convert_btn = QPushButton("🚀 Конвертировать")
        self._convert_btn.setMinimumWidth(150)
        self._convert_btn.clicked.connect(self._start_conversion)
        convert_layout.addWidget(self._convert_btn)
        
        main_layout.addLayout(convert_layout)
    
    def _load_settings(self):
        """Загрузить сохранённые настройки"""
        settings_path = self._app_dir / SETTINGS_FILE
        if settings_path.exists():
            try:
                with open(settings_path, 'r') as f:
                    data = json.load(f)
                    quality = data.get('quality', 75)
                    self._quality_slider.setValue(quality)
                    
                    # Выбираем пресет или "Вручную"
                    preset_found = False
                    for preset_name, preset_value in QUALITY_PRESETS.items():
                        if preset_value == quality:
                            self._preset_combo.setCurrentText(preset_name)
                            preset_found = True
                            break
                    if not preset_found:
                        self._preset_combo.setCurrentText("Вручную")
            except Exception:
                pass
    
    def _save_settings(self):
        """Сохранить настройки"""
        settings_path = self._app_dir / SETTINGS_FILE
        try:
            with open(settings_path, 'w') as f:
                json.dump({'quality': self._quality_slider.value()}, f)
        except Exception:
            pass
    
    def _add_files(self, paths: List[Path]):
        """Добавить файлы в очередь"""
        for path in paths:
            # Проверяем, не добавлен ли уже
            if any(item.path == path for item in self._items):
                continue
            
            try:
                size = ImageProcessor.get_image_size(path)
                item = ImageItem(path=path, original_size=size)
                self._items.append(item)
                self._update_list_item(len(self._items) - 1)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить {path.name}: {e}")
        
        self._update_status()
    
    def _update_list_item(self, index: int):
        """Обновить или создать элемент списка"""
        item = self._items[index]
        
        # Формируем текст
        status_icons = {
            'pending': '⏳',
            'processing': '⚙️',
            'done': '✅',
            'error': '❌'
        }
        icon = status_icons.get(item.status, '⏳')
        
        # Имя файла (с учётом переименования)
        if item.output_name:
            name_display = f"{item.output_name}.webp ← {item.filename}"
        else:
            name_display = item.filename
        
        crop_info = " [обрезано]" if item.crop_rect else ""
        size_info = ""
        if item.output_size_kb:
            size_info = f" → {item.output_size_kb:.1f} KB"
        
        text = f"{icon} {name_display}{crop_info} ({item.dimensions_str}){size_info}"
        
        if index < self._file_list.count():
            self._file_list.item(index).setText(text)
        else:
            self._file_list.addItem(text)
    
    def _update_status(self):
        """Обновить статус"""
        total = len(self._items)
        done = sum(1 for item in self._items if item.status == 'done')
        if total > 0:
            self._status_label.setText(f"Файлов: {total}, готово: {done}")
        else:
            self._status_label.setText("")
    
    def _on_item_double_clicked(self, list_item: QListWidgetItem):
        """Двойной клик — открыть обрезку"""
        index = self._file_list.row(list_item)
        if 0 <= index < len(self._items):
            self._open_crop_dialog(index)
    
    def _on_selection_changed(self):
        """Изменение выбора — обновить предпросмотр"""
        selected = self._file_list.selectedIndexes()
        if selected and len(selected) == 1:
            index = selected[0].row()
            if 0 <= index < len(self._items):
                self._preview_widget.show_preview(self._items[index])
        else:
            self._preview_widget.clear_preview()
    
    def _crop_selected(self):
        """Обрезать выбранные файлы"""
        selected = self._file_list.selectedIndexes()
        if not selected:
            QMessageBox.information(self, "Обрезка", "Выберите файл для обрезки")
            return
        
        # Обрезаем только первый выбранный
        self._open_crop_dialog(selected[0].row())
    
    def _rename_all(self):
        """Переименовать все файлы"""
        if not self._items:
            QMessageBox.information(self, "Переименование", "Добавьте файлы для переименования")
            return
        
        dialog = RenameDialog(len(self._items), self)
        
        if dialog.exec() == QDialog.Accepted:
            names = dialog.get_names()
            
            # Применяем имена к элементам
            for i, item in enumerate(self._items):
                if i < len(names):
                    item.output_name = names[i]
                self._update_list_item(i)
            
            QMessageBox.information(
                self, 
                "Переименование", 
                f"Назначено {len(names)} уникальных имён"
            )
    
    def _open_crop_dialog(self, index: int):
        """Открыть диалог обрезки"""
        if index < 0 or index >= len(self._items):
            return
        
        item = self._items[index]
        dialog = CropDialog(item.path, self)
        
        if dialog.exec() == QDialog.Accepted:
            crop_rect = dialog.get_crop_rect()
            if crop_rect and crop_rect[2] > 0 and crop_rect[3] > 0:
                item.crop_rect = crop_rect
                self._update_list_item(index)
                # Обновляем preview если этот элемент выбран
                self._on_selection_changed()
    
    def _remove_selected(self):
        """Удалить выбранные файлы"""
        selected = sorted([idx.row() for idx in self._file_list.selectedIndexes()], reverse=True)
        for index in selected:
            if 0 <= index < len(self._items):
                del self._items[index]
                self._file_list.takeItem(index)
        self._update_status()
    
    def _clear_all(self):
        """Очистить всю очередь"""
        self._items.clear()
        self._file_list.clear()
        self._update_status()
    
    def _on_preset_changed(self, text: str):
        """Изменение пресета"""
        if text in QUALITY_PRESETS:
            self._quality_slider.setValue(QUALITY_PRESETS[text])
    
    def _on_quality_changed(self, value: int):
        """Изменение качества"""
        self._quality_label.setText(str(value))
        
        # Проверяем, соответствует ли какому-то пресету
        current_preset = self._preset_combo.currentText()
        if current_preset != "Вручную":
            if QUALITY_PRESETS.get(current_preset) != value:
                self._preset_combo.blockSignals(True)
                self._preset_combo.setCurrentText("Вручную")
                self._preset_combo.blockSignals(False)
    
    def _start_conversion(self):
        """Запустить конвертацию"""
        if not self._items:
            QMessageBox.information(self, "Конвертация", "Добавьте файлы для конвертации")
            return
        
        # Собираем pending элементы с их реальными индексами
        items_with_indices = [
            (i, item) for i, item in enumerate(self._items) 
            if item.status in ('pending', 'error')
        ]
        
        if not items_with_indices:
            QMessageBox.information(self, "Конвертация", "Все файлы уже обработаны")
            return
        
        self._save_settings()
        self._ensure_output_dir()
        
        # Блокируем интерфейс
        self._convert_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setMaximum(len(items_with_indices))
        self._progress_bar.setValue(0)
        
        # Запускаем worker
        self._worker = ConversionWorker(
            items_with_indices,
            self._quality_slider.value(),
            self._output_dir
        )
        self._worker.progress.connect(self._on_conversion_progress)
        self._worker.item_done.connect(self._on_item_done)
        self._worker.item_error.connect(self._on_item_error)
        self._worker.finished_all.connect(self._on_conversion_finished)
        self._worker.start()
    
    def _on_conversion_progress(self, real_index: int, status: str):
        """Прогресс конвертации"""
        if 0 <= real_index < len(self._items):
            self._items[real_index].status = status
            self._update_list_item(real_index)
    
    def _on_item_done(self, real_index: int, output_path: str, size_kb: float):
        """Элемент обработан"""
        if 0 <= real_index < len(self._items):
            item = self._items[real_index]
            item.status = 'done'
            item.output_path = Path(output_path)
            item.output_size_kb = size_kb
            self._update_list_item(real_index)
            # Обновляем preview если этот элемент выбран
            self._on_selection_changed()
        
        self._progress_bar.setValue(self._progress_bar.value() + 1)
        self._update_status()
    
    def _on_item_error(self, real_index: int, error: str):
        """Ошибка обработки"""
        if 0 <= real_index < len(self._items):
            self._items[real_index].status = 'error'
            self._update_list_item(real_index)
        
        self._progress_bar.setValue(self._progress_bar.value() + 1)
    
    def _on_conversion_finished(self):
        """Конвертация завершена"""
        self._convert_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._worker = None
        
        done_count = sum(1 for item in self._items if item.status == 'done')
        error_count = sum(1 for item in self._items if item.status == 'error')
        
        if error_count > 0:
            QMessageBox.warning(
                self,
                "Конвертация завершена",
                f"Готово: {done_count}, ошибок: {error_count}"
            )
        else:
            QMessageBox.information(
                self,
                "Конвертация завершена",
                f"Успешно конвертировано: {done_count} файлов"
            )
    
    def _open_output_folder(self):
        """Открыть папку с результатами"""
        self._ensure_output_dir()
        os.system(f'open "{self._output_dir}"')
    
    def closeEvent(self, event):
        """Закрытие приложения"""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()
        self._save_settings()
        event.accept()


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Тёмная тема
    palette = app.palette()
    palette.setColor(palette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(palette.ColorRole.WindowText, QColor(224, 224, 224))
    palette.setColor(palette.ColorRole.Base, QColor(45, 45, 45))
    palette.setColor(palette.ColorRole.AlternateBase, QColor(35, 35, 35))
    palette.setColor(palette.ColorRole.ToolTipBase, QColor(224, 224, 224))
    palette.setColor(palette.ColorRole.ToolTipText, QColor(224, 224, 224))
    palette.setColor(palette.ColorRole.Text, QColor(224, 224, 224))
    palette.setColor(palette.ColorRole.Button, QColor(45, 45, 45))
    palette.setColor(palette.ColorRole.ButtonText, QColor(224, 224, 224))
    palette.setColor(palette.ColorRole.BrightText, Qt.red)
    palette.setColor(palette.ColorRole.Highlight, QColor(0, 120, 212))
    palette.setColor(palette.ColorRole.HighlightedText, Qt.white)
    app.setPalette(palette)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
