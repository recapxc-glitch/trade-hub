import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit


ROOT = Path(__file__).resolve().parent
UPLOADS_PATH = ROOT / "uploads"
DATABASE_PATH = Path(os.environ.get("TREDE_HUB_DB", ROOT / "data" / "trede-hub.sqlite3"))
HOST = os.environ.get("TREDE_HUB_HOST", "127.0.0.1")
PORT = int(os.environ.get("TREDE_HUB_PORT", "8000"))
SESSION_TTL_SECONDS = 12 * 60 * 60
PASSWORD_ITERATIONS = 310_000
SESSIONS = {}
SELLER_SESSIONS = {}
SESSION_LOCK = threading.Lock()

DEFAULT_CATEGORIES = [
    {"name": "Électronique", "label": "Électronique", "icon": "▣"},
    {"name": "Informatique", "label": "Ordinateurs & informatique", "icon": "💻"},
    {"name": "Mode & vêtements", "label": "Mode & vêtements", "icon": "♧"},
    {"name": "Chaussures", "label": "Chaussures", "icon": "👟"},
    {"name": "Maison", "label": "Maison & jardin", "icon": "⌂"},
    {"name": "Beauté", "label": "Beauté & santé", "icon": "✿"},
    {"name": "Sports", "label": "Sports & loisirs", "icon": "⚽"},
    {"name": "Outils", "label": "Machines & outils", "icon": "⚙"},
    {"name": "Automobile", "label": "Automobiles", "icon": "▰"},
    {"name": "Jouets", "label": "Jouets & jeux", "icon": "♧"},
    {"name": "Bébé", "label": "Produits pour bébés", "icon": "♙"},
    {"name": "Industrie", "label": "Équipements industriels", "icon": "⚒"},
]

DEFAULT_PRODUCTS = [
    {"name": "Smartphone Android — 128 Go", "cat": "Électronique", "price": "129,00 $", "old": "159,00 $", "discount": "-19%", "rating": "4,8", "reviews": "(248)", "emoji": "📱", "supplier": "Tech Market"},
    {"name": "Ordinateur portable 15 pouces", "cat": "Informatique", "price": "489,00 $", "old": "559,00 $", "discount": "-13%", "rating": "4,7", "reviews": "(186)", "emoji": "💻", "supplier": "Nova Computing"},
    {"name": "Baskets sport unisexes", "cat": "Chaussures", "price": "29,90 $", "old": "39,90 $", "discount": "-25%", "rating": "4,6", "reviews": "(321)", "emoji": "👟", "supplier": "Urban Steps"},
    {"name": "Écouteurs sans fil Bluetooth", "cat": "Électronique", "price": "18,50 $", "old": "24,00 $", "discount": "-23%", "rating": "4,5", "reviews": "(112)", "emoji": "🎧", "supplier": "Sound Avenue"},
    {"name": "Friteuse à air 5,5 L", "cat": "Maison", "price": "64,90 $", "old": "79,90 $", "discount": "-19%", "rating": "4,7", "reviews": "(93)", "emoji": "🍳", "supplier": "Home Essentials"},
    {"name": "Sweat à capuche unisexe", "cat": "Mode & vêtements", "price": "22,90 $", "old": "32,00 $", "discount": "-28%", "rating": "4,6", "reviews": "(154)", "emoji": "🧥", "supplier": "Urban Textile"},
    {"name": "Montre connectée sport", "cat": "Électronique", "price": "35,00 $", "old": "45,00 $", "discount": "-22%", "rating": "4,4", "reviews": "(89)", "emoji": "⌚", "supplier": "Tech Market"},
    {"name": "Lampe de bureau LED", "cat": "Maison", "price": "17,90 $", "old": "23,00 $", "discount": "-22%", "rating": "4,5", "reviews": "(67)", "emoji": "💡", "supplier": "Home Essentials"},
    {"name": "Sac à dos polyvalent", "cat": "Mode & vêtements", "price": "26,50 $", "old": "34,00 $", "discount": "-22%", "rating": "4,6", "reviews": "(103)", "emoji": "🎒", "supplier": "Urban Textile"},
    {"name": "Clavier sans fil compact", "cat": "Informatique", "price": "21,90 $", "old": "29,90 $", "discount": "-27%", "rating": "4,5", "reviews": "(78)", "emoji": "⌨️", "supplier": "Nova Computing"},
    {"name": "Ballon de football", "cat": "Sports", "price": "15,00 $", "old": "19,00 $", "discount": "-21%", "rating": "4,7", "reviews": "(121)", "emoji": "⚽", "supplier": "Active Goods"},
    {"name": "Perceuse sans fil", "cat": "Outils", "price": "58,00 $", "old": "72,00 $", "discount": "-19%", "rating": "4,4", "reviews": "(56)", "emoji": "🛠️", "supplier": "Pro Tools"},
]

DEFAULT_CONTENT = {
    "eyebrow": "La marketplace pour les professionnels",
    "title": "Votre partenaire de confiance pour le commerce.",
    "description": "Trouvez des produits de qualité auprès de fournisseurs et comparez les offres pour faire grandir votre activité.",
    "button": "Explorer les produits",
    "benefit1": "Choix varié",
    "benefit2": "Achats en gros",
    "benefit3": "Offres comparables",
    "brand_name": "Trede Hub",
    "tagline": "Plus de produits, plus d'opportunités",
    "search_placeholder": "Rechercher un produit, une catégorie ou un fournisseur...",
    "nav_sales": "Meilleures ventes",
    "nav_suppliers": "Fournisseurs",
    "nav_wholesale": "Achats en gros",
    "nav_delivery": "Livraison",
    "nav_help": "Centre d'aide",
    "categories_title": "Toutes les catégories",
    "products_title": "Meilleures ventes",
    "products_subtitle": "Exemples de produits pour présenter la boutique.",
    "footer_notice": "Tous droits réservés",
    "footer_disclaimer": "Prototype de démonstration · Produits et prix fictifs",
    "logo_text": "T",
    "logo_url": "",
    "hero_image_url": "",
    "hero_video_url": "",
    "intro_video_url": "",
    "intro_image_url": "",
    "ad_image_url": "",
    "intro_ad_title": "Espace publicitaire",
    "intro_ad_description": "Votre publicité peut apparaître ici.",
    "welcome_ad_enabled": "1",
    "films_enabled": "1",
    "films_brand_name": "F4 studio film",
    "films_board_title": "Films et séries",
    "films_logo_url": "",
    "footer_logo_1_url": "",
    "footer_logo_2_url": "",
    "footer_logo_3_url": "",
    "footer_logo_4_url": "",
    "footer_logo_5_url": "",
    "footer_logo_6_url": "",
    "primary_color": "#ff7900",
    "header_color": "#101315",
}


