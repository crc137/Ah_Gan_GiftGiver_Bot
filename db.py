#! /usr/bin/env python3

import aiomysql
import json
import asyncio
import logging
from aiogram import types

logger = logging.getLogger(__name__)

async def get_db_connection(config, max_retries=3, retry_delay=5):
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting database connection (attempt {attempt + 1}/{max_retries})")
            return await aiomysql.connect(**config)
        except aiomysql.Error as e:
            logger.error(f"Database connection failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise Exception("Failed to connect to database after retries")

async def init_database(config):
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS contests (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    contest_name VARCHAR(255) NOT NULL,
                    duration INT NOT NULL,
                    winners_count INT NOT NULL,
                    prizes TEXT NOT NULL,
                    image_url VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS contest_prizes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    contest_id INT NOT NULL,
                    position INT NOT NULL,
                    prize_name VARCHAR(255) NOT NULL,
                    prize_type ENUM('text', 'link') NOT NULL DEFAULT 'text',
                    prize_value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contest_id) REFERENCES contests(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_contest_position (contest_id, position)
                )
            """)
            
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS prize_claims (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    contest_id INT NOT NULL,
                    position INT NOT NULL,
                    winner_user_id BIGINT NOT NULL,
                    claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    security_code VARCHAR(32) NOT NULL,
                    FOREIGN KEY (contest_id) REFERENCES contests(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_winner_prize (contest_id, position, winner_user_id)
                )
            """)
            
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS giveaway_state (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    participants TEXT,
                    winners TEXT,
                    claimed_winners TEXT,
                    giveaway_message_id BIGINT,
                    giveaway_chat_id BIGINT,
                    giveaway_has_image BOOLEAN DEFAULT FALSE,
                    current_contest_id INT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            await conn.commit()
            logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
    finally:
        conn.close()

async def get_contest_by_id(contest_id: int, config):
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT contest_name, duration, winners_count, prizes, image_url FROM contests WHERE id = %s",
                (contest_id,)
            )
            result = await cursor.fetchone()
            if result:
                contest = {
                    'name': result[0],
                    'duration': result[1],
                    'winners_count': result[2],
                    'prizes': result[3].split(',') if result[3] else [],
                    'image_url': result[4]
                }
                logger.info(f"Retrieved contest {contest_id}: {contest['name']}")
                return contest
            return None
    except Exception as e:
        logger.error(f"Error getting contest {contest_id}: {e}")
        raise
    finally:
        conn.close()

async def add_contest(contest_name: str, duration: int, winners_count: int, prizes: list, config, image_url: str = None):
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            prizes_str = ','.join(prizes) if prizes else ''
            await cursor.execute(
                "INSERT INTO contests (contest_name, duration, winners_count, prizes, image_url) VALUES (%s, %s, %s, %s, %s)",
                (contest_name, duration, winners_count, prizes_str, image_url)
            )
            await conn.commit()
            contest_id = cursor.lastrowid
            logger.info(f"Created contest {contest_id}: {contest_name}")
            return contest_id
    except Exception as e:
        logger.error(f"Error creating contest: {e}")
        raise
    finally:
        conn.close()

async def list_contests(config):
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id, contest_name, duration, winners_count FROM contests ORDER BY id")
            results = await cursor.fetchall()
            contests = []
            for row in results:
                contests.append({
                    'id': row[0],
                    'name': row[1],
                    'duration': row[2],
                    'winners_count': row[3]
                })
            return contests
    except Exception as e:
        logger.error(f"Error listing contests: {e}")
        raise
    finally:
        conn.close()

def serialize_user(user: types.User) -> dict:
    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "language_code": user.language_code,
        "is_bot": user.is_bot,
    }

def deserialize_user(data: dict) -> types.User:
    return types.User(**{k: v for k, v in data.items() if v is not None})

async def save_state_to_db(participants, winners, claimed_winners, giveaway_message_id, giveaway_chat_id, giveaway_has_image, current_contest_id, config):
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            participants_json = json.dumps([serialize_user(u) for u in participants.values()])
            winners_json = json.dumps(winners)
            claimed_winners_json = json.dumps(list(claimed_winners))
            
            await cursor.execute("SELECT id FROM giveaway_state LIMIT 1")
            existing = await cursor.fetchone()
            
            if existing:
                await cursor.execute("""
                    UPDATE giveaway_state SET 
                    participants = %s, winners = %s, claimed_winners = %s,
                    giveaway_message_id = %s, giveaway_chat_id = %s, giveaway_has_image = %s,
                    current_contest_id = %s
                    WHERE id = 1
                """, (participants_json, winners_json, claimed_winners_json, 
                      giveaway_message_id, giveaway_chat_id, giveaway_has_image, current_contest_id))
            else:
                await cursor.execute("""
                    INSERT INTO giveaway_state 
                    (participants, winners, claimed_winners, giveaway_message_id, giveaway_chat_id, giveaway_has_image, current_contest_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (participants_json, winners_json, claimed_winners_json,
                      giveaway_message_id, giveaway_chat_id, giveaway_has_image, current_contest_id))
            await conn.commit()
            logger.info("State saved to database")
    except Exception as e:
        logger.error(f"Error saving state to database: {e}")
        raise
    finally:
        conn.close()

async def load_state_from_db(config):
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT participants, winners, claimed_winners, giveaway_message_id, 
                       giveaway_chat_id, giveaway_has_image, current_contest_id
                FROM giveaway_state LIMIT 1
            """)
            result = await cursor.fetchone()
            
            if result:
                participants_data = json.loads(result[0] or '[]')
                participants = {u["id"]: deserialize_user(u) for u in participants_data}
                
                winners = json.loads(result[1] or '{}')
                claimed_winners = set(json.loads(result[2] or '[]'))
                
                giveaway_message_id = result[3]
                giveaway_chat_id = result[4]
                giveaway_has_image = bool(result[5])
                current_contest_id = result[6]
                
                logger.info("State loaded from database")
                return participants, winners, claimed_winners, giveaway_message_id, giveaway_chat_id, giveaway_has_image, current_contest_id
            else:
                logger.info("No existing state found in database")
                return {}, {}, set(), None, None, False, None
    except Exception as e:
        logger.error(f"Error loading state from database: {e}")
        return {}, {}, set(), None, None, False, None
    finally:
        conn.close()

