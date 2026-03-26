"""Helper to configure a Telegram bot for Resell Bot notifications.

Usage:
    python scripts/setup_telegram.py

Steps:
1. Create a bot via @BotFather on Telegram → gives you the token
2. Send a message to your bot
3. Run this script with your token to get the chat_id
4. Copy both to your .env file
"""

import sys

import httpx


def main() -> None:
    print("=== Resell Bot — Telegram Setup ===\n")
    token = input("Paste your bot token (from @BotFather): ").strip()

    if not token:
        print("Error: token cannot be empty.")
        sys.exit(1)

    print("\nFetching updates from Telegram API...")
    url = f"https://api.telegram.org/bot{token}/getUpdates"

    try:
        resp = httpx.get(url, timeout=10)
        data = resp.json()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    if not data.get("ok"):
        print(f"API error: {data}")
        sys.exit(1)

    results = data.get("result", [])
    if not results:
        print("\nNo messages found. Make sure you've sent at least one message to your bot first!")
        print("1. Open Telegram")
        print("2. Find your bot and send any message (e.g. 'hello')")
        print("3. Re-run this script")
        sys.exit(0)

    # Extract unique chat IDs
    chats: dict[int, str] = {}
    for update in results:
        msg = update.get("message", {})
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        chat_name = chat.get("first_name", "") + " " + chat.get("last_name", "")
        if chat_id:
            chats[chat_id] = chat_name.strip()

    print(f"\nFound {len(chats)} chat(s):\n")
    for cid, name in chats.items():
        print(f"  Chat ID: {cid}  ({name})")

    print("\n--- Add these to your .env file ---")
    print(f"TELEGRAM_BOT_TOKEN={token}")
    if len(chats) == 1:
        cid = next(iter(chats))
        print(f"TELEGRAM_CHAT_ID={cid}")
    else:
        print("TELEGRAM_CHAT_ID=<pick one from above>")

    print("\nDone!")


if __name__ == "__main__":
    main()
