#!/usr/bin/env python3
"""
Telegram Music Bot + API Server - Финальная рабочая версия
Исправлены все проблемы с webhook и event loop
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
import queue
import mimetypes

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Web API
from flask import Flask, request, jsonify, send_file, Response

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
PORT = int(os.getenv('PORT', 10000))

# Создание директорий
MUSIC_DIR = Path("music")
MUSIC_DIR.mkdir(exist_ok=True)

# Простое хранилище треков
tracks_storage = {}

# Очередь для обработки Telegram updates
update_queue = queue.Queue()

def save_tracks():
    """Сохранить треки на диск"""
    try:
        with open(MUSIC_DIR / "tracks.json", 'w', encoding='utf-8') as f:
            json.dump(tracks_storage, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

def load_tracks():
    """Загрузить треки с диска"""
    global tracks_storage
    try:
        tracks_file = MUSIC_DIR / "tracks.json"
        if tracks_file.exists():
            with open(tracks_file, 'r', encoding='utf-8') as f:
                tracks_storage = json.load(f)
                logger.info(f"Loaded {len(tracks_storage)} tracks")
    except Exception as e:
        logger.error(f"Load error: {e}")

# Загружаем треки при старте
load_tracks()

# Flask приложение
app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    """Добавляем CORS заголовки"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return response

