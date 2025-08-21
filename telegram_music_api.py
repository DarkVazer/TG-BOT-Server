#!/usr/bin/env python3
"""
Telegram Music Bot + API Server
Компактный сервер для загрузки музыки через бота и воспроизведения через API
"""

import os
import asyncio
import logging
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional
import threading
import uuid
from pathlib import Path

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Web API
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import mimetypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
PORT = int(os.getenv('PORT', 10000))
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]

# Создание директорий
MUSIC_DIR = Path("music")
MUSIC_DIR.mkdir(exist_ok=True)

class MusicStorage:
    """Простое хранилище музыки в памяти"""
    
    def __init__(self):
        self.tracks: Dict[str, dict] = {}
        self.load_from_disk()
    
    def add_track(self, file_id: str, title: str, artist: str, file_path: str, 
                  duration: int = 0, user_id: int = None) -> str:
        """Добавить трек"""
        track_id = str(uuid.uuid4())[:8]
        
        self.tracks[track_id] = {
            'id': track_id,
            'file_id': file_id,
            'title': title,
            'artist': artist,
            'file_path': file_path,
            'duration': duration,
            'user_id': user_id,
            'uploaded_at': datetime.now().isoformat(),
            'play_count': 0
        }
        
        self.save_to_disk()
        return track_id
    
    def get_track(self, track_id: str) -> Optional[dict]:
        """Получить трек по ID"""
        return self.tracks.get(track_id)
    
    def get_all_tracks(self) -> List[dict]:
        """Получить все треки"""
        return list(self.tracks.values())
    
    def search_tracks(self, query: str) -> List[dict]:
        """Поиск треков"""
        query = query.lower()
        results = []
        
        for track in self.tracks.values():
            if (query in track['title'].lower() or 
                query in track['artist'].lower()):
                results.append(track)
        
        return results
    
    def increment_play_count(self, track_id: str):
        """Увеличить счетчик прослушиваний"""
        if track_id in self.tracks:
            self.tracks[track_id]['play_count'] += 1
            self.save_to_disk()
    
    def delete_track(self, track_id: str) -> bool:
        """Удалить трек"""
        if track_id in self.tracks:
            track = self.tracks[track_id]
            # Удаляем файл
            try:
                if os.path.exists(track['file_path']):
                    os.remove(track['file_path'])
            except Exception as e:
                logger.error(f"Error deleting file: {e}")
            
            del self.tracks[track_id]
            self.save_to_disk()
            return True
        return False
    
    def save_to_disk(self):
        """Сохранить метаданные на диск"""
        try:
            with open(MUSIC_DIR / "tracks.json", 'w', encoding='utf-8') as f:
                json.dump(self.tracks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving tracks: {e}")
    
    def load_from_disk(self):
        """Загрузить метаданные с диска"""
        try:
            if os.path.exists(MUSIC_DIR / "tracks.json"):
                with open(MUSIC_DIR / "tracks.json", 'r', encoding='utf-8') as f:
                    self.tracks = json.load(f)
                    logger.info(f"Loaded {len(self.tracks)} tracks from disk")
        except Exception as e:
            logger.error(f"Error loading tracks: {e}")

# Глобальное хранилище
music_storage = MusicStorage()

# Flask приложение
app = Flask(__name__)
CORS(app)

# API маршруты
@app.route('/')
def index():
    """Главная страница"""
    stats = {
        'tracks_count': len(music_storage.tracks),
        'status': 'running',
        'bot_status': 'active' if BOT_TOKEN != 'YOUR_BOT_TOKEN' else 'not_configured'
    }
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🎵 Music Bot API</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
            .stat {{ display: inline-block; margin: 10px; padding: 10px 20px; background: #e3f2fd; border-radius: 5px; }}
            .endpoint {{ background: #f0f0f0; padding: 10px; margin: 10px 0; border-radius: 5px; }}
            code {{ background: #e8e8e8; padding: 2px 5px; border-radius: 3px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎵 Music Bot API Server</h1>
            
            <h2>📊 Статистика</h2>
            <div class="stat">Треков: {stats['tracks_count']}</div>
            <div class="stat">Статус: {stats['status']}</div>
            <div class="stat">Бот: {stats['bot_status']}</div>
            
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
                <strong>GET /api/track/&lt;id&gt;</strong> - Информация о треке<br>
                <code>curl {request.host_url}api/track/12345</code>
            </div>
            
            <div class="endpoint">
                <strong>GET /api/play/&lt;id&gt;</strong> - Воспроизвести трек<br>
                <code>curl {request.host_url}api/play/12345</code>
            </div>
            
            <div class="endpoint">
                <strong>GET /api/download/&lt;id&gt;</strong> - Скачать трек<br>
                <code>curl -O {request.host_url}api/download/12345</code>
            </div>
            
            <h2>🤖 Telegram Bot</h2>
            <p>Отправьте аудиофайлы боту для загрузки в библиотеку.</p>
            <p>Бот автоматически обработает файлы и добавит их в API.</p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'ok', 'tracks': len(music_storage.tracks)})

@app.route('/api/tracks')
def api_tracks():
    """Получить все треки"""
    tracks = music_storage.get_all_tracks()
    
    # Убираем file_path из ответа (безопасность)
    safe_tracks = []
    for track in tracks:
        safe_track = track.copy()
        safe_track.pop('file_path', None)
        safe_track.pop('file_id', None)
        safe_tracks.append(safe_track)
    
    return jsonify({
        'tracks': safe_tracks,
        'count': len(safe_tracks)
    })

@app.route('/api/search')
def api_search():
    """Поиск треков"""
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify({'error': 'Query parameter "q" is required'}), 400
    
    tracks = music_storage.search_tracks(query)
    
    # Убираем приватные поля
    safe_tracks = []
    for track in tracks:
        safe_track = track.copy()
        safe_track.pop('file_path', None)
        safe_track.pop('file_id', None)
        safe_tracks.append(safe_track)
    
    return jsonify({
        'query': query,
        'tracks': safe_tracks,
        'count': len(safe_tracks)
    })

@app.route('/api/track/<track_id>')
def api_track_info(track_id):
    """Информация о треке"""
    track = music_storage.get_track(track_id)
    
    if not track:
        return jsonify({'error': 'Track not found'}), 404
    
    # Убираем приватные поля
    safe_track = track.copy()
    safe_track.pop('file_path', None)
    safe_track.pop('file_id', None)
    
    return jsonify(safe_track)

@app.route('/api/play/<track_id>')
def api_play_track(track_id):
    """Воспроизвести трек (стрим)"""
    track = music_storage.get_track(track_id)
    
    if not track:
        return jsonify({'error': 'Track not found'}), 404
    
    file_path = track['file_path']
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'Audio file not found'}), 404
    
    # Увеличиваем счетчик
    music_storage.increment_play_count(track_id)
    
    # Определяем MIME тип
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = 'audio/mpeg'
    
    def generate():
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(8192)  # 8KB chunks
                if not chunk:
                    break
                yield chunk
    
    return Response(
        generate(),
        mimetype=mime_type,
        headers={
            'Content-Disposition': f'inline; filename="{track["title"]}.mp3"',
            'Accept-Ranges': 'bytes'
        }
    )

@app.route('/api/download/<track_id>')
def api_download_track(track_id):
    """Скачать трек"""
    track = music_storage.get_track(track_id)
    
    if not track:
        return jsonify({'error': 'Track not found'}), 404
    
    file_path = track['file_path']
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'Audio file not found'}), 404
    
    # Увеличиваем счетчик
    music_storage.increment_play_count(track_id)
    
    filename = f"{track['artist']} - {track['title']}.mp3"
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype='audio/mpeg'
    )

