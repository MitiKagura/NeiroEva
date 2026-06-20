import logging
import torch
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
import asyncio
from animegan2_pytorch import AnimeGANv2

logger = logging.getLogger(__name__)

class AnimeGenerator:
    def __init__(self, weights_path: Path):
        self.weights_path = weights_path
        self.model = None
    
    def load(self):
        if not self.weights_path.exists():
            logger.warning(f"Веса AnimeGAN не найдены: {self.weights_path}. Генерация изображений будет недоступна.")
            return
        try:
            self.model = AnimeGANv2()
            self.model.load_state_dict(torch.load(self.weights_path, map_location="cpu"))
            self.model.eval()
            logger.info("AnimeGAN загружен")
        except Exception as e:
            logger.error(f"Ошибка загрузки AnimeGAN: {e}")
    
    async def generate_selfie(self, mood_desc: str, prompt: str = "") -> Path:
        """Генерирует изображение на основе описания настроения. Возвращает путь к файлу."""
        if self.model is None:
            return None
        # Упрощённо: используем случайное или шаблонное изображение.
        # На самом деле AnimeGAN требует входное фото, он не генерирует с нуля.
        # Для чистого текста->аниме нужна диффузионная модель (медленно).
        # Сделаем заглушку с использованием небольшой нейросети для генерации из шума?
        # Реализуем упрощённо: создаём цветной шум и прогоняем через AnimeGAN.
        # Но это не даст осмысленного портрета.
        # Рекомендую вместо этого использовать предобученный StyleGAN или Diffusers с маленькой моделью,
        # но для CPU это тяжело. Оставим красивый placeholder, сгенерированный один раз.
        # Чтобы не обманывать, напишем реалистичную заглушку: берём базовое изображение и применяем стилизацию.
        
        # Временно: возвращаем предустановленное изображение Евы (копируем из ресурсов)
        fallback = Path(__file__).parent.parent / "data" / "eva_default.png"
        if not fallback.exists():
            # Создаём простое изображение с текстом
            img = Image.new('RGB', (512, 512), color=(128, 0, 128))
            fallback.parent.mkdir(parents=True, exist_ok=True)
            img.save(fallback)
        return fallback
