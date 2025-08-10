import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ParseMode
from dotenv import load_dotenv
import praw

load_dotenv()

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("TELEGRAM_TOKEN")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = "TelegramRedditBot by /u/yourusername"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Your Telegram ID here

if not API_TOKEN or not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET or ADMIN_ID == 0:
    raise ValueError("Missing required environment variables!")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Initialize Reddit API client
reddit = praw.Reddit(client_id=REDDIT_CLIENT_ID,
                     client_secret=REDDIT_CLIENT_SECRET,
                     user_agent=REDDIT_USER_AGENT)

# SQLite DB for storing subreddits and last post time
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    """CREATE TABLE IF NOT EXISTS subreddits (
        name TEXT PRIMARY KEY,
        last_post INTEGER
    )"""
)
conn.commit()


async def send_post(post: praw.models.Submission):
    chat_id = ADMIN_ID
    title = post.title
    url = post.url
    nsfw = post.over_18
    post_url = f"https://reddit.com{post.permalink}"
    created = datetime.fromtimestamp(post.created_utc).strftime("%Y-%m-%d %H:%M:%S")

    prefix = "[NSFW]\n" if nsfw else ""
    text = f"{prefix}<b>{title}</b>\n\n"
    if post.selftext:
        text += f"{post.selftext}\n\n"
    text += f"🔗 <a href='{post_url}'>Reddit Link</a>\n"
    text += f"🕒 {created}\n"

    try:
        if post.is_self:
            await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        elif any(post.url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"]):
            await bot.send_photo(chat_id, post.url, caption=text, parse_mode=ParseMode.HTML)
        elif "v.redd.it" in post.url or post.is_video:
            video_url = None
            try:
                video_url = post.media["reddit_video"]["fallback_url"]
            except Exception:
                video_url = None
            if video_url:
                await bot.send_message(chat_id, text + f"\n📹 [Video Link]({video_url})", parse_mode=ParseMode.HTML)
            else:
                await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        elif post.is_gallery:
            media_items = []
            for item in post.gallery_data["items"]:
                media_id = item["media_id"]
                media_metadata = post.media_metadata[media_id]
                if media_metadata["e"] == "Image":
                    img_url = media_metadata["s"]["u"].replace("&amp;", "&")
                    media_items.append(types.InputMediaPhoto(media=img_url))
            if media_items:
                await bot.send_media_group(chat_id, media_items)
                await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
            else:
                await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(chat_id, text + f"\n🔗 {url}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Failed to send post {post.id}: {e}")


async def poll_subreddit(subreddit_name: str):
    cursor.execute("SELECT last_post FROM subreddits WHERE name=?", (subreddit_name,))
    row = cursor.fetchone()
    last_post_time = row[0] if row else None
    try:
        subreddit = reddit.subreddit(subreddit_name)
        new_posts = subreddit.new(limit=10)
        new_posts_list = []
        for post in new_posts:
            created = int(post.created_utc)
            if last_post_time is None or created > int(last_post_time):
                new_posts_list.append(post)
        if new_posts_list:
            new_posts_list.reverse()  # send oldest first
            for post in new_posts_list:
                await send_post(post)
            newest_post = max(int(post.created_utc) for post in new_posts_list)
            cursor.execute("INSERT OR REPLACE INTO subreddits(name, last_post) VALUES (?, ?)",
                           (subreddit_name, newest_post))
            conn.commit()
    except Exception as e:
        logging.error(f"Error polling subreddit {subreddit_name}: {e}")


async def polling_loop():
    while True:
        cursor.execute("SELECT name FROM subreddits")
        subs = cursor.fetchall()
        for (sub,) in subs:
            await poll_subreddit(sub)
        await asyncio.sleep(60)


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.reply("Hello! Send /add subreddit to subscribe.\nUse /list to see your subscriptions.")


@dp.message_handler(commands=["add"])
async def cmd_add(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("You are not authorized.")
        return
    args = message.get_args().strip().lower()
    if not args:
        await message.reply("Usage: /add subreddit_name")
        return
    subreddit = args
    cursor.execute("SELECT name FROM subreddits WHERE name=?", (subreddit,))
    if cursor.fetchone():
        await message.reply(f"Already subscribed to r/{subreddit}")
        return
    try:
        result = reddit.subreddits.search_by_name(subreddit, exact=True)
        if not result:
            await message.reply("Subreddit not found.")
            return
        cursor.execute("INSERT INTO subreddits(name, last_post) VALUES (?, ?)", (subreddit, 0))
        conn.commit()
        await message.reply(f"Subscribed to r/{subreddit}")
    except Exception as e:
        logging.error(f"Error adding subreddit {subreddit}: {e}")
        await message.reply("Subreddit not found or Reddit API error.")


@dp.message_handler(commands=["remove"])
async def cmd_remove(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("You are not authorized.")
        return
    args = message.get_args().strip().lower()
    if not args:
        await message.reply("Usage: /remove subreddit_name")
        return
    subreddit = args
    cursor.execute("DELETE FROM subreddits WHERE name=?", (subreddit,))
    conn.commit()
    await message.reply(f"Unsubscribed from r/{subreddit}")


@dp.message_handler(commands=["list"])
async def cmd_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("You are not authorized.")
        return
    cursor.execute("SELECT name FROM subreddits")
    subs = cursor.fetchall()
    if not subs:
        await message.reply("No subscriptions yet.")
        return
    text = "Subscribed subreddits:\n" + "\n".join(f"r/{sub[0]}" for sub in subs)
    await message.reply(text)


async def on_startup(dispatcher):
    asyncio.create_task(polling_loop())


if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)