async def create_contest_prizes(contest_id: int, prizes_list: list, config):
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            for position, prize in enumerate(prizes_list, 1):
                # Import is_safe_link function
                from giveaway_bot import is_safe_link
                prize_type = 'link' if is_safe_link(prize) else 'text'
                
                await cursor.execute("""
                    INSERT INTO contest_prizes (contest_id, position, prize_name, prize_type, prize_value)
                    VALUES (%s, %s, %s, %s, %s)
                """, (contest_id, position, prize, prize_type, prize))
            
            await conn.commit()
            logger.info(f"Created {len(prizes_list)} contest prizes for contest {contest_id}")
    except Exception as e:
        logger.error(f"Error creating contest prizes: {e}")
        raise
    finally:
        conn.close()

async def get_contest_prizes(contest_id: int, config):
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT position, prize_name, prize_type, prize_value 
                FROM contest_prizes 
                WHERE contest_id = %s 
                ORDER BY position
            """, (contest_id,))
            
            results = await cursor.fetchall()
            prizes = []
            for result in results:
                prizes.append({
                    'position': result[0],
                    'prize_name': result[1],
                    'prize_type': result[2],
                    'prize_value': result[3]
                })
            return prizes
    except Exception as e:
        logger.error(f"Error getting contest prizes: {e}")
        raise
    finally:
        conn.close()

async def assign_winner_to_prize_position(contest_id: int, position: int, user_id: int, config):
    import secrets
    
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            security_code = secrets.token_hex(16)
            
            await cursor.execute("""
                INSERT INTO prize_claims (contest_id, position, winner_user_id, security_code)
                VALUES (%s, %s, %s, %s)
            """, (contest_id, position, user_id, security_code))
            
            await conn.commit()
            logger.info(f"Assigned user {user_id} to prize position {position} in contest {contest_id}")
    except Exception as e:
        logger.error(f"Error assigning winner to prize: {e}")
        raise
    finally:
        conn.close()

async def get_winner_prize_info(contest_id: int, user_id: int, config):
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT cp.position, cp.prize_name, cp.prize_type, cp.prize_value, 
                       pc.claimed_at, pc.security_code
                FROM contest_prizes cp
                JOIN prize_claims pc ON cp.contest_id = pc.contest_id AND cp.position = pc.position
                WHERE cp.contest_id = %s AND pc.winner_user_id = %s
            """, (contest_id, user_id))
            
            result = await cursor.fetchone()
            if result:
                return {
                    'position': result[0],
                    'prize_name': result[1],
                    'prize_type': result[2],
                    'prize_value': result[3],
                    'claimed_at': result[4],
                    'security_code': result[5]
                }
            return None
    except Exception as e:
        logger.error(f"Error getting winner prize info: {e}")
        raise
    finally:
        conn.close()

async def mark_prize_as_claimed(contest_id: int, user_id: int, config):
    """Mark prize as claimed by updating claimed_at timestamp in prize_claims table"""
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                UPDATE prize_claims 
                SET claimed_at = NOW() 
                WHERE contest_id = %s AND winner_user_id = %s AND claimed_at IS NULL
            """, (contest_id, user_id))
            
            if cursor.rowcount == 0:
                logger.warning(f"No unclaimed prize found for user {user_id} in contest {contest_id}")
                return False
                
            await conn.commit()
            logger.info(f"Marked prize as claimed for user {user_id} in contest {contest_id}")
            return True
    except Exception as e:
        logger.error(f"Error marking prize as claimed: {e}")
        raise
    finally:
        conn.close()

async def get_latest_unclaimed_prize_for_user(user_id: int, config):
    """Get the latest unclaimed prize for a user from any contest"""
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT cp.contest_id, cp.position, cp.prize_name, cp.prize_type, cp.prize_value, 
                       pc.security_code
                FROM contest_prizes cp
                JOIN prize_claims pc ON cp.contest_id = pc.contest_id AND cp.position = pc.position
                WHERE pc.winner_user_id = %s AND pc.claimed_at IS NULL
                ORDER BY pc.contest_id DESC, cp.position ASC
                LIMIT 1
            """, (user_id,))
            
            result = await cursor.fetchone()
            if result:
                return {
                    'contest_id': result[0],
                    'position': result[1],
                    'prize_name': result[2],
                    'prize_type': result[3],
                    'prize_value': result[4],
                    'security_code': result[5]
                }
            return None
    except Exception as e:
        logger.error(f"Error getting latest unclaimed prize for user {user_id}: {e}")
        raise
    finally:
        conn.close()

async def is_prize_claimed(contest_id: int, position: int, config):
    conn = await get_db_connection(config)
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT claimed_at FROM prize_claims 
                WHERE contest_id = %s AND position = %s
            """, (contest_id, position))
            
            result = await cursor.fetchone()
            return result and result[0] is not None
    except Exception as e:
        logger.error(f"Error checking if prize is claimed: {e}")
        return False
    finally:
        conn.close()
