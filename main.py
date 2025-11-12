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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
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
        '• ⚡ Best Available Quality\n\n'
        '✅ Fixed YouTube blocking issue',
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
            InlineKeyboardButton("⚡ Best", callback_data="quality_best"),
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
        
        # Get video info with anti-bot measures
        ydl_opts = {
            'quiet': True,
            'no_warnings': False,
            'extract_flat': False,
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
        await update.message.reply_text("❌ Cannot access this video. Try another URL.")

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
        'best': '⚡ Best Quality'
    }
    
    await query.edit_message_text(
        f"⏳ Downloading **{quality_names[quality]}**...\nPlease wait ⏰",
        parse_mode='Markdown'
    )
    
    try:
        file_path = await asyncio.wait_for(
            download_media(youtube_url, quality, chat_id),
            timeout=300
        )
        
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
            text="❌ Download timeout! Video too long."
        )
    except Exception as e:
        logger.error(f"Download error: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Download failed. YouTube is blocking this video. Try another video."
        )

async def download_media(url: str, quality: str, chat_id: int) -> str:
    """Download media with anti-bot measures"""
    
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
            'format': 'best[height<=360]',
        },
        '720p': {
            'format': 'best[height<=720]',
        },
        'best': {
            'format': 'best',
        }
    }
    
    # Anti-bot configuration
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title).80s.%(ext)s'),
        'noplaylist': True,
        
        # Anti-bot measures
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'skip_unavailable_fragments': True,
        'continue_dl': True,
        
        # Browser simulation
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
        
        # Throttle to avoid detection
        'throttled_rate': 102400,  # 100 KB/s
        'retry_sleep': 5,
        
        'quiet': False,
        'no_warnings': False,
    }
    
    # Merge quality options
    ydl_opts.update(quality_map[quality])
    
    logger.info(f"Starting download: {quality} - {url}")
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
            
            if quality == 'audio':
                file_path = file_path.replace('.webm', '.mp3').replace('.m4a', '.mp3')
            
            logger.info(f"Download completed: {file_path}")
            return file_path
            
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise e

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

        print("🤖 Bot starting with anti-bot measures...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Bot failed: {e}")

if __name__ == '__main__':
    main()
