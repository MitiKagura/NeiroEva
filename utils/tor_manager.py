import logging
import socket
from pathlib import Path

logger = logging.getLogger(__name__)

class TorManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.socks_port = 9050   # стандартный порт системного Tor

    def start(self) -> bool:
        """Проверяет, доступен ли системный Tor на порту 9050."""
        if self.is_socks_alive():
            logger.info("Системный Tor доступен на порту 9050")
            return True
        else:
            logger.error("Системный Tor не найден. Запустите: sudo systemctl start tor")
            return False

    def is_socks_alive(self) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', self.socks_port))
        sock.close()
        return result == 0

    def stop(self):
        logger.info("Системный Tor не управляется из бота.")
