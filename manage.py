#!/usr/bin/env python3

import subprocess
import sys
import os
import time

def show_status():
    print("Giveaway Bot System Status")
    print("=" * 40)
    
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        processes = result.stdout
        
        main_processes = [line for line in processes.split('\n') if 'main.py' in line and 'grep' not in line]
        bot_processes = [line for line in processes.split('\n') if 'giveaway_bot.py' in line and 'grep' not in line]
        uvicorn_processes = [line for line in processes.split('\n') if 'uvicorn' in line and 'grep' not in line]
        
        print(f"Main processes: {len(main_processes)}")
        print(f"Bot processes: {len(bot_processes)}")
        print(f"Web processes: {len(uvicorn_processes)}")
        
        if main_processes:
            print("System is running!")
        else:
            print("System is not running")
            
    except Exception as e:
        print(f"Error checking status: {e}")

def start_system():
    print("Starting Giveaway Bot System...")
    
    try:
        result = subprocess.run(['pgrep', '-f', 'main.py'], capture_output=True)
        if result.returncode == 0:
            print("System is already running!")
            return
        
        subprocess.Popen(['python3', 'main.py'], 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL)
        
        print("System started!")
        print("Web interface: http://localhost:3001")
        print("Prize URLs: https://ahgan.coonlink.com/giftgiver/card/show/code/{security_code}")
        
    except Exception as e:
        print(f"Error starting system: {e}")

def stop_system():
    print("Stopping Giveaway Bot System...")
    
    try:
        subprocess.run(['pkill', '-f', 'main.py'], capture_output=True)
        subprocess.run(['pkill', '-f', 'giveaway_bot.py'], capture_output=True)
        subprocess.run(['pkill', '-f', 'uvicorn'], capture_output=True)
        
        print("System stopped!")
        
    except Exception as e:
        print(f"Error stopping system: {e}")

def restart_system():
    print("Restarting Giveaway Bot System...")
    stop_system()
    time.sleep(2)
    start_system()

def reset_system():
    print("Resetting Giveaway Bot System...")
    stop_system()
    
    try:
        subprocess.run(['python3', 'fresh_start.py'], check=True)
        print("System reset completed!")
        print("Now you can start the system with: python3 manage.py start")
    except Exception as e:
        print(f"Error resetting system: {e}")

def main():
    if len(sys.argv) < 2:
        print("Giveaway Bot Manager")
        print("=" * 30)
        print("Usage: python3 manage.py <command>")
        print()
        print("Commands:")
        print("  status   - Show system status")
        print("  start    - Start the system")
        print("  stop     - Stop the system")
        print("  restart  - Restart the system")
        print("  reset    - Reset system (fresh start)")
        print()
        return
    
    command = sys.argv[1].lower()
    
    if command == "status":
        show_status()
    elif command == "start":
        start_system()
    elif command == "stop":
        stop_system()
    elif command == "restart":
        restart_system()
    elif command == "reset":
        reset_system()
    else:
        print(f"Unknown command: {command}")
        print("Use: python3 manage.py (without arguments) to see available commands")

if __name__ == "__main__":
    main()
