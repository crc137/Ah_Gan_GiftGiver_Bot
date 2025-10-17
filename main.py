#!/usr/bin/env python3

import asyncio
import multiprocessing
import os
import signal
import sys
from concurrent.futures import ProcessPoolExecutor

def run_telegram_bot():
    try:
        from giveaway_bot import main as bot_main
        asyncio.run(bot_main())
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
                asyncio.sleep(1)
                
    except KeyboardInterrupt:
        print("\nShutting down services...")
    except Exception as e:
        print(f"Error running services: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
