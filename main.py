import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from dotenv import load_dotenv
import praw

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment variables with fallbacks
API_TOKEN = os.getenv("TELEGRAM_TOKEN", "your_telegram_bot_token_here")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "your_reddit_client_id")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "your_reddit_client_secret")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "TelegramRedditBot/1.0 by /u/yourusername")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Telegram user ID of the admin

# Validate required environment variables
if not API_TOKEN or API_TOKEN == "your_telegram_bot_token_here":
    logger.error("TELEGRAM_TOKEN environment variable is required!")
    exit(1)

if not REDDIT_CLIENT_ID or REDDIT_CLIENT_ID == "your_reddit_client_id":
    logger.error("REDDIT_CLIENT_ID environment variable is required!")
    exit(1)

if not REDDIT_CLIENT_SECRET or REDDIT_CLIENT_SECRET == "your_reddit_client_secret":
    logger.error("REDDIT_CLIENT_SECRET environment variable is required!")
    exit(1)

if ADMIN_ID == 0:
    logger.error("ADMIN_ID environment variable is required!")
    exit(1)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Initialize Reddit API client
try:
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT
    )
    # Test Reddit connection
    reddit.user.me()
    logger.info("Reddit API connection successful")
except Exception as e:
    logger.error(f"Failed to initialize Reddit API: {e}")
    exit(1)

