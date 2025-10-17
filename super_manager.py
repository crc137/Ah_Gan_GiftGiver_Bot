#!/usr/bin/env python3

import subprocess
import time
import os
import asyncio
import sys
import requests
from dotenv import load_dotenv
from aiogram import Bot
import aiomysql

load_dotenv()

class SuperManager:
    def __init__(self):
        self.db_config = {
            'host': os.getenv("DB_HOST", ""),
            'port': int(os.getenv("DB_PORT", "3306")),
            'user': os.getenv("DB_USER", ""),
            'password': os.getenv("DB_PASSWORD", ""),
            'db': os.getenv("DB_NAME", ""),
            'charset': 'utf8mb4'
        }
    
    def print_header(self, title):
        print(f"\n{'='*50}")
        print(f"  {title}")
        print(f"{'='*50}")
    
    def stop_all_processes(self):
        self.print_header("Stopping processes")
        
        processes = ['main.py', 'giveaway_bot.py', 'uvicorn']
        for process in processes:
            try:
                result = subprocess.run(['pkill', '-f', process], capture_output=True)
                if result.returncode == 0:
                    print(f"Stopped: {process}")
                else:
                    print(f"Not found: {process}")
            except Exception as e:
                print(f"Error stopping {process}: {e}")
        
        time.sleep(2)
        print("All processes stopped!")
    
    async def check_bot_token(self):
        self.print_header("Checking bot token")
        
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            print("TELEGRAM_TOKEN not set!")
            return False
        
        try:
            bot = Bot(token=token)
            me = await bot.get_me()
            print(f"Bot is valid: {me.first_name} (@{me.username})")
            print(f"   ID: {me.id}")
            print(f"   Can join groups: {me.can_join_groups}")
            await bot.session.close()
            return True
        except Exception as e:
            print(f"Bot token is invalid: {e}")
            print("Solutions:")
            print("   1. Check the token accuracy")
            print("   2. Create a new bot using @BotFather")
            print("   3. Update the token in environment variables")
            return False
    
    def check_environment(self):
        self.print_header("Checking environment variables")
        
        required_vars = {
            'TELEGRAM_TOKEN': 'Telegram bot token',
            'DB_HOST': 'Database host',
            'DB_USER': 'Database user',
            'DB_PASSWORD': 'Database password',
            'DB_NAME': 'Database name'
        }
        
        missing_vars = []
        for var, description in required_vars.items():
            value = os.getenv(var)
            if not value:
                missing_vars.append(f"{var} ({description})")
            else:
                print(f"{var}: {value[:10]}..." if len(value) > 10 else f"{var}: {value}")
        
        if missing_vars:
            print(f"\nMissing variables:")
            for var in missing_vars:
                print(f"   - {var}")
            print("\nSolutions:")
            print("   1. Copy env.example to .env")
            print("   2. Fill out all variables in .env")
            print("   3. Set environment variables accordingly")
            return False
        
        print("\nAll required environment variables are set!")
        return True
    
    async def reset_database(self):
        self.print_header("Resetting database")
        
        try:
            conn = await aiomysql.connect(**self.db_config)
            async with conn.cursor() as cursor:
                tables_to_drop = [
                    'prize_claims',
                    'contest_prizes', 
                    'prizes',
                    'contests',
                    'giveaway_state'
                ]
                
                for table in tables_to_drop:
                    try:
                        await cursor.execute(f"DROP TABLE IF EXISTS {table}")
                        print(f"Dropped table: {table}")
                    except Exception as e:
                        print(f"Could not drop {table}: {e}")
                
                await conn.commit()
                print("\nDatabase reset complete!")
                
        except Exception as e:
            print(f"Error resetting database: {e}")
        finally:
            if 'conn' in locals():
                conn.close()
    
    def install_dependencies(self):
        self.print_header("Installing dependencies")
        
        try:
            result = subprocess.run(['pip', 'install', '-r', 'requirements.txt'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("Dependencies installed!")
            else:
                print(f"Error installing: {result.stderr}")
        except Exception as e:
            print(f"Error installing dependencies: {e}")
    
    def start_system(self):
        self.print_header("Starting system")
        
        try:
            result = subprocess.run(['pgrep', '-f', 'main.py'], capture_output=True)
            if result.returncode == 0:
                print("System is already running!")
                return True
            
            subprocess.Popen(['python3', 'main.py'], 
                            stdout=subprocess.DEVNULL, 
                            stderr=subprocess.DEVNULL)
            
            time.sleep(3)
            print("System started!")
            return True
            
        except Exception as e:
            print(f"Error starting system: {e}")
            return False
    
    def check_system_status(self):
        self.print_header("Checking system status")
        
        try:
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
            processes = result.stdout
            
            main_count = len([line for line in processes.split('\n') if 'main.py' in line and 'grep' not in line])
            bot_count = len([line for line in processes.split('\n') if 'giveaway_bot.py' in line and 'grep' not in line])
            uvicorn_count = len([line for line in processes.split('\n') if 'uvicorn' in line and 'grep' not in line])
            
            print(f"Main processes: {main_count}")
            print(f"Bot processes: {bot_count}")
            print(f"Web processes: {uvicorn_count}")
            
            if main_count > 0:
                print("\nSystem is running!")
                
                # Check web interface availability
                try:
                    response = requests.get('http://localhost:3001/', timeout=5)
                    if response.status_code == 200:
                        print("Web interface is available: http://localhost:3001")
                    else:
                        print(f"Web interface not available (status: {response.status_code})")
                except Exception as e:
                    print(f"Web interface not available: {e}")
                
                return True
            else:
                print("\nSystem is not running!")
                return False
                
        except Exception as e:
            print(f"Error checking system status: {e}")
            return False
    
    def show_help(self):
        self.print_header("Commands help")
        
        print("Available commands:")
        print("  status    - Check system status")
        print("  start     - Start the system")
        print("  stop      - Stop the system")
        print("  restart   - Restart the system")
        print("  reset     - Fully reset the system")
        print("  fix       - Fix all issues")
        print("  check     - Check all components")
        print("  help      - Show this help")
        print("\nUsage examples:")
        print("  python3 super_manager.py status")
        print("  python3 super_manager.py fix")
        print("  python3 super_manager.py reset")
    
    async def fix_all(self):
        self.print_header("Fixing all issues")
        
        self.stop_all_processes()

        if not self.check_environment():
            print("\nIssues with environment variables!")
            return False

        if not await self.check_bot_token():
            print("\nIssues with bot token!")
            return False
        
        self.install_dependencies()
        
        if not self.start_system():
            print("\nCould not start the system!")
            return False
        
        time.sleep(3)
        if self.check_system_status():
            print("\nAll issues fixed!")
            print("Web interface: http://localhost:3001")
            print("Prizes: https://ahgan.coonlink.com/giftgiver/card/show/code/{security_code}")
            return True
        else:
            print("\nSystem is still not working!")
            return False
    
    async def reset_all(self):
        self.print_header("Full system reset")
        
        print("WARNING: This will DELETE ALL data!")
        print("Press Ctrl+C to cancel, or wait 5 seconds...")
        
        try:
            await asyncio.sleep(5)
        except KeyboardInterrupt:
            print("\nReset cancelled!")
            return
        
        self.stop_all_processes()
        
        await self.reset_database()
        
        if self.start_system():
            print("\nSystem reset and started!")
        else:
            print("\nError starting after reset!")
    
    async def check_all(self):
        self.print_header("Checking all components")
        
        checks = [
            ("Environment variables", self.check_environment),
            ("Bot token", self.check_bot_token),
            ("System status", self.check_system_status)
        ]
        
        all_passed = True
        for check_name, check_func in checks:
            print(f"\n{check_name}:")
            if asyncio.iscoroutinefunction(check_func):
                result = await check_func()
            else:
                result = check_func()
            
            if not result:
                all_passed = False
        
        if all_passed:
            print("\nAll checks passed!")
        else:
            print("\nSome checks failed!")
    
    async def main(self):
        if len(sys.argv) < 2:
            self.show_help()
            return
        
        command = sys.argv[1].lower()
        
        if command == "status":
            self.check_system_status()
        elif command == "start":
            self.start_system()
        elif command == "stop":
            self.stop_all_processes()
        elif command == "restart":
            self.stop_all_processes()
            time.sleep(2)
            self.start_system()
        elif command == "reset":
            await self.reset_all()
        elif command == "fix":
            await self.fix_all()
        elif command == "check":
            await self.check_all()
        elif command == "help":
            self.show_help()
        else:
            print(f"Unknown command: {command}")
            self.show_help()

if __name__ == "__main__":
    manager = SuperManager()
    asyncio.run(manager.main())
