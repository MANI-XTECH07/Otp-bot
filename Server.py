#!/usr/bin/env python3
"""
MANI-OTP Server for Render
Starts Flask health check and the bot in a background thread.
"""

import asyncio
from threading import Thread
from flask import Flask, jsonify
import app  # your bot's main module

flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "MANI-OTP Bot is running", 200

@flask_app.route('/status')
def status():
    # You can extend this to return real bot status if needed
    return jsonify({"status": "ok"})

def run_bot():
    asyncio.run(app.main())

if __name__ == '__main__':
    # Start the bot in a background thread
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    # Start Flask on the port Render provides
    port = int(os.environ.get("PORT", 8000))
    flask_app.run(host='0.0.0.0', port=port)
