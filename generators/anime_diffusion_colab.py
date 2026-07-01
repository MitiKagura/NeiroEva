import logging
import requests
import base64
import random
import subprocess
from pathlib import Path
from datetime import datetime
from PIL import Image
from io import BytesIO
from utils.config import get_time_context

logger = logging.getLogger(__name__)

class ColabAnimeDiffusionGenerator:
    def __init__(self, model_dir: Path, colab_url: str):
        self.model_dir = model_dir
        self.colab_url = colab_url.rstrip('/')
        self.proxies = None
        self.upscayl_bin = "/usr/share/upscayl/bin/upscayl-bin"
        self.upscayl_models = "/usr/share/upscayl/models/"
        self.upscayl_model_name = "digital-art-4x"

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
        logger.info("Используется удалённый генератор на Colab")

    async def generate_selfie(self, prompt: str, location: str, reference_key: str = None, lora_path: str = None, negative_prompt: str = None) -> Path:
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

        if "masterpiece" in prompt.lower() and "1girl" in prompt.lower():
            full_prompt = f"{prompt}, {location_desc}, waist up"
        else:
            full_prompt = (
                f"masterpiece, best quality, 1girl, cat girl, pink hair, pink cat ears, pink cat tail, pink eyes, "
                f"{prompt}, {location_desc}, "
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

        formats = {
            "vertical": (768, 1024),
            "horizontal": (1024, 768),
            "square": (960, 960)
        }
        chosen_format = random.choice(list(formats.keys()))
        width, height = formats[chosen_format]
        logger.info(f"Выбран формат: {chosen_format} ({width}x{height})")

        payload = {
            "prompt": full_prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": 40,
            "guidance_scale": 7.5,
            "strength": 0.65,
        }

        # --- Передача имени LoRA (вместо base64) ---
        if lora_path and Path(lora_path).exists():
            lora_filename = Path(lora_path).name
            payload["lora_filename"] = lora_filename
            logger.info(f"LoRA filename: {lora_filename}")

        # --- Референс ---
        if reference_key:
            ref_path = Path(__file__).parent.parent / "data" / f"{reference_key}_reference.png"
            if ref_path.exists():
                img = Image.open(ref_path).convert("RGB").resize((512, 512))
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                ref_base64 = base64.b64encode(buffered.getvalue()).decode()
                payload["reference_image_base64"] = ref_base64
                logger.info(f"Добавлен референс для {reference_key}")
            else:
                logger.warning(f"Референс {reference_key} не найден, игнорируем")

        try:
            response = requests.post(
                f"{self.colab_url}/generate_image",
                json=payload,
                timeout=300,
                proxies=self.proxies
            )
            response.raise_for_status()
            data = response.json()
            img_data = base64.b64decode(data["image"])
            img = Image.open(BytesIO(img_data))

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(__file__).parent.parent / "generated_images" / f"selfie_{timestamp}.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path)
            logger.info(f"Изображение получено и сохранено: {output_path}")

            if self._check_upscayl():
                upscaled = self._upscale_image(output_path)
                if upscaled:
                    return upscaled
                else:
                    logger.warning("Апскейл не удался, возвращаем оригинал.")
            else:
                logger.info("Апскейл недоступен, возвращаем оригинал.")

            return output_path

        except Exception as e:
            logger.exception("Ошибка при запросе к Colab")
            raise RuntimeError(f"Не удалось сгенерировать: {e}")
