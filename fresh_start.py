#!/usr/bin/env python3

import asyncio
import subprocess
import sys
import os
from dotenv import load_dotenv

load_dotenv()

def stop_all_processes():
    print("Stopping all bot processes...")
    
    try:
        subprocess.run(['pkill', '-f', 'giveaway_bot.py'], capture_output=True)
        subprocess.run(['pkill', '-f', 'main.py'], capture_output=True)
        subprocess.run(['pkill', '-f', 'uvicorn'], capture_output=True)
        print("All processes stopped!")
    except Exception as e:
        print(f"Error stopping processes: {e}")

async def reset_database():
    print("Resetting database...")
    
    DB_CONFIG = {
        'host': os.getenv("DB_HOST", ""),
        'port': int(os.getenv("DB_PORT", "3306")),
        'user': os.getenv("DB_USER", ""),
        'password': os.getenv("DB_PASSWORD", ""),
        'db': os.getenv("DB_NAME", ""),
        'charset': 'utf8mb4'
    }
    
    try:
        import aiomysql
        conn = await aiomysql.connect(**DB_CONFIG)
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
                    print(f"Could not drop table {table}: {e}")
            
            await conn.commit()
            print("Database reset completed!")
            
    except Exception as e:
        print(f"Error resetting database: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    print("Giveaway Bot Fresh Start")
    print("=" * 40)
    print("This will:")
    print("1. Stop all running bot processes")
    print("2. Reset the database (delete all data)")
    print("3. Prepare for a clean restart")
    print()
    
    stop_all_processes()
    
    print("\nResetting database...")
    asyncio.run(reset_database())
    
    print("\nFresh start completed!")
    print("Now you can run: python3 main.py")
    print("Prize URLs will be: https://ahgan.coonlink.com/giftgiver/card/show/code/{security_code}")

if __name__ == "__main__":
    main()
