import os
import logging
import asyncio
import threading
import re

from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import ChatForwardsRestrictedError

# ══════════════════════════════════════════════════════════════
# الإعدادات (CONFIGURATION)
# ══════════════════════════════════════════════════════════════

API_ID   = 34105911
API_HASH = 'b444ab6b4eeba8a66db4143b934dc540'

SESSION_STRING = os.environ.get('TELEGRAM_SESSION', '')

SOURCE_CHANNELS = [
    '@protrading36', 
    '@protradingg1', 
    'me',
    '@TradeX_net',
    '@elhorreyabrokeragetelegram',
    '@Crypto_Cabaal',
    '@Alwegdanycryptonews',
    '@lrnai',
    '@sherlockholmesfx'
]
DEST_CHANNEL = -1003772528470'

FLASK_PORT    = 10000
CACHE_LIMIT   = 1000

# ══════════════════════════════════════════════════════════════
# السجلات (LOGGING)
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('AutoCopier')

# ══════════════════════════════════════════════════════════════
# خادم FLASK — لمنع غفوة السيرفر
# ══════════════════════════════════════════════════════════════

flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return 'OK', 200

def start_flask():
    thread = threading.Thread(
        target=lambda: flask_app.run(host='0.0.0.0', port=FLASK_PORT),
        daemon=True,
    )
    thread.start()
    log.info(f'Keep-alive server running on port {FLASK_PORT}')

# ══════════════════════════════════════════════════════════════
# نظام منع التكرار المعدل (تم إصلاح الثغرة هنا)
# ══════════════════════════════════════════════════════════════

processed: set = set()

def register(chat_id: int, msg_id: int) -> bool:
    """ترجع True لو الرسالة جديدة فعلاً بناءً على ميكس (رقم القناة + رقم الرسالة)."""
    unique_key = (chat_id, msg_id)
    if unique_key in processed:
        return False
    processed.add(unique_key)
    if len(processed) > CACHE_LIMIT:
        processed.clear()
        log.info('تم تفريغ ذاكرة التكرار المؤقتة.')
    return True

# ══════════════════════════════════════════════════════════════
# تهيئة عميل تليجرام
# ══════════════════════════════════════════════════════════════

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
    loop=loop
)

# ══════════════════════════════════════════════════════════════
# المعالج الأساسي 
# ══════════════════════════════════════════════════════════════

@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handle_new_message(event: events.NewMessage.Event):
    try:
        msg     = event.message
        msg_id  = msg.id
        chat_id = event.chat_id  # سحب رقم القناة الفريد

        # التحقق من التكرار باستخدام المفتاح المركب الجديد
        if not register(chat_id, msg_id):
            log.warning(f'تم تجاهل رسالة مكررة أو متضاربة الأرقام — chat_id={chat_id} | msg_id={msg_id}')
            return

        source = getattr(event.chat, 'username', str(chat_id))
        log.info(f'رسالة جديدة من @{source} | msg_id={msg_id}')

        # تنظيف الرسالة من أي منشن أو لينكات تليجرام
        original_text = msg.text or ""
        clean_text = re.sub(r'(@[a-zA-Z0-9_]+)|(https?://t\.me/[a-zA-Z0-9_]+)|(t\.me/[a-zA-Z0-9_]+)', '', original_text)

        try:
            # المحاولة العادية للنسخ السريع
            if msg.media:
                await client.send_message(DEST_CHANNEL, clean_text, file=msg.media)
            else:
                await client.send_message(DEST_CHANNEL, clean_text)
                
            log.info(f'تم النسخ إلى {DEST_CHANNEL} بنجاح.')
            
        except ChatForwardsRestrictedError:
            # تجاوز حماية القنوات المقفولة
            log.warning(f'القناة @{source} محمية. جاري كسر الحماية والتحميل يدوياً...')
            if msg.media:
                file_path = await msg.download_media()
                await client.send_message(DEST_CHANNEL, clean_text, file=file_path)
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            else:
                await client.send_message(DEST_CHANNEL, clean_text)
                
            log.info(f'تم تجاوز الحماية والنسخ إلى {DEST_CHANNEL} بنجاح.')

    except Exception as e:
        log.exception(f'حدث خطأ أثناء نسخ الرسالة: {e}')

# ══════════════════════════════════════════════════════════════
# نقطة البداية
# ══════════════════════════════════════════════════════════════

async def main():
    await client.start()
    
    log.info('جاري تنشيط ذاكرة القنوات (get_dialogs) لضمان التقاط كل الرسائل...')
    await client.get_dialogs()

    if not SESSION_STRING:
        saved = client.session.save()
        log.info('════════════════════════════════════════')
        log.info('التشغيل الأول — انسخ نص الـ StringSession ده واحفظه فوراً:')
        log.info(saved)
        log.info('════════════════════════════════════════')

    me = await client.get_me()
    log.info(f'تم تسجيل الدخول باسم: {me.first_name} (@{me.username})')
    log.info(f'جاري مراقبة القنوات: {SOURCE_CHANNELS}')
    log.info(f'قناة النشر المستهدفة: {DEST_CHANNEL}')

    await client.run_until_disconnected()


if __name__ == '__main__':
    start_flask()
    loop.run_until_complete(main())
