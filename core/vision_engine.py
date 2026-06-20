import logging
import asyncio
from io import BytesIO
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
import torch

logger = logging.getLogger(__name__)

class VisionEngine:
    def __init__(self):
        self.processor = None
        self.model = None
        self.device = "cpu"

    def load(self):
        if self.model is not None:
            return
        logger.info("Загрузка модели BLIP для описания изображений (около 1.2 ГБ)...")
        try:
            self.processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-large")
            self.model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-large")
            self.model.to(self.device)
            self.model.eval()
            logger.info("Модель BLIP загружена")
        except Exception as e:
            logger.exception("Ошибка загрузки BLIP")
            raise

    async def describe_image(self, image_bytes: bytes) -> str:
        if self.model is None:
            self.load()
        loop = asyncio.get_event_loop()
        caption = await loop.run_in_executor(None, self._predict_sync, image_bytes)
        return caption

    def _predict_sync(self, image_bytes: bytes) -> str:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        inputs = self.processor(image, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.generate(**inputs, max_length=50, num_beams=4)
        caption = self.processor.decode(out[0], skip_special_tokens=True)
        return caption.strip()
