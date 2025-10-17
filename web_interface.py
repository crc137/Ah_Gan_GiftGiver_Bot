#!/usr/bin/env python3

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import asyncio
import aiomysql
import os

app = FastAPI()

DB_CONFIG = {
    'host': os.getenv("DB_HOST", ""),
    'port': int(os.getenv("DB_PORT", "")),
    'user': os.getenv("DB_USER", ""),
    'password': os.getenv("DB_PASSWORD", ""),
    'db': os.getenv("DB_NAME", ""),
    'charset': 'utf8mb4'
}

async def get_db_connection():
    return await aiomysql.connect(**DB_CONFIG)

async def get_prize_by_security_code(security_code: str):
    conn = await get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT p.name, p.description, p.prize_type, p.prize_data, 
                       pc.contest_id, pc.position, pc.winner_user_id, pc.claimed_at,
                       c.contest_name, c.group_title
                FROM prize_claims pc
                LEFT JOIN prizes p ON pc.prize_id = p.id
                LEFT JOIN contests c ON pc.contest_id = c.id
                WHERE pc.security_code = %s
            """, (security_code,))
            
            result = await cursor.fetchone()
            if result:
                return {
                    'prize_name': result[0],
                    'prize_description': result[1],
                    'prize_type': result[2],
                    'prize_data': result[3],
                    'contest_id': result[4],
                    'position': result[5],
                    'winner_user_id': result[6],
                    'claimed_at': result[7],
                    'contest_name': result[8],
                    'group_title': result[9]
                }
            return None
    finally:
        conn.close()

async def mark_prize_as_claimed(security_code: str):
    conn = await get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                UPDATE prize_claims 
                SET claimed_at = CURRENT_TIMESTAMP 
                WHERE security_code = %s AND claimed_at IS NULL
            """, (security_code,))
            
            await conn.commit()
            return cursor.rowcount > 0
    finally:
        conn.close()

@app.get("/")
async def root():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Giveaway Bot Web Interface</title>
        <meta charset="utf-8">
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: #f5f6fa;
            }
            h1 {
                color: #4b6cb7;
            }
            .desc {
                margin: 25px auto;
                max-width: 550px;
                color: #444;
            }
            .example {
                color: #111;
                background: #e1e7ed;
                padding: 15px 20px;
                border-radius: 8px;
                margin-top: 25px;
                display: inline-block;
                font-size: 1.1em;
                box-shadow: 0 2px 10px rgba(120,144,156,0.07);
            }
        </style>
    </head>
    <body>
        <h1>🎉 Giveaway Bot Prize Claim Portal</h1>
        <div class="desc">
            <p>Welcome to the Giveaway Bot web interface.</p>
            <p>If you're here to claim a prize, please visit the URL you received for your prize (it will look like <code>/&lt;security_code&gt;</code>).</p>
        </div>
        <div class="example">
            Example: <br>
            <strong>https://your-domain.com/ABC123XYZ</strong>
        </div>
        <div style="margin-top: 30px; color: #888; font-size: 0.95em;">
            <p>Powered by Giveaway Bot.</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

@app.get("/{security_code}")
async def show_prize(security_code: str):
    try:
        prize_info = await get_prize_by_security_code(security_code)
        
        if not prize_info:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Prize Not Found</title>
                <meta charset="utf-8">
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .error { color: #e74c3c; }
                </style>
            </head>
            <body>
                <h1 class="error">❌ Prize Not Found</h1>
                <p>The prize code is invalid or has expired.</p>
            </body>
            </html>
            """)
        
        if prize_info['claimed_at']:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Prize Already Claimed</title>
                <meta charset="utf-8">
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .warning { color: #f39c12; }
                </style>
            </head>
            <body>
                <h1 class="warning">⚠️ Prize Already Claimed</h1>
                <p>This prize has already been claimed.</p>
            </body>
            </html>
            """)
        
        await mark_prize_as_claimed(security_code)
        
        position = prize_info['position']
        if position == 1:
            position_emoji = "🥇"
        elif position == 2:
            position_emoji = "🥈"
        elif position == 3:
            position_emoji = "🥉"
        else:
            position_emoji = "🏅"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Congratulations!</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    margin: 0;
                    padding: 20px;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    background: white;
                    border-radius: 20px;
                    padding: 40px;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                    text-align: center;
                    max-width: 500px;
                    width: 100%;
                }}
                .emoji {{
                    font-size: 4em;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #2c3e50;
                    margin-bottom: 20px;
                }}
                .prize-info {{
                    background: #f8f9fa;
                    border-radius: 10px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .prize-data {{
                    background: #e8f5e8;
                    border: 2px solid #27ae60;
                    border-radius: 10px;
                    padding: 15px;
                    margin: 20px 0;
                    font-family: monospace;
                    white-space: pre-wrap;
                    word-break: break-all;
                }}
                .contest-info {{
                    color: #7f8c8d;
                    font-size: 0.9em;
                    margin-top: 20px;
                }}
                .copy-btn {{
                    background: #3498db;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 5px;
                    cursor: pointer;
                    font-size: 16px;
                    margin-top: 10px;
                }}
                .copy-btn:hover {{
                    background: #2980b9;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="emoji">🎉</div>
                <h1>Congratulations!</h1>
                <p>You won a prize in the contest!</p>
                
                <div class="prize-info">
                    <h2>{position_emoji} {prize_info['prize_name']}</h2>
                    <p><strong>Position:</strong> {position}st place</p>
                    <p><strong>Description:</strong> {prize_info['prize_description']}</p>
                </div>
                
                <div class="prize-data" id="prizeData">
{prize_info['prize_data']}
                </div>
                
                <button class="copy-btn" onclick="copyPrizeData()">📋 Copy Prize Data</button>
                
                <div class="contest-info">
                    <p><strong>Contest:</strong> {prize_info['contest_name']}</p>
                    <p><strong>Group:</strong> {prize_info['group_title']}</p>
                </div>
            </div>
            
            <script>
                function copyPrizeData() {{
                    const prizeData = document.getElementById('prizeData').textContent;
                    navigator.clipboard.writeText(prizeData).then(function() {{
                        alert('Prize data copied to clipboard!');
                    }});
                }}
            </script>
        </body>
        </html>
        """
        
        return HTMLResponse(html_content)
        
    except Exception as e:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .error {{ color: #e74c3c; }}
            </style>
        </head>
        <body>
            <h1 class="error">❌ Error</h1>
            <p>An error occurred: {str(e)}</p>
        </body>
        </html>
        """)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)
