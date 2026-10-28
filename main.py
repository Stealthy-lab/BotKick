import subprocess
import sys

# --- AUTO-INSTALADOR DE DEPENDENCIAS ---
def instalar_dependencias():
    paquetes = {
        "tls_client": "tls_client",
        "telebot": "pytelegrambotapi",
        "websockets": "websockets",
        "websockets_proxy": "websockets-proxy"
    }
    
    for mod, pkg in paquetes.items():
        try:
            __import__(mod)
        except ImportError:
            print(f"[+] Instalando dependencia necesaria: {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

instalar_dependencias()

# --- IMPORTACIONES ---
import asyncio
import datetime
import json
import os
import random
import threading
import time
from threading import Semaphore, Thread

import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
import tls_client
import websockets
from websockets_proxy import Proxy, proxy_connect

# --- CONFIGURACIÓN DE SEGURIDAD Y TELEGRAM ---
TELEGRAM_TOKEN = "8684389899:AAExwUA_YvB3f8m1i6eIApHXVHH1AJ07EdU"
bot = telebot.TeleBot(TELEGRAM_TOKEN)

ADMIN_ID = 8163467261  # ⚠️ Reemplaza por tu ID de Telegram (@userinfobot)
CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
WHITELIST_FILE = "autorizados.json"
PROXY_FILE = "proxies.txt"

# --- GESTIÓN DE USUARIOS Y PROXIES ---
def cargar_autorizados():
    if not os.path.exists(WHITELIST_FILE):
        datos = {str(ADMIN_ID): {"username": "Admin", "fecha": str(datetime.date.today())}}
        guardar_autorizados(datos)
        return datos
    try:
        with open(WHITELIST_FILE, "r") as f:
            datos = json.load(f)
            if str(ADMIN_ID) not in datos:
                datos[str(ADMIN_ID)] = {"username": "Admin", "fecha": str(datetime.date.today())}
            return datos
    except:
        return {str(ADMIN_ID): {"username": "Admin", "fecha": str(datetime.date.today())}}

def guardar_autorizados(diccionario):
    try:
        with open(WHITELIST_FILE, "w") as f:
            json.dump(diccionario, f, indent=4)
    except Exception as e:
        print(f"[!] Error guardando whitelist: {e}")

usuarios_autorizados = cargar_autorizados()

def cargar_proxies():
    if not os.path.exists(PROXY_FILE):
        return []
    with open(PROXY_FILE, "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

lista_proxies = cargar_proxies()

def es_autorizado(message_or_call):
    user_id = str(message_or_call.from_user.id)
    return user_id in usuarios_autorizados

# --- DICCIONARIO DE SESIONES (MULTIUSUARIO / MULTITAREA) ---
SESIONES = {}
lock = threading.Lock()

def clean_channel_name(name):
    if "kick.com/" in name:
        parts = name.split("kick.com/")
        return parts[1].split("/")[0].split("?")[0].lower()
    return name.lower()

def get_channel_info_and_viewers(name):
    try:
        s = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
        s.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://kick.com/',
            'Origin': 'https://kick.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        })
        response = s.get(f'https://kick.com/api/v2/channels/{name}')
        if response.status_code == 200:
            data = response.json()
            channel_id = data.get("id")
            livestream = data.get("livestream")
            
            if livestream and livestream.get("is_live"):
                viewers = livestream.get("viewer_count", 0)
                return channel_id, viewers, True
            else:
                return channel_id, 0, False
    except Exception as e:
        pass
    return None, 0, False

def get_token(proxy_url=None):
    try:
        s = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
        
        if proxy_url:
            s.proxies = {
                "http": proxy_url,
                "https": proxy_url
            }

        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        })
        s.get("https://kick.com")
        s.headers["X-CLIENT-TOKEN"] = CLIENT_TOKEN
        response = s.get('https://websockets.kick.com/viewer/v1/token')
        if response.status_code == 200:
            return response.json().get("data", {}).get("token")
    except:
        pass
    return None

