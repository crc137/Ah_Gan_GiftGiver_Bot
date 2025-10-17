#! /usr/bin/env python3

import asyncio
import secrets
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
except (OSError, PermissionError):
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
    if not duration_str:
        raise ValueError("Duration cannot be empty")
    duration_str = duration_str.lower().strip()
    
    if ':' in duration_str:
        try:
            parts = duration_str.split(':')
            if len(parts) == 2:
                hours = int(parts[0])
                minutes = int(parts[1])
                
                if hours < 0 or hours > 23:
                    raise ValueError("Hours must be between 0 and 23")
                if minutes < 0 or minutes > 59:
                    raise ValueError("Minutes must be between 0 and 59")
                
                tallinn_tz = pytz.timezone('Europe/Tallinn')
                now = datetime.now(tallinn_tz)
                target_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
                
                if target_time <= now:
                    current_time_str = now.strftime("%H:%M")
                    requested_time_str = f"{hours:02d}:{minutes:02d}"
                    raise ValueError(f"Time {requested_time_str} has already passed. Current time is {current_time_str}. Please specify a future time.")
                
                duration_seconds = int((target_time - now).total_seconds())
                return duration_seconds
        except ValueError as e:
            raise ValueError(str(e))
    
    if duration_str.startswith('d'):
        try:
            days_str = duration_str[1:]
            if not days_str:
                raise ValueError("Days value cannot be empty")
            days = int(days_str)
            if days <= 0:
                raise ValueError("Days must be a positive number")
            if days > 365:
                raise ValueError("Duration cannot exceed 365 days")
            return days * 24 * 3600
        except ValueError as e:
            raise ValueError(str(e))
    
    if 'm' in duration_str and 'd' in duration_str:
        try:
            parts = duration_str.split()
            total_seconds = 0
            for part in parts:
                if part.startswith('m'):
                    months = int(part[1:])
                    if months <= 0:
                        raise ValueError("Months must be a positive number")
                    if months > 12:
                        raise ValueError("Months cannot exceed 12")
                    total_seconds += months * 30 * 24 * 3600
                elif part.startswith('d'):
                    days = int(part[1:])
                    if days <= 0:
                        raise ValueError("Days must be a positive number")
                    if days > 365:
                        raise ValueError("Days cannot exceed 365")
                    total_seconds += days * 24 * 3600
            if total_seconds > 365 * 24 * 3600:
                raise ValueError("Total duration cannot exceed 365 days")
            return total_seconds
        except ValueError as e:
            raise ValueError(str(e))
    
    if duration_str.isdigit():
        days = int(duration_str)
        if days <= 0:
            raise ValueError("Duration must be a positive number")
        if days > 365:
            raise ValueError("Duration cannot exceed 365 days")
        return days * 24 * 3600
    
    if 'д' in duration_str or 'day' in duration_str:
        days = int(''.join(filter(str.isdigit, duration_str)))
        if days <= 0:
            raise ValueError("Days must be a positive number")
        if days > 365:
            raise ValueError("Days cannot exceed 365")
        return days * 24 * 3600 
    
    elif 'мин' in duration_str or 'minute' in duration_str:
        minutes = int(''.join(filter(str.isdigit, duration_str)))
        if minutes <= 0:
            raise ValueError("Minutes must be a positive number")
        if minutes > 1440: 
            raise ValueError("Minutes cannot exceed 1440 (24 hours)")
        return minutes * 60 
    
    elif 'ч' in duration_str or 'hour' in duration_str:
        hours = int(''.join(filter(str.isdigit, duration_str)))
        if hours <= 0:
            raise ValueError("Hours must be a positive number")
        if hours > 8760: 
            raise ValueError("Hours cannot exceed 8760 (365 days)")
        return hours * 3600 
    
    elif 'м' in duration_str or 'month' in duration_str:
        months = int(''.join(filter(str.isdigit, duration_str)))
        if months <= 0:
            raise ValueError("Months must be a positive number")
        if months > 12:
            raise ValueError("Months cannot exceed 12")
        return months * 30 * 24 * 3600 
    
    else:
        try:
            days = int(duration_str)
            if days <= 0:
                raise ValueError("Duration must be a positive number")
            if days > 365:
                raise ValueError("Duration cannot exceed 365 days")
            return days * 24 * 3600
        except ValueError as e:
            raise ValueError(f"Invalid duration format: {duration_str}. {str(e)}")

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

