import aiohttp
from aiohttp_socks import ProxyConnector
import logging

logger = logging.getLogger(__name__)

class ProxyManager:
    def __init__(self, tor_manager):
        self.tor_manager = tor_manager
        self.connector = None
        self.session = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Возвращает aiohttp сессию с SOCKS5 прокси через Tor."""
        if self.session is None or self.session.closed:
            socks_url = f"socks5://127.0.0.1:{self.tor_manager.socks_port}"
            self.connector = ProxyConnector.from_url(socks_url)
            self.session = aiohttp.ClientSession(connector=self.connector)
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        if self.connector and not self.connector.closed:
            await self.connector.close()
