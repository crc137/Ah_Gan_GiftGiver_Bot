#!/usr/bin/env python3

import asyncio
import aiomysql
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv("DB_HOST", ""),
    'port': int(os.getenv("DB_PORT", "3306")),
    'user': os.getenv("DB_USER", ""),
    'password': os.getenv("DB_PASSWORD", ""),
    'db': os.getenv("DB_NAME", ""),
    'charset': 'utf8mb4'
}

async def reset_database():
    print("Resetting database...")
    
    try:
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
        conn.close()

async def main():
    print("WARNING: This will delete ALL data from the database!")
    print("Press Ctrl+C to cancel, or wait 5 seconds to continue...")
    
    try:
        await asyncio.sleep(5)
    except KeyboardInterrupt:
        print("\nDatabase reset cancelled.")
        return
    
    await reset_database()
    print("Now restart your application to recreate tables.")

if __name__ == "__main__":
    asyncio.run(main())
