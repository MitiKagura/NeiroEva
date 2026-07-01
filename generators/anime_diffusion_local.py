import logging
import torch
import asyncio
import subprocess
import random
from pathlib import Path
from datetime import datetime
from diffusers import StableDiffusionPipeline, EulerAncestralDiscreteScheduler
from PIL import Image
from utils.config import get_time_context

logger = logging.getLogger(__name__)

class AnimeDiffusionGenerator:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.pipe = None
        # Путь к модели NablaThetaA5 (папка со всеми компонентами)
        self.model_path = model_dir / "NablaThetaA5"
        # Если есть GhostMix — можно использовать, но по умолчанию Nabla
        self.reference_images = {}
        self._load_references()
        self.upscayl_bin = "/usr/share/upscayl/bin/upscayl-bin"
        self.upscayl_models = "/usr/share/upscayl/models/"
        self.upscayl_model_name = "digital-art-4x"

    def _load_references(self):
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

    def _upscale_image(self, input_path: Path) -> Path:
        output_path = input_path.parent / f"upscaled_{input_path.name}"
        cmd = [
            self.upscayl_bin,
            "-i", str(input_path),
            "-o", str(output_path),
            "-s", "2",
            "-m", self.upscayl_models,
            "-n", self.upscayl_model_name,
            "-f", "png"
        ]
        try:
            env = {"NCNN_VULKAN": "0"}
            subprocess.run(cmd, check=True, timeout=120, env=env)
            logger.info(f"Апскейл успешен: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Ошибка апскейла: {e}")
            return None

    def load(self):
        if self.pipe is not None:
            return
        logger.info(f"Загрузка модели из {self.model_path}...")
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
            logger.info(f"Модель NablaThetaA5 загружена из {self.model_path}")
        except Exception as e:
            logger.exception(f"Ошибка загрузки модели из {self.model_path}")
            raise

    async def generate_selfie(self, prompt: str, location: str, reference_key: str = None, lora_path: str = None, negative_prompt: str = None) -> Path:
        if self.pipe is None:
            self.load()

        time_of_day = get_time_context()
        time_map = {
            "утро": "morning light, sunrise, warm colors, fresh atmosphere",
            "день": "sunlight, bright colors, lively atmosphere",
            "вечер": "sunset, warm golden light, cozy atmosphere",
            "ночь": "night, moonlight, dark sky, stars, soft shadows"
        }
        time_desc = time_map.get(time_of_day, "daylight, bright colors")

        location_map = {
            "родной дом": f"a cozy forest cottage, wooden walls, warm lamp light, {time_desc}, witchy but bright, forest surroundings",
            "дом Миши": f"modern cozy apartment, soft lighting, {time_desc}, home atmosphere",
            "дом Агнес": f"a quirky laboratory with glass flasks, bookshelves, scientific equipment, {time_desc}, cluttered but organized",
            "дом Виолетты": f"gothic style room, dark furniture, candles, books, {time_desc}, mysterious atmosphere",
            "подоконник": f"a windowsill with soft cushions, view of the night sky or street, {time_desc}, cozy",
            "кровать": f"a soft bed with plush pillows, blankets, {time_desc}, sleeping atmosphere",
            "кухня": f"a warm kitchen, wooden table, dishes, cooking utensils, {time_desc}, homey smell",
            "парк": f"a sunny park, green grass, trees, flowers, fresh air, {time_desc}, nature background",
            "лес": f"a magical forest, tall trees, sunlight through leaves, path, mystical atmosphere, {time_desc}",
            "город": f"city street, buildings, urban background, neon lights, {time_desc}",
            "кафе": f"inside a cozy cafe, warm lighting, tables, coffee aroma, relaxed atmosphere, {time_desc}",
            "пляж": f"on a sandy beach, sea waves, sunset, palm trees, relaxing atmosphere, {time_desc}",
            "автобус": f"inside a bus, seats, window view, road, {time_desc}",
            "в пути": f"blurry moving background, travel vibes, {time_desc}",
            "гости": f"in a cozy living room, friends, warm atmosphere, {time_desc}",
            "улица": f"street, city life, buildings, sky, {time_desc}",
            "деревня": f"rural village, wooden houses, nature, peaceful atmosphere, {time_desc}"
        }

        main_location = location.split(',')[0].strip()
        location_desc = location_map.get(main_location)
        if not location_desc:
            for key in location_map:
                if key in main_location:
                    location_desc = location_map[key]
                    break
        if not location_desc:
            location_desc = f"cozy room, {time_desc}, anime style"

        if location.startswith("в пути к "):
            dest = location.replace("в пути к ", "")
            location_desc = f"on the road to {dest}, motion blur, travel, {time_desc}"

        # Школьная форма Трасен-академии (Umamusume)
        school_uniform = (
            "summer school uniform, purple sailor collar, white pleated skirt, "
            "large ribbon on back, white knee-high socks, brown loafers"
        )

        if "masterpiece" in prompt.lower() and "1girl" in prompt.lower():
            full_prompt = f"{prompt}, {school_uniform}, {location_desc}, waist up"
        else:
            full_prompt = (
                f"masterpiece, best quality, 1girl, cat girl, pink hair, pink cat ears, pink cat tail, pink eyes, "
                f"{prompt}, {school_uniform}, {location_desc}, "
                f"waist up, looking at viewer, "
                f"(cat ears:1.5), (cat tail:1.5)"
            )

        if negative_prompt is None:
            negative_prompt = (
                "bad anatomy, bad hands, extra fingers, fewer fingers, mutated hands, "
                "extra limbs, missing limbs, duplicated limbs, duplicate tail, extra tail, "
                "multiple tails, two tails, three tails, "
                "blurry, low quality, ugly, deformed, disfigured, "
                "human, no cat ears, no cat tail, realistic, photograph, "
                "purple hair, green hair, blue hair"
            )

        # Случайный выбор формата
        formats = {
            "vertical": (768, 1024),
            "horizontal": (1024, 768),
            "square": (960, 960)
        }
        chosen_format = random.choice(list(formats.keys()))
        width, height = formats[chosen_format]
        logger.info(f"Выбран формат: {chosen_format} ({width}x{height})")

        pipe_kwargs = {
            "prompt": full_prompt,
            "negative_prompt": negative_prompt,
            "num_inference_steps": 40,
            "height": height,
            "width": width,
            "guidance_scale": 7.5
        }

        if reference_key and reference_key in self.reference_images:
            pipe_kwargs["image"] = self.reference_images[reference_key]
            pipe_kwargs["strength"] = 0.65
            logger.info(f"Генерация с эталонным фото для {reference_key}")

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

        if lora_loaded:
            self.pipe.unload_lora_weights()
            logger.info("LoRA выгружена")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(__file__).parent.parent / "generated_images" / f"selfie_{timestamp}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(output_path)
        logger.info(f"Оригинал сохранён: {output_path}")

        if self._check_upscayl():
            upscaled_path = output_path.parent / f"upscaled_{output_path.name}"
            cmd = [
                self.upscayl_bin,
                "-i", str(output_path),
                "-o", str(upscaled_path),
                "-s", "2",
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
