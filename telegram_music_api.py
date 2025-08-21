#!/usr/bin/env python3
"""
Простой Telegram Music Bot + API Server
Минимальная версия для быстрого развертывания на Render
"""

import os
import asyncio
import logging
import json
import hashlib
from datetime import datetime
import threading
import uuid
from pathlib import Path
import mimetypes

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Web API
from flask import Flask, request, jsonify, send_file, Response

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
PORT = int(os.getenv('PORT', 10000))

# Создание директорий
MUSIC_DIR = Path("music")
MUSIC_DIR.mkdir(exist_ok=True)

# Хранилище треков (простое в памяти)
tracks_db = {}

def save_tracks():
    """Сохранить треки на диск"""
    try:
        with open(MUSIC_DIR / "tracks.json", 'w', encoding='utf-8') as f:
            json.dump(tracks_db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving tracks: {e}")

def load_tracks():
    """Загрузить треки с диска"""
    global tracks_db
    try:
        if os.path.exists(MUSIC_DIR / "tracks.json"):
            with open(MUSIC_DIR / "tracks.json", 'r', encoding='utf-8') as f:
                tracks_db = json.load(f)
                logger.info(f"Loaded {len(tracks_db)} tracks")
    except Exception as e:
        logger.error(f"Error loading tracks: {e}")

# Загружаем существующие треки
load_tracks()

# Flask приложение
app = Flask(__name__)

@app.after_request
def after_request(response):
    """Простая CORS поддержка"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def index():
    """Главная страница"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🎵 Music Bot API</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
            .stat {{ display: inline-block; margin: 10px; padding: 10px 20px; background: #e3f2fd; border-radius: 5px; }}
            .endpoint {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #007bff; }}
            code {{ background: #f1f3f4; padding: 4px 8px; border-radius: 4px; font-family: monospace; }}
            h2 {{ color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎵 Music Bot API Server</h1>
            
            <h2>📊 Статистика</h2>
            <div class="stat">Треков: {len(tracks_db)}</div>
            <div class="stat">Статус: Работает</div>
            <div class="stat">Режим: {'Webhook' if WEBHOOK_URL else 'Polling'}</div>
            
            <h2>🔗 API Endpoints</h2>
            
            <div class="endpoint">
                <strong>GET /api/tracks</strong> - Список всех треков<br>
                <code>curl {request.host_url}api/tracks</code>
            </div>
            
            <div class="endpoint">
                <strong>GET /api/search?q=запрос</strong> - Поиск треков<br>
                <code>curl "{request.host_url}api/search?q=music"</code>
            </div>
            
            <div class="endpoint">
                <strong>GET /api/play/&lt;id&gt;</strong> - Воспроизведение<br>
                <code>curl {request.host_url}api/play/12345</code>
            </div>
            
            <div class="endpoint">
                <strong>GET /api/download/&lt;id&gt;</strong> - Скачивание<br>
                <code>curl -O {request.host_url}api/download/12345</code>
            </div>
            
            <h2>🤖 Telegram Bot</h2>
            <p>📤 Отправьте аудиофайлы боту для добавления в библиотеку</p>
            <p>🎵 Файлы автоматически станут доступны через API</p>
            
            <h2>🎧 Плеер</h2>
            <div id="player"></div>
            
            <script>
                // Простой веб-плеер
                fetch('/api/tracks')
                    .then(r => r.json())
                    .then(data => {{
                        const player = document.getElementById('player');
                        if (data.tracks && data.tracks.length > 0) {{
                            let html = '<h3>Последние треки:</h3>';
                            data.tracks.slice(0, 5).forEach(track => {{
                                html += `
                                    <div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px;">
                                        <strong>${{track.title}}</strong> - ${{track.artist}}<br>
                                        <audio controls style="width: 100%; margin-top: 5px;">
                                            <source src="/api/play/${{track.id}}" type="audio/mpeg">
                                        </audio>
                                    </div>
                                `;
                            }});
                            player.innerHTML = html;
                        }} else {{
                            player.innerHTML = '<p>Нет треков. Загрузите через Telegram бота!</p>';
                        }}
                    }});
            </script>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'tracks': len(tracks_db)})

@app.route('/api/tracks')
def api_tracks():
    """Все треки"""
    safe_tracks = []
    for track in tracks_db.values():
        safe_track = track.copy()
        safe_track.pop('file_path', None)
        safe_track.pop('file_id', None)
        safe_tracks.append(safe_track)
    
    return jsonify({'tracks': safe_tracks, 'count': len(safe_tracks)})

@app.route('/api/search')
def api_search():
    """Поиск треков"""
    query = request.args.get('q', '').strip().lower()
    if not query:
        return jsonify({'error': 'Parameter q required'}), 400
    
    results = []
    for track in tracks_db.values():
        if query in track['title'].lower() or query in track['artist'].lower():
            safe_track = track.copy()
            safe_track.pop('file_path', None)
            safe_track.pop('file_id', None)
            results.append(safe_track)
    
    return jsonify({'query': query, 'tracks': results, 'count': len(results)})

@app.route('/api/play/<track_id>')
def api_play(track_id):
    """Воспроизведение трека"""
    if track_id not in tracks_db:
        return jsonify({'error': 'Track not found'}), 404
    
    track = tracks_db[track_id]
    file_path = track['file_path']
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    
    # Увеличиваем счетчик
    tracks_db[track_id]['play_count'] = tracks_db[track_id].get('play_count', 0) + 1
    save_tracks()
    
    mime_type = 'audio/mpeg'
    
    def generate():
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                yield chunk
    
    return Response(
        generate(),
        mimetype=mime_type,
        headers={'Content-Disposition': f'inline; filename="{track["title"]}.mp3"'}
    )

@app.route('/api/download/<track_id>')
def api_download(track_id):
    """Скачивание трека"""
    if track_id not in tracks_db:
        return jsonify({'error': 'Track not found'}), 404
    
    track = tracks_db[track_id]
    file_path = track['file_path']
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    
    filename = f"{track['artist']} - {track['title']}.mp3"
    return send_file(file_path, as_attachment=True, download_name=filename)

# Webhook для Telegram
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    if BOT_TOKEN == 'YOUR_BOT_TOKEN':
        return 'Bot not configured', 400
    
    try:
        update_data = request.get_json()
        update = Update.de_json(update_data, telegram_app.bot)
        asyncio.create_task(telegram_app.process_update(update))
        return 'OK'
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return 'Error', 500

# Telegram бот
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    text = f"""
🎵 *Музыкальный бот*

Привет, {user.first_name}! 

*Как пользоваться:*
1. Отправьте аудиофайл боту
2. Файл автоматически добавится в библиотеку
3. Используйте API для воспроизведения

*Команды:*
/start - Запуск
/stats - Статистика  
/list - Список треков
/api - API информация

📤 Просто отправьте аудиофайл!
    """
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📋 Список", callback_data="list")],
        [InlineKeyboardButton("🔗 API", callback_data="api")]
    ]
    
    await update.message.reply_text(
        text, 
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка аудиофайлов"""
    audio = update.message.audio
    user = update.effective_user
    
    if not audio:
        await update.message.reply_text("❌ Это не аудиофайл")
        return
    
    if audio.file_size > 50 * 1024 * 1024:
        await update.message.reply_text("❌ Файл слишком большой (макс 50MB)")
        return
    
    await update.message.reply_text("⏳ Загружаю...")
    
    try:
        file = await context.bot.get_file(audio.file_id)
        
        title = audio.title or audio.file_name or "Unknown"
        artist = audio.performer or "Unknown Artist"
        
        track_id = str(uuid.uuid4())[:8]
        safe_filename = f"{track_id}.mp3"
        file_path = MUSIC_DIR / safe_filename
        
        await file.download_to_drive(file_path)
        
        tracks_db[track_id] = {
            'id': track_id,
            'title': title,
            'artist': artist,
            'file_path': str(file_path),
            'file_id': audio.file_id,
            'duration': audio.duration or 0,
            'user_id': user.id,
            'uploaded_at': datetime.now().isoformat(),
            'play_count': 0
        }
        
        save_tracks()
        
        base_url = WEBHOOK_URL or "http://localhost:10000"
        
        success_text = f"""
✅ *Трек загружен!*

🎵 {title}
👤 {artist}
🆔 `{track_id}`

*Ссылки:*
▶️ Воспроизведение: `{base_url}/api/play/{track_id}`
💾 Скачивание: `{base_url}/api/download/{track_id}`
        """
        
        await update.message.reply_text(success_text, parse_mode='Markdown')
        logger.info(f"Track uploaded: {title} by {artist}")
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика"""
    count = len(tracks_db)
    total_plays = sum(track.get('play_count', 0) for track in tracks_db.values())
    
    text = f"""
📊 *Статистика*

🎵 Треков: {count}
▶️ Прослушиваний: {total_plays}
    """
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список треков"""
    if not tracks_db:
        await update.message.reply_text("📋 Библиотека пуста")
        return
    
    tracks = list(tracks_db.values())
    recent = sorted(tracks, key=lambda x: x['uploaded_at'], reverse=True)[:5]
    
    text = f"📋 *Последние треки* ({len(tracks)} всего):\n\n"
    
    for i, track in enumerate(recent, 1):
        text += f"{i}. {track['title']} - {track['artist']}\n"
        text += f"   ID: `{track['id']}`\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def api_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """API информация"""
    base_url = WEBHOOK_URL or "http://localhost:10000"
    
    text = f"""
🔗 *API Endpoints*

*Базовый URL:* `{base_url}`

• `/api/tracks` - Все треки
• `/api/search?q=запрос` - Поиск  
• `/api/play/ID` - Воспроизведение
• `/api/download/ID` - Скачивание

*Веб-интерфейс:* {base_url}
    """
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "stats":
        count = len(tracks_db)
        text = f"📊 Треков: {count}"
        await query.edit_message_text(text)
    elif query.data == "list":
        count = len(tracks_db)
        text = f"📋 Библиотека: {count} треков"
        await query.edit_message_text(text)
    elif query.data == "api":
        base_url = WEBHOOK_URL or "http://localhost:10000"
        text = f"🔗 API: {base_url}"
        await query.edit_message_text(text)

def run_flask():
    """Запуск Flask"""
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)

async def setup_telegram():
    """Настройка Telegram"""
    if BOT_TOKEN == 'YOUR_BOT_TOKEN':
        logger.warning("BOT_TOKEN not set!")
        return None
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("api", api_command))
    application.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    return application

async def main():
    """Главная функция"""
    global telegram_app
    
    logger.info("🚀 Starting Music Bot + API")
    
    # Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"🌐 API Server on port {PORT}")
    
    # Telegram бот
    telegram_app = await setup_telegram()
    
    if telegram_app and WEBHOOK_URL:
        logger.info("🤖 Webhook mode")
        await telegram_app.bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        while True:
            await asyncio.sleep(60)
    elif telegram_app:
        logger.info("🤖 Polling mode")
        await telegram_app.run_polling()
    else:
        logger.info("🤖 API only mode")
        while True:
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
