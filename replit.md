# Overview

This is a Reddit to Telegram Bot built in Python that monitors specified subreddits and automatically forwards new posts to Telegram chats. The bot polls Reddit every 60 seconds for new content and sends formatted messages with post details, images, videos, and galleries to designated Telegram channels or users. It includes admin-only controls for managing subreddit subscriptions and handles NSFW content detection.

## Recent Changes (August 10, 2025)

✓ **Updated to aiogram v3**: Migrated from deprecated aiogram v2 executor to modern v3 async/await pattern
✓ **Fixed imports**: Updated ParseMode import from aiogram.enums and added Command filter
✓ **Enhanced error handling**: Improved validation and logging for API credentials
✓ **Updated README**: Added comprehensive setup instructions for Replit environment
✓ **Cleaned project structure**: Removed old attached files and consolidated to main.py
✓ **Environment template**: Created .env.template for local development setup
✓ **Added sorting functionality**: Users can now choose between new, hot, top (daily/weekly/monthly) content modes
✓ **RedGifs video download**: Bot now downloads and forwards RedGifs videos directly instead of just sending links
✓ **Enhanced media handling**: Improved video processing with size limits and fallback mechanisms

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Application Structure
The application follows a single-file architecture pattern with `main.py` serving as the entry point. This monolithic approach simplifies deployment and maintenance for a focused bot application.

## Bot Framework
Uses aiogram as the Telegram bot framework, providing async/await support for handling multiple concurrent operations. This choice enables efficient handling of both Reddit API polling and Telegram message sending without blocking operations.

## Reddit Integration
Integrates with Reddit via the PRAW (Python Reddit API Wrapper) library, which provides a clean interface to Reddit's API. The bot operates in read-only mode, focusing on content consumption rather than posting.

## Data Storage
Uses SQLite for local data persistence with a simple schema tracking:
- Subreddit names and their last processed post timestamps
- Post history to prevent duplicate forwarding

The lightweight SQLite approach fits the bot's simple data requirements without requiring a separate database server.

## Content Processing
Implements multi-content type support including:
- Text posts with HTML formatting
- Image and video content
- Gallery posts with multiple media items
- NSFW content detection and labeling

## Security Model
Employs admin-only access control using Telegram user ID verification. Only the specified admin can add/remove subreddit subscriptions, preventing unauthorized bot configuration changes.

## Polling Architecture
Uses a background polling mechanism that checks Reddit every 60 seconds for new posts. This interval balances timely content delivery with API rate limit considerations.

# External Dependencies

## Telegram Bot API
- **Service**: Telegram Bot API via aiogram library
- **Purpose**: Send messages, handle commands, and manage bot interactions
- **Authentication**: Bot token from BotFather

## Reddit API
- **Service**: Reddit API via PRAW library
- **Purpose**: Access subreddit content and post data
- **Authentication**: OAuth2 client credentials (client ID and secret)
- **Rate Limits**: Subject to Reddit's API rate limiting

## Environment Configuration
- **Service**: python-dotenv for environment variable management
- **Purpose**: Secure storage of API credentials and configuration
- **Required Variables**: TELEGRAM_TOKEN, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, ADMIN_ID

## Local Storage
- **Service**: SQLite database (data.db)
- **Purpose**: Track processed posts and subreddit configurations
- **Schema**: Simple table structure for subreddit names and timestamps