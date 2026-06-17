#!/usr/bin/env python3
"""
MANI-OTP BOT - iVASMS scraper with multiple bypass layers
Optimized for Render deployment
Developer: MANI-XTECH 🇳🇵
"""

import os
import re
import json
import time
import random
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Set

# Try to import playwright, but fallback gracefully
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

import cloudscraper
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ======================== CONFIGURATION ========================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8418350898:AAGPqP4iekN_mTzUvs3xsi9QvZ9SUdF6Ze4")
ADMIN_IDS = [int(x.strip()) for x in os.environ.get("ADMIN_IDS", "6895265731").split(",") if x.strip()]
IVASMS_EMAIL = os.environ.get("IVASMS_EMAIL", "devilknight0698@gmail.com")
IVASMS_PASSWORD = os.environ.get("IVASMS_PASSWORD", "9V9GjkFQBz.4#B@")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "15"))
DATA_FILE = "otp_cache.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ======================== PERSISTENT CACHE ========================
class OTPSet:
    def __init__(self, path):
        self.path = path
        self.cache = set()
        self.total = 0
        self.load()
    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    d = json.load(f)
                    self.cache = set(d.get("cache", []))
                    self.total = d.get("total", 0)
                logger.info(f"Loaded {len(self.cache)} OTPs")
            except: pass
    def save(self):
        try:
            with open(self.path, 'w') as f:
                json.dump({"cache": list(self.cache)[-500:], "total": self.total}, f)
        except: pass
    def add(self, key):
        self.cache.add(key)
        self.total += 1
        self.save()
    def contains(self, key): return key in self.cache
    def recent(self, limit=20):
        return [{"otp": k.split("|")[0], "phone": k.split("|")[1] if "|" in k else "?"} for k in list(self.cache)[-limit:]][::-1]