@app.route('/')
def home():
    """Главная страница с веб-плеером"""
    tracks_count = len(tracks_storage)
    bot_status = 'Настроен ✅' if BOT_TOKEN else 'Не настроен ❌'
    
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🎵 Music Bot API</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                   background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                   min-height: 100vh; color: white; padding: 20px; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .stats {{ display: flex; justify-content: center; gap: 20px; margin: 20px 0; flex-wrap: wrap; }}
            .stat-card {{ background: rgba(255,255,255,0.1); padding: 20px; 
                         border-radius: 10px; text-align: center; min-width: 150px; }}
            .endpoints {{ background: rgba(255,255,255,0.1); padding: 30px; 
                        border-radius: 15px; margin: 20px 0; }}
            .endpoint {{ background: rgba(255,255,255,0.1); padding: 15px; 
                       margin: 10px 0; border-radius: 8px; }}
            .player-section {{ background: rgba(255,255,255,0.1); padding: 30px; 
                              border-radius: 15px; margin: 20px 0; }}
            code {{ background: rgba(0,0,0,0.3); padding: 4px 8px; 
                   border-radius: 4px; font-family: monospace; }}
            .track-item {{ background: rgba(255,255,255,0.1); padding: 15px; 
                          margin: 10px 0; border-radius: 8px; }}
            audio {{ width: 100%; margin-top: 10px; }}
            .refresh-btn {{ background: #1DB954; color: white; border: none; 
                           padding: 10px 20px; border-radius: 5px; cursor: pointer; 
                           margin-bottom: 20px; }}
            .no-tracks {{ text-align: center; padding: 40px; color: #ccc; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎵 Music Bot API Server</h1>
                <p>Загружайте музыку через Telegram, воспроизводите через API</p>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <h3>{tracks_count}</h3>
                    <p>Треков в библиотеке</p>
                </div>
                <div class="stat-card">
                    <h3>{bot_status}</h3>
                    <p>Telegram бот</p>
                </div>
                <div class="stat-card">
                    <h3>🟢 Онлайн</h3>
                    <p>Статус сервера</p>
                </div>
            </div>
            
            <div class="endpoints">
                <h2>🔗 API Endpoints</h2>
                
                <div class="endpoint">
                    <strong>GET /api/tracks</strong> - Все треки<br>
                    <code>curl {request.host_url}api/tracks</code>
                </div>
                
                <div class="endpoint">
                    <strong>GET /api/search?q=запрос</strong> - Поиск<br>
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
            </div>
            
            <div class="player-section">
                <h2>🎧 Веб-плеер</h2>
                <button class="refresh-btn" onclick="loadTracks()">🔄 Обновить</button>
                <div id="tracks-list">Загрузка...</div>
            </div>
        </div>
        
        <script>
            function loadTracks() {{
                const container = document.getElementById('tracks-list');
                container.innerHTML = 'Загрузка...';
                
                fetch('/api/tracks')
                    .then(response => response.json())
                    .then(data => {{
                        if (data.tracks && data.tracks.length > 0) {{
                            let html = `<h3>Доступные треки (${{data.tracks.length}}):</h3>`;
                            data.tracks.forEach(track => {{
                                html += `
                                    <div class="track-item">
                                        <strong>${{track.title}}</strong> - ${{track.artist}}<br>
                                        <small>ID: ${{track.id}} | Прослушиваний: ${{track.play_count || 0}}</small>
                                        <audio controls preload="none">
                                            <source src="/api/play/${{track.id}}" type="audio/mpeg">
                                            Ваш браузер не поддерживает аудио элемент.
                                        </audio>
                                        <div style="margin-top: 10px;">
                                            <a href="/api/download/${{track.id}}" download style="color: #1DB954; text-decoration: none;">
                                                💾 Скачать
                                            </a>
                                        </div>
                                    </div>
                                `;
                            }});
                            container.innerHTML = html;
                        }} else {{
                            container.innerHTML = `
                                <div class="no-tracks">
                                    <h3>📭 Нет треков</h3>
                                    <p>Отправьте аудиофайлы Telegram боту для добавления!</p>
                                    <p style="margin-top: 10px; font-size: 14px;">
                                        Бот: {bot_status}
                                    </p>
                                </div>
                            `;
                        }}
                    }})
                    .catch(error => {{
                        console.error('Error:', error);
                        container.innerHTML = '<p style="color: #ff6b6b;">Ошибка загрузки треков</p>';
                    }});
            }}
            
            // Загружаем треки при открытии страницы
            loadTracks();
            
            // Автообновление каждые 30 секунд
            setInterval(loadTracks, 30000);
        </script>
    </body>
    </html>
    """

@app.route('/health')
def health_check():
    """Health check для мониторинга"""
    return jsonify({
        'status': 'healthy',
        'tracks_count': len(tracks_storage),
        'bot_configured': bool(BOT_TOKEN)
    })

@app.route('/api/tracks')
def get_tracks():
    """Получить все треки"""
    safe_tracks = []
    for track in tracks_storage.values():
        safe_track = {
            'id': track['id'],
            'title': track['title'],
            'artist': track['artist'],
            'duration': track.get('duration', 0),
            'uploaded_at': track.get('uploaded_at', ''),
            'play_count': track.get('play_count', 0)
        }
        safe_tracks.append(safe_track)
    
    # Сортируем по дате загрузки (новые сначала)
    safe_tracks.sort(key=lambda x: x['uploaded_at'], reverse=True)
    
    return jsonify({
        'tracks': safe_tracks,
        'count': len(safe_tracks)
    })

@app.route('/api/search')
def search_tracks():
    """Поиск треков"""
    query = request.args.get('q', '').strip().lower()
    
    if not query:
        return jsonify({'error': 'Query parameter "q" is required'}), 400
    
    results = []
    for track in tracks_storage.values():
        if (query in track['title'].lower() or 
            query in track['artist'].lower()):
            
            safe_track = {
                'id': track['id'],
                'title': track['title'],
                'artist': track['artist'],
                'duration': track.get('duration', 0),
                'play_count': track.get('play_count', 0)
            }
            results.append(safe_track)
    
    return jsonify({
        'query': query,
        'tracks': results,
        'count': len(results)
    })

@app.route('/api/play/<track_id>')
def play_track(track_id):
    """Воспроизведение трека"""
    if track_id not in tracks_storage:
        return jsonify({'error': 'Track not found'}), 404
    
    track = tracks_storage[track_id]
    file_path = track['file_path']
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'Audio file not found'}), 404
    
    # Увеличиваем счетчик прослушиваний
    tracks_storage[track_id]['play_count'] = tracks_storage[track_id].get('play_count', 0) + 1
    save_tracks()
    
    def generate_audio():
        with open(file_path, 'rb') as audio_file:
            while True:
                chunk = audio_file.read(8192)  # 8KB chunks
                if not chunk:
                    break
                yield chunk
    
    return Response(
        generate_audio(),
        mimetype='audio/mpeg',
        headers={
            'Content-Disposition': f'inline; filename="{track["title"]}.mp3"',
            'Accept-Ranges': 'bytes'
        }
    )

@app.route('/api/download/<track_id>')
def download_track(track_id):
    """Скачивание трека"""
    if track_id not in tracks_storage:
        return jsonify({'error': 'Track not found'}), 404
    
    track = tracks_storage[track_id]
    file_path = track['file_path']
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'Audio file not found'}), 404
    
    filename = f"{track['artist']} - {track['title']}.mp3"
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype='audio/mpeg'
    )

@app.route('/api/stats')
def get_stats():
    """Статистика сервера"""
    total_plays = sum(track.get('play_count', 0) for track in tracks_storage.values())
    
    return jsonify({
        'total_tracks': len(tracks_storage),
        'total_plays': total_plays,
        'bot_configured': bool(BOT_TOKEN)
    })

# Webhook endpoint для Telegram (упрощенный)
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Обработка webhook от Telegram"""
    if not BOT_TOKEN:
        return 'Bot not configured', 400
    
    try:
        update_data = request.get_json()
        if update_data:
            # Добавляем update в очередь для обработки
            update_queue.put(update_data)
        return 'OK'
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return 'Error', 500

# Telegram бот функции
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    user = update.effective_user
    
    welcome_text = f"""
🎵 *Музыкальный бот + API*

Привет, {user.first_name}! 

*Возможности:*
• 📤 Загрузка аудиофайлов (до 50MB)
• 🎵 Автоматическое добавление в API
• 🔗 Веб-плеер и REST API
• 📊 Статистика прослушиваний

*Команды:*
/start - Главное меню
/stats - Статистика
/list - Список треков
/api - API информация

*Инструкция:*
Просто отправьте мне аудиофайл! 🎶
    """
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("📋 Список", callback_data="list")
        ],
        [
            InlineKeyboardButton("🔗 API", callback_data="api"),
            InlineKeyboardButton("🌐 Веб-плеер", url=WEBHOOK_URL or "https://telegram-music-bot-api-server.onrender.com")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text, 
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def handle_audio_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка загрузки аудиофайлов"""
    audio = update.message.audio
    user = update.effective_user
    
    if not audio:
        await update.message.reply_text("❌ Отправьте аудиофайл")
        return
    
    # Проверка размера файла
    if audio.file_size and audio.file_size > 50 * 1024 * 1024:  # 50MB
        await update.message.reply_text("❌ Файл слишком большой (максимум 50MB)")
        return
    
    status_msg = await update.message.reply_text("⏳ Загружаю файл...")
    
    try:
        # Получаем файл от Telegram
        file = await context.bot.get_file(audio.file_id)
        
        # Извлекаем метаданные
        title = audio.title or audio.file_name or "Unknown Title"
        artist = audio.performer or "Unknown Artist"
        duration = audio.duration or 0
        
        # Очищаем название от недопустимых символов
        title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).strip()
        
        # Генерируем уникальный ID и безопасное имя файла
        track_id = str(uuid.uuid4())[:8]
        file_hash = hashlib.md5(audio.file_id.encode()).hexdigest()[:8]
        safe_filename = f"{track_id}_{file_hash}.mp3"
        file_path = MUSIC_DIR / safe_filename
        
        # Скачиваем файл
        await file.download_to_drive(file_path)
        
        # Сохраняем в базе данных
        tracks_storage[track_id] = {
            'id': track_id,
            'title': title,
            'artist': artist,
            'file_path': str(file_path),
            'file_id': audio.file_id,
            'duration': duration,
            'user_id': user.id,
            'uploaded_at': datetime.now().isoformat(),
            'play_count': 0
        }
        
        save_tracks()
        
        # Формируем ответ
        base_url = WEBHOOK_URL or "https://telegram-music-bot-api-server.onrender.com"
        
        success_text = f"""
✅ *Трек успешно загружен!*

🎵 *{title}*
👤 {artist}
⏱️ {duration//60}:{duration%60:02d}
🆔 `{track_id}`

*API ссылки:*
▶️ Воспроизведение: `{base_url}/api/play/{track_id}`
💾 Скачивание: `{base_url}/api/download/{track_id}`

*Веб-плеер:* {base_url}
        """
        
        keyboard = [
            [
                InlineKeyboardButton("🌐 Открыть веб-плеер", url=base_url)
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data="stats")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.edit_text(
            success_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        logger.info(f"Track uploaded: {title} by {artist} (ID: {track_id}, User: {user.id})")
        
    except Exception as e:
        logger.error(f"Audio upload error: {e}")
        await status_msg.edit_text(f"❌ Ошибка при загрузке: {str(e)}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Статистика"""
    total_tracks = len(tracks_storage)
    total_plays = sum(track.get('play_count', 0) for track in tracks_storage.values())
    user_tracks = len([t for t in tracks_storage.values() if t.get('user_id') == update.effective_user.id])
    
    stats_text = f"""
📊 *Статистика сервера*

🎵 Всего треков: {total_tracks}
▶️ Общее прослушиваний: {total_plays}
👤 Ваших треков: {user_tracks}

*Топ-3 треков:*
"""
    
    # Топ треков по прослушиваниям
    sorted_tracks = sorted(tracks_storage.values(), key=lambda x: x.get('play_count', 0), reverse=True)[:3]
    
    for i, track in enumerate(sorted_tracks, 1):
        stats_text += f"{i}. {track['title']} ({track.get('play_count', 0)} ▶️)\n"
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Список треков"""
    if not tracks_storage:
        await update.message.reply_text("📋 Библиотека пуста. Загрузите первый трек!")
        return
    
    # Показываем последние 5 треков
    tracks_list = list(tracks_storage.values())
    recent_tracks = sorted(tracks_list, key=lambda x: x.get('uploaded_at', ''), reverse=True)[:5]
    
    list_text = f"📋 *Последние треки* ({len(tracks_storage)} всего):\n\n"
    
    for i, track in enumerate(recent_tracks, 1):
        list_text += f"{i}. *{track['title']}* - {track['artist']}\n"
        list_text += f"   🆔 `{track['id']}` | ▶️ {track.get('play_count', 0)}\n\n"
    
    if len(tracks_storage) > 5:
        list_text += f"... и еще {len(tracks_storage) - 5} треков"
    
    await update.message.reply_text(list_text, parse_mode='Markdown')

async def api_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """API информация"""
    base_url = WEBHOOK_URL or "https://telegram-music-bot-api-server.onrender.com"
    
    api_text = f"""
🔗 *API Документация*

*Базовый URL:* `{base_url}`

*Endpoints:*
• `GET /api/tracks` - Все треки
• `GET /api/search?q=запрос` - Поиск
• `GET /api/play/ID` - Воспроизведение
• `GET /api/download/ID` - Скачивание
• `GET /api/stats` - Статистика

*Веб-интерфейс:* {base_url}
    """
    
    await update.message.reply_text(api_text, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "stats":
        total = len(tracks_storage)
        plays = sum(track.get('play_count', 0) for track in tracks_storage.values())
        text = f"📊 Треков: {total} | Прослушиваний: {plays}"
        await query.edit_message_text(text)
        
    elif query.data == "list":
        count = len(tracks_storage)
        text = f"📋 В библиотеке {count} треков\n\nИспользуйте /list для подробного списка"
        await query.edit_message_text(text)
        
    elif query.data == "api":
        base_url = WEBHOOK_URL or "https://telegram-music-bot-api-server.onrender.com"
        text = f"🔗 API доступен по адресу:\n{base_url}\n\nИспользуйте /api для подробной информации"
        await query.edit_message_text(text)

def run_flask_server():
    """Запуск Flask сервера в отдельном потоке"""
    try:
        app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"Flask server error: {e}")

async def process_telegram_updates():
    """Обработка Telegram updates из очереди"""
    while True:
        try:
            if not update_queue.empty():
                update_data = update_queue.get_nowait()
                if telegram_app:
                    update = Update.de_json(update_data, telegram_app.bot)
                    await telegram_app.process_update(update)
            await asyncio.sleep(0.1)  # Небольшая пауза
        except Exception as e:
            logger.error(f"Update processing error: {e}")
            await asyncio.sleep(1)

async def setup_telegram_bot():
    """Настройка и создание Telegram бота"""
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN not configured - running in API-only mode")
        return None
    
    try:
        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики команд
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("list", list_command))
        application.add_handler(CommandHandler("api", api_command))
        
        # Обработчик аудиофайлов
        application.add_handler(MessageHandler(filters.AUDIO, handle_audio_upload))
        
        # Обработчик кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        return application
        
    except Exception as e:
        logger.error(f"Failed to setup Telegram bot: {e}")
        return None

async def main():
    """Главная асинхронная функция"""
    global telegram_app
    
    logger.info("🚀 Starting Telegram Music Bot + API Server")
    
    # Запускаем Flask сервер в отдельном потоке
    flask_thread = threading.Thread(target=run_flask_server, daemon=True)
    flask_thread.start()
    logger.info(f"🌐 Flask API server started on port {PORT}")
    
    # Настраиваем Telegram бота
    telegram_app = await setup_telegram_bot()
    
    if telegram_app and WEBHOOK_URL:
        # Webhook режим для продакшена
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await telegram_app.bot.set_webhook(url=webhook_url)
        logger.info(f"🤖 Telegram bot webhook set to: {webhook_url}")
        
        # Запускаем обработчик updates
        update_processor = asyncio.create_task(process_telegram_updates())
        
        # Держим приложение запущенным
        try:
            while True:
                await asyncio.sleep(60)  # Проверяем каждую минуту
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            update_processor.cancel()
            
    elif telegram_app:
        # Polling режим для разработки
        logger.info("🤖 Starting Telegram bot in polling mode")
        await telegram_app.run_polling(drop_pending_updates=True)
        
    else:
        # Только API режим
        logger.info("🤖 Running in API-only mode (no Telegram bot)")
        try:
            while True:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
