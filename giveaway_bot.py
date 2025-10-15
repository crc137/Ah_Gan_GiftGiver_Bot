#! /usr/bin/env python3

import asyncio
import random
import shlex
import json
import os
import aiohttp
import aiomysql
import logging
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import BufferedInputFile
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz

load_dotenv()

try:
    os.makedirs("logs", exist_ok=True)
    handlers = [
        logging.FileHandler("logs/giveaway_bot.log"),
        logging.StreamHandler()
    ]
except (OSError, PermissionError) as e:
    handlers = [logging.StreamHandler()]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
group_id_str = os.getenv("GROUP_ID", "")
GROUP_ID = int(group_id_str) if group_id_str.strip() else None

DB_CONFIG = {
    'host': os.getenv("DB_HOST", ""),
    'port': int(os.getenv("DB_PORT", "")),
    'user': os.getenv("DB_USER", ""),
    'password': os.getenv("DB_PASSWORD", ""),
    'db': os.getenv("DB_NAME", ""),
    'charset': 'utf8mb4'
}

allowed_chats_str = os.getenv("ALLOWED_CHATS", "")
ALLOWED_CHATS = [int(chat_id.strip()) for chat_id in allowed_chats_str.split(",") if chat_id.strip()]

bot = Bot(token=TOKEN)
dp = Dispatcher()

participants = {}  
winners = {}      
claimed_winners = set() 
current_contest_id = None 
giveaway_message_id = None
giveaway_chat_id = None
giveaway_has_image = False

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

def sanitize_string(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r'[^\w\s,.()-]', '', s)  
    return s[:255]  