# ======================== IVASMS CLIENT (hybrid: cloudscraper + optional playwright) ========================
class IVASMSClient:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.logged_in = False
        self.method = "cloudscraper"  # will switch to playwright if needed
        self.scraper = None
        self.browser = None
        self.page = None
        self.playwright = None
        self._init_cloudscraper()

    def _init_cloudscraper(self):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
            delay=random.uniform(1.5, 3.5)
        )
        self.scraper.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Ch-Ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Connection': 'keep-alive',
        })

    async def _init_playwright(self):
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed")
            return False
        try:
            p = await async_playwright().start()
            self.playwright = p
            self.browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            self.page = await self.browser.new_page()
            logger.info("Playwright browser launched")
            return True
        except Exception as e:
            logger.error(f"Playwright init failed: {e}")
            return False

    async def login(self):
        # Try cloudscraper first
        if self.method == "cloudscraper":
            try:
                time.sleep(random.uniform(2, 4))
                r = self.scraper.get("https://ivasms.com/user/login", timeout=25)
                if r.status_code != 200:
                    logger.error(f"Login page status {r.status_code}")
                    # Switch to playwright if possible
                    if PLAYWRIGHT_AVAILABLE:
                        logger.info("Switching to Playwright...")
                        self.method = "playwright"
                        return await self.login()
                    return False
                csrf = re.search(r'name="_token"\s+value="([^"]+)"', r.text)
                payload = {"email": self.email, "password": self.password, "remember": "1"}
                if csrf:
                    payload["_token"] = csrf.group(1)
                time.sleep(random.uniform(1.5, 3))
                resp = self.scraper.post("https://ivasms.com/user/login", data=payload, timeout=25, allow_redirects=True)
                if "dashboard" in resp.url.lower() or resp.status_code == 302:
                    dash = self.scraper.get("https://ivasms.com/user/dashboard", timeout=15)
                    if dash.status_code == 200 and ("logout" in dash.text.lower() or "dashboard" in dash.text.lower()):
                        self.logged_in = True
                        logger.info("✅ iVASMS login successful (cloudscraper)")
                        return True
                logger.error("Login failed – wrong credentials or site changed")
                # Try playwright as fallback
                if PLAYWRIGHT_AVAILABLE:
                    logger.info("Fallback to Playwright...")
                    self.method = "playwright"
                    return await self.login()
                return False
            except Exception as e:
                logger.error(f"cloudscraper login exception: {e}")
                if PLAYWRIGHT_AVAILABLE:
                    self.method = "playwright"
                    return await self.login()
                return False

        elif self.method == "playwright":
            if not self.browser:
                if not await self._init_playwright():
                    return False
            try:
                await self.page.goto("https://ivasms.com/user/login", wait_until="networkidle")
                await self.page.fill('input[name="email"]', self.email)
                await self.page.fill('input[name="password"]', self.password)
                await self.page.click('button[type="submit"]')
                await self.page.wait_for_timeout(5000)
                if await self.page.is_visible('.dashboard, .user-menu, a[href*="logout"]'):
                    self.logged_in = True
                    logger.info("✅ iVASMS login successful (Playwright)")
                    return True
                else:
                    logger.error("Playwright login failed")
                    return False
            except Exception as e:
                logger.error(f"Playwright login exception: {e}")
                return False

    async def fetch_sms(self):
        if not self.logged_in:
            return ""
        if self.method == "cloudscraper":
            try:
                time.sleep(random.uniform(1.5, 3))
                r = self.scraper.get("https://ivasms.com/user/sms", timeout=25)
                return r.text if r.status_code == 200 else ""
            except Exception as e:
                logger.error(f"cloudscraper fetch error: {e}")
                return ""
        elif self.method == "playwright":
            try:
                await self.page.goto("https://ivasms.com/user/sms", wait_until="networkidle")
                await self.page.wait_for_timeout(2000)
                return await self.page.content()
            except Exception as e:
                logger.error(f"Playwright fetch error: {e}")
                return ""

    def extract(self, html):
        otps = []
        clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
        phones = re.finditer(r'\+?\d{1,4}[\s\-]?\d{3,4}[\s\-]?\d{4,10}', clean)
        for m in phones:
            phone = m.group()
            ctx = clean[max(0, m.start()-300):min(len(clean), m.end()+300)]
            codes = re.findall(r'\b\d{4,8}\b', ctx)
            phone_digits = re.sub(r'\D', '', phone)
            for c in codes:
                if c != phone_digits and len(c) >= 4:
                    service = self._detect(ctx)
                    otps.append({"otp": c, "phone": phone, "service": service})
                    break
        unique = {}
        for o in otps:
            key = f"{o['otp']}|{o['phone']}"
            if key not in unique:
                unique[key] = o
        return list(unique.values())

    def _detect(self, text):
        l = text.lower()
        services = {
            "Google": ["google","gmail"], "Facebook": ["facebook","fb"], "Instagram": ["instagram"],
            "WhatsApp": ["whatsapp"], "Telegram": ["telegram"], "Amazon": ["amazon"],
            "PayPal": ["paypal"], "Microsoft": ["microsoft","outlook"], "Twitter": ["twitter","x.com"],
            "Discord": ["discord"], "TikTok": ["tiktok"], "Binance": ["binance"]
        }
        for s, kw in services.items():
            if any(k in l for k in kw):
                return s
        return "Unknown"

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