# --- BUCLE DE CONEXIÓN CON SOPORTE DE PROXY WSS ---
async def websocket_handler(token, session_id, proxy_url):
    if session_id not in SESIONES:
        return
    
    sesion = SESIONES[session_id]
    connected = False
    
    try:
        url = f"wss://websockets.kick.com/viewer/v1/connect?token={token}"
        
        if proxy_url:
            proxy = Proxy.from_url(proxy_url)
            async with proxy_connect(url, proxy=proxy) as ws:
                with lock:
                    sesion['connections'] += 1
                connected = True
                
                handshake = {
                    "type": "channel_handshake",
                    "data": {"message": {"channelId": sesion['channel_id']}}
                }
                await ws.send(json.dumps(handshake))
                with lock:
                    sesion['heartbeats'] += 1
                
                while not sesion['stop_signal']:
                    await ws.send(json.dumps({"type": "ping"}))
                    with lock:
                        sesion['pings'] += 1
                    
                    wait_time = 12 + random.randint(1, 5)
                    for _ in range(wait_time):
                        if sesion['stop_signal']:
                            break
                        await asyncio.sleep(1)
        else:
            async with websockets.connect(url) as ws:
                with lock:
                    sesion['connections'] += 1
                connected = True
                
                handshake = {
                    "type": "channel_handshake",
                    "data": {"message": {"channelId": sesion['channel_id']}}
                }
                await ws.send(json.dumps(handshake))
                with lock:
                    sesion['heartbeats'] += 1
                
                while not sesion['stop_signal']:
                    await ws.send(json.dumps({"type": "ping"}))
                    with lock:
                        sesion['pings'] += 1
                    
                    wait_time = 12 + random.randint(1, 5)
                    for _ in range(wait_time):
                        if sesion['stop_signal']:
                            break
                        await asyncio.sleep(1)
    except:
        pass
    finally:
        if connected and session_id in SESIONES:
            with lock:
                if sesion['connections'] > 0:
                    sesion['connections'] -= 1

def send_connection(session_id):
    if session_id not in SESIONES:
        return
    
    sesion = SESIONES[session_id]
    with lock:
        sesion['attempts'] += 1
    
    proxy_url = random.choice(lista_proxies) if lista_proxies else None
    
    try:
        token = get_token(proxy_url)
        if token and sesion['channel_id']:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(websocket_handler(token, session_id, proxy_url))
            loop.close()
    except:
        pass
    finally:
        if session_id in SESIONES:
            sesion['thread_limit'].release()

def core_runner(session_id):
    sesion = SESIONES.get(session_id)
    if not sesion:
        return

    channel_id, viewers, is_live = get_channel_info_and_viewers(sesion['channel'])
    if not channel_id:
        sesion['status'] = "❌ Error: Canal no encontrado"
        return

    sesion['channel_id'] = channel_id
    sesion['live_viewers'] = viewers
    sesion['is_live'] = is_live
    sesion['status'] = "🟢 En ejecución"
    
    while not sesion['stop_signal']:
        if sesion['thread_limit'].acquire(timeout=1):
            if sesion['stop_signal']:
                break
            t = Thread(target=send_connection, args=(session_id,), daemon=True)
            t.start()
            time.sleep(0.35)

    sesion['status'] = "🔴 Detenido"