def is_safe_link(link: str) -> bool:
    if not link:
        return False
    return link.startswith(('https://', 't.me/', 'tg://'))

def is_url(text: str) -> bool:
    return is_safe_link(text)

def _ordinal_suffix(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"

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
    is_running = current_contest_id is not None
    logger.debug(f"Giveaway running check: {is_running} (contest_id: {current_contest_id})")
    return is_running

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
    
    message = f"🎂 {contest_name} Giveaway Started!\n\n"
    message += f"⏰ Ends: {time_info}\n\n"
    
    if valid_prizes:
        message += "🎁 Prizes:\n"
        for i, prize in enumerate(valid_prizes, 1):
            position_emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"
            message += f"{position_emoji} {prize}\n"
    else:
        message += "🎁 Prizes: 🎁 Mystery Prize\n"
    
    message += f"\n 🏆 Winners: {winners_count}\n\n"
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
            conn = await aiomysql.connect(**DB_CONFIG)
            logger.info("Database connection established successfully")
            return conn
        except aiomysql.Error as e:
            logger.error(f"Database connection failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.critical("Failed to connect to database after all retries")
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
            
            from db import create_contest_prizes
            await create_contest_prizes(contest_id, prizes, DB_CONFIG)
            
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
                
                logger.info(f"Restored state: contest_id={current_contest_id}, participants={len(participants)}, winners={len(winners)}")
            else:
                participants = {}
                winners = {}
                claimed_winners = set()
                giveaway_message_id = None
                giveaway_chat_id = None
                giveaway_has_image = False
                current_contest_id = None
                logger.info("No existing state found, starting fresh")
    except Exception as e:
        logger.error(f"Error loading state from database: {e}")
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
        await callback.answer("This chat is not authorized for giveaways.", show_alert=True)
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
    secure_random = secrets.SystemRandom()
    selected_winners = secure_random.sample(list(participants.values()), winners_count)

    from db import assign_winner_to_prize_position
    
    winners.clear()
    for i, winner in enumerate(selected_winners):
        position = i + 1  
        await assign_winner_to_prize_position(current_contest_id, position, winner.id, DB_CONFIG)
        prize_name = prizes[i] if i < len(prizes) else f"Prize {position}"
        winners[winner.id] = prize_name

    text = (
        "✨ The giveaway is over!\n"
        "Thank you for taking part — your energy made it special 💕\n\n"
        "🎀 Winner:\n"
    )

    for i, winner in enumerate(selected_winners):
        position = i + 1
        position_emoji = "🥇" if position == 1 else "🥈" if position == 2 else "🥉" if position == 3 else "🏅"
        prize_name = prizes[i] if i < len(prizes) else f"Prize {position}"
        
        if winner.username:
            display_name = f"@{winner.username}"
        else:
            name = f"{winner.first_name} {winner.last_name or ''}".strip()
            if name:
                display_name = f"[{name}](tg://user?id={winner.id})"
            else:
                display_name = f"[Anonymous](tg://user?id={winner.id})"
        
        text += f"{position_emoji} {_ordinal_suffix(position)} place: {display_name} - {prize_name}\n"

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
        await callback.answer("This chat is not authorized for giveaways.", show_alert=True)
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
    
    from db import get_latest_unclaimed_prize_for_user, mark_prize_as_claimed
    
    winner_prize = await get_latest_unclaimed_prize_for_user(user_id, DB_CONFIG)
    
    if not winner_prize:
        await message.answer("😿 Sorry, you don't have any unclaimed prizes.")
        return
    
    success = await mark_prize_as_claimed(winner_prize['contest_id'], user_id, DB_CONFIG)
    if not success:
        await message.answer("Error claiming prize. Please try again later.")
        return
    
    message_text = "🧁 Yay~ You made it! (✿◠‿◠)\nHere's your little gift 🎁\nHope it brings you a smile and a bit of luck 💖\n\n"
    
    builder = InlineKeyboardBuilder()
    
    position = winner_prize['position']
    position_emoji = "🥇" if position == 1 else "🥈" if position == 2 else "🥉" if position == 3 else "🏅"
    message_text += f"{position_emoji} You won {_ordinal_suffix(position)} place!\n"
    message_text += f"🎁 Prize: {winner_prize['prize_name']}\n"
    
    if winner_prize['prize_type'] == 'link':
        builder.button(text="🎀 Claim Prize", url=winner_prize['prize_value'])
        message_text += "✨ Click the button below to claim your prize!\n"
    else:
        message_text += f"✨ Prize Details: {winner_prize['prize_value']}\n"
    
    message_text += "\nYou're amazing — stay cute and lucky! (≧◡≦)♡"
    
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
        await message.answer("This chat is not authorized for giveaways.")
        return
    
    if await is_giveaway_running():
        await message.answer("A giveaway is already running! Please wait for it to finish before starting a new one.")
        logger.warning(f"Attempted to start giveaway while one is running by user {message.from_user.id}")
        return
    
    try:
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await message.answer("This chat is not authorized for giveaways.")
            return
    except Exception:
        await message.answer("This chat is not authorized for giveaways.")
        return
    
    args = message.text.split()[1:]
    if not args:
        contests = await list_contests()
        if not contests:
            await message.answer("This chat is not authorized for giveaways.")
            return
        
        text = "Available contests:\n"
        for contest in contests:
            text += f"ID {contest['id']}: {contest['name']} ({contest['duration']}s, {contest['winners_count']} winners)\n"
        await message.answer(text)
        return
    
    try:
        contest_id = int(args[0])
    except ValueError:
        await message.answer("This chat is not authorized for giveaways.")
        return
    
    contest = await get_contest_by_id(contest_id)
    if not contest:
        await message.answer("This chat is not authorized for giveaways.")
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
            warning_msg = "The image is in an unsupported format (AVIF/HEIC). The contest has been created without an image.\n\n"
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
        await message.answer("This chat is not authorized for giveaways.")
        return
    
    try:
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await message.answer("This chat is not authorized for giveaways.")
            return
    except Exception:
        await message.answer("This chat is not authorized for giveaways.")
        return
    
    args = message.text.split()[1:]
    if not args:
        contests = await list_contests()
        if not contests:
            await message.answer("This chat is not authorized for giveaways.")
            return
        
        text = "Available contests:\n"
        for contest in contests:
            text += f"ID {contest['id']}: {contest['name']} ({contest['duration']}s, {contest['winners_count']} winners)\n"
        await message.answer(text)
        return
    
    try:
        contest_id = int(args[0])
    except ValueError:
        await message.answer("This chat is not authorized for giveaways.")
        return
    
    contest = await get_contest_by_id(contest_id)
    if not contest:
        await message.answer("This chat is not authorized for giveaways.")
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
            warning_msg = "The image is in an unsupported format (AVIF/HEIC). The contest has been created without an image.\n\n"
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
    logger.info(f"Starting image download from: {url}")
    
    try:
        if not url or not is_safe_link(url):
            logger.warning(f"Invalid URL format: {url}")
            return None
            
        timeout = aiohttp.ClientTimeout(total=15)  
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/*,*/*;q=0.8'
        }
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            logger.info(f"Making request to: {url}")
            async with session.get(url, allow_redirects=True) as resp:
                logger.info(f"Response status: {resp.status}")
                logger.info(f"Response headers: {dict(resp.headers)}")
                
                if resp.status != 200:
                    logger.warning(f"HTTP error {resp.status} for URL: {url}")
                    return None
                    
                content_type = resp.headers.get("Content-Type", "").lower()
                logger.info(f"Content-Type: {content_type}")
                
                if not content_type.startswith("image/"):
                    logger.warning(f"Invalid content type {content_type} for URL: {url}")
                    return None
                    
                content_length = resp.headers.get('Content-Length')
                if content_length:
                    logger.info(f"Content-Length: {content_length} bytes")
                    if int(content_length) > 20 * 1024 * 1024:
                        logger.warning(f"Image too large ({content_length} bytes) for URL: {url}")
                        return None
                    
                data = await resp.read()
                logger.info(f"Downloaded {len(data)} bytes")
                
                if not data:
                    logger.warning(f"Empty image data for URL: {url}")
                    return None
                    
                if len(data) > 20 * 1024 * 1024:
                    logger.warning(f"Downloaded image too large ({len(data)} bytes) for URL: {url}")
                    return None
                    
                supported_formats = ['jpeg', 'jpg', 'png', 'gif', 'webp']
                subtype = content_type.split("/", 1)[1].split(';')[0] if "/" in content_type else "jpg"
                logger.info(f"Image subtype from Content-Type: {subtype}")
                
                if subtype not in supported_formats:
                    logger.warning(f"Unsupported image format {subtype} for URL: {url}")
                    return None
                
                if data.startswith(b'\xff\xd8\xff'):
                    actual_format = 'jpeg'
                elif data.startswith(b'\x89PNG\r\n\x1a\n'):
                    actual_format = 'png'
                elif data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
                    actual_format = 'gif'
                elif data.startswith(b'RIFF') and b'WEBP' in data[:12]:
                    actual_format = 'webp'
                elif data.startswith(b'\x00\x00\x00 ftypavif'):
                    actual_format = 'avif'
                    logger.warning(f"AVIF format detected - not supported by Telegram Bot API: {url}")
                    return None
                else:
                    actual_format = 'unknown'
                    logger.warning(f"Unknown image format detected in data for URL: {url}")
                
                logger.info(f"Actual image format detected: {actual_format}")
                
                filename = f"image.{actual_format if actual_format != 'unknown' else subtype}"
                logger.info(f"Successfully downloaded image from {url} ({len(data)} bytes, {actual_format})")
                
                if actual_format == 'unknown' and len(data) > 100:  
                    logger.warning(f"Unknown image format, but data size suggests it might be valid: {len(data)} bytes")
                    filename = f"image.{subtype}"
                
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
        await message.answer("This chat is not authorized for giveaways.")
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
    logger.info(f"Parsed args: {args}")
    logger.info(f"Number of args: {len(args)}")
    
    if len(args) < 3:
        await message.answer("Usage: /create_contest <name> <duration> <winners_count> [prizes...] [image_url]\n\nDuration formats:\n• 7д, 7дней - 7 days (max 365)\n• 1м, 1месяц - 1 month (max 12)\n• 2ч, 2часа - 2 hours (max 8760)\n• 30мин - 30 minutes (max 1440)\n• 7 - 7 days (max 365)\n• 50 - 50 days (max 365)\n• 8:46 - specific time (Europe/Tallinn, must be in future)\n\nYou can attach an image or provide image_url!")
        return
    
    try:
        name = args[0]
        duration = parse_duration_input(args[1])
        winners_count = int(args[2])
        
        remaining_args = args[3:] if len(args) > 3 else []
        logger.info(f"Remaining args for prizes: {remaining_args}")
        prizes = []
        url_image = None
        
        for arg in remaining_args:
            logger.info(f"Processing arg: '{arg}'")
            if is_safe_link(arg):
                if any(ext in arg.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                    url_image = arg
                    logger.info(f"Detected image URL: {arg}")
                else:
                    if 'image' in arg.lower() or 'photo' in arg.lower() or 'img' in arg.lower():
                        url_image = arg
                        logger.info(f"Detected potential image URL (no extension): {arg}")
                    else:
                        logger.warning(f"URL does not appear to be an image: {arg}")
                        prizes.append(arg) 
            else:
                prizes.append(arg)
                logger.info(f"Added prize: '{arg}'")
        
        logger.info(f"Final prizes list: {prizes}")
        logger.info(f"Final image URL: {url_image}")
        final_image_url = image_url if image_url else url_image
        
        from db import add_contest
        contest_id = await add_contest(name, duration, winners_count, prizes, DB_CONFIG, final_image_url)
        
        duration_formatted = format_duration(duration)
        response_text = f"Contest '{name}' created with ID {contest_id}.\nDuration: {duration_formatted}\nUse /start_giveaway {contest_id} to start it."
        if final_image_url:
            response_text += f"\nImage: {final_image_url}"
        
        await message.answer(response_text)
        logger.info(f"Created contest {contest_id}: {name} with image: {final_image_url}")
    except ValueError as e:
        await message.answer(f"Invalid parameters: {e}")
        logger.error(f"Invalid contest creation parameters: {e}")
    except Exception as e:
        await message.answer(f"Error creating contest: {e}")
        logger.error(f"Error creating contest: {e}")

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    logger.info(f"Stats command by user {message.from_user.id} in chat {message.chat.id}")
    
    if message.chat.id not in ALLOWED_CHATS:
        await message.answer("This chat is not authorized for giveaways.")
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
        await message.answer("No active giveaway.")
        return
    
    try:
        contest = await get_contest_by_id(current_contest_id)
        if not contest:
            await message.answer("Contest not found.")
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
        await message.answer(f"Error getting stats: {e}")
        logger.error(f"Error getting stats: {e}")

@dp.message(Command("set_prize_data"))
async def set_prize_data_command(message: types.Message):
    logger.info(f"Set prize data command by user {message.from_user.id} in chat {message.chat.id}")
    
    if message.chat.id not in ALLOWED_CHATS:
        await message.answer("This chat is not authorized for giveaways.")
        return
    
    try:
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await message.answer("Only admins can set prize data.")
            return
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        await message.answer("Error checking admin status.")
        return
    
    args = shlex.split(message.text)[1:]
    if len(args) < 3:
        await message.answer("Usage: /set_prize_data <contest_id> <position> <prize_name> <prize_value>\n\nExample: /set_prize_data 1 1 \"100 USDT\" \"https://example.com/claim\"")
        return
    
    try:
        contest_id = int(args[0])
        position = int(args[1])
        prize_name = args[2]
        prize_value = args[3] if len(args) > 3 else ""
        
        prize_type = 'link' if is_safe_link(prize_value) else 'text'
        
        from db import get_db_connection
        conn = await get_db_connection(DB_CONFIG)
        try:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    UPDATE contest_prizes 
                    SET prize_name = %s, prize_type = %s, prize_value = %s 
                    WHERE contest_id = %s AND position = %s
                """, (prize_name, prize_type, prize_value, contest_id, position))
                
                if cursor.rowcount == 0:
                    await message.answer(f"No prize found for contest {contest_id}, position {position}")
                    return
                
                await conn.commit()
            
            await message.answer(f"✅ Prize updated for contest {contest_id}, position {position}:\n🎁 Name: {prize_name}\n🔗 Type: {prize_type}\n💎 Value: {prize_value}")
            logger.info(f"Prize data updated for contest {contest_id} by user {message.from_user.id}")
        finally:
            conn.close()
        
    except ValueError as e:
        await message.answer(f"Invalid parameters: {e}")
        logger.error(f"Invalid prize data parameters: {e}")
    except Exception as e:
        await message.answer(f"Error setting prize data: {e}")
        logger.error(f"Error setting prize data: {e}")

@dp.message(Command("prize_info"))
async def prize_info_command(message: types.Message):
    logger.info(f"Prize info command by user {message.from_user.id} in chat {message.chat.id}")
    
    if message.chat.id not in ALLOWED_CHATS:
        await message.answer("This chat is not authorized for giveaways.")
        return
    
    try:
        chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await message.answer("Only admins can view prize info.")
            return
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        await message.answer("Error checking admin status.")
        return
    
    args = shlex.split(message.text)[1:]
    if not args:
        await message.answer("Usage: /prize_info <contest_id>\n\nExample: /prize_info 1")
        return
    
    try:
        contest_id = int(args[0])
        
        from db import get_contest_prizes
        prize_details = await get_contest_prizes(contest_id, DB_CONFIG)
        
        if prize_details:
            message_text = f"🎁 Prize Info for Contest {contest_id}:\n\n"
            for prize in prize_details:
                position_emoji = "🥇" if prize['position'] == 1 else "🥈" if prize['position'] == 2 else "🥉" if prize['position'] == 3 else "🏆"
                message_text += f"{position_emoji} Position {prize['position']}:\n"
                message_text += f"📝 Prize: {prize['prize_name']}\n"
                message_text += f"🔗 Type: {prize['prize_type']}\n"
                message_text += f"💎 Value: {prize['prize_value']}\n\n"
        else:
            message_text = f"No prize data found for contest {contest_id}"
        
        await message.answer(message_text)
        logger.info(f"Prize info requested for contest {contest_id}")
        
    except ValueError as e:
        await message.answer(f"Invalid contest ID: {e}")
        logger.error(f"Invalid contest ID: {e}")
    except Exception as e:
        await message.answer(f"Error getting prize info: {e}")
        logger.error(f"Error getting prize info: {e}")

@dp.message(Command("help"))
async def help_command(message: types.Message):
    if message.chat.id not in ALLOWED_CHATS:
        await message.answer("This chat is not authorized for giveaways.")
        return
    
    help_text = """🤖 **Giveaway Bot Commands**

**📋 Contest Management:**
• `/create_contest <name> <duration> <winners> [prizes...] [image_url]` - Create contest
• `/start_giveaway <contest_id>` - Start giveaway
• `/contest <contest_id>` - Start contest (alias)
• `/cancel_giveaway` - Cancel active giveaway
• `/stats` - View giveaway statistics

**🎁 Prize Management:**
• `/set_prize_data <contest_id> <position> <reward_info> <data>` - Set prize data
• `/prize_info <contest_id>` - View prize information

**⏰ Duration Formats:**
• `8:46` - Specific time (Europe/Tallinn, must be in future)
• `7д` - 7 days (max 365)
• `2ч` - 2 hours (max 8760)
• `30мин` - 30 minutes (max 1440)
• `7` - 7 days (max 365)

**📸 Images:**
• Attach image to message or provide URL
• Supported: JPEG, PNG, GIF, WebP
• Max size: 20MB

**🔒 Admin Only:**
• Contest creation and management
• Prize data configuration
• Statistics viewing"""
    
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("cancel_giveaway"))
async def cancel_giveaway_command(message: types.Message):
    global participants, winners, claimed_winners, current_contest_id, giveaway_message_id, giveaway_chat_id, giveaway_has_image
    
    logger.info(f"Cancel giveaway command by user {message.from_user.id} in chat {message.chat.id}")
    
    if message.chat.id not in ALLOWED_CHATS:
        await message.answer("This chat is not authorized for giveaways.")
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
        await message.answer("No active giveaway to cancel.")
        return
    
    try:
        contest = await get_contest_by_id(current_contest_id)
        if not contest:
            await message.answer("Contest not found.")
            return
        
        cancel_text = f"Giveaway '{contest['name']}' has been cancelled.\nThank you for participating, better luck next time! 🌷"
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
        
        await message.answer(f"Giveaway '{contest['name']}' has been cancelled.")
        logger.info(f"Giveaway cancelled by user {message.from_user.id}")
    except Exception as e:
        await message.answer(f"Error cancelling giveaway: {e}")
        logger.error(f"Error cancelling giveaway: {e}")

@dp.message()
async def handle_any_message(message: types.Message):
    logger.info(f"Received message: '{message.text}' from user {message.from_user.id} in chat {message.chat.id}")
    logger.info(f"ALLOWED_CHATS: {ALLOWED_CHATS}")
    logger.info(f"Chat in whitelist: {message.chat.id in ALLOWED_CHATS}")
    
    if (not message.text or not (message.text.startswith('/claim') or message.text.startswith('/start_giveaway') or message.text.startswith('/contest') or message.text.startswith('/create_contest') or message.text.startswith('/stats') or message.text.startswith('/set_prize_data') or message.text.startswith('/prize_info') or message.text.startswith('/help') or message.text.startswith('/cancel_giveaway'))) and message.chat.id not in ALLOWED_CHATS:
        logger.warning(f"Sending backward compatibility message for chat {message.chat.id}")
        await message.answer("This chat is not authorized for giveaways.")

if __name__ == "__main__":
    async def main():   
        validate_config()
        from db import init_database
        await init_database(DB_CONFIG)
        
        await load_state_from_db()
        
        logger.info("Bot starting with restored state")
        await dp.start_polling(bot)
    
    asyncio.run(main())