# ======================== TELEGRAM BOT ========================
class MANIOTPBot:
    def __init__(self):
        self.client = IVASMSClient(IVASMS_EMAIL, IVASMS_PASSWORD)
        self.cache = OTPSet(DATA_FILE)
        self.start = datetime.now()
        self.running = True

    async def send_alert(self, otp, bot):
        emoji = {"Google":"🔴","Facebook":"📘","Instagram":"📷","WhatsApp":"💚","Telegram":"✈️","Amazon":"📦","PayPal":"💙","Microsoft":"🪟","Twitter":"🐦","Discord":"💜","TikTok":"🎵","Binance":"🟡"}.get(otp['service'], "🔐")
        msg = f"{emoji} <b>MANI-OTP ALERT</b> {emoji}\n\n━━━━━━━━━━━━━━━━━━━\n🔑 <b>CODE</b> : <code>{otp['otp']}</code>\n📱 <b>SERVICE</b> : {otp['service']}\n📞 <b>PHONE</b> : {otp['phone']}\n⏰ <b>TIME</b> : {datetime.now().strftime('%H:%M:%S')}\n━━━━━━━━━━━━━━━━━━━\n\n<i>Tap to copy</i>\n\n👨‍💻 @MANI-XTECH 🇳🇵"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📋 Copy", callback_data=f"copy_{otp['otp']}")]])
        for uid in ADMIN_IDS:
            try:
                await bot.send_message(uid, msg, parse_mode='HTML', reply_markup=kb)
                logger.info(f"Sent OTP {otp['otp']}")
            except Exception as e:
                logger.error(f"Send error: {e}")

    async def monitor(self, bot):
        logger.info("🔄 Monitoring started")
        while self.running:
            try:
                if not self.client.logged_in:
                    logger.info("Logging in...")
                    if await self.client.login():
                        logger.info("Login OK")
                    else:
                        await asyncio.sleep(30)
                        continue
                html = await self.client.fetch_sms()
                if html:
                    for o in self.client.extract(html):
                        key = f"{o['otp']}|{o['phone']}"
                        if not self.cache.contains(key):
                            self.cache.add(key)
                            await self.send_alert(o, bot)
                else:
                    logger.warning("Empty SMS page – re‑logging")
                    self.client.logged_in = False
                await asyncio.sleep(CHECK_INTERVAL + random.uniform(-2, 2))
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                self.client.logged_in = False
                await asyncio.sleep(30)

    # ----- commands -----
    async def cmd_start(self, update, context):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Unauthorized")
            return
        await update.message.reply_text(
            "🤖 MANI-OTP Bot\n"
            "/status – check bot\n"
            "/testlogin – test iVASMS\n"
            "/recent – last OTPs\n"
            "/restart – force re-login",
            parse_mode='HTML'
        )
    async def cmd_status(self, update, context):
        if update.effective_user.id not in ADMIN_IDS:
            return
        up = (datetime.now()-self.start).seconds
        h, m = up//3600, (up%3600)//60
        await update.message.reply_text(
            f"📊 STATUS\n"
            f"🟢 Running\n"
            f"🔐 iVASMS: {'✅' if self.client.logged_in else '❌'}\n"
            f"📦 Cache: {len(self.cache.cache)}\n"
            f"📈 Total: {self.cache.total}\n"
            f"⏱️ Uptime: {h}h {m}m\n"
            f"🛠️ Method: {self.client.method}",
            parse_mode='HTML'
        )
    async def cmd_recent(self, update, context):
        if update.effective_user.id not in ADMIN_IDS:
            return
        rec = self.cache.recent(10)
        if not rec:
            await update.message.reply_text("No OTPs yet.")
            return
        msg = "📋 Recent OTPs:\n" + "\n".join(f"{i+1}. <code>{r['otp']}</code> ({r['phone'][-6:]})" for i,r in enumerate(rec))
        await update.message.reply_text(msg, parse_mode='HTML')
    async def cmd_testlogin(self, update, context):
        if update.effective_user.id not in ADMIN_IDS:
            return
        await update.message.reply_text("🔄 Testing iVASMS login...")
        ok = await self.client.login()
        await update.message.reply_text("✅ Login successful" if ok else "❌ Login failed. Check credentials or site.")
    async def cmd_restart(self, update, context):
        if update.effective_user.id not in ADMIN_IDS:
            return
        await update.message.reply_text("🔄 Restarting monitor...")
        self.client.logged_in = False
        self.client = IVASMSClient(IVASMS_EMAIL, IVASMS_PASSWORD)
        await asyncio.sleep(2)
        await update.message.reply_text("✅ Restarted.")
    async def callback(self, update, context):
        q = update.callback_query
        await q.answer()
        if q.data.startswith("copy_"):
            otp = q.data.split("_")[1]
            await q.edit_message_text(f"✅ Copied: <code>{otp}</code>", parse_mode='HTML')

# ======================== MAIN (for server.py) ========================
async def main():
    if not BOT_TOKEN or not ADMIN_IDS or not IVASMS_EMAIL or not IVASMS_PASSWORD:
        logger.error("Missing environment variables!")
        return
    bot = MANIOTPBot()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", bot.cmd_start))
    app.add_handler(CommandHandler("status", bot.cmd_status))
    app.add_handler(CommandHandler("recent", bot.cmd_recent))
    app.add_handler(CommandHandler("testlogin", bot.cmd_testlogin))
    app.add_handler(CommandHandler("restart", bot.cmd_restart))
    app.add_handler(CallbackQueryHandler(bot.callback))
    asyncio.create_task(bot.monitor(app.bot))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("🤖 MANI-OTP Bot is running")
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        bot.running = False
        await bot.client.close()
        await app.stop()

# For direct execution (testing)
if __name__ == "__main__":
    asyncio.run(main())
