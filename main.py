import subprocess
import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yt_dlp import YoutubeDL

# Load environment variables from .env file first
load_dotenv()

# Get token from environment variable
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Check if token is available
if not TOKEN:
    print("❌ ERROR: TELEGRAM_BOT_TOKEN not found in environment variables!")
    print("Please create a .env file with: TELEGRAM_BOT_TOKEN=your_bot_token_here")
    exit(1)

print(f"✅ Bot token loaded successfully! Starting bot...")

DOWNLOAD_FOLDER = './downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store user choices temporarily
user_choices = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        '🎵 **YouTube Video Downloader** 🎵\n\n'
        'Send me a YouTube link and choose your preferred quality!\n\n'
        '**Features:**\n'
        '• 🎧 MP3 Audio (320kbps)\n'
        '• 📱 360p Video\n'
        '• 💻 720p Video\n'
        '• 🖥️ 1080p Video\n'
        '• ⚡ Best Quality Available\n\n'
        'Just send a YouTube URL to get started!',
        parse_mode='Markdown'
    )

def create_quality_keyboard():
    """Create inline keyboard for quality selection"""
    keyboard = [
        [
            InlineKeyboardButton("🎧 MP3 Audio", callback_data="quality_audio"),
            InlineKeyboardButton("📱 360p", callback_data="quality_360p"),
        ],
        [
            InlineKeyboardButton("💻 720p", callback_data="quality_720p"),
            InlineKeyboardButton("🖥️ 1080p", callback_data="quality_1080p"),
        ],
        [
            InlineKeyboardButton("⚡ Best Quality", callback_data="quality_best"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle YouTube URL and show quality options"""
    chat_id = update.message.chat_id
    youtube_url = update.message.text
    
    # Validate YouTube URL
    if not ('youtube.com' in youtube_url or 'youtu.be' in youtube_url):
        await update.message.reply_text("❌ Please provide a valid YouTube link.")
        return
    
    try:
        # Store the URL for this user
        user_choices[chat_id] = {'url': youtube_url}
        
        # Get video info for preview
        ydl_opts = {'quiet': True}
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(youtube_url, download=False)
            title = info_dict.get('title', 'Unknown Title')
            duration = info_dict.get('duration', 0)
        
        # Format duration
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            duration_str = f"{minutes}:{seconds:02d}"
        
        # Send video info with quality options
        message = (
            f"🎬 **{title}**\n"
            f"⏱️ Duration: {duration_str}\n\n"
            f"**Select download quality:**"
        )
        
        await update.message.reply_text(
            message,
            reply_markup=create_quality_keyboard(),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logging.error(f"Error processing YouTube link: {e}")
        await update.message.reply_text("❌ Error processing YouTube link. Please try again.")

async def handle_quality_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle quality selection from inline keyboard"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    quality = query.data.replace('quality_', '')
    
    # Get stored URL for this user
    if chat_id not in user_choices or 'url' not in user_choices[chat_id]:
        await query.edit_message_text("❌ Session expired. Please send the YouTube link again.")
        return
    
    youtube_url = user_choices[chat_id]['url']
    
    # Update message to show processing
    quality_names = {
        'audio': '🎧 MP3 Audio',
        '360p': '📱 360p',
        '720p': '💻 720p',
        '1080p': '🖥️ 1080p',
        'best': '⚡ Best Quality'
    }
    
    await query.edit_message_text(
        f"⏳ Downloading in **{quality_names[quality]}**...\nPlease wait, this may take a while.",
        parse_mode='Markdown'
    )
    
    # Download based on selected quality
    try:
        file_path = await download_media(youtube_url, quality, chat_id)
        
        if quality == 'audio':
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=open(file_path, 'rb'),
                caption=f"✅ Download complete! 🎧"
            )
        else:
            await context.bot.send_video(
                chat_id=chat_id,
                video=open(file_path, 'rb'),
                caption=f"✅ Download complete! 🎬",
                supports_streaming=True
            )
        
        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Clear user choice
        if chat_id in user_choices:
            del user_choices[chat_id]
            
    except Exception as e:
        logging.error(f"Error downloading media: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Error downloading media. Please try again with a different quality or check the URL."
        )

async def download_media(url: str, quality: str, chat_id: int) -> str:
    """Download media based on selected quality"""
    
    quality_map = {
        'audio': {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]
        },
        '360p': {
            'format': 'best[height<=360]',
        },
        '720p': {
            'format': 'best[height<=720]',
        },
        '1080p': {
            'format': 'best[height<=1080]',
        },
        'best': {
            'format': 'best',
        }
    }
    
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title).100s.%(ext)s'),
        'noplaylist': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'quiet': False,
    }
    
    # Merge quality-specific options
    ydl_opts.update(quality_map[quality])
    
    with YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        
        if quality == 'audio':
            # For audio, return the MP3 file path
            file_path = ydl.prepare_filename(info_dict)
            file_path = file_path.replace('.webm', '.mp3').replace('.m4a', '.mp3')
        else:
            # For video, return the original file path
            file_path = ydl.prepare_filename(info_dict)
        
        return file_path

async def handle_unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle non-YouTube messages"""
    await update.message.reply_text(
        "🤖 I only process YouTube links!\n\n"
        "Please send a valid YouTube URL to download media."
    )

def main() -> None:
    try:
        application = ApplicationBuilder().token(TOKEN).build()

        # Register handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)') & ~filters.COMMAND, 
            handle_youtube_url
        ))
        application.add_handler(CallbackQueryHandler(handle_quality_selection, pattern="^quality_"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_message))

        print("🤖 Bot is starting...")
        # Start the Bot
        application.run_polling()
        
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        print(f"❌ Bot failed to start: {e}")

if __name__ == '__main__':
    main()
