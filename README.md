<div align="center">
  <a href="https://github.com/coonlink">
    <img width="90px" src="https://raw.coonlink.com/cloud/logo.svg" alt="Ah Gan Logo" />
  </a>
  <h1>Ah Gan GiftGiver Bot</h1>

<img alt="last-commit" src="https://img.shields.io/github/last-commit/crc137/Ah_Gan_GiftGiver_Bot?style=flat&amp;logo=git&amp;logoColor=white&amp;color=0080ff" style="margin: 0px 2px;">
<img alt="repo-top-language" src="https://img.shields.io/github/languages/top/crc137/Ah_Gan_GiftGiver_Bot?style=flat&amp;color=0080ff" style="margin: 0px 2px;">
<img alt="repo-language-count" src="https://img.shields.io/github/languages/count/crc137/Ah_Gan_GiftGiver_Bot?style=flat&amp;color=0080ff" style="margin: 0px 2px;">
<img alt="version" src="https://img.shields.io/badge/version-1.0.0-blue" style="margin: 0px 2px;">

</div>

<br />

<div align="center">
  <p>A Telegram bot designed for managing giveaways and contests in group chats. It allows admins to create contests, start giveaways, track participants, automatically select winners after a specified duration, and handle prize claims. The bot uses a MySQL database for persistent storage of contest data, prizes, and giveaway state.</p>
</div>

## Features

- **Contest Creation**: Admins can create contests with customizable names, durations, number of winners, prizes, and optional images.
- **Giveaway Management**: Start giveaways in whitelisted chats, with users joining via an inline button.
- **Automatic Winner Selection**: Giveaways end automatically after the set duration, with winners chosen randomly from participants.
- **Prize Claiming**: Winners can claim prizes using a `/claim` command, with security codes for verification.
- **Admin Tools**: View stats, cancel ongoing giveaways, list contests, and manage prizes.
- **Persistence**: State (participants, winners, etc.) is saved to a MySQL database for reliability across restarts.
- **Security**: Restricted to whitelisted chats and admin-only commands for sensitive operations.
- **Image Support**: Attach images to contests for visual appeal in giveaway messages.
- **Flexible Durations**: Supports various duration formats (e.g., days, hours, minutes, months, or specific end times).

## Requirements

- Python 3.8+
- MySQL database
- Dependencies (from `requirements.txt`):
  - aiogram
  - aiomysql
  - aiohttp
  - python-dotenv

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/crc137/Ah_Gan_GiftGiver_Bot.git
   cd Ah_Gan_GiftGiver_Bot
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up the MySQL database:
   - Create a database and user with appropriate permissions.
   - The bot will automatically initialize tables on startup (contests, prizes, giveaway_state).

## Configuration

1. Copy the example environment file:
   ```
   cp .env.example .env
   ```

2. Edit `.env` with your details:
   ```
   # Telegram Bot Configuration
   TELEGRAM_TOKEN=your_bot_token_here  # From @BotFather
   GROUP_ID=your_group_id_here  # Main group ID (integer)

   # Database Configuration
   DB_HOST=your_database_host
   DB_PORT=3306
   DB_USER=your_database_user
   DB_PASSWORD=your_database_password
   DB_NAME=your_database_name

   # Allowed Chats (comma-separated chat IDs)
   ALLOWED_CHATS=chat_id1,chat_id2,chat_id3  # Chats where the bot can operate
   ```

## Usage

1. Run the bot:
   ```
   python3 giveaway_bot.py
   ```

2. In a whitelisted Telegram chat:
   - Use admin commands to create and manage contests.
   - Users interact via inline buttons or the `/claim` command.

### Available Commands

- `/create_contest <name> <duration> <winners_count> [prizes...]`: Create a new contest. Attach an image to the message for visual giveaway posts.
  - Duration examples: `7д` (7 days), `2ч` (2 hours), `30мин` (30 minutes), `1м` (1 month), `14:30` (specific time today/tomorrow), or `7` (7 days auto).
- `/start_giveaway <contest_id>`: Start a giveaway based on an existing contest.
- `/list_contests`: List all created contests with IDs.
- `/stats`: View stats for the active giveaway (admin only).
- `/cancel_giveaway`: Cancel the active giveaway (admin only).
- `/claim`: Claim a prize if you're a winner (private message to the bot).

### How Giveaways Work

1. Admin creates a contest with `/create_contest`.
2. Admin starts the giveaway with `/start_giveaway <id>`.
3. Users join by tapping the "🎁 Join" button on the giveaway message.
4. After the duration ends, winners are selected randomly and notified.
5. Winners use `/claim` in private chat with the bot to receive prize details.

## Database Schema

The bot uses three main tables in MySQL:

- **contests**:
  - `id` (PK, auto-increment)
  - `contest_name` (VARCHAR)
  - `duration` (INT, seconds)
  - `winners_count` (INT)
  - `prizes` (TEXT, comma-separated)
  - `image_url` (VARCHAR)
  - `created_at` (TIMESTAMP)

- **prizes**:
  - `id` (PK, auto-increment)
  - `contest_id` (FK to contests)
  - `position` (INT)
  - `reward_info` (VARCHAR)
  - `data` (TEXT)
  - `winner_user_id` (BIGINT)
  - `claimed_at` (TIMESTAMP)
  - `security_code` (VARCHAR)
  - `created_at` (TIMESTAMP)

- **giveaway_state**:
  - `id` (PK, auto-increment)
  - `participants` (TEXT, JSON)
  - `winners` (TEXT, JSON)
  - `claimed_winners` (TEXT, JSON)
  - `giveaway_message_id` (BIGINT)
  - `giveaway_chat_id` (BIGINT)
  - `giveaway_has_image` (BOOLEAN)
  - `current_contest_id` (INT)
  - `updated_at` (TIMESTAMP)

## Deployment

- **Local/VM**: Run `python3 giveaway_bot.py` as a background process (e.g., via `screen`, `tmux`, or systemd).
- **Heroku**: Use the provided `Procfile` for deployment. Set environment variables in Heroku settings. Note: The bot uses long polling, so ensure the dyno doesn't sleep (free dynos may have limitations).
  - Push to Heroku: `git push heroku main`
  - Scale: `heroku ps:scale web=1`

## Logging

Logs are written to `logs/giveaway_bot.log` and stdout. Level: INFO.

## Contributing

Contributions are welcome! Please fork the repo, create a feature branch, and submit a pull request. Ensure code follows PEP8 and includes tests where possible.

## License

MIT © [Coonlink](https://coonlink.com)
