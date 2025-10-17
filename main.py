#!/usr/bin/env python3

import asyncio
import multiprocessing
import os
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor

def run_telegram_bot():
    try:
        import subprocess
        import sys
        result = subprocess.run([sys.executable, "giveaway_bot.py"], 
                              capture_output=False, text=True)
        if result.returncode != 0:
            print(f"Telegram bot exited with code {result.returncode}")
    except Exception as e:
        print(f"Error running Telegram bot: {e}")
        sys.exit(1)

def run_web_interface():
    try:
        import uvicorn
        from web_interface import app
        uvicorn.run(app, host="0.0.0.0", port=3000)
    except Exception as e:
        print(f"Error running web interface: {e}")
        sys.exit(1)

def signal_handler(signum, frame):
    print(f"Received signal {signum}, shutting down...")
    sys.exit(0)

def main():
    print("Starting Giveaway Bot Services...")
    
    required_vars = ['TELEGRAM_TOKEN', 'DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these variables or copy env.example to .env and configure it.")
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--bot-only":
        print("Running Telegram bot only...")
        run_telegram_bot()
        return
    
    if len(sys.argv) > 1 and sys.argv[1] == "--web-only":
        print("Running web interface only...")
        run_web_interface()
        return
    
    print("Starting Telegram bot...")
    print("Starting web interface...")
    
    try:
        with ProcessPoolExecutor(max_workers=2) as executor:
            bot_future = executor.submit(run_telegram_bot)
            web_future = executor.submit(run_web_interface)
            
            print("Both services started successfully!")
            print("Telegram bot is running...")
            print("Web interface is running on port 3000...")
            print("Prize claims: https://ahgan.coonlink.com/giftgiver/card/show/code/{security_code}")
            
            while True:
                if bot_future.done():
                    print("Telegram bot process ended")
                    web_future.cancel()
                    break
                if web_future.done():
                    print("Web interface process ended")
                    bot_future.cancel()
                    break
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\nShutting down services...")
    except Exception as e:
        print(f"Error running services: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