# --- GENERADOR DEL PANEL TÁCTIL ---
def generar_panel_ui(session_id):
    sesion = SESIONES.get(session_id)
    if not sesion:
        return "⚠️ La sesión ya no existe.", None

    _, current_viewers, is_live = get_channel_info_and_viewers(sesion['channel'])
    sesion['live_viewers'] = current_viewers
    sesion['is_live'] = is_live

    viewers_str = f"`{current_viewers}` 👥" if is_live else "`Offline` 🔴"

    elapsed = datetime.datetime.now() - sesion['start_time']
    duracion = f"{int(elapsed.total_seconds())}s"

    texto = (
        "🔥 **CENTER CONTROL PANEL - KICK BOT** 🔥\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Operador:** `{sesion['owner_name']}`\n"
        f"📺 **Canal Target:** `{sesion['channel']}`\n"
        f"👁️ **Audiencia en Kick:** {viewers_str}\n"
        f"📌 **Estado Bot:** {sesion['status']}\n\n"
        f"🚀 **Potencia Solicitada:** `{sesion['max_threads']}` Hilos\n"
        f"📈 **Conexiones Estables:** `{sesion['connections']}` / `{sesion['max_threads']}`\n"
        f"🔄 **Intentos Totales:** `{sesion['attempts']}`\n"
        f"📡 **Pings Enviados:** `{sesion['pings']}` | 💓 **Pulsos:** `{sesion['heartbeats']}`\n"
        f"⏱️ **Uptime Sesión:** `{duracion}`\n"
        f"🌐 **Proxies Cargados:** `{len(lista_proxies)}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 **ACCIONES RÁPIDAS & PRESETS DE POTENCIA** 👇"
    )

    markup = InlineKeyboardMarkup()
    
    if not sesion['stop_signal']:
        btn_refrescar = InlineKeyboardButton("🔄 Refrescar Panel", callback_data=f"refresh_{session_id}")
        btn_stop = InlineKeyboardButton("🛑 APAGAR BOT", callback_data=f"stop_{session_id}")
        markup.row(btn_refrescar, btn_stop)

        p15 = InlineKeyboardButton("⚡ 15 Viewers", callback_data=f"set_{session_id}_15")
        p30 = InlineKeyboardButton("⚡ 30 Viewers", callback_data=f"set_{session_id}_30")
        p50 = InlineKeyboardButton("🔥 50 Viewers", callback_data=f"set_{session_id}_50")
        markup.row(p15, p30, p50)

        p80 = InlineKeyboardButton("🚀 80 Viewers", callback_data=f"set_{session_id}_80")
        p100 = InlineKeyboardButton("💥 100 Viewers", callback_data=f"set_{session_id}_100")
        p150 = InlineKeyboardButton("👑 150 Viewers", callback_data=f"set_{session_id}_150")
        markup.row(p80, p100, p150)

        btn_restart = InlineKeyboardButton("♻️ Reiniciar Conexiones", callback_data=f"restart_{session_id}")
        markup.row(btn_restart)
    else:
        btn_relaunch = InlineKeyboardButton("🚀 Volver a Lanzar (50 Hilos)", callback_data=f"relaunch_{session_id}")
        markup.row(btn_relaunch)

    return texto, markup

