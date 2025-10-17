#!/usr/bin/env python3

import subprocess
import sys
import os

def stop_bot_processes():
    print("Stopping all bot processes...")
    
    try:
        result = subprocess.run(['pkill', '-f', 'giveaway_bot.py'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("Stopped giveaway_bot.py processes")
        else:
            print("No giveaway_bot.py processes found")
            
        result = subprocess.run(['pkill', '-f', 'main.py'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("Stopped main.py processes")
        else:
            print("No main.py processes found")
            
        result = subprocess.run(['pkill', '-f', 'uvicorn'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("Stopped uvicorn processes")
        else:
            print("No uvicorn processes found")
            
        print("All bot processes stopped!")
        
    except Exception as e:
        print(f"Error stopping bot processes: {e}")

def main():
    print("Giveaway Bot Process Manager")
    print("=" * 40)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--stop":
        stop_bot_processes()
    else:
        print("Usage: python3 stop_bot.py --stop")
        print("This will stop all running bot processes.")

if __name__ == "__main__":
    main()