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

## Contributing

Contributions are welcome! Please fork the repo, create a feature branch, and submit a pull request. Ensure code follows PEP8 and includes tests where possible.

## License

MIT © [Coonlink](https://coonlink.com)