# --- MANEJADOR DE EVENTOS TÁCTILES ---
@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    user_id = str(call.from_user.id)
    
    if not es_autorizado(call):
        bot.answer_callback_query(call.id, "⛔ Acceso denegado.", show_alert=True)
        return

    data = call.data

    if data.startswith("refresh_"):
        session_id = data.replace("refresh_", "")
        texto, markup = generar_panel_ui(session_id)
        try:
            bot.edit_message_text(texto, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id, "✅ Métricas actualizadas")
        except:
            bot.answer_callback_query(call.id, "Sin cambios")

    elif data.startswith("set_"):
        parts = data.split("_")
        session_id = parts[1]
        new_threads = int(parts[2])

        if session_id in SESIONES:
            if str(call.from_user.id) != str(SESIONES[session_id]['owner_id']) and call.from_user.id != ADMIN_ID:
                bot.answer_callback_query(call.id, "⛔ Solo el creador puede cambiar la potencia.", show_alert=True)
                return

            channel = SESIONES[session_id]['channel']
            SESIONES[session_id]['stop_signal'] = True
            
            bot.answer_callback_query(call.id, f"⚙️ Cambiando potencia a {new_threads} viewers...")
            time.sleep(1.5)

            SESIONES[user_id] = {
                'owner_id': call.from_user.id,
                'owner_name': call.from_user.first_name,
                'channel': channel,
                'channel_id': None,
                'live_viewers': 0,
                'is_live': False,
                'max_threads': new_threads,
                'thread_limit': Semaphore(new_threads),
                'start_time': datetime.datetime.now(),
                'connections': 0,
                'attempts': 0,
                'pings': 0,
                'heartbeats': 0,
                'stop_signal': False,
                'status': "⏳ Aplicando Preset..."
            }

            worker = Thread(target=core_runner, args=(user_id,), daemon=True)
            worker.start()

            time.sleep(1)
            texto, markup = generar_panel_ui(user_id)
            bot.edit_message_text(texto, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("restart_"):
        session_id = data.replace("restart_", "")
        if session_id in SESIONES:
            channel = SESIONES[session_id]['channel']
            threads = SESIONES[session_id]['max_threads']
            SESIONES[session_id]['stop_signal'] = True
            
            bot.answer_callback_query(call.id, "♻️ Reiniciando sockets...")
            time.sleep(1.5)

            SESIONES[user_id] = {
                'owner_id': call.from_user.id,
                'owner_name': call.from_user.first_name,
                'channel': channel,
                'channel_id': None,
                'live_viewers': 0,
                'is_live': False,
                'max_threads': threads,
                'thread_limit': Semaphore(threads),
                'start_time': datetime.datetime.now(),
                'connections': 0,
                'attempts': 0,
                'pings': 0,
                'heartbeats': 0,
                'stop_signal': False,
                'status': "⏳ Reiniciando..."
            }

            worker = Thread(target=core_runner, args=(user_id,), daemon=True)
            worker.start()

            time.sleep(1)
            texto, markup = generar_panel_ui(user_id)
            bot.edit_message_text(texto, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("stop_"):
        session_id = data.replace("stop_", "")
        if session_id in SESIONES:
            if str(call.from_user.id) != str(SESIONES[session_id]['owner_id']) and call.from_user.id != ADMIN_ID:
                bot.answer_callback_query(call.id, "⛔ Sin permisos.", show_alert=True)
                return

            SESIONES[session_id]['stop_signal'] = True
            SESIONES[session_id]['status'] = "🛑 Detenido"
            
            texto, markup = generar_panel_ui(session_id)
            bot.edit_message_text(texto, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id, "🛑 Proceso detenido.")

# --- COMANDOS PRINCIPALES ---
@bot.message_handler(commands=['run'])
def start_execution(message):
    if not es_autorizado(message):
        bot.reply_to(message, "⛔ No estás autorizado.")
        return

    user_id = str(message.from_user.id)

    if user_id in SESIONES and not SESIONES[user_id]['stop_signal']:
        SESIONES[user_id]['stop_signal'] = True
        time.sleep(1.5)

    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Formato: `/run <canal> [cantidad_opcional]`\nEjemplo: `/run streamer 50`", parse_mode="Markdown")
            return

        target_channel = clean_channel_name(args[1])
        num_threads = int(args[2]) if len(args) >= 3 else 30

        SESIONES[user_id] = {
            'owner_id': message.from_user.id,
            'owner_name': message.from_user.first_name,
            'channel': target_channel,
            'channel_id': None,
            'live_viewers': 0,
            'is_live': False,
            'max_threads': num_threads,
            'thread_limit': Semaphore(num_threads),
            'start_time': datetime.datetime.now(),
            'connections': 0,
            'attempts': 0,
            'pings': 0,
            'heartbeats': 0,
            'stop_signal': False,
            'status': "⏳ Lanzando Sockets..."
        }

        worker = Thread(target=core_runner, args=(user_id,), daemon=True)
        worker.start()

        time.sleep(1)
        texto, markup = generar_panel_ui(user_id)
        bot.reply_to(message, texto, parse_mode="Markdown", reply_markup=markup)

    except Exception as e:
        bot.reply_to(message, f"Error al iniciar: {str(e)}")

@bot.message_handler(commands=['panel', 'status'])
def show_panel(message):
    if not es_autorizado(message):
        return

    user_id = str(message.from_user.id)
    if user_id in SESIONES:
        texto, markup = generar_panel_ui(user_id)
        bot.reply_to(message, texto, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.reply_to(message, "No tienes ninguna sesión activa. Usa `/run <canal>` para lanzar una.", parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_execution(message):
    if not es_autorizado(message):
        return

    user_id = str(message.from_user.id)
    if user_id in SESIONES and not SESIONES[user_id]['stop_signal']:
        SESIONES[user_id]['stop_signal'] = True
        SESIONES[user_id]['status'] = "🔴 Detenido"
        bot.reply_to(message, f"🛑 Sesión de {message.from_user.first_name} apagada.")
    else:
        bot.reply_to(message, "No tienes procesos corriendo.")

if __name__ == "__main__":
    print(f"[+] Bot activo. Se cargaron {len(lista_proxies)} proxies desde 'proxies.txt'.")
    bot.infinity_polling()
