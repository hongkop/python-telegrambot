import subprocess
import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yt_dlp import YoutubeDL

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    print("❌ ERROR: TELEGRAM_BOT_TOKEN not found!")
    exit(1)

print("✅ Bot token loaded! Starting...")

DOWNLOAD_FOLDER = './downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Changed to DEBUG for more details
)
logger = logging.getLogger(__name__)

user_choices = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        '🎵 **YouTube Downloader** 🎵\n\n'
        'Send YouTube link and choose quality:\n\n'
        '**Options:**\n'
        '• 🎧 MP3 Audio (Fast & Recommended)\n'
        '• 📱 360p Video\n' 
        '• 💻 720p Video\n'
        '• 🖥️ 1080p Video\n'
        '• ⚡ Best Quality\n\n'
        'Server: 8GB RAM ✅',
        parse_mode='Markdown'
    )

def create_quality_keyboard():
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
    chat_id = update.message.chat_id
    youtube_url = update.message.text
    
    if not ('youtube.com' in youtube_url or 'youtu.be' in youtube_url):
        await update.message.reply_text("❌ Please provide valid YouTube link.")
        return
    
    try:
        user_choices[chat_id] = {'url': youtube_url}
        
        # Get video info
        ydl_opts = {
            'quiet': True,
            'no_warnings': True
        }
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
        
        message = (
            f"🎬 **{title}**\n"
            f"⏱️ Duration: {duration_str}\n\n"
            f"**Select quality:**"
        )
        
        await update.message.reply_text(
            message,
            reply_markup=create_quality_keyboard(),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error processing URL: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_quality_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    quality = query.data.replace('quality_', '')
    
    if chat_id not in user_choices or 'url' not in user_choices[chat_id]:
        await query.edit_message_text("❌ Session expired. Send link again.")
        return
    
    youtube_url = user_choices[chat_id]['url']
    
    quality_names = {
        'audio': '🎧 MP3 Audio',
        '360p': '📱 360p', 
        '720p': '💻 720p',
        '1080p': '🖥️ 1080p',
        'best': '⚡ Best Quality'
    }
    
    await query.edit_message_text(
        f"⏳ Downloading **{quality_names[quality]}**...\nPlease wait ⏰",
        parse_mode='Markdown'
    )
    
    try:
        # Download with timeout
        file_path = await asyncio.wait_for(
            download_media(youtube_url, quality, chat_id),
            timeout=300  # 5 minutes timeout
        )
        
        # Check file size
        file_size = os.path.getsize(file_path)
        logger.info(f"File size: {file_size / 1024 / 1024:.2f} MB")
        
        if quality == 'audio':
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=open(file_path, 'rb'),
                caption="✅ Download complete! 🎧"
            )
        else:
            await context.bot.send_video(
                chat_id=chat_id,
                video=open(file_path, 'rb'),
                caption="✅ Download complete! 🎬",
                supports_streaming=True
            )
        
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
        
        if chat_id in user_choices:
            del user_choices[chat_id]
            
    except asyncio.TimeoutError:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Download timeout! Video too long or server busy."
        )
    except Exception as e:
        logger.error(f"Download error: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Download failed: {str(e)}"
        )

async def download_media(url: str, quality: str, chat_id: int) -> str:
    """Download media with optimized settings"""
    
    quality_map = {
        'audio': {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        },
        '360p': {
            'format': 'best[height<=360]/best[height<=480]',
        },
        '720p': {
            'format': 'best[height<=720]/best[height<=480]',
        },
        '1080p': {
            'format': 'best[height<=1080]/best[height<=720]',
        },
        'best': {
            'format': 'best[height<=1080]/best',
        }
    }
    
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title).80s.%(ext)s'),
        'noplaylist': True,
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 3,
        'continue_dl': True,
        'noprogress': True,
        'quiet': False,  # Show logs for debugging
        'no_warnings': False,
    }
    
    # Merge quality options
    ydl_opts.update(quality_map[quality])
    
    logger.info(f"Starting download: {quality} - {url}")
    
    with YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info_dict)
        
        if quality == 'audio':
            file_path = file_path.replace('.webm', '.mp3').replace('.m4a', '.mp3')
        
        logger.info(f"Download completed: {file_path}")
        return file_path

async def handle_unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🤖 Send YouTube URL only!")

def main() -> None:
    try:
        application = ApplicationBuilder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)') & ~filters.COMMAND, 
            handle_youtube_url
        ))
        application.add_handler(CallbackQueryHandler(handle_quality_selection, pattern="^quality_"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_message))

        print("🤖 Bot starting with 8GB RAM support...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Bot failed: {e}")

if __name__ == '__main__':
    main()