@app.route('/api/stats')
def api_stats():
    """Статистика"""
    tracks = music_storage.get_all_tracks()
    
    total_plays = sum(track.get('play_count', 0) for track in tracks)
    top_tracks = sorted(tracks, key=lambda x: x.get('play_count', 0), reverse=True)[:10]
    
    return jsonify({
        'total_tracks': len(tracks),
        'total_plays': total_plays,
        'top_tracks': [
            {
                'id': track['id'],
                'title': track['title'],
                'artist': track['artist'],
                'play_count': track.get('play_count', 0)
            }
            for track in top_tracks
        ]
    })

# Webhook для Telegram
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    """Webhook для Telegram"""
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
    
    welcome_text = f"""
🎵 *Музыкальный бот с API*

Привет, {user.first_name}! 

*Что умеет этот бот:*
• 📤 Загрузка аудиофайлов
• 🎵 Автоматическое добавление в библиотеку
• 🔗 Создание API для воспроизведения
• 📊 Статистика прослушиваний

*Как пользоваться:*
1. Отправьте мне аудиофайл
2. Бот автоматически добавит его в библиотеку
3. Используйте API для воспроизведения

*Команды:*
/start - Это сообщение
/stats - Статистика
/list - Список треков
/api - Информация об API

Просто отправьте аудиофайл! 🎶
    """
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("📋 Список", callback_data="list")
        ],
        [
            InlineKeyboardButton("🔗 API Info", callback_data="api"),
            InlineKeyboardButton("ℹ️ Помощь", callback_data="help")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика"""
    tracks = music_storage.get_all_tracks()
    total_plays = sum(track.get('play_count', 0) for track in tracks)
    
    if not tracks:
        await update.message.reply_text("📊 Пока нет загруженных треков")
        return
    
    # Топ-5 треков
    top_tracks = sorted(tracks, key=lambda x: x.get('play_count', 0), reverse=True)[:5]
    
    stats_text = f"""
📊 *Статистика библиотеки*

🎵 Всего треков: {len(tracks)}
▶️ Общее прослушиваний: {total_plays}

*Топ-5 треков:*
"""
    
    for i, track in enumerate(top_tracks, 1):
        stats_text += f"{i}. *{track['title']}* - {track['artist']} ({track.get('play_count', 0)} ▶️)\n"
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список треков"""
    tracks = music_storage.get_all_tracks()
    
    if not tracks:
        await update.message.reply_text("📋 Библиотека пуста. Загрузите аудиофайлы!")
        return
    
    # Показываем последние 10 треков
    recent_tracks = sorted(tracks, key=lambda x: x['uploaded_at'], reverse=True)[:10]
    
    list_text = f"📋 *Последние треки* ({len(tracks)} всего):\n\n"
    
    for i, track in enumerate(recent_tracks, 1):
        list_text += f"{i}. *{track['title']}* - {track['artist']}\n"
        list_text += f"   ID: `{track['id']}` | ▶️ {track.get('play_count', 0)}\n\n"
    
    if len(tracks) > 10:
        list_text += f"... и еще {len(tracks) - 10} треков"
    
    await update.message.reply_text(list_text, parse_mode='Markdown')

async def api_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация об API"""
    base_url = WEBHOOK_URL or "https://your-app.onrender.com"
    
    api_text = f"""
🔗 *API Endpoints*

*Базовый URL:* `{base_url}`

*Основные endpoints:*
• `GET /api/tracks` - Все треки
• `GET /api/search?q=запрос` - Поиск
• `GET /api/play/ID` - Воспроизведение
• `GET /api/download/ID` - Скачивание

*Примеры:*
```
curl {base_url}/api/tracks
curl "{base_url}/api/search?q=music"
curl {base_url}/api/play/12345
```

*Веб-интерфейс:*
{base_url}
    """
    
    await update.message.reply_text(api_text, parse_mode='Markdown')

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка аудиофайлов"""
    audio = update.message.audio
    user = update.effective_user
    
    if not audio:
        await update.message.reply_text("❌ Это не аудиофайл")
        return
    
    # Проверка размера (макс 50MB)
    if audio.file_size > 50 * 1024 * 1024:
        await update.message.reply_text("❌ Файл слишком большой (макс 50MB)")
        return
    
    await update.message.reply_text("⏳ Загружаю файл...")
    
    try:
        # Скачиваем файл
        file = await context.bot.get_file(audio.file_id)
        
        # Извлекаем информацию
        title = audio.title or audio.file_name or "Unknown Title"
        artist = audio.performer or "Unknown Artist"
        duration = audio.duration or 0
        
        # Создаем безопасное имя файла
        safe_filename = f"{hashlib.md5(audio.file_id.encode()).hexdigest()[:8]}.mp3"
        file_path = MUSIC_DIR / safe_filename
        
        # Скачиваем
        await file.download_to_drive(file_path)
        
        # Добавляем в библиотеку
        track_id = music_storage.add_track(
            file_id=audio.file_id,
            title=title,
            artist=artist,
            file_path=str(file_path),
            duration=duration,
            user_id=user.id
        )
        
        # Формируем ответ
        base_url = WEBHOOK_URL or "https://your-app.onrender.com"
        
        success_text = f"""
✅ *Трек загружен!*

🎵 *{title}*
👤 {artist}
⏱️ {duration//60}:{duration%60:02d}
🆔 `{track_id}`

*API ссылки:*
▶️ Воспроизведение: `{base_url}/api/play/{track_id}`
💾 Скачивание: `{base_url}/api/download/{track_id}`
        """
        
        keyboard = [
            [
                InlineKeyboardButton("▶️ Воспроизвести", url=f"{base_url}/api/play/{track_id}"),
                InlineKeyboardButton("💾 Скачать", url=f"{base_url}/api/download/{track_id}")
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data="stats")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            success_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        logger.info(f"Track uploaded: {title} by {artist} (ID: {track_id})")
        
    except Exception as e:
        logger.error(f"Error uploading audio: {e}")
        await update.message.reply_text(f"❌ Ошибка при загрузке: {str(e)}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "stats":
        tracks = music_storage.get_all_tracks()
        total_plays = sum(track.get('play_count', 0) for track in tracks)
        
        stats_text = f"""
📊 *Статистика*

🎵 Треков: {len(tracks)}
▶️ Прослушиваний: {total_plays}
        """
        await query.edit_message_text(stats_text, parse_mode='Markdown')
        
    elif query.data == "list":
        tracks = music_storage.get_all_tracks()
        if tracks:
            list_text = f"📋 *Библиотека* ({len(tracks)} треков)\n\nИспользуйте /list для подробного списка"
        else:
            list_text = "📋 Библиотека пуста"
        await query.edit_message_text(list_text, parse_mode='Markdown')
        
    elif query.data == "api":
        base_url = WEBHOOK_URL or "https://your-app.onrender.com"
        api_text = f"🔗 *API:* {base_url}\n\nИспользуйте /api для подробной информации"
        await query.edit_message_text(api_text, parse_mode='Markdown')
        
    elif query.data == "help":
        help_text = """
ℹ️ *Помощь*

1. Отправьте аудиофайл боту
2. Бот автоматически добавит в библиотеку
3. Используйте API для воспроизведения

Команды: /start /stats /list /api
        """
        await query.edit_message_text(help_text, parse_mode='Markdown')

def run_flask():
    """Запуск Flask сервера"""
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)

async def setup_telegram():
    """Настройка Telegram бота"""
    if BOT_TOKEN == 'YOUR_BOT_TOKEN':
        logger.warning("BOT_TOKEN not configured!")
        return None
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("api", api_command))
    
    # Обработчики
    application.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Установка команд бота
    commands = [
        BotCommand("start", "Запуск бота"),
        BotCommand("stats", "Статистика"),
        BotCommand("list", "Список треков"),
        BotCommand("api", "API информация"),
    ]
    await application.bot.set_my_commands(commands)
    
    return application

async def main():
    """Главная функция"""
    global telegram_app
    
    logger.info("🚀 Starting Music Bot + API Server")
    
    # Запуск Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"🌐 API Server started on port {PORT}")
    
    # Настройка Telegram бота
    telegram_app = await setup_telegram()
    
    if telegram_app and WEBHOOK_URL:
        # Webhook режим
        logger.info("🤖 Setting up webhook mode")
        await telegram_app.bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        logger.info("✅ Webhook configured")
        
        # Держим приложение активным
        while True:
            await asyncio.sleep(60)
            
    elif telegram_app:
        # Polling режим (для локальной разработки)
        logger.info("🤖 Starting polling mode")
        await telegram_app.run_polling()
    else:
        logger.info("🤖 Bot not configured, running API only")
        # Только API сервер
        while True:
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
