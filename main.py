import sys
import time
import random
import datetime
import threading
import asyncio
import websockets
import json
import os
from threading import Thread, Semaphore
import tls_client
import telebot

TELEGRAM_TOKEN = "8684389899:AAExwUA_YvB3f8m1i6eIApHXVHH1AJ07EdU"
bot = telebot.TeleBot(TELEGRAM_TOKEN)

CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"

task_running = False
stop_signal = False
worker_thread = None

channel = ""
channel_id = None
stream_id = None
max_threads = 0
thread_limit = None
active = 0
start_time = None
lock = threading.Lock()
connections = 0
attempts = 0
pings = 0
heartbeats = 0
viewers = 0

def clean_channel_name(name):
    if "kick.com/" in name:
        parts = name.split("kick.com/")
        channel = parts[1].split("/")[0].split("?")[0]
        return channel.lower()
    return name.lower()

def get_channel_info(name):
    global channel_id, stream_id
    try:
        s = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
        s.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://kick.com/',
            'Origin': 'https://kick.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        
        response = s.get(f'https://kick.com/api/v2/channels/{name}')
        if response.status_code == 200:
            data = response.json()
            channel_id = data.get("id")
            if 'livestream' in data and data['livestream']:
                stream_id = data['livestream'].get('id')
            return channel_id
    except Exception as e:
        print(f"[!] Error al obtener canal: {e}")
    return None

def get_token():
    try:
        s = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        s.get("https://kick.com")
        s.headers["X-CLIENT-TOKEN"] = CLIENT_TOKEN
        response = s.get('https://websockets.kick.com/viewer/v1/token')
        if response.status_code == 200:
            return response.json().get("data", {}).get("token")
    except:
        pass
    return None

async def websocket_handler(token):
    global connections, stop_signal, channel_id, heartbeats, pings
    connected = False
    try:
        url = f"wss://websockets.kick.com/viewer/v1/connect?token={token}"
        async with websockets.connect(url) as ws:
            with lock:
                connections += 1
            connected = True
            
            handshake = {
                "type": "channel_handshake",
                "data": {"message": {"channelId": channel_id}}
            }
            await ws.send(json.dumps(handshake))
            with lock:
                heartbeats += 1
            
            ping_count = 0
            while not stop_signal and ping_count < 10:
                ping_count += 1
                await ws.send(json.dumps({"type": "ping"}))
                with lock:
                    pings += 1
                await asyncio.sleep(12 + random.randint(1, 5))
    except:
        pass
    finally:
        if connected:
            with lock:
                if connections > 0:
                    connections -= 1

def send_connection():
    global active, attempts, channel_id, thread_limit
    active += 1
    with lock:
        attempts += 1
    try:
        token = get_token()
        if token and channel_id:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(websocket_handler(token))
            loop.close()
    except:
        pass
    finally:
        active -= 1
        thread_limit.release()

def core_runner(thread_count, channel_name):
    global max_threads, channel, start_time, thread_limit, channel_id, stop_signal, task_running
    
    max_threads = int(thread_count)
    channel = clean_channel_name(channel_name)
    thread_limit = Semaphore(max_threads)
    start_time = datetime.datetime.now()
    channel_id = get_channel_info(channel)
    
    if not channel_id:
        print("[!] No se pudo resolver el Channel ID.")
        task_running = False
        return

    while not stop_signal:
        if thread_limit.acquire(timeout=1):
            t = Thread(target=send_connection, daemon=True)
            t.start()
            time.sleep(0.35)
            
    task_running = False
    print("[+] Tarea finalizada.")


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    texto = (
        "🤖 **Panel de Control**\n\n"
        "Comandos disponibles:\n"
        "`/run <canal> <hilos>` - Inicia el proceso (Ej: `/run streamer 50`)\n"
        "`/status` - Muestra el estado actual de las conexiones\n"
        "`/stop` - Detiene la ejecución actual"
    )
    bot.reply_to(message, texto, parse_mode="Markdown")

@bot.message_handler(commands=['run'])
def start_execution(message):
    global task_running, stop_signal, worker_thread
    
    if task_running:
        bot.reply_to(message, "⚠️ Ya hay un proceso ejecutándose. Usa `/stop` primero.")
        return
        
    try:
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(message, "Format incorrecto. Uso: `/run <canal_o_url> <cantidad>`", parse_mode="Markdown")
            return
            
        target_channel = args[1]
        num_threads = int(args[2])
        
        if num_threads <= 0:
            bot.reply_to(message, "La cantidad debe ser mayor a 0.")
            return

        stop_signal = False
        task_running = True
        
        # Ejecutar la lógica pesada en un hilo secundario para no congelar Telegram
        worker_thread = Thread(target=core_runner, args=(num_threads, target_channel), daemon=True)
        worker_thread.start()
        
        bot.reply_to(message, f"🚀 **Iniciando proceso**\nCanal: `{target_channel}`\nHilos: `{num_threads}`", parse_mode="Markdown")
        
    except ValueError:
        bot.reply_to(message, "Asegúrate de enviar un número válido de hilos.")
    except Exception as e:
        bot.reply_to(message, f"Error al iniciar: {str(e)}")

@bot.message_handler(commands=['status'])
def check_status(message):
    if not task_running:
        bot.reply_to(message, "🔴 El proceso está detenido.")
        return
        
    with lock:
        elapsed = datetime.datetime.now() - start_time if start_time else 0
        duration = f"{int(elapsed.total_seconds())}s" if start_time else "0s"
        
        status_msg = (
            "📊 **Estado Actual**\n\n"
            f"• **Conexiones Activas:** `{connections}`\n"
            f"• **Intentos:** `{attempts}`\n"
            f"• **Pings:** `{pings}`\n"
            f"• **Heartbeats:** `{heartbeats}`\n"
            f"• **Tiempo transcurrido:** `{duration}`\n"
            f"• **Channel ID:** `{channel_id or 'N/A'}`"
        )
    bot.reply_to(message, status_msg, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_execution(message):
    global stop_signal, task_running
    if not task_running:
        bot.reply_to(message, "No hay ningún proceso activo para detener.")
        return
        
    stop_signal = True
    bot.reply_to(message, "🛑 Enviando señal de parada... Esto puede tomar unos segundos.")

if __name__ == "__main__":
    print("[+] Bot levantado y escuchando peticiones en Telegram...")
    bot.infinity_polling()