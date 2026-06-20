import json
import random
import time
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class MoodEngine:
    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.mood_score = 0.5
        self.horny_level = 0.3
        self.energy = 0.7
        self.emotion = "нейтральное"
        self.last_update = time.time()
        self._load()
        self.emotions_list = [
            "радость", "грусть", "злость", "спокойствие", "игривость", "сонливость",
            "энергичность", "влюблённость", "раздражение", "тревога", "ностальгия",
            "любопытство", "смущение", "гордость", "вина", "благодарность", "восхищение",
            "надежда", "отчаяние", "одиночество", "восторг", "скука", "ревность",
            "заботливость", "романтичность", "обида"
        ]

    def _load(self):
        if self.state_path.exists():
            try:
                with open(self.state_path, 'r') as f:
                    data = json.load(f)
                self.mood_score = data.get("mood_score", 0.5)
                self.horny_level = data.get("horny_level", 0.3)
                self.energy = data.get("energy", 0.7)
                self.emotion = data.get("emotion", "нейтральное")
                self.last_update = data.get("last_update", time.time())
                logger.info(f"Настроение загружено: {self.emotion}")
            except Exception as e:
                logger.error(f"Ошибка загрузки: {e}")

    def save(self):
        try:
            with open(self.state_path, 'w') as f:
                json.dump({
                    "mood_score": self.mood_score,
                    "horny_level": self.horny_level,
                    "energy": self.energy,
                    "emotion": self.emotion,
                    "last_update": self.last_update
                }, f)
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")

    def spontaneous_change(self):
        old = self.emotion
        self.emotion = random.choice(self.emotions_list)
        emotion_params = {
            "радость": (0.9, 0.4, 0.8), "грусть": (0.2, 0.1, 0.3), "злость": (0.1, 0.3, 0.6),
            "спокойствие": (0.7, 0.2, 0.5), "игривость": (0.8, 0.7, 0.9), "сонливость": (0.5, 0.1, 0.2),
            "энергичность": (0.8, 0.5, 0.9), "влюблённость": (0.9, 0.8, 0.8), "раздражение": (0.2, 0.3, 0.5),
            "тревога": (0.3, 0.1, 0.4), "ностальгия": (0.5, 0.2, 0.4), "любопытство": (0.7, 0.3, 0.7),
            "смущение": (0.5, 0.5, 0.5), "гордость": (0.7, 0.2, 0.7), "вина": (0.3, 0.1, 0.4),
            "благодарность": (0.8, 0.2, 0.7), "восхищение": (0.9, 0.4, 0.8), "надежда": (0.7, 0.3, 0.6),
            "отчаяние": (0.1, 0.0, 0.2), "одиночество": (0.2, 0.1, 0.3), "восторг": (1.0, 0.6, 1.0),
            "скука": (0.4, 0.1, 0.3), "ревность": (0.2, 0.4, 0.5), "заботливость": (0.8, 0.3, 0.7),
            "романтичность": (0.8, 0.7, 0.7), "обида": (0.2, 0.1, 0.4)
        }
        if self.emotion in emotion_params:
            self.mood_score, self.horny_level, self.energy = emotion_params[self.emotion]
        self.save()
        logger.info(f"Настроение сменилось: {old} -> {self.emotion}")

    def get_mood_description(self) -> str:
        return f"Сейчас она {self.emotion}. {'Настроение отличное.' if self.mood_score>0.7 else 'Настроение плохое.' if self.mood_score<0.3 else 'Настроение среднее.'}"

    # ВОТ ЭТОТ МЕТОД БЫЛ УТЕРЯН – ВОССТАНАВЛИВАЕМ
    def apply_reaction_to_user_message(self, sentiment: str, keywords: list = None):
        if sentiment == "positive":
            self.mood_score = min(1.0, self.mood_score + 0.07)
            self.horny_level = min(1.0, self.horny_level + 0.05)
        elif sentiment == "negative":
            self.mood_score = max(0.0, self.mood_score - 0.1)
            self.horny_level = max(0.0, self.horny_level - 0.05)
        if keywords:
            if "люблю" in keywords:
                self.emotion = "влюблённость"
            elif "грустно" in keywords:
                self.emotion = "грусть"
        self.save()
