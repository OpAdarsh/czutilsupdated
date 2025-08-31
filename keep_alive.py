
import asyncio
import aiohttp
import os
import time
from datetime import datetime

class KeepAlive:
    def __init__(self, bot):
        self.bot = bot
        self.url = None
        self.running = False
        
    async def start_keep_alive(self):
        """Start the keep-alive service"""
        self.running = True
        await asyncio.sleep(30)  # Wait for bot to fully start
        
        while self.running:
            try:
                await self.ping_self()
                await asyncio.sleep(240)  # Ping every 4 minutes
            except Exception as e:
                print(f"Keep-alive error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def ping_self(self):
        """Ping the web server to keep it alive"""
        if not self.url:
            # Try to get the URL from environment or construct it
            repl_id = os.environ.get('REPL_ID', '')
            repl_owner = os.environ.get('REPL_OWNER', '')
            
            if repl_id and repl_owner:
                # Use the current replit dev URL format
                self.url = f"https://{repl_id}-00-35iv8qqisnpfi.spock.replit.dev/ping"
            else:
                self.url = "http://127.0.0.1:5000/ping"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"🔄 Keep-alive ping successful [{timestamp}]")
                    else:
                        print(f"⚠️ Keep-alive ping returned status {response.status}")
        except Exception as e:
            print(f"❌ Keep-alive ping failed: {e}")
    
    def stop(self):
        """Stop the keep-alive service"""
        self.running = False