def connect_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def compress_film_video(source_path, output_path, maximum_bytes):
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("Pou konprese fim otomatikman, enstale depandans yo ak « python -m pip install -r requirements.txt ».") from exc

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(source_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", probe.stderr)
    if not duration_match:
        raise ValueError("FFmpeg pa ka detèmine dire videyo a. Verifye fichye a.")
    hours, minutes, seconds = duration_match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if duration <= 0:
        raise ValueError("Dire videyo a pa valab.")

    maximum_bytes = min(maximum_bytes, int(source_path.stat().st_size * 0.90))
    audio_bitrate = 128_000
    video_bitrate = int(maximum_bytes * 8 / duration * 0.90) - audio_bitrate
    if video_bitrate < 300_000:
        raise ValueError("Espas ki rete a pa ase pou konprese fim nan nan yon kalite ki akseptab.")
    if video_bitrate >= 8_000_000:
        max_width, max_height = 3840, 2160
    elif video_bitrate >= 3_000_000:
        max_width, max_height = 1920, 1080
    else:
        max_width, max_height = 1280, 720

    pass_log = output_path.with_suffix(".pass")
    null_output = "NUL" if os.name == "nt" else os.devnull
    common = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_path),
        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
        "-vf", f"scale=w='min(iw,{max_width})':h='min(ih,{max_height})':force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-b:v", str(video_bitrate), "-maxrate", str(int(video_bitrate * 1.5)),
        "-bufsize", str(video_bitrate * 2), "-passlogfile", str(pass_log),
    ]

    try:
        for attempt in range(3):
            for log_path in output_path.parent.glob(pass_log.name + "*"):
                log_path.unlink(missing_ok=True)
            bitrate = max(int(video_bitrate * (0.75 ** attempt)), 300_000)
            command = common.copy()
            command[command.index("-b:v") + 1] = str(bitrate)
            command[command.index("-maxrate") + 1] = str(int(bitrate * 1.5))
            command[command.index("-bufsize") + 1] = str(bitrate * 2)
            first_pass = subprocess.run(
                command + ["-pass", "1", "-an", "-f", "null", null_output],
                capture_output=True,
                text=True,
                check=False,
            )
            if first_pass.returncode:
                details = first_pass.stderr.strip()[-1000:]
                raise RuntimeError("Premye etap konpresyon an echwe: " + details)
            second_pass = subprocess.run(
                command + [
                    "-pass", "2", "-c:a", "aac", "-b:a", str(audio_bitrate),
                    "-movflags", "+faststart", str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if second_pass.returncode:
                details = second_pass.stderr.strip()[-1000:]
                raise RuntimeError("Dezyèm etap konpresyon an echwe: " + details)
            if output_path.stat().st_size <= maximum_bytes:
                return
            output_path.unlink()
        raise RuntimeError("Konpresyon an pa t ka mete fim nan nan limit 4 Go la.")
    finally:
        for log_path in output_path.parent.glob(pass_log.name + "*"):
            log_path.unlink(missing_ok=True)


@contextmanager
def database():
    db = connect_db()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize_database():
    with database() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS owners (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                icon TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                cat TEXT NOT NULL,
                price TEXT NOT NULL,
                old TEXT NOT NULL,
                discount TEXT NOT NULL,
                rating TEXT NOT NULL,
                reviews TEXT NOT NULL,
                emoji TEXT NOT NULL,
                supplier TEXT NOT NULL,
                image_url TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS sellers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                whatsapp TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                blue_badge INTEGER NOT NULL DEFAULT 0,
                gold_badge INTEGER NOT NULL DEFAULT 0,
                profile_photo TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                department TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                street TEXT NOT NULL DEFAULT '',
                address_details TEXT NOT NULL DEFAULT '',
                password_salt BLOB,
                password_hash BLOB,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS films (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                video_url TEXT NOT NULL DEFAULT '',
                genre TEXT NOT NULL DEFAULT 'Autres',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS film_comments (
                id INTEGER PRIMARY KEY,
                film_id INTEGER NOT NULL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(film_id) REFERENCES films(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                seller_id INTEGER NOT NULL,
                sender_role TEXT NOT NULL CHECK(sender_role IN ('owner','seller')),
                sender_name TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(seller_id) REFERENCES sellers(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS site_content (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS visitor_activity (
                visitor_id TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                pageviews INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS visitor_daily (
                visitor_id TEXT NOT NULL,
                visit_date TEXT NOT NULL,
                pageviews INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(visitor_id, visit_date)
            );
            CREATE TABLE IF NOT EXISTS seller_page_views (
                id INTEGER PRIMARY KEY,
                seller_id INTEGER NOT NULL,
                visitor_id TEXT NOT NULL,
                viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(seller_id) REFERENCES sellers(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS seller_follows (
                seller_id INTEGER NOT NULL,
                visitor_id TEXT NOT NULL,
                followed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(seller_id, visitor_id),
                FOREIGN KEY(seller_id) REFERENCES sellers(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS purchase_clicks (
                id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL,
                seller_id INTEGER NOT NULL,
                visitor_id TEXT NOT NULL,
                clicked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
                FOREIGN KEY(seller_id) REFERENCES sellers(id) ON DELETE CASCADE
            );
            """
        )
        seller_columns = {row["name"] for row in db.execute("PRAGMA table_info(sellers)")}
        if "password_salt" not in seller_columns:
            db.execute("ALTER TABLE sellers ADD COLUMN password_salt BLOB")
        if "password_hash" not in seller_columns:
            db.execute("ALTER TABLE sellers ADD COLUMN password_hash BLOB")
        if "profile_photo" not in seller_columns:
            db.execute("ALTER TABLE sellers ADD COLUMN profile_photo TEXT NOT NULL DEFAULT ''")
        if "show_whatsapp" not in seller_columns:
            db.execute("ALTER TABLE sellers ADD COLUMN show_whatsapp INTEGER NOT NULL DEFAULT 1")
        for column in ("country", "department", "city", "street", "address_details"):
            if column not in seller_columns:
                db.execute(f"ALTER TABLE sellers ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        film_columns = {row["name"] for row in db.execute("PRAGMA table_info(films)")}
        if "genre" not in film_columns:
            db.execute("ALTER TABLE films ADD COLUMN genre TEXT NOT NULL DEFAULT 'Autres'")
        product_columns = {row["name"] for row in db.execute("PRAGMA table_info(products)")}
        if "image_url" not in product_columns:
            db.execute("ALTER TABLE products ADD COLUMN image_url TEXT NOT NULL DEFAULT ''")
        if "seller_id" not in product_columns:
            db.execute("ALTER TABLE products ADD COLUMN seller_id INTEGER")
        category_columns = {row["name"] for row in db.execute("PRAGMA table_info(categories)")}
        if "image_url" not in category_columns:
            db.execute("ALTER TABLE categories ADD COLUMN image_url TEXT NOT NULL DEFAULT ''")
        if "label" not in category_columns:
            db.execute("ALTER TABLE categories ADD COLUMN label TEXT NOT NULL DEFAULT ''")
            db.execute("UPDATE categories SET label = name WHERE label = ''")
        seeded = db.execute(
            "SELECT value FROM app_settings WHERE key = 'catalog_seeded'"
        ).fetchone()
        if seeded is None:
            if (
                db.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0
                and db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0
            ):
                db.executemany(
                    "INSERT INTO categories (name, icon, label) VALUES (?, ?, ?)",
                    [(item["name"], item["icon"], item["label"]) for item in DEFAULT_CATEGORIES],
                )
                db.executemany(
                    """INSERT INTO products
                       (name, cat, price, old, discount, rating, reviews, emoji, supplier)
                       VALUES (:name, :cat, :price, :old, :discount, :rating, :reviews, :emoji, :supplier)""",
                    DEFAULT_PRODUCTS,
                )
            db.execute(
                "INSERT INTO app_settings (key, value) VALUES ('catalog_seeded', '1')"
            )
        db.executemany(
            "INSERT OR IGNORE INTO site_content (key, value) VALUES (?, ?)",
            list(DEFAULT_CONTENT.items()),
        )
        db.execute(
            """UPDATE site_content SET value = 'F4 studio film'
               WHERE key = 'films_brand_name'
               AND value IN ('Trede Hub Cinéma', 'Trede Hub Cinema')"""
        )


def make_password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return salt, digest


def text_field(data, key, limit, required=True):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"Le champ « {key} » doit être du texte.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"Le champ « {key} » est obligatoire.")
    if len(value) > limit:
        raise ValueError(f"Le champ « {key} » dépasse {limit} caractères.")
    return value


def product_fields(data):
    if not isinstance(data, dict):
        raise ValueError("Produit invalide.")
    result = {
        "name": text_field(data, "name", 160),
        "cat": text_field(data, "cat", 80),
        "price": text_field(data, "price", 40),
        "old": text_field(data, "old", 40, required=False),
        "discount": text_field(data, "discount", 20, required=False),
        "rating": text_field(data, "rating", 10, required=False),
        "reviews": text_field(data, "reviews", 20, required=False),
        "emoji": text_field(data, "emoji", 20, required=False),
        "supplier": text_field(data, "supplier", 100),
        "image_url": text_field(data, "image_url", 1000, required=False),
    }
    if result["image_url"] and not result["image_url"].startswith(("/uploads/", "https://", "http://")):
        raise ValueError("L'image du produit doit être un média téléversé ou un lien http(s).")
    if not result["emoji"]:
        result["emoji"] = "📦"
    return result


def category_fields(data):
    if not isinstance(data, dict):
        raise ValueError("Catégorie invalide.")
    icon = text_field(data, "icon", 12)
    name = text_field(data, "name", 80)
    label = text_field(data, "label", 100, required=False) or name
    image_url = text_field(data, "image_url", 1000, required=False)
    return {"name": name, "label": label, "icon": icon, "image_url": image_url}


class Handler(BaseHTTPRequestHandler):
    server_version = "TredeHub/1.0"

    def log_message(self, format_string, *args):
        print("%s - %s" % (self.address_string(), format_string % args))

    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Taille de requête invalide.") from exc
        if length <= 0 or length > 40 * 1024 * 1024:
            raise ValueError("La requête doit contenir au maximum 40 Mo de JSON.")
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON invalide.") from exc
        if not isinstance(value, dict):
            raise ValueError("Le corps JSON doit être un objet.")
        return value

    def validate_origin(self):
        origin = self.headers.get("Origin")
        if origin and origin.rstrip("/") != f"http://{self.headers.get('Host', '')}":
            self.send_json(403, {"error": "Origine de requête refusée."})
            return False
        return True

    def owner_id(self):
        cookie = self.headers.get("Cookie", "")
        token = next(
            (part.partition("=")[2] for part in cookie.split("; ") if part.startswith("trede_session=")),
            "",
        )
        if not token:
            return None
        now = time.time()
        with SESSION_LOCK:
            session = SESSIONS.get(token)
            if not session or session[1] <= now:
                SESSIONS.pop(token, None)
                return None
            return session[0]

    def seller_id(self):
        cookie = self.headers.get("Cookie", "")
        token = next((part.partition("=")[2] for part in cookie.split("; ") if part.startswith("trede_seller_session=")), "")
        if not token:
            return None
        now = time.time()
        with SESSION_LOCK:
            session = SELLER_SESSIONS.get(token)
            if not session or session[1] <= now:
                SELLER_SESSIONS.pop(token, None)
                return None
            return session[0]

    def create_seller_cookie(self, seller_id):
        token = secrets.token_urlsafe(32)
        with SESSION_LOCK:
            SELLER_SESSIONS[token] = (seller_id, time.time() + SESSION_TTL_SECONDS)
        return f"trede_seller_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL_SECONDS}"

    def require_seller(self):
        sid = self.seller_id()
        if sid is None:
            self.send_json(401, {"error":"Connectez-vous comme vendeur pour continuer."})
            return False
        with database() as db:
            row = db.execute("SELECT status FROM sellers WHERE id=?", (sid,)).fetchone()
        if not row or row["status"] != "active":
            self.send_json(403, {"error":"Votre compte vendeur est suspendu. Contactez le propriétaire."})
            return False
        return True

    def create_session_cookie(self, owner_id):
        token = secrets.token_urlsafe(32)
        with SESSION_LOCK:
            SESSIONS[token] = (owner_id, time.time() + SESSION_TTL_SECONDS)
        return f"trede_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL_SECONDS}"

    def require_owner(self):
        if self.owner_id() is None:
            self.send_json(401, {"error": "Connectez-vous comme propriétaire pour continuer."})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/contact/"):
            try: seller_id = int(path.rsplit("/",1)[1])
            except ValueError: self.send_error(404); return
            query = parse_qs(urlsplit(self.path).query)
            message = quote(query.get("message", ["Bonjour, je souhaite des informations sur un produit Trede Hub."])[0][:1500])
            with database() as db: seller = db.execute("SELECT whatsapp,status FROM sellers WHERE id=?",(seller_id,)).fetchone()
            if not seller or seller["status"] != "active": self.send_error(404, "Vendeur indisponible"); return
            digits = re.sub(r"[^0-9]", "", seller["whatsapp"])
            self.send_response(302); self.send_header("Location", f"https://wa.me/{digits}?text={message}"); self.send_header("Cache-Control","no-store"); self.end_headers(); return
        if path.startswith("/uploads/"):
            filename = Path(path.removeprefix("/uploads/")).name
            target = UPLOADS_PATH / filename
            if not filename or not target.is_file():
                self.send_error(404)
                return
            mime = {".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".webp":"image/webp", ".mp4":"video/mp4", ".webm":"video/webm"}.get(target.suffix.lower(), "application/octet-stream")
            size = target.stat().st_size
            start, end = 0, size - 1
            range_header = self.headers.get("Range")
            status = 200
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                if not match or not any(match.groups()):
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), size - 1) if last else size - 1
                else:
                    suffix_length = int(last)
                    start = max(size - suffix_length, 0)
                if start >= size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                with target.open("rb") as media_file:
                    media_file.seek(start)
                    remaining = length
                    while remaining:
                        chunk = media_file.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (OSError, ConnectionError):
                return
            return
        if path in ("/", "/trede-hub.html"):
            try:
                body = (ROOT / "trede-hub.html").read_bytes()
            except OSError:
                self.send_error(500, "Impossible de lire la page Trede Hub.")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.end_headers()
            self.wfile.write(body)
            return
        static_files = {
            "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
            "/service-worker.js": ("service-worker.js", "text/javascript; charset=utf-8"),
            "/app-icon-192.png": ("app-icon-192.png", "image/png"),
            "/app-icon-512.png": ("app-icon-512.png", "image/png"),
        }
        if path in static_files:
            filename, mime = static_files[path]
            try:
                body = (ROOT / filename).read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/owner/analytics":
            if not self.require_owner(): return
            with database() as db:
                online = db.execute("SELECT COUNT(*) FROM visitor_activity WHERE last_seen >= datetime('now','-90 seconds')").fetchone()[0]
                sellers = db.execute("SELECT COUNT(*) FROM sellers WHERE status='active'").fetchone()[0]
                pending = db.execute("SELECT COUNT(*) FROM sellers WHERE status='pending'").fetchone()[0]
                total_views = db.execute("SELECT COALESCE(SUM(pageviews),0) FROM visitor_activity").fetchone()[0]
                daily_rows = [dict(r) for r in db.execute("""SELECT visit_date AS day, COUNT(*) AS visitors,
                    COALESCE(SUM(pageviews),0) AS pageviews FROM visitor_daily
                    WHERE visit_date >= date('now','-6 days') GROUP BY visit_date ORDER BY visit_date""")]
                seller_views = [dict(r) for r in db.execute("""SELECT s.id,s.name,s.status,COUNT(v.id) AS views,
                    (SELECT COUNT(*) FROM products p WHERE p.seller_id=s.id) AS products
                    FROM sellers s LEFT JOIN seller_page_views v ON v.seller_id=s.id
                    GROUP BY s.id ORDER BY views DESC,s.name""")]
                purchase_daily = [dict(r) for r in db.execute("""SELECT date(clicked_at) AS day,COUNT(DISTINCT visitor_id) AS clicks
                    FROM purchase_clicks WHERE clicked_at>=datetime('now','-6 days')
                    GROUP BY date(clicked_at) ORDER BY day""")]
                purchase_sellers = [dict(r) for r in db.execute("""SELECT s.id,s.name,COUNT(pc.id) AS clicks,
                    COUNT(DISTINCT CASE WHEN date(pc.clicked_at)=date('now') THEN pc.visitor_id END) AS today_clicks
                    FROM sellers s LEFT JOIN purchase_clicks pc ON pc.seller_id=s.id
                    GROUP BY s.id ORDER BY today_clicks DESC,clicks DESC,s.name""")]
                follower_daily = [dict(r) for r in db.execute("""SELECT date(followed_at) AS day,COUNT(*) AS followers
                    FROM seller_follows WHERE followed_at>=datetime('now','-6 days')
                    GROUP BY date(followed_at) ORDER BY day""")]
                follower_sellers = [dict(r) for r in db.execute("""SELECT s.id,s.name,COUNT(sf.visitor_id) AS followers
                    FROM sellers s LEFT JOIN seller_follows sf ON sf.seller_id=s.id
                    GROUP BY s.id ORDER BY followers DESC,s.name""")]
            self.send_json(200,{"online":online,"active_sellers":sellers,"pending_sellers":pending,"pageviews":total_views,"daily":daily_rows,"seller_views":seller_views,"purchase_daily":purchase_daily,"purchase_sellers":purchase_sellers,"follower_daily":follower_daily,"follower_sellers":follower_sellers})
            return
        if path == "/api/seller/stats":
            if not self.require_seller(): return
            sid=self.seller_id()
            with database() as db:
                product_count=db.execute("SELECT COUNT(*) FROM products WHERE seller_id=?",(sid,)).fetchone()[0]
                views=db.execute("SELECT COUNT(*) FROM seller_page_views WHERE seller_id=?",(sid,)).fetchone()[0]
                daily=[dict(r) for r in db.execute("SELECT date(viewed_at) AS day,COUNT(*) AS views FROM seller_page_views WHERE seller_id=? AND viewed_at>=datetime('now','-6 days') GROUP BY date(viewed_at) ORDER BY day",(sid,))]
            self.send_json(200,{"products":product_count,"views":views,"daily":daily}); return
        if path == "/api/auth/status":
            with database() as db:
                owner = db.execute("SELECT username FROM owners LIMIT 1").fetchone()
            self.send_json(200, {"setupRequired": owner is None, "authenticated": self.owner_id() is not None})
            return

        if path == "/api/site":
            with database() as db:
                products = [dict(row) for row in db.execute("""SELECT p.*, s.name AS seller_name,
                    COALESCE(s.blue_badge,0) AS blue_badge, COALESCE(s.gold_badge,0) AS gold_badge, COALESCE(s.profile_photo,'') AS profile_photo, s.whatsapp AS seller_whatsapp, COALESCE(s.show_whatsapp,1) AS seller_show_whatsapp, COALESCE(s.country,'') AS seller_country, COALESCE(s.department,'') AS seller_department, COALESCE(s.city,'') AS seller_city, COALESCE(s.street,'') AS seller_street, COALESCE(s.address_details,'') AS seller_address_details
                    FROM products p LEFT JOIN sellers s ON s.id=p.seller_id
                    WHERE p.seller_id IS NULL OR s.status='active' ORDER BY p.id DESC""")]
                categories = [dict(row) for row in db.execute("SELECT * FROM categories ORDER BY id")]
                content = {row["key"]: row["value"] for row in db.execute("SELECT key, value FROM site_content")}
            self.send_json(200, {"products": products, "categories": categories, "content": content})
            return
        if path == "/api/seller/follow":
            query = parse_qs(urlsplit(self.path).query)
            try: sid = int(query.get("seller_id", [""])[0])
            except (TypeError, ValueError): self.send_json(400, {"error":"Vendeur invalide."}); return
            visitor_id = query.get("visitor_id", [""])[0]
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", visitor_id): self.send_json(400, {"error":"Identifiant visiteur invalide."}); return
            with database() as db:
                seller = db.execute("SELECT id,status FROM sellers WHERE id=?", (sid,)).fetchone()
                if not seller or seller["status"] != "active": self.send_json(404, {"error":"Vendeur introuvable."}); return
                count = db.execute("SELECT COUNT(*) FROM seller_follows WHERE seller_id=?", (sid,)).fetchone()[0]
                following = db.execute("SELECT 1 FROM seller_follows WHERE seller_id=? AND visitor_id=?", (sid, visitor_id)).fetchone() is not None
            self.send_json(200, {"followers":count,"following":following}); return
        film_comments_match = re.fullmatch(r"/api/films/(\d+)/comments", path)
        if film_comments_match:
            film_id = int(film_comments_match.group(1))
            with database() as db:
                comments = [dict(row) for row in db.execute(
                    "SELECT id,film_id,author,body,created_at FROM film_comments WHERE film_id=? ORDER BY id ASC", (film_id,)
                )]
            self.send_json(200, {"comments": comments})
            return
        if path == "/api/films":
            with database() as db:
                films = [dict(row) for row in db.execute("SELECT id,title,description,image_url,video_url,genre FROM films ORDER BY id DESC")]
            self.send_json(200, {"films": films})
            return
        if path == "/api/seller/me":
            sid = self.seller_id()
            if sid is None:
                self.send_json(401, {"error":"Connectez-vous comme vendeur."}); return
            with database() as db:
                seller = db.execute("SELECT id,name,whatsapp,COALESCE(show_whatsapp,1) AS show_whatsapp,status,blue_badge,gold_badge,profile_photo,country,department,city,street,address_details FROM sellers WHERE id=?", (sid,)).fetchone()
                own_products = [dict(r) for r in db.execute("SELECT * FROM products WHERE seller_id=? ORDER BY id DESC", (sid,))]
            if not seller or seller["status"] != "active":
                self.send_json(403, {"error":"Compte vendeur suspendu."}); return
            with database() as db:
                view_count=db.execute("SELECT COUNT(*) FROM seller_page_views WHERE seller_id=?",(sid,)).fetchone()[0]
            self.send_json(200, {"seller":dict(seller),"products":own_products,"views":view_count}); return
        if path == "/api/messages":
            query = parse_qs(urlsplit(self.path).query)
            if self.owner_id() is not None:
                try: sid = int(query.get("seller_id", [""])[0])
                except ValueError: self.send_json(400, {"error":"Choisissez un vendeur."}); return
                with database() as db:
                    seller = db.execute("SELECT id FROM sellers WHERE id=?", (sid,)).fetchone()
                    if not seller: self.send_json(404, {"error":"Vendeur introuvable."}); return
                    rows = [dict(r) for r in db.execute("SELECT id,seller_id,sender_role,sender_name,body,created_at FROM messages WHERE seller_id=? ORDER BY id", (sid,))]
                self.send_json(200, {"messages": rows}); return
            sid = self.seller_id()
            if sid is None:
                self.send_json(401, {"error":"Connectez-vous comme propriétaire ou vendeur."}); return
            with database() as db:
                seller = db.execute("SELECT status FROM sellers WHERE id=?", (sid,)).fetchone()
                if not seller or seller["status"] != "active": self.send_json(403, {"error":"Compte vendeur suspendu."}); return
                rows = [dict(r) for r in db.execute("SELECT id,seller_id,sender_role,sender_name,body,created_at FROM messages WHERE seller_id=? ORDER BY id", (sid,))]
            self.send_json(200, {"messages": rows}); return
        if path == "/api/sellers":
            if not self.require_owner(): return
            with database() as db:
                sellers = [dict(r) for r in db.execute("SELECT id,name,whatsapp,status,blue_badge,gold_badge,profile_photo,created_at FROM sellers ORDER BY id DESC")]
            self.send_json(200, {"sellers":sellers}); return
        if path == "/api/owner/films":
            if not self.require_owner(): return
            with database() as db:
                films = [dict(r) for r in db.execute("SELECT * FROM films ORDER BY id DESC")]
            self.send_json(200, {"films":films}); return
        self.send_json(404, {"error": "Route introuvable."})

    def do_POST(self):
        path = urlsplit(self.path).path
        if not self.validate_origin():
            return
        if path == "/api/upload":
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            upload_types = {
                "image/png": ("png", 8 * 1024 * 1024),
                "image/jpeg": ("jpg", 8 * 1024 * 1024),
                "image/webp": ("webp", 8 * 1024 * 1024),
                "video/mp4": ("mp4", None),
                "video/webm": ("webm", None),
            }
            if content_type in upload_types:
                if self.owner_id() is None and not self.require_seller():
                    return
                extension, limit = upload_types[content_type]
                is_video = content_type.startswith("video/")
                if is_video:
                    try:
                        import imageio_ffmpeg
                        imageio_ffmpeg.get_ffmpeg_exe()
                    except (ImportError, RuntimeError, OSError):
                        self.close_connection = True
                        self.send_json(
                            503,
                            {"error": "Konpresyon fim mande FFmpeg. Enstale li ak « python -m pip install -r requirements.txt », epi rekòmanse sèvè a."},
                        )
                        return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.send_json(400, {"error": "Taille de fichier invalide."})
                    return
                if length <= 0:
                    self.close_connection = True
                    self.send_json(400, {"error": "Le fichier est vide ou sa taille est inconnue."})
                    return
                if limit is not None and length > limit:
                    self.close_connection = True
                    self.send_json(413, {"error": "Image trop volumineuse (maximum 8 Mo)."})
                    return

                filename = secrets.token_hex(16)
                temporary_path = UPLOADS_PATH / (filename + ".source.part")
                final_path = UPLOADS_PATH / (filename + "." + extension)
                compressed_path = UPLOADS_PATH / (filename + ".compressed.mp4")
                compressed_final_path = UPLOADS_PATH / (filename + ".mp4")
                header = bytearray()
                remaining = length
                try:
                    UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
                    required_space = length + (64 * 1024 * 1024 if is_video else 0)
                    if shutil.disk_usage(UPLOADS_PATH).free < required_space:
                        self.close_connection = True
                        self.send_json(507, {"error": "Espas disk pa ase pou resevwa epi konprese fim nan. Libere espas epi eseye ankò." if is_video else "Espace disque insuffisant pour enregistrer ce fichier."})
                        return
                    with temporary_path.open("xb") as uploaded:
                        while remaining:
                            chunk = self.rfile.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("Téléversement interrompu avant la fin du fichier.")
                            if len(header) < 16:
                                header.extend(chunk[:16 - len(header)])
                            uploaded.write(chunk)
                            remaining -= len(chunk)
                    valid = (
                        (content_type == "image/png" and header.startswith(b"\x89PNG\r\n\x1a\n")) or
                        (content_type == "image/jpeg" and header.startswith(b"\xff\xd8\xff")) or
                        (content_type == "image/webp" and header[:4] == b"RIFF" and header[8:12] == b"WEBP") or
                        (content_type == "video/mp4" and b"ftyp" in header[:16]) or
                        (content_type == "video/webm" and header.startswith(b"\x1aE\xdf\xa3"))
                    )
                    if not valid:
                        raise ValueError("Le fichier ne correspond pas au format annoncé.")
                    if is_video:
                        available = shutil.disk_usage(UPLOADS_PATH).free - (64 * 1024 * 1024)
                        target_size = min(4 * 1024 * 1024 * 1024, available)
                        if target_size < 1024 * 1024:
                            raise ValueError("Espas disk ki rete a pa ase pou kreye vèsyon konprese a.")
                        if length > target_size:
                            compress_film_video(temporary_path, compressed_path, target_size)
                            compressed_size = compressed_path.stat().st_size
                            temporary_path.unlink()
                            compressed_path.replace(compressed_final_path)
                            video_path = compressed_final_path
                            was_compressed = True
                        else:
                            compressed_size = length
                            temporary_path.replace(final_path)
                            video_path = final_path
                            was_compressed = False
                        self.send_json(201, {
                            "url": "/uploads/" + video_path.name,
                            "mime": "video/mp4" if was_compressed else content_type,
                            "compressed": was_compressed,
                            "original_size": length,
                            "compressed_size": compressed_size,
                        })
                        return
                    temporary_path.replace(final_path)
                except ValueError as exc:
                    try:
                        temporary_path.unlink(missing_ok=True)
                        compressed_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    self.send_json(400, {"error": str(exc)})
                    return
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    try:
                        temporary_path.unlink(missing_ok=True)
                        compressed_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    message = "Impossible d’enregistrer le fichier téléversé."
                    if is_video:
                        message = "Konpresyon fim nan echwe. Verifye fòma fichye a ak espas disk la, epi eseye ankò."
                    self.send_json(500, {"error": message})
                    return
                self.send_json(201, {"url": "/uploads/" + final_path.name, "mime": content_type})
                return
        try:
            data = self.read_json()
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return

        if path == "/api/seller/profile":
            if not self.require_seller(): return
            try:
                profile_photo=text_field(data,"profile_photo",1000,required=False)
                if profile_photo and not profile_photo.startswith("/uploads/"):
                    raise ValueError("Choisissez une photo téléversée sur Trede Hub.")
                whatsapp=text_field(data,"whatsapp",30)
                digits=re.sub(r"[^0-9]","",whatsapp)
                if len(digits)<8 or len(digits)>15:
                    raise ValueError("Numéro WhatsApp invalide. Utilisez le format international, par exemple +509...")
                show_whatsapp=1 if data.get("show_whatsapp",True) in (True,1,"1","true","on") else 0
                country=text_field(data,"country",120,required=False)
                department=text_field(data,"department",120,required=False)
                city=text_field(data,"city",120,required=False)
                street=text_field(data,"street",180,required=False)
                address_details=text_field(data,"address_details",500,required=False)
                sid=self.seller_id()
                with database() as db:
                    duplicate=db.execute("SELECT id FROM sellers WHERE whatsapp=? AND id<>?",(whatsapp,sid)).fetchone()
                    if duplicate:
                        raise ValueError("Ce numéro WhatsApp est déjà utilisé par un autre vendeur.")
                    db.execute("UPDATE sellers SET whatsapp=?, show_whatsapp=?, profile_photo=?, country=?, department=?, city=?, street=?, address_details=? WHERE id=?",(whatsapp,show_whatsapp,profile_photo,country,department,city,street,address_details,sid))
                    seller=db.execute("SELECT id,name,whatsapp,COALESCE(show_whatsapp,1) AS show_whatsapp,status,blue_badge,gold_badge,profile_photo,country,department,city,street,address_details FROM sellers WHERE id=?",(sid,)).fetchone()
                self.send_json(200,{"seller":dict(seller)}); return
            except ValueError as exc:
                self.send_json(400,{"error":str(exc)}); return

        if path == "/api/seller/follow":
            try:
                sid = int(data.get("seller_id"))
                visitor_id = text_field(data, "visitor_id", 80)
                following = data.get("following")
                if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", visitor_id): raise ValueError("Identifiant visiteur invalide.")
                if not isinstance(following, bool): raise ValueError("Action de suivi invalide.")
                with database() as db:
                    seller = db.execute("SELECT id,status FROM sellers WHERE id=?", (sid,)).fetchone()
                    if not seller or seller["status"] != "active": self.send_json(404, {"error":"Vendeur introuvable."}); return
                    if following:
                        db.execute("INSERT OR IGNORE INTO seller_follows(seller_id,visitor_id) VALUES(?,?)", (sid, visitor_id))
                    else:
                        db.execute("DELETE FROM seller_follows WHERE seller_id=? AND visitor_id=?", (sid, visitor_id))
                    count = db.execute("SELECT COUNT(*) FROM seller_follows WHERE seller_id=?", (sid,)).fetchone()[0]
                    if count >= 20:
                        seller_name = db.execute("SELECT name FROM sellers WHERE id=?", (sid,)).fetchone()[0]
                        congratulations = "🎉 Félicitations ! Votre boutique Trede Hub vient d’atteindre 20 abonnés. Continuez à publier de bons produits et à développer votre communauté !"
                        exists = db.execute("SELECT 1 FROM messages WHERE seller_id=? AND sender_role='owner' AND body=? LIMIT 1", (sid, congratulations)).fetchone()
                        if not exists:
                            db.execute("INSERT INTO messages(seller_id,sender_role,sender_name,body) VALUES(?,?,?,?)", (sid,"owner","Trede Hub",congratulations))
                self.send_json(200, {"followers":count,"following":following}); return
            except (ValueError, TypeError) as exc:
                self.send_json(400, {"error":str(exc) or "Données invalides."}); return

        if path == "/api/analytics/heartbeat":
            visitor_id=text_field(data,"visitor_id",80)
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}",visitor_id):
                self.send_json(400,{"error":"Identifiant visiteur invalide."}); return
            event=text_field(data,"event",20,required=False) or "heartbeat"
            if event not in ("pageview","heartbeat"):
                self.send_json(400,{"error":"Événement invalide."}); return
            with database() as db:
                db.execute("INSERT INTO visitor_activity(visitor_id,first_seen,last_seen,pageviews) VALUES(?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?) ON CONFLICT(visitor_id) DO UPDATE SET last_seen=CURRENT_TIMESTAMP,pageviews=visitor_activity.pageviews+excluded.pageviews",(visitor_id,1 if event=="pageview" else 0))
                if event=="pageview":
                    db.execute("INSERT INTO visitor_daily(visitor_id,visit_date,pageviews) VALUES(?,date('now'),1) ON CONFLICT(visitor_id,visit_date) DO UPDATE SET pageviews=pageviews+1",(visitor_id,))
            self.send_json(200,{"ok":True}); return
        if path == "/api/analytics/purchase-click":
            visitor_id=text_field(data,"visitor_id",80)
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}",visitor_id):
                self.send_json(400,{"error":"Identifiant visiteur invalide."}); return
            try: product_id=int(data.get("product_id"))
            except (TypeError,ValueError): self.send_json(400,{"error":"Produit invalide."}); return
            with database() as db:
                product=db.execute("SELECT id,seller_id FROM products WHERE id=?",(product_id,)).fetchone()
                if not product or not product["seller_id"]:
                    self.send_json(404,{"error":"Produit ou vendeur introuvable."}); return
                db.execute("INSERT INTO purchase_clicks(product_id,seller_id,visitor_id) VALUES(?,?,?)",(product_id,product["seller_id"],visitor_id))
            self.send_json(201,{"ok":True}); return
        if path == "/api/analytics/seller-view":
            visitor_id=text_field(data,"visitor_id",80)
            try: sid=int(data.get("seller_id"))
            except (TypeError,ValueError): self.send_json(400,{"error":"Vendeur invalide."}); return
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}",visitor_id): self.send_json(400,{"error":"Identifiant visiteur invalide."}); return
            with database() as db:
                seller=db.execute("SELECT id,status FROM sellers WHERE id=?",(sid,)).fetchone()
                if not seller or seller["status"]!="active": self.send_json(404,{"error":"Vendeur introuvable."}); return
                db.execute("INSERT INTO seller_page_views(seller_id,visitor_id) VALUES(?,?)",(sid,visitor_id))
            self.send_json(201,{"ok":True}); return
        if path == "/api/seller/register":
            name=text_field(data,"name",100)
            whatsapp=text_field(data,"whatsapp",30)
            digits=re.sub(r"[^0-9]","",whatsapp)
            password=text_field(data,"password",256)
            if len(digits)<8 or len(digits)>15: self.send_json(400,{"error":"Numéro WhatsApp invalide."}); return
            if len(password)<10: self.send_json(400,{"error":"Le mot de passe doit contenir au moins 10 caractères."}); return
            salt,digest=make_password_hash(password)
            with database() as db:
                rows=db.execute("SELECT id,name,whatsapp,status,password_hash FROM sellers WHERE name=? COLLATE NOCASE",(name,)).fetchall()
                match=next((r for r in rows if re.sub(r"[^0-9]","",r["whatsapp"])==digits),None)
                if match:
                    if match["password_hash"]:
                        self.send_json(409,{"error":"Ce compte existe déjà. Connectez-vous avec votre mot de passe."}); return
                    db.execute("UPDATE sellers SET password_salt=?,password_hash=? WHERE id=?",(salt,digest,match["id"]))
                    if match["status"]=="active":
                        self.send_json(201,{"ok":True,"approved":True,"message":"Compte activé. Vous pouvez maintenant vous connecter."}); return
                    self.send_json(201,{"ok":True,"approved":False,"message":"Compte créé. Il attend l'approbation du propriétaire."}); return
                try:
                    cur=db.execute("INSERT INTO sellers(name,whatsapp,status,password_salt,password_hash) VALUES(?,?,'pending',?,?)",(name,whatsapp,salt,digest))
                except sqlite3.IntegrityError:
                    self.send_json(409,{"error":"Ce nom ou numéro WhatsApp est déjà utilisé."}); return
            self.send_json(201,{"ok":True,"approved":False,"message":"Demande créée. Attendez que le propriétaire approuve votre compte."}); return
        if path == "/api/seller/login":
            name = text_field(data, "name", 100)
            whatsapp_raw = data.get("whatsapp", "")
            if not isinstance(whatsapp_raw, str):
                raise ValueError("Le numéro WhatsApp doit être du texte.")
            whatsapp = re.sub(r"[^0-9]", "", whatsapp_raw[:30])
            password = text_field(data,"password",256)
            with database() as db:
                rows=db.execute("SELECT id,status,whatsapp,password_salt,password_hash FROM sellers WHERE name=? COLLATE NOCASE",(name,)).fetchall()
            # Existing sellers may sign in with name + password; when a phone is supplied, verify it too.
            candidates=[r for r in rows if (not whatsapp or re.sub(r"[^0-9]","",r["whatsapp"])==whatsapp)]
            seller=None
            for candidate in candidates:
                if not candidate["password_hash"]:
                    continue
                _,digest=make_password_hash(password,candidate["password_salt"])
                if hmac.compare_digest(digest,candidate["password_hash"]):
                    seller=candidate
                    break
            if not seller:
                self.send_json(401,{"error":"Nom, WhatsApp ou mot de passe incorrect. Vérifiez vos informations ou créez un compte vendeur."}); return
            if seller["status"]!="active":
                self.send_json(403,{"error":"Votre compte attend l'approbation du propriétaire ou est suspendu."}); return
            self.send_json(200,{"ok":True},{"Set-Cookie":self.create_seller_cookie(seller["id"])}); return
        if path == "/api/seller/logout":
            cookie=self.headers.get("Cookie","")
            token=next((part.partition("=")[2] for part in cookie.split("; ") if part.startswith("trede_seller_session=")),"")
            with SESSION_LOCK: SELLER_SESSIONS.pop(token,None)
            self.send_json(200,{"ok":True},{"Set-Cookie":"trede_seller_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"}); return
        if path == "/api/messages":
            try:
                body = text_field(data, "body", 2000)
                owner = self.owner_id()
                if owner is not None:
                    try: sid = int(data.get("seller_id", ""))
                    except (TypeError, ValueError): raise ValueError("Choisissez un vendeur.")
                    with database() as db:
                        seller = db.execute("SELECT id,name FROM sellers WHERE id=?", (sid,)).fetchone()
                        if not seller: self.send_json(404, {"error":"Vendeur introuvable."}); return
                        db.execute("INSERT INTO messages(seller_id,sender_role,sender_name,body) VALUES(?,?,?,?)", (sid,"owner","Propriétaire",body))
                        row = db.execute("SELECT id,seller_id,sender_role,sender_name,body,created_at FROM messages WHERE id=last_insert_rowid()").fetchone()
                else:
                    if not self.require_seller(): return
                    sid = self.seller_id()
                    with database() as db:
                        seller = db.execute("SELECT name,status FROM sellers WHERE id=?", (sid,)).fetchone()
                        if not seller or seller["status"] != "active": self.send_json(403, {"error":"Compte vendeur suspendu."}); return
                        db.execute("INSERT INTO messages(seller_id,sender_role,sender_name,body) VALUES(?,?,?,?)", (sid,"seller",seller["name"],body))
                        row = db.execute("SELECT id,seller_id,sender_role,sender_name,body,created_at FROM messages WHERE id=last_insert_rowid()").fetchone()
            except ValueError as exc:
                self.send_json(400, {"error":str(exc)}); return
            self.send_json(201, {"message":dict(row)}); return
        if path == "/api/upload":
            if self.owner_id() is None and not self.require_seller(): return
            try:
                data_url = text_field(data, "data", 40 * 1024 * 1024)
                match = re.fullmatch(r"data:(image/png|image/jpeg|image/webp|video/mp4|video/webm);base64,([A-Za-z0-9+/=]+)", data_url)
                if not match: raise ValueError("Format refusé. Utilisez PNG, JPG, WebP, MP4 ou WebM.")
                mime, encoded = match.groups()
                raw = base64.b64decode(encoded, validate=True)
                limit = 25 * 1024 * 1024 if mime.startswith("video/") else 8 * 1024 * 1024
                if not raw or len(raw) > limit: raise ValueError("Fichier trop volumineux (images 8 Mo, vidéos 25 Mo maximum).")
                valid = ((mime == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n")) or
                         (mime == "image/jpeg" and raw.startswith(b"\xff\xd8\xff")) or
                         (mime == "image/webp" and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP") or
                         (mime == "video/mp4" and b"ftyp" in raw[:16]) or
                         (mime == "video/webm" and raw.startswith(b"\x1aE\xdf\xa3")))
                if not valid: raise ValueError("Le fichier ne correspond pas au format annoncé.")
                ext={"image/png":"png","image/jpeg":"jpg","image/webp":"webp","video/mp4":"mp4","video/webm":"webm"}[mime]
                UPLOADS_PATH.mkdir(parents=True,exist_ok=True)
                filename=secrets.token_hex(16)+"."+ext
                (UPLOADS_PATH/filename).write_bytes(raw)
            except (ValueError, base64.binascii.Error) as exc:
                self.send_json(400,{"error":str(exc)}); return
            self.send_json(201,{"url":"/uploads/"+filename,"mime":mime}); return
        if path == "/api/sellers":
            if not self.require_owner(): return
            try:
                name=text_field(data,"name",100); whatsapp=text_field(data,"whatsapp",30)
                digits=re.sub(r"[^0-9]","",whatsapp)
                if len(digits)<8 or len(digits)>15: raise ValueError("Numéro WhatsApp invalide.")
                with database() as db:
                    cur=db.execute("INSERT INTO sellers(name,whatsapp) VALUES(?,?)",(name,whatsapp))
                    seller_id=cur.lastrowid
            except ValueError as exc: self.send_json(400,{"error":str(exc)}); return
            except sqlite3.IntegrityError: self.send_json(409,{"error":"Ce nom ou numéro WhatsApp existe déjà."}); return
            self.send_json(201,{"id":seller_id,"name":name,"whatsapp":whatsapp,"status":"active","blue_badge":0,"gold_badge":0}); return
        film_comment_match = re.fullmatch(r"/api/films/(\d+)/comments", path)
        if film_comment_match:
            try:
                film_id = int(film_comment_match.group(1))
                author = text_field(data, "author", 60)
                body = text_field(data, "body", 1000)
                with database() as db:
                    if not db.execute("SELECT 1 FROM films WHERE id=?", (film_id,)).fetchone():
                        self.send_json(404, {"error": "Film introuvable."}); return
                    cur = db.execute("INSERT INTO film_comments(film_id,author,body) VALUES(?,?,?)", (film_id, author, body))
                    comment = dict(db.execute("SELECT id,film_id,author,body,created_at FROM film_comments WHERE id=?", (cur.lastrowid,)).fetchone())
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)}); return
            self.send_json(201, {"comment": comment}); return
        if path == "/api/films":
            if not self.require_owner(): return
            try:
                title=text_field(data,"title",180); description=text_field(data,"description",1000,required=False)
                image_url=text_field(data,"image_url",1000,required=False); video_url=text_field(data,"video_url",1000,required=False)
                genre=text_field(data,"genre",40,required=False) or "Autres"
                with database() as db:
                    cur=db.execute("INSERT INTO films(title,description,image_url,video_url,genre) VALUES(?,?,?,?,?)",(title,description,image_url,video_url,genre))
                    film_id=cur.lastrowid
            except ValueError as exc: self.send_json(400,{"error":str(exc)}); return
            self.send_json(201,{"id":film_id,"title":title,"description":description,"image_url":image_url,"video_url":video_url,"genre":genre}); return
        if path == "/api/seller/products":
            if not self.require_seller(): return
            try:
                product=product_fields(data); sid=self.seller_id()
                with database() as db:
                    if not db.execute("SELECT 1 FROM categories WHERE name=?",(product["cat"],)).fetchone():
                        self.send_json(400,{"error":"La catégorie sélectionnée n'existe pas."}); return
                    cur=db.execute("""INSERT INTO products(name,cat,price,old,discount,rating,reviews,emoji,supplier,image_url,seller_id)
                        VALUES(:name,:cat,:price,:old,:discount,:rating,:reviews,:emoji,:supplier,:image_url,:seller_id)""",{**product,"seller_id":sid,"supplier":product.get("supplier") or "Vendeur"})
                    product["id"]=cur.lastrowid; product["seller_id"]=sid
            except ValueError as exc: self.send_json(400,{"error":str(exc)}); return
            self.send_json(201,product); return
        if path == "/api/auth/setup":
            try:
                remote_ip = ipaddress.ip_address(self.client_address[0])
            except ValueError:
                self.send_json(403, {"error": "Initialisation locale uniquement."})
                return
            if not remote_ip.is_loopback:
                self.send_json(403, {"error": "Initialisation locale uniquement."})
                return
            username = text_field(data, "username", 64)
            password = text_field(data, "password", 256)
            if len(password) < 12:
                self.send_json(400, {"error": "Le mot de passe doit contenir au moins 12 caractères."})
                return
            salt, digest = make_password_hash(password)
            try:
                with database() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if db.execute("SELECT 1 FROM owners LIMIT 1").fetchone():
                        self.send_json(409, {"error": "Le compte propriétaire existe déjà."})
                        return
                    cursor = db.execute(
                        "INSERT INTO owners (username, salt, password_hash) VALUES (?, ?, ?)",
                        (username, salt, digest),
                    )
                    owner_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                self.send_json(409, {"error": "Ce nom d'utilisateur est déjà utilisé."})
                return
            self.send_json(201, {"ok": True}, {"Set-Cookie": self.create_session_cookie(owner_id)})
            return

        if path == "/api/auth/login":
            username = text_field(data, "username", 64)
            password = text_field(data, "password", 256)
            with database() as db:
                owner = db.execute(
                    "SELECT id, salt, password_hash FROM owners WHERE username = ?",
                    (username,),
                ).fetchone()
            if owner is None:
                self.send_json(401, {"error": "Nom d'utilisateur ou mot de passe incorrect."})
                return
            _, digest = make_password_hash(password, owner["salt"])
            if not hmac.compare_digest(digest, owner["password_hash"]):
                self.send_json(401, {"error": "Nom d'utilisateur ou mot de passe incorrect."})
                return
            self.send_json(
                200,
                {"ok": True},
                {"Set-Cookie": self.create_session_cookie(owner["id"])},
            )
            return

        if path == "/api/auth/logout":
            cookie = self.headers.get("Cookie", "")
            token_value = next((part.partition("=")[2] for part in cookie.split("; ") if part.startswith("trede_session=")), "")
            with SESSION_LOCK:
                SESSIONS.pop(token_value, None)
            self.send_json(200, {"ok": True}, {"Set-Cookie": "trede_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
            return

        if not self.require_owner():
            return

        if path == "/api/products":
            try:
                product = product_fields(data)
                with database() as db:
                    if not db.execute("SELECT 1 FROM categories WHERE name = ?", (product["cat"],)).fetchone():
                        self.send_json(400, {"error": "La catégorie sélectionnée n'existe pas."})
                        return
                    cursor = db.execute(
                        """INSERT INTO products
                           (name, cat, price, old, discount, rating, reviews, emoji, supplier, image_url)
                           VALUES (:name, :cat, :price, :old, :discount, :rating, :reviews, :emoji, :supplier, :image_url)""",
                        product,
                    )
                    product["id"] = cursor.lastrowid
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
                return
            self.send_json(201, product)
            return

        if path == "/api/categories":
            try:
                category = category_fields(data)
                with database() as db:
                    cursor = db.execute(
                        "INSERT INTO categories (name, icon, label, image_url) VALUES (?, ?, ?, ?)",
                        (category["name"], category["icon"], category["label"], category["image_url"]),
                    )
                    category["id"] = cursor.lastrowid
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
                return
            except sqlite3.IntegrityError:
                self.send_json(409, {"error": "Cette catégorie existe déjà."})
                return
            self.send_json(201, category)
            return

        self.send_json(404, {"error": "Route introuvable."})

    def do_PUT(self):
        path = urlsplit(self.path).path
        if not self.validate_origin():
            return
        is_seller_product = path.startswith("/api/seller-products/")
        if is_seller_product:
            if not self.require_seller(): return
        elif not self.require_owner():
            return
        try:
            data = self.read_json()
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return

        parts = path.strip("/").split("/")
        if len(parts) != 3:
            self.send_json(404, {"error": "Route introuvable."})
            return
        try:
            item_id = int(parts[2])
        except ValueError:
            self.send_json(400, {"error": "Identifiant invalide."})
            return

        if parts[:2] == ["api", "products"]:
            try:
                product = product_fields(data)
                with database() as db:
                    if not db.execute("SELECT 1 FROM categories WHERE name = ?", (product["cat"],)).fetchone():
                        self.send_json(400, {"error": "La catégorie sélectionnée n'existe pas."})
                        return
                    cursor = db.execute(
                        """UPDATE products SET name=:name, cat=:cat, price=:price, old=:old,
                           discount=:discount, rating=:rating, reviews=:reviews, emoji=:emoji,
                           supplier=:supplier, image_url=:image_url WHERE id=:id""",
                        {**product, "id": item_id},
                    )
                if cursor.rowcount == 0:
                    self.send_json(404, {"error": "Produit introuvable."})
                    return
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
                return
            self.send_json(200, {"id": item_id, **product})
            return

        if parts[:2] == ["api", "categories"]:
            try:
                category = category_fields(data)
                with database() as db:
                    existing = db.execute(
                        "SELECT name FROM categories WHERE id = ?",
                        (item_id,),
                    ).fetchone()
                    if existing is None:
                        self.send_json(404, {"error": "Catégorie introuvable."})
                        return
                    cursor = db.execute(
                        "UPDATE categories SET name = ?, icon = ?, label = ?, image_url = ? WHERE id = ?",
                        (category["name"], category["icon"], category["label"], category["image_url"], item_id),
                    )
                    if existing["name"] != category["name"]:
                        db.execute(
                            "UPDATE products SET cat = ? WHERE cat = ?",
                            (category["name"], existing["name"]),
                        )
                if cursor.rowcount == 0:
                    self.send_json(404, {"error": "Catégorie introuvable."})
                    return
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
                return
            except sqlite3.IntegrityError:
                self.send_json(409, {"error": "Cette catégorie existe déjà."})
                return
            self.send_json(200, {"id": item_id, **category})
            return

        if parts[:2] == ["api", "seller-products"]:
            if not self.require_seller(): return
            try:
                product=product_fields(data); sid=self.seller_id()
                with database() as db:
                    if not db.execute("SELECT 1 FROM products WHERE id=? AND seller_id=?",(item_id,sid)).fetchone():
                        self.send_json(404,{"error":"Produit introuvable."}); return
                    if not db.execute("SELECT 1 FROM categories WHERE name=?",(product["cat"],)).fetchone():
                        self.send_json(400,{"error":"Catégorie inexistante."}); return
                    db.execute("""UPDATE products SET name=:name,cat=:cat,price=:price,old=:old,discount=:discount,rating=:rating,reviews=:reviews,emoji=:emoji,supplier=:supplier,image_url=:image_url WHERE id=:id AND seller_id=:seller_id""",{**product,"id":item_id,"seller_id":sid})
            except ValueError as exc: self.send_json(400,{"error":str(exc)}); return
            self.send_json(200,{"id":item_id,**product}); return
        if parts[:2] == ["api", "sellers"]:
            try:
                name=text_field(data,"name",100); whatsapp=text_field(data,"whatsapp",30)
                status=text_field(data,"status",20); blue=1 if data.get("blue_badge") else 0; gold=1 if data.get("gold_badge") else 0
                profile_photo=text_field(data,"profile_photo",1000,required=False)
                if profile_photo and not profile_photo.startswith("/uploads/"): raise ValueError("Choisissez une photo téléversée sur Trede Hub.")
                if status not in ("active","suspended","pending"): raise ValueError("Statut invalide.")
                with database() as db:
                    cur=db.execute("UPDATE sellers SET name=?,whatsapp=?,status=?,blue_badge=?,gold_badge=?,profile_photo=? WHERE id=?",(name,whatsapp,status,blue,gold,profile_photo,item_id))
                    if cur.rowcount==0: self.send_json(404,{"error":"Vendeur introuvable."}); return
            except ValueError as exc: self.send_json(400,{"error":str(exc)}); return
            except sqlite3.IntegrityError: self.send_json(409,{"error":"Nom ou numéro WhatsApp déjà utilisé."}); return
            self.send_json(200,{"ok":True}); return
        if parts[:2] == ["api", "films"]:
            if not self.require_owner(): return
            try:
                title=text_field(data,"title",180); description=text_field(data,"description",1000,required=False)
                image_url=text_field(data,"image_url",1000,required=False); video_url=text_field(data,"video_url",1000,required=False)
                genre=text_field(data,"genre",40,required=False) or "Autres"
                with database() as db:
                    cur=db.execute("UPDATE films SET title=?,description=?,image_url=?,video_url=?,genre=? WHERE id=?",(title,description,image_url,video_url,genre,item_id))
                    if cur.rowcount==0: self.send_json(404,{"error":"Film introuvable."}); return
            except ValueError as exc: self.send_json(400,{"error":str(exc)}); return
            self.send_json(200,{"ok":True}); return
        self.send_json(404, {"error": "Route introuvable."})

    def do_DELETE(self):
        path = urlsplit(self.path).path
        if not self.validate_origin():
            return
        is_seller_product = path.startswith("/api/seller-products/")
        if is_seller_product:
            if not self.require_seller(): return
        elif not self.require_owner():
            return
        parts = path.strip("/").split("/")
        if len(parts) != 3:
            self.send_json(404, {"error": "Route introuvable."})
            return
        try:
            item_id = int(parts[2])
        except ValueError:
            self.send_json(400, {"error": "Identifiant invalide."})
            return

        if parts[:2] == ["api", "products"]:
            with database() as db:
                cursor = db.execute("DELETE FROM products WHERE id = ?", (item_id,))
            if cursor.rowcount == 0:
                self.send_json(404, {"error": "Produit introuvable."})
                return
            self.send_json(200, {"ok": True})
            return

        if parts[:2] == ["api", "categories"]:
            with database() as db:
                category = db.execute("SELECT name FROM categories WHERE id = ?", (item_id,)).fetchone()
                if category is None:
                    self.send_json(404, {"error": "Catégorie introuvable."})
                    return
                if db.execute("SELECT 1 FROM products WHERE cat = ? LIMIT 1", (category["name"],)).fetchone():
                    self.send_json(409, {"error": "Cette catégorie est utilisée par des produits; modifiez ou supprimez ces produits d'abord."})
                    return
                db.execute("DELETE FROM categories WHERE id = ?", (item_id,))
            self.send_json(200, {"ok": True})
            return

        if parts[:2] == ["api", "sellers"]:
            with database() as db:
                db.execute("DELETE FROM products WHERE seller_id=?",(item_id,))
                db.execute("DELETE FROM messages WHERE seller_id=?",(item_id,))
                cur=db.execute("DELETE FROM sellers WHERE id=?",(item_id,))
            if cur.rowcount==0: self.send_json(404,{"error":"Vendeur introuvable."}); return
            self.send_json(200,{"ok":True}); return
        if parts[:2] == ["api", "films"]:
            with database() as db: cur=db.execute("DELETE FROM films WHERE id=?",(item_id,))
            if cur.rowcount==0: self.send_json(404,{"error":"Film introuvable."}); return
            self.send_json(200,{"ok":True}); return
        if parts[:2] == ["api", "seller-products"]:
            if not self.require_seller(): return
            with database() as db: cur=db.execute("DELETE FROM products WHERE id=? AND seller_id=?",(item_id,self.seller_id()))
            if cur.rowcount==0: self.send_json(404,{"error":"Produit introuvable."}); return
            self.send_json(200,{"ok":True}); return
        self.send_json(404, {"error": "Route introuvable."})

    def do_PATCH(self):
        path = urlsplit(self.path).path
        if path != "/api/content":
            self.send_json(404, {"error": "Route introuvable."})
            return
        if not self.validate_origin() or not self.require_owner():
            return
        try:
            data = self.read_json()
            allowed = set(DEFAULT_CONTENT)
            if not data:
                raise ValueError("Aucun contenu du site n’a été envoyé.")
            # Accept fields from compatible/newer admin pages instead of rejecting the
            # entire save. This prevents logo/photo/video uploads from failing just
            # because an older DEFAULT_CONTENT list does not yet contain a new setting.
            invalid_keys = sorted(
                key for key in data
                if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,79}", key)
            )
            if invalid_keys:
                raise ValueError("Nom de champ invalide dans le contenu du site.")
            limits = {key: (1000 if key.endswith("_url") else 250 if key in {"tagline", "search_placeholder", "products_subtitle", "footer_disclaimer"} else 500) for key in data}
            values = {key: text_field(data, key, limits[key], required=False) for key in data}
            for key, value in values.items():
                if key.endswith("_url") and value and not value.startswith(("/uploads/", "https://", "http://")):
                    raise ValueError(f"Le champ « {key} » doit être un lien http(s) ou un média téléversé.")
            for key in ("primary_color", "header_color"):
                if key in values and values[key] and not re.fullmatch(r"#[0-9a-fA-F]{6}", values[key]):
                    raise ValueError(f"La couleur « {key} » doit être au format #RRGGBB.")
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return
        with database() as db:
            db.executemany(
                "INSERT INTO site_content (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                list(values.items()),
            )
        self.send_json(200, {"ok": True})


if __name__ == "__main__":
    initialize_database()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Trede Hub server running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTrede Hub server stopped.")
    finally:
        server.server_close()