def parse_duration_input(duration_str: str) -> int:
    duration_str = duration_str.lower().strip()
    
    if ':' in duration_str:
        try:
            parts = duration_str.split(':')
            if len(parts) == 2:
                hours = int(parts[0])
                minutes = int(parts[1])
                
                tallinn_tz = pytz.timezone('Europe/Tallinn')
                now = datetime.now(tallinn_tz)
                target_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
                
                if target_time <= now:
                    target_time = target_time.replace(day=target_time.day + 1)
                
                duration_seconds = int((target_time - now).total_seconds())
                return duration_seconds
        except ValueError:
            pass
    
    if duration_str.startswith('d'):
        try:
            days = int(duration_str[1:])
            return days * 24 * 3600
        except ValueError:
            pass
    
    if 'm' in duration_str and 'd' in duration_str:
        try:
            parts = duration_str.split()
            total_seconds = 0
            for part in parts:
                if part.startswith('m'):
                    months = int(part[1:])
                    total_seconds += months * 30 * 24 * 3600
                elif part.startswith('d'):
                    days = int(part[1:])
                    total_seconds += days * 24 * 3600
            return total_seconds
        except ValueError:
            pass
    
    if duration_str.isdigit():
        return int(duration_str)
    
    if 'д' in duration_str or 'day' in duration_str:
        days = int(''.join(filter(str.isdigit, duration_str)))
        return days * 24 * 3600 
    
    elif 'мин' in duration_str or 'minute' in duration_str:
        minutes = int(''.join(filter(str.isdigit, duration_str)))
        return minutes * 60 
    
    elif 'ч' in duration_str or 'hour' in duration_str:
        hours = int(''.join(filter(str.isdigit, duration_str)))
        return hours * 3600 
    
    elif 'м' in duration_str or 'month' in duration_str:
        months = int(''.join(filter(str.isdigit, duration_str)))
        return months * 30 * 24 * 3600 
    
    else:
        try:
            days = int(duration_str)
            if days <= 365:  
                return days * 24 * 3600
            else:
                return (days // 30) * 30 * 24 * 3600
        except ValueError:
            return 3600

def format_duration(duration_seconds: int) -> str:
    if duration_seconds < 60:
        return f"{duration_seconds} секунд"
    elif duration_seconds < 3600:
        minutes = duration_seconds // 60
        return f"{minutes} минут"
    elif duration_seconds < 86400:
        hours = duration_seconds // 3600
        return f"{hours} часов"
    elif duration_seconds < 2592000:  
        days = duration_seconds // 86400
        return f"{days} дней"
    else:
        months = duration_seconds // (30 * 86400)
        return f"{months} месяцев"

def is_url(text: str) -> bool:
    return text.startswith(('http://', 'https://', 'www.', 't.me/', 'tg://'))

def is_data(text: str) -> bool:
    data_patterns = [
        r'^[A-Za-z0-9]{8,}$',  
        r'^[0-9]{4,}$',         
        r'^[A-Za-z0-9+/]{20,}$', 
        r'^[a-f0-9]{32,}$',     
    ]
    import re
    for pattern in data_patterns:
        if re.match(pattern, text.strip()):
            return True
    return False

def validate_contest_params(duration: int, winners_count: int, prizes: list) -> tuple[bool, str]:
    if duration <= 0:
        return False, "Duration must be positive"
    if winners_count <= 0:
        return False, "Winners count must be positive"
    if not prizes or all(not p.strip() for p in prizes):
        return False, "At least one valid prize is required"
    return True, ""

async def is_giveaway_running() -> bool:
    return current_contest_id is not None

def validate_config():
    errors = []
    if not TOKEN:
        errors.append("TELEGRAM_TOKEN is not set")
    if not GROUP_ID:
        errors.append("GROUP_ID is not set")
    if not DB_CONFIG['host']:
        errors.append("DB_HOST is not set")
    if not DB_CONFIG['port']:
        errors.append("DB_PORT is not set or invalid")
    if not DB_CONFIG['user']:
        errors.append("DB_USER is not set")
    if not DB_CONFIG['password']:
        errors.append("DB_PASSWORD is not set")
    if not DB_CONFIG['db']:
        errors.append("DB_NAME is not set")
    if not ALLOWED_CHATS:
        errors.append("ALLOWED_CHATS is empty or invalid")
    
    if errors:
        error_msg = "Configuration errors:\n" + "\n".join(errors)
        logger.critical(error_msg)
        raise ValueError(error_msg)
    
    logger.info("Configuration validation passed")

def create_giveaway_start_message(contest_name: str, duration: int, winners_count: int, prizes: list) -> str:
    tallinn_tz = pytz.timezone('Europe/Tallinn')
    now = datetime.now(tallinn_tz)
    end_time = now + timedelta(seconds=duration)
    
    end_str = end_time.strftime("%B %d, %H:%M")
    time_info = f"{end_str} (Europe/Tallinn)"
     
    valid_prizes = [prize.strip() for prize in prizes if prize and prize.strip()]
    prizes_text = ", ".join(valid_prizes) if valid_prizes else "🎁 Mystery Prize"
    
    message = f"🎂 {contest_name} Giveaway Started!\n\n"
    message += f"⏰ Ends: {time_info}\n"
    
    if valid_prizes:
        message += f"🎁 Prizes: {prizes_text}\n"
    
    message += f"🏆 Winners: {winners_count}\n\n"
    message += "📌 How to participate:\n"
    message += "(｡･ω･｡) Tap the \"🎁 Join\" button, sweetie!\n"
    message += "(*≧ω≦) Sit tight until the giveaway ends!\n"
    message += "(✿◠‿◠) Winners will be announced and can collect their prize!\n\n"
    message += "Good luck, lovebirds! ✿♥‿♥✿"
    
    return message

async def get_db_connection(max_retries=3, retry_delay=5):
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting database connection (attempt {attempt + 1}/{max_retries})")
            return await aiomysql.connect(**DB_CONFIG)
        except aiomysql.Error as e:
            logger.error(f"Database connection failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise Exception("Failed to connect to database after retries")

async def init_database():
    conn = await get_db_connection()
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
                CREATE TABLE IF NOT EXISTS prizes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    contest_id INT NOT NULL,
                    position INT NOT NULL,
                    reward_info VARCHAR(255) NOT NULL,
                    data TEXT NOT NULL,
                    winner_user_id BIGINT,
                    claimed_at TIMESTAMP NULL,
                    security_code VARCHAR(32) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contest_id) REFERENCES contests(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_contest_position (contest_id, position)
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
    finally:
        conn.close()

async def get_prize_details(contest_id: int):
    conn = await get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT reward_info, data FROM prizes WHERE contest_id = %s",
                (contest_id,)
            )
            result = await cursor.fetchone()
            if result:
                return {
                    'reward_info': result[0],
                    'data': result[1]
                }
            return None
    finally:
        conn.close()

async def set_prize_details(contest_id: int, reward_info: str, data: str):
    conn = await get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id FROM prizes WHERE contest_id = %s", (contest_id,))
            existing = await cursor.fetchone()
            
            if existing:
                await cursor.execute(
                    "UPDATE prizes SET reward_info = %s, data = %s WHERE contest_id = %s",
                    (reward_info, data, contest_id)
                )
            else:
                await cursor.execute(
                    "INSERT INTO prizes (contest_id, reward_info, data) VALUES (%s, %s, %s)",
                    (contest_id, reward_info, data)
                )
            await conn.commit()
    finally:
        conn.close()

async def get_contest_by_id(contest_id: int):
    conn = await get_db_connection()
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
                is_valid, error_msg = validate_contest_params(
                    contest['duration'], 
                    contest['winners_count'], 
                    contest['prizes']
                )
                if not is_valid:
                    logger.error(f"Invalid contest {contest_id}: {error_msg}")
                    raise ValueError(f"Invalid contest parameters: {error_msg}")
                return contest
            return None
    except Exception as e:
        logger.error(f"Error getting contest {contest_id}: {e}")
        raise
    finally:
        conn.close()

async def add_contest(contest_name: str, duration: int, winners_count: int, prizes: list, image_url: str = None):
    contest_name = sanitize_string(contest_name)
    prizes = [sanitize_string(p) for p in prizes if p and sanitize_string(p)]
    image_url = sanitize_string(image_url) if image_url else None
    
    is_valid, error_msg = validate_contest_params(duration, winners_count, prizes)
    if not is_valid:
        raise ValueError(error_msg)
    
    conn = await get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO contests (contest_name, duration, winners_count, prizes, image_url) VALUES (%s, %s, %s, %s, %s)",
                (contest_name, duration, winners_count, ','.join(prizes), image_url)
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

async def list_contests():
    conn = await get_db_connection()
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
    finally:
        conn.close()

async def save_state_to_db():
    conn = await get_db_connection()
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
    finally:
        conn.close()

async def load_state_from_db():
    global participants, winners, claimed_winners
    global giveaway_message_id, giveaway_chat_id, giveaway_has_image, current_contest_id
    
    conn = await get_db_connection()
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
            else:
                participants = {}
                winners = {}
                claimed_winners = set()
                giveaway_message_id = None
                giveaway_chat_id = None
                giveaway_has_image = False
                current_contest_id = None
    except Exception:
        participants = {}
        winners = {}
        claimed_winners = set()
        giveaway_message_id = None
        giveaway_chat_id = None
        giveaway_has_image = False
        current_contest_id = None
    finally:
        conn.close()

@dp.callback_query(lambda c: c.data == "join")
async def join_callback(callback: types.CallbackQuery):
    user = callback.from_user

    if callback.message.chat.id not in ALLOWED_CHATS:
        await callback.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.", show_alert=True)
        return

    if user.is_bot:
        await callback.answer("😿 Sorry, bots cannot participate in the giveaway…", show_alert=True)
        return

    if user.id not in participants:
        participants[user.id] = user
        await callback.answer("🎉 You have joined the giveaway! Wait for the results 🧸")
    else:
        await callback.answer("😉 You are already participating!")
    await save_state_to_db()

async def end_giveaway(duration: int, winners_count: int, prizes: list[str]):
    global current_contest_id, giveaway_message_id, giveaway_chat_id, giveaway_has_image
    await asyncio.sleep(duration)
    if not participants:
        if giveaway_has_image:
            try:
                await bot.edit_message_caption(
                    chat_id=giveaway_chat_id,
                    message_id=giveaway_message_id,
                    caption="😿 Oh no, nobody joined the giveaway…"
                )
            except Exception as e:
                logger.warning(f"Failed to edit caption for no participants, falling back to text edit: {e}")
                await bot.edit_message_text(
                    chat_id=giveaway_chat_id,
                    message_id=giveaway_message_id,
                    text="😿 Oh no, nobody joined the giveaway…"
                )
        else:
            await bot.edit_message_text(
                chat_id=giveaway_chat_id,
                message_id=giveaway_message_id,
                text="😿 Oh no, nobody joined the giveaway…"
            )
        current_contest_id = None
        giveaway_message_id = None
        giveaway_chat_id = None
        giveaway_has_image = False
        
        await save_state_to_db()
        return

    winners_count = min(winners_count, len(participants))
    selected_winners = random.sample(list(participants.values()), winners_count)

    from db import create_prizes_for_contest, assign_winner_to_prize
    await create_prizes_for_contest(current_contest_id, winners_count, DB_CONFIG)
    
    winners.clear()
    for i, winner in enumerate(selected_winners):
        position = i + 1  
        await assign_winner_to_prize(current_contest_id, position, winner.id, DB_CONFIG)
        winners[winner.id] = f"Position {position}"

    text = (
        "✨ The giveaway is over!\n"
        "Thank you for taking part — your energy made it special 💕\n\n"
        "🎀 Winner:\n"
    )

    for i, winner in enumerate(selected_winners):
        position = i + 1
        position_emoji = "🥇" if position == 1 else "🥈" if position == 2 else "🥉" if position == 3 else "🏆"
        
        if winner.username:
            display_name = f"@{winner.username}"
        else:
            name = f"{winner.first_name} {winner.last_name or ''}".strip()
            if name:
                display_name = f"[{name}](tg://user?id={winner.id})"
            else:
                display_name = f"[Anonymous](tg://user?id={winner.id})"
        
        text += f"{position_emoji} {position}st place: {display_name}\n"

    text += (
        "\nTap the button below to claim your prize 🎁\n"
        "Good luck in the next drop! 🌷"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Claim Prize", callback_data="claim")

    if giveaway_has_image:
        MAX_CAPTION = 1024
        caption = text if len(text) <= MAX_CAPTION else (text[:MAX_CAPTION - 1] + "…")
        try:
            await bot.edit_message_caption(
                chat_id=giveaway_chat_id,
                message_id=giveaway_message_id,
                caption=caption,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Failed to edit caption, falling back to text edit: {e}")
            await bot.edit_message_text(
                chat_id=giveaway_chat_id,
                message_id=giveaway_message_id,
                text=text,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
    else:
        await bot.edit_message_text(
            chat_id=giveaway_chat_id,
            message_id=giveaway_message_id,
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

    current_contest_id = None
    giveaway_message_id = None
    giveaway_chat_id = None
    giveaway_has_image = False

    await save_state_to_db()

@dp.callback_query(lambda c: c.data == "claim")
async def claim_prize(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    if callback.message.chat.id not in ALLOWED_CHATS:
        await callback.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.", show_alert=True)
        return

    if user_id not in winners:
        await callback.answer("😿 Sorry, you are not a winner this time!\n\n Don't worry, try the next giveaway!", show_alert=True)
        return
    if user_id in claimed_winners:
        await callback.answer("💕 You already claimed your prize!", show_alert=True)
        return
    
    await callback.answer("💬 To receive your reward, please send the /claim command directly to the bot in a private chat! 🎁", show_alert=True)

@dp.message(Command("claim"))
async def claim_command(message: types.Message):
    user_id = message.from_user.id
    
    if message.chat.type != "private":
        await message.answer("💬 To claim your reward, please send the /claim command to the bot in a private chat! 🎁")
        return
    
    if user_id not in winners:
        await message.answer("😿 Sorry, you are not a winner in any active giveaway.")
        return
    
    if user_id in claimed_winners:
        await message.answer("💕 You already claimed your prize!")
        return
    
    claimed_winners.add(user_id)
    prize = winners[user_id]
    
    from db import get_winner_prize, mark_prize_as_claimed
    winner_prize = await get_winner_prize(current_contest_id, user_id, DB_CONFIG) if current_contest_id else None
    
    message_text = "🧁 Yay~ You made it! (✿◠‿◠)\nHere's your little gift 🎁\nHope it brings you a smile and a bit of luck 💖\n\n"
    
    from aiogram.types import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    if winner_prize:
        position = winner_prize['position']
        position_emoji = "🥇" if position == 1 else "🥈" if position == 2 else "🥉" if position == 3 else "🏆"
        message_text += f"{position_emoji} You won {position}st place!\n"
        
        if winner_prize['reward_info'] and winner_prize['reward_info'].strip():
            message_text += f"✨ Reward: {winner_prize['reward_info']}\n"
        else:
            message_text += "✨ Reward: (coming soon...)\n"
        
        if winner_prize['data'] and winner_prize['data'].strip():
            data = winner_prize['data'].strip()
            if is_url(data):
                builder.button(text="🎀 Open Link", url=data)
            elif is_data(data):
                message_text += f"🔑 Data: `{data}`\n"
            else:
                message_text += f"🔑 Data: `{data}`\n"
        
        await mark_prize_as_claimed(current_contest_id, user_id, DB_CONFIG)
        message_text += "\nYou're amazing — stay cute and lucky! (≧◡≦)♡"
    else:
        if prize and prize.strip() and prize != "🎁":
            message_text += f"🎀 Reward: {prize}\n"
        else:
            message_text += "✨ Reward: (coming soon...)\n"
        
        message_text += "\nThank you for your patience — you're the sweetest! (✿◠‿◠)"
    
    if builder.buttons:
        await message.answer(message_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    else:
        await message.answer(message_text, parse_mode="Markdown")
    
    await save_state_to_db()

@dp.message(Command("start_giveaway"))
async def start_giveaway_command(message: types.Message):
    logger.info(f"Start giveaway command by user {message.from_user.id} in chat {message.chat.id}")
    logger.info(f"ALLOWED_CHATS: {ALLOWED_CHATS}")
    logger.info(f"Chat type: {message.chat.type}")
    
    if message.chat.id not in ALLOWED_CHATS:
        logger.warning(f"Chat {message.chat.id} not in whitelist. Allowed chats: {ALLOWED_CHATS}")
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    if await is_giveaway_running():
        await message.answer("🚫 A giveaway is already running! Please wait for it to finish before starting a new one.")
        logger.warning(f"Attempted to start giveaway while one is running by user {message.from_user.id}")
        return
    
    try:
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
            return
    except Exception:
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    args = message.text.split()[1:]
    if not args:
        contests = await list_contests()
        if not contests:
            await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
            return
        
        text = "Available contests:\n"
        for contest in contests:
            text += f"ID {contest['id']}: {contest['name']} ({contest['duration']}s, {contest['winners_count']} winners)\n"
        await message.answer(text)
        return
    
    try:
        contest_id = int(args[0])
    except ValueError:
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    contest = await get_contest_by_id(contest_id)
    if not contest:
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    global giveaway_message_id, giveaway_chat_id, giveaway_has_image, current_contest_id
    
    participants.clear()
    winners.clear()
    claimed_winners.clear()
    current_contest_id = contest_id
    
    giveaway_has_image = False 
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Join", callback_data="join")
    
    if contest['image_url']:
        try:
            photo_file = await download_image(contest['image_url'])
            if photo_file is not None:
                sent_msg = await message.answer_photo(
                    photo=photo_file,
                    caption=create_giveaway_start_message(contest['name'], contest['duration'], contest['winners_count'], contest['prizes']),
                    reply_markup=builder.as_markup()
                )
                giveaway_has_image = True
            else:
                sent_msg = await message.answer(
                    create_giveaway_start_message(contest['name'], contest['duration'], contest['winners_count'], contest['prizes']),
                    reply_markup=builder.as_markup()
                )
                giveaway_has_image = False
        except Exception as e:
            logger.warning(f"Failed to download image from {contest['image_url']}: {e}")
            warning_msg = f"⚠️ Не удалось загрузить изображение из URL. Конкурс создан без изображения.\n\n"
            sent_msg = await message.answer(
                warning_msg + create_giveaway_start_message(contest['name'], contest['duration'], contest['winners_count'], contest['prizes']),
                reply_markup=builder.as_markup()
            )
            giveaway_has_image = False
    else:
        sent_msg = await message.answer(
            create_giveaway_start_message(contest['name'], contest['duration'], contest['winners_count'], contest['prizes']),
            reply_markup=builder.as_markup()
        )

    giveaway_message_id = sent_msg.message_id
    giveaway_chat_id = sent_msg.chat.id
    await save_state_to_db()
    
    asyncio.create_task(end_giveaway(contest['duration'], contest['winners_count'], contest['prizes']))

@dp.message(Command("contest"))
async def contest_command(message: types.Message):
    if message.chat.id not in ALLOWED_CHATS:
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    try:
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
            return
    except Exception:
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    args = message.text.split()[1:]
    if not args:
        contests = await list_contests()
        if not contests:
            await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
            return
        
        text = "Available contests:\n"
        for contest in contests:
            text += f"ID {contest['id']}: {contest['name']} ({contest['duration']}s, {contest['winners_count']} winners)\n"
        await message.answer(text)
        return
    
    try:
        contest_id = int(args[0])
    except ValueError:
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    contest = await get_contest_by_id(contest_id)
    if not contest:
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    global giveaway_message_id, giveaway_chat_id, giveaway_has_image, current_contest_id
    
    participants.clear()
    winners.clear()
    claimed_winners.clear()
    current_contest_id = contest_id
    
    giveaway_has_image = False 
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Join", callback_data="join")
    
    if contest['image_url']:
        try:
            photo_file = await download_image(contest['image_url'])
            if photo_file is not None:
                sent_msg = await message.answer_photo(
                    photo=photo_file,
                    caption=create_giveaway_start_message(contest['name'], contest['duration'], contest['winners_count'], contest['prizes']),
                    reply_markup=builder.as_markup()
                )
                giveaway_has_image = True
            else:
                sent_msg = await message.answer(
                    create_giveaway_start_message(contest['name'], contest['duration'], contest['winners_count'], contest['prizes']),
                    reply_markup=builder.as_markup()
                )
                giveaway_has_image = False
        except Exception as e:
            logger.warning(f"Failed to download image from {contest['image_url']}: {e}")
            warning_msg = f"⚠️ Не удалось загрузить изображение из URL. Конкурс создан без изображения.\n\n"
            sent_msg = await message.answer(
                warning_msg + create_giveaway_start_message(contest['name'], contest['duration'], contest['winners_count'], contest['prizes']),
                reply_markup=builder.as_markup()
            )
            giveaway_has_image = False
    else:
        sent_msg = await message.answer(
            create_giveaway_start_message(contest['name'], contest['duration'], contest['winners_count'], contest['prizes']),
            reply_markup=builder.as_markup()
        )

    giveaway_message_id = sent_msg.message_id
    giveaway_chat_id = sent_msg.chat.id
    await save_state_to_db()
    
    asyncio.create_task(end_giveaway(contest['duration'], contest['winners_count'], contest['prizes']))

async def download_image(url: str) -> BufferedInputFile | None:
    try:
        if not url or not url.startswith(('http://', 'https://')):
            logger.warning(f"Invalid URL format: {url}")
            return None
            
        timeout = aiohttp.ClientTimeout(total=15)  
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    logger.warning(f"HTTP error {resp.status} for URL: {url}")
                    return None
                    
                content_type = resp.headers.get("Content-Type", "").lower()
                if not content_type.startswith("image/"):
                    logger.warning(f"Invalid content type {content_type} for URL: {url}")
                    return None
                    
                content_length = resp.headers.get('Content-Length')
                if content_length and int(content_length) > 20 * 1024 * 1024:
                    logger.warning(f"Image too large ({content_length} bytes) for URL: {url}")
                    return None
                    
                data = await resp.read()
                if not data:
                    logger.warning(f"Empty image data for URL: {url}")
                    return None
                    
                if len(data) > 20 * 1024 * 1024:
                    logger.warning(f"Downloaded image too large ({len(data)} bytes) for URL: {url}")
                    return None
                    
                supported_formats = ['jpeg', 'jpg', 'png', 'gif', 'webp']
                subtype = content_type.split("/", 1)[1].split(';')[0] if "/" in content_type else "jpg"
                
                if subtype not in supported_formats:
                    logger.warning(f"Unsupported image format {subtype} for URL: {url}")
                    return None
                    
                filename = f"image.{subtype}"
                logger.info(f"Successfully downloaded image from {url} ({len(data)} bytes, {subtype})")
                return BufferedInputFile(data, filename)
                
    except aiohttp.ClientError as e:
        logger.warning(f"Network error downloading image from {url}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error downloading image from {url}: {e}")
        return None

@dp.message(Command("create_contest"))
async def create_contest_command(message: types.Message):
    logger.info(f"Create contest command by user {message.from_user.id} in chat {message.chat.id}")
    logger.info(f"ALLOWED_CHATS: {ALLOWED_CHATS}")
    logger.info(f"Chat type: {message.chat.type}")
    
    if message.chat.id not in ALLOWED_CHATS:
        logger.warning(f"Chat {message.chat.id} not in whitelist. Allowed chats: {ALLOWED_CHATS}")
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    try:
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await message.answer("Only admins can create contests.")
            return
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        await message.answer("Error checking admin status.")
        return
    
    image_url = None
    if message.photo:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        logger.info(f"Image attached: {image_url}")
    
    args = shlex.split(message.text)[1:]
    if len(args) < 3:
        await message.answer("Usage: /create_contest <name> <duration> <winners_count> [prizes...] [image_url]\n\n⏰ Duration formats:\n• 7д, 7дней - 7 days\n• 1м, 1месяц - 1 month\n• 2ч, 2часа - 2 hours\n• 30мин - 30 minutes\n• 7 - 7 days (auto)\n• 50 - 50 days (auto)\n• 8:46 - specific time (Europe/Tallinn)\n\n📸 You can attach an image or provide image_url!")
        return
    
    try:
        name = args[0]
        duration = parse_duration_input(args[1])
        winners_count = int(args[2])
        
        remaining_args = args[3:] if len(args) > 3 else []
        prizes = []
        url_image = None
        
        for arg in remaining_args:
            if arg.startswith(('http://', 'https://')):
                if any(ext in arg.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                    url_image = arg
                else:
                    logger.warning(f"URL does not appear to be an image: {arg}")
                    prizes.append(arg) 
            else:
                prizes.append(arg)
        final_image_url = image_url if image_url else url_image
        
        from db import add_contest
        contest_id = await add_contest(name, duration, winners_count, prizes, DB_CONFIG, final_image_url)
        
        duration_formatted = format_duration(duration)
        response_text = f"✅ Contest '{name}' created with ID {contest_id}.\n⏰ Duration: {duration_formatted}\nUse /start_giveaway {contest_id} to start it."
        if final_image_url:
            response_text += f"\n📸 Image: {final_image_url}"
        
        await message.answer(response_text)
        logger.info(f"Created contest {contest_id}: {name} with image: {final_image_url}")
    except ValueError as e:
        await message.answer(f"❌ Invalid parameters: {e}")
        logger.error(f"Invalid contest creation parameters: {e}")
    except Exception as e:
        await message.answer(f"❌ Error creating contest: {e}")
        logger.error(f"Error creating contest: {e}")

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    logger.info(f"Stats command by user {message.from_user.id} in chat {message.chat.id}")
    
    if message.chat.id not in ALLOWED_CHATS:
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    try:
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await message.answer("Only admins can view stats.")
            return
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        await message.answer("Error checking admin status.")
        return
    
    if not current_contest_id:
        await message.answer("📊 No active giveaway.")
        return
    
    try:
        contest = await get_contest_by_id(current_contest_id)
        if not contest:
            await message.answer("❌ Contest not found.")
            return
        
        text = f"📊 Giveaway Stats for '{contest['name']}'\n"
        text += f"👥 Participants: {len(participants)}\n"
        text += f"🏆 Winners: {len(winners)}\n"
        text += f"✅ Claimed: {len(claimed_winners)}\n"
        text += f"⏰ Duration: {contest['duration']} seconds\n"
        if contest['prizes']:
            text += f"🎁 Prizes: {', '.join(contest['prizes'])}"
        
        await message.answer(text)
        logger.info(f"Stats requested for contest {current_contest_id}")
    except Exception as e:
        await message.answer(f"❌ Error getting stats: {e}")
        logger.error(f"Error getting stats: {e}")

@dp.message(Command("cancel_giveaway"))
async def cancel_giveaway_command(message: types.Message):
    global participants, winners, claimed_winners, current_contest_id, giveaway_message_id, giveaway_chat_id, giveaway_has_image
    
    logger.info(f"Cancel giveaway command by user {message.from_user.id} in chat {message.chat.id}")
    
    if message.chat.id not in ALLOWED_CHATS:
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")
        return
    
    try:
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await message.answer("Only admins can cancel giveaways.")
            return
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        await message.answer("Error checking admin status.")
        return
    
    if not await is_giveaway_running():
        await message.answer("📊 No active giveaway to cancel.")
        return
    
    try:
        contest = await get_contest_by_id(current_contest_id)
        if not contest:
            await message.answer("❌ Contest not found.")
            return
        
        cancel_text = f"❌ Giveaway '{contest['name']}' has been cancelled.\nThank you for participating, better luck next time! 🌷"
        if giveaway_has_image:
            await bot.edit_message_caption(
                chat_id=giveaway_chat_id,
                message_id=giveaway_message_id,
                caption=cancel_text
            )
        else:
            await bot.edit_message_text(
                chat_id=giveaway_chat_id,
                message_id=giveaway_message_id,
                text=cancel_text
            )
        
        participants.clear()
        winners.clear()
        claimed_winners.clear()
        current_contest_id = None
        giveaway_message_id = None
        giveaway_chat_id = None
        giveaway_has_image = False
        await save_state_to_db()
        
        await message.answer(f"✅ Giveaway '{contest['name']}' has been cancelled.")
        logger.info(f"Giveaway cancelled by user {message.from_user.id}")
    except Exception as e:
        await message.answer(f"❌ Error cancelling giveaway: {e}")
        logger.error(f"Error cancelling giveaway: {e}")

@dp.message()
async def handle_any_message(message: types.Message):
    logger.info(f"Received message: '{message.text}' from user {message.from_user.id} in chat {message.chat.id}")
    logger.info(f"ALLOWED_CHATS: {ALLOWED_CHATS}")
    logger.info(f"Chat in whitelist: {message.chat.id in ALLOWED_CHATS}")
    
    if (not message.text or not (message.text.startswith('/claim') or message.text.startswith('/start_giveaway') or message.text.startswith('/contest') or message.text.startswith('/create_contest') or message.text.startswith('/stats'))) and message.chat.id not in ALLOWED_CHATS:
        logger.warning(f"Sending backward compatibility message for chat {message.chat.id}")
        await message.answer("Sorry, I'm not a real bot, they just made me for backward compatibility. I can't really answer any questions.")

if __name__ == "__main__":
    async def main():   
        validate_config()
        from db import init_database
        await init_database(DB_CONFIG)
        from db import load_state_from_db
        participants, winners, claimed_winners, giveaway_message_id, giveaway_chat_id, giveaway_has_image, current_contest_id = await load_state_from_db(DB_CONFIG)
        await dp.start_polling(bot)
    
    asyncio.run(main())