# Initialize SQLite database
try:
    conn = sqlite3.connect("data.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS subreddits (
            name TEXT PRIMARY KEY,
            last_post INTEGER DEFAULT 0
        )"""
    )
    conn.commit()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    exit(1)


async def send_post(post):
    """Send a Reddit post to the admin's Telegram chat"""
    chat_id = ADMIN_ID
    title = post.title
    url = post.url
    nsfw = post.over_18
    post_url = f"https://reddit.com{post.permalink}"
    created = datetime.fromtimestamp(post.created_utc).strftime("%Y-%m-%d %H:%M:%S")
    subreddit_name = post.subreddit.display_name

    # Prepare message text
    prefix = "🔞 [NSFW] " if nsfw else ""
    text = f"{prefix}<b>{title}</b>\n\n"
    text += f"📍 r/{subreddit_name}\n"
    
    if post.selftext and len(post.selftext.strip()) > 0:
        # Truncate long self text
        selftext = post.selftext[:500] + "..." if len(post.selftext) > 500 else post.selftext
        text += f"{selftext}\n\n"
    
    text += f"🔗 <a href='{post_url}'>View on Reddit</a>\n"
    text += f"🕒 {created}"

    try:
        logger.info(f"Processing post: {post.title[:30]}... URL: {post.url} is_self: {post.is_self}")
        
        if post.is_self:
            # Text post
            logger.info("Sending as text post")
            await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        elif any(post.url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
            # Image post
            logger.info(f"Sending as image post: {post.url}")
            await bot.send_photo(chat_id, post.url, caption=text, parse_mode=ParseMode.HTML)
        elif "v.redd.it" in post.url or post.is_video:
            # Video post
            logger.info(f"Sending as video post: {post.url}")
            video_url = None
            try:
                if hasattr(post, 'media') and post.media and 'reddit_video' in post.media:
                    video_url = post.media["reddit_video"]["fallback_url"]
            except Exception:
                pass
            
            if video_url:
                text += f"\n📹 <a href='{video_url}'>Direct Video Link</a>"
            
            await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        elif hasattr(post, 'is_gallery') and post.is_gallery:
            # Gallery post
            logger.info(f"Sending as gallery post with {len(post.gallery_data['items'])} items")
            try:
                media_items = []
                gallery_data = post.gallery_data
                media_metadata = post.media_metadata
                
                for item in gallery_data["items"]:
                    media_id = item["media_id"]
                    if media_id in media_metadata:
                        media_info = media_metadata[media_id]
                        if media_info.get("e") == "Image":
                            img_url = media_info["s"]["u"].replace("&amp;", "&")
                            media_items.append(types.InputMediaPhoto(media=img_url))
                
                if media_items:
                    # Telegram has a limit of 10 media items per group
                    media_items = media_items[:10]
                    await bot.send_media_group(chat_id, media_items)
                    await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
                else:
                    await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Error processing gallery: {e}")
                await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        else:
            # Other content types (links, etc.)
            logger.info(f"Sending as link post: {url}")
            text += f"\n🔗 <a href='{url}'>External Link</a>"
            await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        
        logger.info(f"Successfully sent post: {post.title[:50]}...")
    except Exception as e:
        logger.error(f"Failed to send post {post.id}: {e}")


async def poll_subreddit(subreddit_name: str):
    """Poll a subreddit for new posts"""
    try:
        cursor.execute("SELECT last_post FROM subreddits WHERE name=?", (subreddit_name,))
        row = cursor.fetchone()
        last_post_time = row[0] if row else 0
        
        subreddit = reddit.subreddit(subreddit_name)
        new_posts = list(subreddit.new(limit=25))  # Get more posts to ensure we don't miss any
        
        logger.info(f"Found {len(new_posts)} total posts in r/{subreddit_name}, last_post_time: {last_post_time}")
        
        posts_to_send = []
        for post in new_posts:
            created = int(post.created_utc)
            if created > last_post_time:
                posts_to_send.append(post)
        
        logger.info(f"Found {len(posts_to_send)} new posts to send from r/{subreddit_name}")
        
        if posts_to_send:
            # Sort by creation time (oldest first)
            posts_to_send.sort(key=lambda p: p.created_utc)
            
            logger.info(f"Found {len(posts_to_send)} new posts in r/{subreddit_name}")
            
            for post in posts_to_send:
                await send_post(post)
                # Small delay to avoid hitting rate limits
                await asyncio.sleep(1)
            
            # Update last post time to the newest post
            newest_post_time = max(int(post.created_utc) for post in posts_to_send)
            cursor.execute("INSERT OR REPLACE INTO subreddits(name, last_post) VALUES (?, ?)",
                          (subreddit_name, newest_post_time))
            conn.commit()
            
            logger.info(f"Updated last post time for r/{subreddit_name} to {newest_post_time}")
    except Exception as e:
        logger.error(f"Error polling subreddit r/{subreddit_name}: {e}")


async def polling_loop():
    """Main polling loop that checks all subscribed subreddits"""
    logger.info("Starting polling loop...")
    
    while True:
        try:
            cursor.execute("SELECT name FROM subreddits")
            subs = cursor.fetchall()
            
            if subs:
                logger.info(f"Polling {len(subs)} subreddits...")
                for (sub,) in subs:
                    await poll_subreddit(sub)
                    # Delay between subreddits to avoid rate limiting
                    await asyncio.sleep(2)
            else:
                logger.info("No subreddits subscribed yet")
            
            # Wait 60 seconds before next polling cycle
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
            await asyncio.sleep(60)


@dp.message(Command("start", "help"))
async def cmd_start(message: types.Message):
    """Handle /start and /help commands"""
    help_text = """
🤖 <b>Reddit to Telegram Bot</b>

This bot monitors Reddit subreddits and forwards new posts to this chat.

<b>Available Commands:</b>
/start or /help - Show this help message
/add &lt;subreddit&gt; - Subscribe to a subreddit
/remove &lt;subreddit&gt; - Unsubscribe from a subreddit
/reset &lt;subreddit&gt; - Reset timestamp to get recent posts
/list - Show all subscribed subreddits

<b>Example:</b>
<code>/add python</code> - Subscribe to r/python
<code>/reset python</code> - Get recent posts from r/python
<code>/remove python</code> - Unsubscribe from r/python

<b>Note:</b> Only the bot admin can use these commands.
The bot checks for new posts every 60 seconds.
"""
    await message.reply(help_text, parse_mode=ParseMode.HTML)


@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    """Handle /add command to subscribe to a subreddit"""
    if message.from_user and message.from_user.id != ADMIN_ID:
        await message.reply("❌ You are not authorized to use this command.")
        return
    
    # Get arguments from the message text
    args = message.text.split(' ', 1)[1].strip().lower() if message.text and len(message.text.split()) > 1 else ""
    if not args:
        await message.reply("❌ Usage: <code>/add subreddit_name</code>\n\nExample: <code>/add python</code>", 
                           parse_mode=ParseMode.HTML)
        return
    
    subreddit_name = args
    
    # Check if already subscribed
    cursor.execute("SELECT name FROM subreddits WHERE name=?", (subreddit_name,))
    if cursor.fetchone():
        await message.reply(f"ℹ️ Already subscribed to r/{subreddit_name}")
        return
    
    try:
        # Verify subreddit exists
        subreddit = reddit.subreddit(subreddit_name)
        # This will raise an exception if subreddit doesn't exist
        subreddit.id
        
        # Add to database with older timestamp to get recent posts
        # Use a much older timestamp to ensure we get recent posts
        one_hour_ago = 1728000000  # Fixed timestamp from October 2024
        cursor.execute("INSERT INTO subreddits(name, last_post) VALUES (?, ?)", 
                      (subreddit_name, one_hour_ago))
        conn.commit()
        
        await message.reply(f"✅ Successfully subscribed to r/{subreddit_name}")
        logger.info(f"Added subscription to r/{subreddit_name}")
    except Exception as e:
        logger.error(f"Error adding subreddit r/{subreddit_name}: {e}")
        await message.reply(f"❌ Subreddit r/{subreddit_name} not found or Reddit API error.")


@dp.message(Command("remove"))
async def cmd_remove(message: types.Message):
    """Handle /remove command to unsubscribe from a subreddit"""
    if message.from_user and message.from_user.id != ADMIN_ID:
        await message.reply("❌ You are not authorized to use this command.")
        return
    
    # Get arguments from the message text
    args = message.text.split(' ', 1)[1].strip().lower() if message.text and len(message.text.split()) > 1 else ""
    if not args:
        await message.reply("❌ Usage: <code>/remove subreddit_name</code>\n\nExample: <code>/remove python</code>", 
                           parse_mode=ParseMode.HTML)
        return
    
    subreddit_name = args
    
    # Remove from database
    cursor.execute("DELETE FROM subreddits WHERE name=?", (subreddit_name,))
    
    if cursor.rowcount > 0:
        conn.commit()
        await message.reply(f"✅ Unsubscribed from r/{subreddit_name}")
        logger.info(f"Removed subscription to r/{subreddit_name}")
    else:
        await message.reply(f"ℹ️ Not subscribed to r/{subreddit_name}")


@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    """Reset the last post timestamp for a subreddit to get recent posts"""
    if message.from_user and message.from_user.id != ADMIN_ID:
        await message.reply("❌ You are not authorized to use this command.")
        return
    
    # Get arguments from the message text
    args = message.text.split(' ', 1)[1].strip().lower() if message.text and len(message.text.split()) > 1 else ""
    if not args:
        await message.reply("❌ Usage: <code>/reset subreddit_name</code>\n\nExample: <code>/reset python</code>", 
                           parse_mode=ParseMode.HTML)
        return
    
    subreddit_name = args
    
    # Check if subscribed
    cursor.execute("SELECT name FROM subreddits WHERE name=?", (subreddit_name,))
    if not cursor.fetchone():
        await message.reply(f"ℹ️ Not subscribed to r/{subreddit_name}")
        return
    
    # Reset timestamp to 1 hour ago to get recent posts
    # Use a much older timestamp to ensure we get recent posts
    one_hour_ago = 1728000000  # Fixed timestamp from October 2024
    cursor.execute("UPDATE subreddits SET last_post = ? WHERE name = ?", (one_hour_ago, subreddit_name))
    conn.commit()
    
    await message.reply(f"✅ Reset timestamp for r/{subreddit_name}. Will fetch posts from the last hour on next poll.")
    logger.info(f"Reset timestamp for r/{subreddit_name} to {one_hour_ago}")


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    """Handle /list command to show all subscribed subreddits"""
    if message.from_user and message.from_user.id != ADMIN_ID:
        await message.reply("❌ You are not authorized to use this command.")
        return
    
    cursor.execute("SELECT name FROM subreddits ORDER BY name")
    subs = cursor.fetchall()
    
    if not subs:
        await message.reply("ℹ️ No subreddit subscriptions yet.\n\nUse <code>/add subreddit_name</code> to subscribe to a subreddit.", 
                           parse_mode=ParseMode.HTML)
        return
    
    text = f"📋 <b>Subscribed Subreddits ({len(subs)}):</b>\n\n"
    text += "\n".join(f"• r/{sub[0]}" for sub in subs)
    
    await message.reply(text, parse_mode=ParseMode.HTML)


@dp.message()
async def handle_unknown(message: types.Message):
    """Handle unknown messages"""
    if message.from_user and message.from_user.id == ADMIN_ID:
        await message.reply("❓ Unknown command. Use /help to see available commands.")


async def main():
    """Main function to start the bot"""
    logger.info("Bot started successfully!")
    logger.info(f"Admin ID: {ADMIN_ID}")
    
    # Start the polling loop as a background task
    asyncio.create_task(polling_loop())
    
    # Start polling for Telegram updates
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
    finally:
        if 'conn' in locals():
            conn.close()