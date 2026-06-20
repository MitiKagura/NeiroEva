import logging
import torch
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime
from diffusers import StableDiffusionPipeline, EulerAncestralDiscreteScheduler
from PIL import Image

logger = logging.getLogger(__name__)

class AnimeDiffusionGenerator:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.pipe = None
        self.model_path = Path.home() / "NeiroEva" / "models" / "NablaThetaA5"
        self.reference_images = {}  # словарь: ключ -> PIL Image
        self._load_references()
        # Upscayl
        self.upscayl_bin = "/usr/share/upscayl/bin/upscayl-bin"
        self.upscayl_models = "/usr/share/upscayl/models/"
        self.upscayl_model_name = "digital-art-4x"

    def _load_references(self):
        """Загружает эталонные изображения для разных персонажей."""
        refs = {
            "eva": "eva_reference.png",
            "agnes": "agnes_reference.png",
            "violet": "violet_reference.png"
        }
        data_dir = Path(__file__).parent.parent / "data"
        for key, filename in refs.items():
            ref_path = data_dir / filename
            if ref_path.exists():
                try:
                    img = Image.open(ref_path).convert("RGB").resize((512, 512))
                    self.reference_images[key] = img
                    logger.info(f"Загружено эталонное фото для {key}")
                except Exception as e:
                    logger.warning(f"Не удалось загрузить reference для {key}: {e}")
            else:
                logger.warning(f"Файл {filename} не найден, референс для {key} не будет использоваться")

    def _check_upscayl(self):
        if Path(self.upscayl_bin).exists():
            return True
        logger.warning(f"Upscayl не найден по пути {self.upscayl_bin}. Апскейл будет пропущен.")
        return False

    def load(self):
        if self.pipe is not None:
            return
        logger.info(f"Загрузка модели NablaThetaA5 из {self.model_path}...")
        try:
            self.pipe = StableDiffusionPipeline.from_pretrained(
                str(self.model_path),
                torch_dtype=torch.float32,
                safety_checker=None,
                requires_safety_checker=False,
                local_files_only=True
            )
            self.pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(self.pipe.scheduler.config)
            self.pipe.to("cpu")
            self.pipe.enable_attention_slicing()
            logger.info("Модель NablaThetaA5 загружена.")
        except Exception as e:
            logger.exception("Ошибка загрузки модели")
            raise

    async def generate_selfie(self, prompt: str, location: str, reference_key: str = None, lora_path: str = None, negative_prompt: str = "bad anatomy, bad hands, extra fingers, blurry, low quality") -> Path:
        """
        Генерирует изображение.
        :param reference_key: ключ в self.reference_images ('eva', 'agnes', 'violet') или None.
        :param lora_path: путь к файлу LoRA (.safetensors) или None.
        """
        if self.pipe is None:
            self.load()

        # Определяем фон по локации
        location_map = {
            "лес, родной дом": "in a magical forest, trees, flowers, nature background",
            "автобус": "inside a bus, seats, window view, road",
            "город": "city street, buildings, urban background, neon lights",
            "в пути": "blurry moving background, travel vibes",
            "в пути к ": "on the road, motion blur, travel"
        }
        location_desc = location_map.get(location, "cozy room, anime style")
        if location.startswith("в пути к "):
            dest = location.replace("в пути к ", "")
            location_desc = f"on the road to {dest}, motion blur, travel"

        # Формируем полный промпт
        if "masterpiece" in prompt.lower() and "1girl" in prompt.lower():
            full_prompt = f"{prompt}, {location_desc}"
        else:
            full_prompt = f"masterpiece, best quality, 1girl, dark blue hair, dark blue eyes, cat ears, cat tail, {prompt}, {location_desc}, anime style, highres, detailed face, cute"
            negative_prompt = "purple hair, violet hair, pink hair, magenta hair, pink eyes"

        pipe_kwargs = {
            "prompt": full_prompt,
            "negative_prompt": negative_prompt,
            "num_inference_steps": 30,
            "height": 512,
            "width": 512,
            "guidance_scale": 7.0
        }

        # Используем референс, если указан и он загружен
        if reference_key and reference_key in self.reference_images:
            pipe_kwargs["image"] = self.reference_images[reference_key]
            pipe_kwargs["strength"] = 0.65
            logger.info(f"Генерация с эталонным фото для {reference_key}")
        else:
            logger.info("Генерация без эталонного фото")

        # Загрузка LoRA, если указана
        lora_loaded = False
        if lora_path and Path(lora_path).exists():
            self.pipe.load_lora_weights(lora_path)
            lora_loaded = True
            logger.info(f"Загружена LoRA: {lora_path}")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.pipe(**pipe_kwargs).images[0]
        )

        # Выгрузка LoRA, если была загружена
        if lora_loaded:
            self.pipe.unload_lora_weights()
            logger.info("LoRA выгружена")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(__file__).parent.parent / "generated_images" / f"selfie_{timestamp}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(output_path)
        logger.info(f"Оригинал сохранён: {output_path}")

        # Апскейл
        if self._check_upscayl():
            upscaled_path = output_path.parent / f"upscaled_{output_path.name}"
            cmd = [
                self.upscayl_bin,
                "-i", str(output_path),
                "-o", str(upscaled_path),
                "-s", "5",
                "-m", self.upscayl_models,
                "-n", self.upscayl_model_name,
                "-f", "png"
            ]
            try:
                env = {"NCNN_VULKAN": "0"}
                subprocess.run(cmd, check=True, timeout=120, env=env)
                logger.info(f"Апскейл успешен: {upscaled_path}")
                return upscaled_path
            except Exception as e:
                logger.error(f"Ошибка апскейла: {e}. Отправляю оригинал.")
        else:
            logger.info("Апскейл недоступен, отправляю оригинал.")
        return output_path
