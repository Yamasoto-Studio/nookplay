from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import date, datetime, timedelta
import sqlite3
from ai import generate_game, generate_impostor, generate_dilema, generate_conexiones, generate_oraculo, generate_donde, generate_carta, generate_reinas, generate_conexion_local, generate_equilibrio, generate_veredicto, generate_perfil, generate_vestuario, generate_sinopsis, generate_muertes, generate_letra, generate_pensamiento, generate_poema, generate_menteagil, generate_constitucion, build_bar_context, get_day_seed
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import random
import string
import time

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nookplay-secret-2026')
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8 MB máx. por subida

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

def get_db():
    import os as _os
    _os.makedirs('/data', exist_ok=True)
    _db_path = '/data/nookplay.db'
    # timeout=10 evita errores "database is locked" si hay escritura concurrente
    # (la pre-generación corre en un hilo de fondo)
    db = sqlite3.connect(_db_path, timeout=10)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript('''
        -- Tabla principal de bares
        CREATE TABLE IF NOT EXISTS bars (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            slug                TEXT UNIQUE NOT NULL,
            name                TEXT NOT NULL,
            type                TEXT DEFAULT '',
            logo_path           TEXT DEFAULT '',

            -- Ubicación
            address             TEXT DEFAULT '',
            city                TEXT DEFAULT '',
            province            TEXT DEFAULT '',
            zip_code            TEXT DEFAULT '',
            country             TEXT DEFAULT 'España',
            latitude            REAL,
            longitude           REAL,
            google_place_id     TEXT DEFAULT '',

            -- Para la IA
            description         TEXT DEFAULT '',
            owner_name          TEXT DEFAULT '',
            staff_names         TEXT DEFAULT '',
            bar_vibe            TEXT DEFAULT '',

            -- Experiencia del cliente
            welcome_message     TEXT DEFAULT '',
            promo_active        INTEGER DEFAULT 0,

            -- Acceso (código semanal)
            access_code         TEXT DEFAULT '',
            access_code_updated_at TEXT DEFAULT '',
            whatsapp_phone      TEXT DEFAULT '',

            -- Colores de marca
            color_primary       TEXT DEFAULT '#C4622D',
            color_primary_text  TEXT DEFAULT '#FFFFFF',
            color_bg            TEXT DEFAULT '#F7F2EB',
            color_bg_subtle     TEXT DEFAULT '#F0EBE3',
            color_accent_dark   TEXT DEFAULT '#1A1A1A',

            -- Meta
            active              INTEGER DEFAULT 1,
            created_at          TEXT DEFAULT (datetime('now')),
            updated_at          TEXT DEFAULT (datetime('now'))
        );

        -- Productos promocionados (hasta 3 por bar)
        CREATE TABLE IF NOT EXISTS bar_products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id      INTEGER NOT NULL REFERENCES bars(id) ON DELETE CASCADE,
            position    INTEGER DEFAULT 1,
            title       TEXT NOT NULL,
            description TEXT DEFAULT '',
            price       TEXT DEFAULT '',
            image_path  TEXT DEFAULT '',
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        -- Historial de códigos semanales
        CREATE TABLE IF NOT EXISTS access_codes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id      INTEGER NOT NULL REFERENCES bars(id) ON DELETE CASCADE,
            code        TEXT NOT NULL,
            valid_from  TEXT NOT NULL,
            valid_until TEXT NOT NULL,
            sent_at     TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        );

        -- Log de accesos (solo analytics, no bloquea)
        CREATE TABLE IF NOT EXISTS access_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id      INTEGER NOT NULL REFERENCES bars(id) ON DELETE CASCADE,
            code_used   TEXT NOT NULL,
            accessed_at TEXT DEFAULT (datetime('now'))
        );

        -- Caché diaria de juegos generados por la IA
        CREATE TABLE IF NOT EXISTS generated_games (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id          INTEGER NOT NULL REFERENCES bars(id) ON DELETE CASCADE,
            game_type       TEXT NOT NULL,
            game_date       TEXT NOT NULL,
            content         TEXT NOT NULL,
            generated_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(bar_id, game_type, game_date)
        );

        CREATE TABLE IF NOT EXISTS app_state (
            key     TEXT PRIMARY KEY,
            value   TEXT DEFAULT ''
        );

        -- Partidas jugadas
        CREATE TABLE IF NOT EXISTS plays (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT NOT NULL,
            bar_slug    TEXT NOT NULL,
            played_on   TEXT NOT NULL,
            correct     INTEGER DEFAULT 0,
            game_type   TEXT DEFAULT 'crimen',
            choice      INTEGER DEFAULT -1,
            elapsed     INTEGER DEFAULT 0
        );

        -- Usuarios admin (superadmin + bar_admin)
        CREATE TABLE IF NOT EXISTS admin_users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT UNIQUE NOT NULL,
            password_hash   TEXT NOT NULL,
            role            TEXT DEFAULT 'bar_admin',
            bar_id          INTEGER REFERENCES bars(id),
            created_at      TEXT DEFAULT (datetime('now'))
        );
    ''')
    db.commit()
    db.close()

def migrate_db():
    """Añade columnas nuevas a tablas existentes sin perder datos."""
    db = get_db()
    migrations = [
        # Nuevas columnas en bars
        "ALTER TABLE bars ADD COLUMN type TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN logo_path TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN address TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN city TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN province TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN zip_code TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN country TEXT DEFAULT 'España'",
        "ALTER TABLE bars ADD COLUMN latitude REAL",
        "ALTER TABLE bars ADD COLUMN longitude REAL",
        "ALTER TABLE bars ADD COLUMN google_place_id TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN description TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN owner_name TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN staff_names TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN bar_vibe TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN promo_active INTEGER DEFAULT 0",
        "ALTER TABLE bars ADD COLUMN access_code TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN access_code_updated_at TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN whatsapp_phone TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN color_primary TEXT DEFAULT '#C4622D'",
        "ALTER TABLE bars ADD COLUMN color_primary_text TEXT DEFAULT '#FFFFFF'",
        "ALTER TABLE bars ADD COLUMN color_bg TEXT DEFAULT '#F7F2EB'",
        "ALTER TABLE bars ADD COLUMN color_bg_subtle TEXT DEFAULT '#F0EBE3'",
        "ALTER TABLE bars ADD COLUMN color_accent_dark TEXT DEFAULT '#1A1A1A'",
        "ALTER TABLE bars ADD COLUMN welcome_message TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN tomorrow_message TEXT DEFAULT ''",
        "ALTER TABLE bars ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))",
        # Nuevas columnas en plays
        "ALTER TABLE plays ADD COLUMN game_type TEXT DEFAULT 'crimen'",
        "ALTER TABLE plays ADD COLUMN choice INTEGER DEFAULT -1",
        "ALTER TABLE plays ADD COLUMN elapsed INTEGER DEFAULT 0",
        "ALTER TABLE plays ADD COLUMN answer_text TEXT DEFAULT ''",
    ]
    for sql in migrations:
        try:
            db.execute(sql)
        except:
            pass  # Columna ya existe, ignorar

    # Migrar iconos PNG → WebP en la tabla games
    try:
        db.execute("UPDATE games SET icon = REPLACE(icon, '.png', '.webp') WHERE icon LIKE '%.png'")
        db.commit()
    except:
        pass

    # Crear tablas nuevas si no existen
    db.executescript('''
        CREATE TABLE IF NOT EXISTS bar_products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id      INTEGER NOT NULL,
            position    INTEGER DEFAULT 1,
            title       TEXT NOT NULL,
            description TEXT DEFAULT '',
            price       TEXT DEFAULT '',
            image_path  TEXT DEFAULT '',
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS access_codes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id      INTEGER NOT NULL,
            code        TEXT NOT NULL,
            valid_from  TEXT NOT NULL,
            valid_until TEXT NOT NULL,
            sent_at     TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS access_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id      INTEGER NOT NULL,
            code_used   TEXT NOT NULL,
            accessed_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS generated_games (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id          INTEGER NOT NULL,
            game_type       TEXT NOT NULL,
            game_date       TEXT NOT NULL,
            content         TEXT NOT NULL,
            generated_at    TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS admin_users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT UNIQUE NOT NULL,
            password_hash   TEXT NOT NULL,
            role            TEXT DEFAULT 'bar_admin',
            bar_id          INTEGER,
            created_at      TEXT DEFAULT (datetime('now'))
        );
    ''')

    # Actualizar datos de Yellow con info completa
    # Solo actualizar campos estructurales que no edita Lorena desde el panel
    # Los campos editables (welcome_message, colores, ubicación...) NUNCA se tocan aquí
    db.execute("""
        UPDATE bars SET
            name                = 'Yellow Specialty Koffee',
            type                = 'Cafetería de especialidad',
            owner_name          = 'Lorena',
            staff_names         = 'Carla'
        WHERE slug = 'yellow'
    """)
    db.commit()

    # Insertar Yellow si no existe
    existing = db.execute("SELECT id FROM bars WHERE slug = 'yellow'").fetchone()
    if not existing:
        db.execute("""
            INSERT INTO bars (slug, name, type, city, province, description, owner_name, staff_names,
                bar_vibe, welcome_message, color_primary, color_primary_text, color_bg, color_bg_subtle, color_accent_dark)
            VALUES ('yellow', 'Yellow Specialty Koffee', 'Cafetería de especialidad', 'Viladecans', 'Barcelona',
                'Cafetería moderna de café de especialidad. Local acogedor con clientela variada.',
                'Lorena', 'Carla', 'acogedor, moderno, especialidad',
                'Bienvenido al Yellow. Elige tu pasatiempo de hoy.',
                '#FEE25A', '#000000', '#FFFBEA', '#FFF8D6', '#1A1A1A')
        """)
        db.commit()

    # Insertar productos de Yellow si no existen
    bar_row = db.execute("SELECT id FROM bars WHERE slug = 'yellow'").fetchone()
    if bar_row:
        bar_id = bar_row['id']
        existing_products = db.execute("SELECT id FROM bar_products WHERE bar_id = ?", (bar_id,)).fetchone()
        if not existing_products:
            products = [
                (bar_id, 1, 'Café de finca etíope', 'Single origin tostado en casa. Notas de fruta y chocolate.', '2,50 €'),
                (bar_id, 2, 'Frappé artesano', 'Preparado al momento con café de especialidad y leche fresca.', '4,00 €'),
                (bar_id, 3, 'Leche con tostada', 'Pan artesano con mantequilla y mermelada casera.', '3,00 €'),
            ]
            for p in products:
                db.execute("INSERT INTO bar_products (bar_id, position, title, description, price) VALUES (?,?,?,?,?)", p)
            db.commit()

    # Generar código semanal para Yellow si no tiene
    if bar_row:
        bar_id = bar_row['id']
        current_code = db.execute("SELECT access_code FROM bars WHERE id = ?", (bar_id,)).fetchone()
        if current_code and not current_code['access_code']:
            new_code = generate_weekly_code()
            today = date.today()
            monday = today - timedelta(days=today.weekday())
            sunday = monday + timedelta(days=6)
            db.execute("UPDATE bars SET access_code = ?, access_code_updated_at = ? WHERE id = ?",
                      (new_code, str(monday), bar_id))
            db.execute("INSERT INTO access_codes (bar_id, code, valid_from, valid_until) VALUES (?,?,?,?)",
                      (bar_id, new_code, str(monday), str(sunday)))
            db.commit()

    db.close()

# --------------------------------------------------------------------------
# Helpers — Código semanal
# --------------------------------------------------------------------------

def generate_weekly_code():
    """Genera un código de 5 caracteres alfanumérico legible."""
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # Sin caracteres confusos (0,O,1,I)
    return ''.join(random.choices(chars, k=5))

def get_current_code(bar_id):
    """Devuelve el código válido esta semana para un bar."""
    db = get_db()
    today = str(date.today())
    result = db.execute("""
        SELECT code FROM access_codes
        WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?
        ORDER BY created_at DESC LIMIT 1
    """, (bar_id, today, today)).fetchone()
    db.close()
    return result['code'] if result else None

def rotate_weekly_codes():
    """Genera nuevos códigos para todos los bares activos. Llamar cada lunes."""
    db = get_db()
    bars = db.execute("SELECT id, slug, whatsapp_phone FROM bars WHERE active = 1").fetchall()
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    for bar in bars:
        new_code = generate_weekly_code()
        db.execute("UPDATE bars SET access_code = ?, access_code_updated_at = ? WHERE id = ?",
                  (new_code, str(monday), bar['id']))
        db.execute("INSERT INTO access_codes (bar_id, code, valid_from, valid_until) VALUES (?,?,?,?)",
                  (bar['id'], new_code, str(monday), str(sunday)))

    db.commit()
    db.close()

# --------------------------------------------------------------------------
# Routes — Públicas
# --------------------------------------------------------------------------

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/juegos')
def games_catalog():
    db = get_db()
    games = db.execute("SELECT slug, name, description, icon, plan_min FROM games WHERE active = 1 ORDER BY position").fetchall()
    db.close()
    return render_template('games.html', games=[dict(g) for g in games])



# ─────────────────────────────────────────────────────────────────────────────
# Scheduled tasks
# ─────────────────────────────────────────────────────────────────────────────

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

def generate_weekly_codes():
    """Ejecuta cada lunes a las 6am — genera códigos semanales para todos los bares."""
    from datetime import timedelta
    import random
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    def gen_code():
        return ''.join(random.choices(chars, k=5))

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    db = get_db()
    bars = db.execute("SELECT id, slug FROM bars WHERE active = 1").fetchall()
    for bar in bars:
        existing = db.execute(
            "SELECT id FROM access_codes WHERE bar_id = ? AND valid_from = ?",
            (bar['id'], str(monday))
        ).fetchone()
        if not existing:
            new_code = gen_code()
            db.execute("UPDATE bars SET access_code = ?, access_code_updated_at = ? WHERE id = ?",
                      (new_code, str(monday), bar['id']))
            db.execute("INSERT INTO access_codes (bar_id, code, valid_from, valid_until) VALUES (?,?,?,?)",
                      (bar['id'], new_code, str(monday), str(sunday)))
            print(f"[CRON] Código semanal para {bar['slug']}: {new_code}")
    db.commit()
    db.close()

def get_historial_reciente(db, game_type, bar_slug=None, dias=10, campo='titulo'):
    """Recupera contenidos recientes de un juego para evitar repeticiones.
    Devuelve una lista de strings (el campo indicado de cada contenido)."""
    import json as _json
    from datetime import date, timedelta
    hoy = str(date.today())
    desde = str(date.today() - timedelta(days=dias))
    if bar_slug:
        rows = db.execute(
            "SELECT content FROM generated_games WHERE game_type = ? AND bar_id = (SELECT id FROM bars WHERE slug = ?) AND game_date >= ? AND game_date < ? ORDER BY game_date DESC",
            (game_type, bar_slug, desde, hoy)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT content FROM generated_games WHERE game_type = ? AND game_date >= ? AND game_date < ? ORDER BY game_date DESC",
            (game_type, desde, hoy)
        ).fetchall()
    items = []
    for r in rows:
        try:
            data = _json.loads(r['content'])
            if campo == 'preguntas' and 'preguntas' in data:
                # vestuario: extraer la curiosidad de cada pregunta
                for p in data['preguntas']:
                    if isinstance(p, dict) and p.get('curiosidad'):
                        items.append(p['curiosidad'][:80])
            elif campo == 'opciones' and 'opciones' in data:
                # sinopsis/letra: la respuesta correcta
                idx = data.get('correcta', 0)
                if isinstance(data['opciones'], list) and idx < len(data['opciones']):
                    items.append(data['opciones'][idx])
            elif campo in data and data[campo]:
                items.append(str(data[campo]))
        except Exception:
            continue
    return items[:30]


# Estado global de la pre-generación (para mostrar progreso en vivo)
import threading as _threading
_pregen_estado = {
    'corriendo': False,
    'total': 0,
    'hechos': 0,
    'actual': '',
    'ok': [],
    'error': [],
    'inicio': None,
    'fin': None,
}
_pregen_lock = _threading.Lock()


def pregen_daily_games():
    """Ejecuta cada día a las 6am — pre-genera los juegos del día para todos los bares."""
    today = str(date.today())
    resumen = {'ok': [], 'error': []}
    GAME_TYPES = ['crimen', 'impostor', 'dilema', 'conexiones', 'oraculo', 'donde', 'local', 'veredicto', 'perfil', 'vestuario', 'sinopsis', 'muertes', 'letra', 'pensamiento', 'menteagil', 'constitucion']

    db = get_db()
    bars = db.execute("SELECT * FROM bars WHERE active = 1").fetchall()
    # Inicializar el contador de progreso (estimación: juegos x bares)
    _pregen_estado['total'] = len(bars) * len(GAME_TYPES)
    _pregen_estado['hechos'] = 0
    for bar in bars:
        for game_type in GAME_TYPES:
            existing = db.execute(
                "SELECT id FROM generated_games WHERE bar_id = ? AND game_type = ? AND game_date = ?",
                (bar['id'], game_type, today)
            ).fetchone()
            if not existing:
                try:
                    products = db.execute(
                        "SELECT title FROM bar_products WHERE bar_id = ? AND active = 1",
                        (bar['id'],)
                    ).fetchall()
                    if game_type == 'crimen':
                        ctx = build_bar_context(dict(bar))
                        ctx['productos'] = [p['title'] for p in products]
                        game_data = generate_game(ctx, bar['slug'])
                    elif game_type == 'impostor':
                        game_data = generate_impostor(bar['name'], bar['slug'])
                    elif game_type == 'dilema':
                        ev = get_historial_reciente(db, 'dilema', bar['slug'], campo='situacion')
                        game_data = generate_dilema(bar['name'], bar['slug'], evitar=ev)
                    elif game_type == 'conexiones':
                        game_data = generate_conexiones(bar['name'], bar['slug'])
                    elif game_type == 'oraculo':
                        # Oráculo es único para todos los bares — solo generar una vez
                        existing_oraculo = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'oraculo' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing_oraculo:
                            continue
                        game_data = generate_oraculo(bar['slug'])
                    elif game_type == 'donde':
                        # Dónde es único para todos los bares — solo generar una vez
                        existing_donde = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'donde' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing_donde:
                            continue
                        game_data = generate_donde(bar['slug'])
                    elif game_type == 'local':
                        city = bar['city'] or ''
                        province = bar['province'] or city
                        if not city:
                            continue  # Sin ciudad no se puede generar Conexión Local
                        game_data = generate_conexion_local(bar['name'], city, province, bar['slug'])
                    elif game_type == 'veredicto':
                        ev = get_historial_reciente(db, 'veredicto', bar['slug'], campo='titulo')
                        game_data = generate_veredicto(bar['name'], bar['slug'], evitar=ev)
                    elif game_type == 'perfil':
                        ev = get_historial_reciente(db, 'perfil', bar['slug'], campo='nombre')
                        game_data = generate_perfil(bar['slug'], evitar=ev)
                    elif game_type == 'vestuario':
                        ev = get_historial_reciente(db, 'vestuario', bar['slug'], campo='preguntas')
                        game_data = generate_vestuario(bar['slug'], evitar=ev)
                    elif game_type == 'sinopsis':
                        # Única para todos los bares — solo generar una vez
                        existing = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'sinopsis' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing:
                            continue
                        ev = get_historial_reciente(db, 'sinopsis', None, campo='opciones')
                        game_data = generate_sinopsis(bar['slug'], evitar=ev)
                    elif game_type == 'muertes':
                        existing = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'muertes' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing:
                            continue
                        ev = get_historial_reciente(db, 'muertes', None, campo='titulo')
                        game_data = generate_muertes(bar['slug'], evitar=ev)
                    elif game_type == 'letra':
                        existing = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'letra' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing:
                            continue
                        ev = get_historial_reciente(db, 'letra', None, campo='opciones')
                        game_data = generate_letra(bar['slug'], evitar=ev)
                    elif game_type == 'pensamiento':
                        existing = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'pensamiento' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing:
                            continue
                        game_data = generate_pensamiento(bar['slug'])
                    elif game_type == 'menteagil':
                        existing = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'menteagil' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing:
                            continue
                        game_data = generate_menteagil(bar['slug'])
                    elif game_type == 'constitucion':
                        existing = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'constitucion' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing:
                            continue
                        game_data = generate_constitucion(bar['slug'])
                    
                    import json as _json
                    db.execute(
                        "INSERT INTO generated_games (bar_id, game_type, game_date, content) VALUES (?,?,?,?)",
                        (bar['id'], game_type, today, _json.dumps(game_data))
                    )
                    db.commit()
                    resumen['ok'].append(f"{game_type}/{bar['slug']}")
                    _pregen_estado['ok'].append(f"{game_type}/{bar['slug']}")
                    print(f"[CRON] Pre-generado {game_type} para {bar['slug']}")
                except Exception as e:
                    resumen['error'].append(f"{game_type}/{bar['slug']}: {e}")
                    _pregen_estado['error'].append(f"{game_type}/{bar['slug']}: {str(e)[:120]}")
                    print(f"[CRON] Error generando {game_type} para {bar['slug']}: {e}")
            # Avanzar contador (tanto si se generó como si ya existía)
            _pregen_estado['hechos'] += 1
            _pregen_estado['actual'] = f"{game_type} · {bar['slug']}"
    db.close()
    return resumen

def start_scheduler():
    scheduler = BackgroundScheduler(timezone=pytz.timezone('Europe/Madrid'))
    # Lunes a las 6am — códigos semanales
    scheduler.add_job(generate_weekly_codes, CronTrigger(day_of_week='mon', hour=6, minute=0))
    # Cada día a las 6am — pre-generación de juegos
    scheduler.add_job(pregen_daily_games, CronTrigger(hour=6, minute=0))
    scheduler.start()
    print("[SCHEDULER] Iniciado — códigos lunes 6am, juegos diarios 6am")

# ─────────────────────────────────────────────────────────────────────────────
# Admin routes
# ─────────────────────────────────────────────────────────────────────────────

import hashlib as _hashlib
from functools import wraps
from flask import session, redirect

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_user_id' not in session:
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated

def hash_password(password):
    return _hashlib.sha256(password.encode()).hexdigest()


@app.route('/admin/api/pregen-now', methods=['POST'])
@admin_required
def admin_pregen_now():
    """Superadmin: fuerza la pre-generación de juegos ahora mismo (diagnóstico/test).
    Borra primero los contenidos de hoy para forzar una regeneración real."""
    if session.get('admin_role') != 'superadmin':
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403
    today = str(date.today())

    # Evitar dos ejecuciones simultáneas (consultando BD, compartida entre workers)
    dbc = get_db()
    dbc.execute("CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT DEFAULT '')")
    dbc.commit()
    running_row = dbc.execute("SELECT value FROM app_state WHERE key = 'pregen_running'").fetchone()
    dbc.close()
    if running_row and running_row['value']:
        try:
            if (time.time() - float(running_row['value'])) < 300:
                return jsonify({'ok': True, 'msg': 'Ya hay una regeneración en curso.', 'corriendo': True})
        except Exception:
            pass

    def _run():
        with _pregen_lock:
            try:
                # Marcar inicio en BD (compartido entre workers)
                dbx = get_db()
                dbx.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('pregen_running', ?)", (str(time.time()),))
                dbx.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('pregen_errores', '')", ())
                dbx.execute("DELETE FROM generated_games WHERE game_date = ?", (today,))
                dbx.commit()
                dbx.close()
                global _game_cache
                _game_cache = {k: v for k, v in _game_cache.items() if today not in k}

                resumen = pregen_daily_games()

                # Guardar errores en BD
                errores = resumen['error'] if resumen else []
                dbx2 = get_db()
                dbx2.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('pregen_errores', ?)", ('|||'.join(errores),))
                dbx2.commit()
                dbx2.close()
            except Exception as e:
                try:
                    dbx3 = get_db()
                    dbx3.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('pregen_errores', ?)", (f"FATAL: {str(e)[:200]}",))
                    dbx3.commit()
                    dbx3.close()
                except Exception:
                    pass
            finally:
                # Marcar fin (borrar la marca de running)
                try:
                    dbf = get_db()
                    dbf.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('pregen_running', '')", ())
                    dbf.commit()
                    dbf.close()
                except Exception:
                    pass

    t = _threading.Thread(target=_run, daemon=True)
    t.start()
    try:
        return jsonify({'ok': True, 'msg': 'Regeneración iniciada en segundo plano.', 'corriendo': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/admin/api/scheduler-status')
@admin_required
def admin_scheduler_status():
    """Superadmin: devuelve el estado del scheduler y cuántos juegos hay pre-generados hoy."""
    if session.get('admin_role') != 'superadmin':
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403
    today = str(date.today())
    db = get_db()
    # Asegurar que la tabla app_state existe (por si la migración no corrió aún)
    db.execute("CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT DEFAULT '')")
    rows = db.execute(
        "SELECT bar_id, game_type, game_date FROM generated_games WHERE game_date = ? ORDER BY bar_id, game_type",
        (today,)
    ).fetchall()
    bars = db.execute("SELECT id, slug FROM bars WHERE active = 1").fetchall()

    # Detectar si hay regeneración en curso (misma conexión, aún abierta)
    corriendo = False
    errores = []
    try:
        estado_row = db.execute("SELECT value FROM app_state WHERE key = 'pregen_running'").fetchone()
        if estado_row and estado_row['value']:
            try:
                corriendo = (time.time() - float(estado_row['value'])) < 300
            except Exception:
                corriendo = False
        err_row = db.execute("SELECT value FROM app_state WHERE key = 'pregen_errores'").fetchone()
        errores = err_row['value'].split('|||') if (err_row and err_row['value']) else []
    except Exception:
        pass
    db.close()

    # Total esperado: juegos por bar (excluyendo globales que solo cuentan 1 vez)
    n_bars = len(bars)
    total_estimado = n_bars * 8 + 8  # 8 por-bar + 8 globales aprox

    return jsonify({
        'ok': True,
        'today': today,
        'bars_active': n_bars,
        'pregenerated_today': len(rows),
        'progreso': {
            'corriendo': corriendo,
            'hechos': len(rows),
            'total': total_estimado,
            'n_error': len([e for e in errores if e]),
            'errores': [e for e in errores if e][:20],
        }
    })

@app.route('/admin')
def admin_index():
    if 'admin_user_id' not in session:
        return redirect('/admin/login')
    db = get_db()
    user = db.execute("SELECT * FROM admin_users WHERE id = ?", (session['admin_user_id'],)).fetchone()
    db.close()
    if not user:
        return redirect('/admin/login')
    if user['role'] == 'superadmin':
        return redirect('/admin/dashboard')
    return redirect('/admin/' + (user['bar_slug'] or 'yellow'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute("SELECT * FROM admin_users WHERE email = ?", (email,)).fetchone()
        db.close()
        if user and user['password_hash'] == hash_password(password):
            session['admin_user_id'] = user['id']
            session['admin_role'] = user['role']
            session['admin_bar_slug'] = user['bar_slug']
            return redirect('/admin')
        return render_template('admin/login.html', error='Email o contraseña incorrectos.')
    return render_template('admin/login.html', error=None)

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin/login')

@app.route('/admin/<bar_slug>')
@admin_required
def admin_bar(bar_slug):
    if session.get('admin_role') != 'superadmin' and session.get('admin_bar_slug') != bar_slug:
        return redirect('/admin')
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ?", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return "Bar no encontrado", 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    today = str(date.today())
    code_row = db.execute(
        "SELECT code, valid_until FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ? ORDER BY id DESC LIMIT 1",
        (bar['id'], today, today)
    ).fetchone()
    current_code = code_row['code'] if code_row else (bar['access_code'] or 'N/D')
    valid_until_str = code_row['valid_until'] if code_row else '—'
    stats_today = db.execute(
        "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on = ?",
        (bar_slug, today)
    ).fetchone()['n']
    from datetime import timedelta
    monday = date.today() - timedelta(days=date.today().weekday())
    stats_week = db.execute(
        "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on >= ?",
        (bar_slug, str(monday))
    ).fetchone()['n']
    correct_week = db.execute(
        "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on >= ? AND correct = 1",
        (bar_slug, str(monday))
    ).fetchone()['n']
    pct_correct = round((correct_week / stats_week * 100)) if stats_week > 0 else 0
    db.close()
    stats = {'today': stats_today, 'week': stats_week, 'pct_correct': pct_correct}
    return render_template('admin/bar_panel.html', bar=bar, products=products,
                           current_code=current_code, valid_until=valid_until_str, stats=stats,
                           admin_role=session.get('admin_role','bar_admin'))

@app.route('/admin/api/save', methods=['POST'])
@admin_required
def admin_save():
    data = request.get_json()
    bar_slug = data.get('bar_slug')
    if session.get('admin_role') != 'superadmin' and session.get('admin_bar_slug') != bar_slug:
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ?", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'ok': False}), 404
    lat = data.get('latitude')
    lng = data.get('longitude')
    try:
        lat = float(lat) if lat else None
        lng = float(lng) if lng else None
    except: pass

    # Update plan if superadmin
    if 'plan' in data and session.get('admin_role') == 'superadmin':
        db.execute("UPDATE bars SET plan=? WHERE slug=?", (data['plan'], bar_slug))

    db.execute(
        "UPDATE bars SET welcome_message=?, tomorrow_message=?, promo_active=?, description=?, owner_name=?, staff_names=?, color_primary=?, color_primary_text=?, color_bg=?, color_bg_subtle=?, address=?, city=?, province=?, zip_code=?, country=?, latitude=?, longitude=? WHERE slug=?",
        (data.get('welcome_message',''), data.get('tomorrow_message',''), data.get('promo_active',0),
         data.get('description',''), data.get('owner_name',''),
         data.get('staff_names',''), data.get('color_primary','#C4622D'),
         data.get('color_primary_text','#FFFFFF'), data.get('color_bg','#F7F2EB'),
         data.get('color_bg_subtle','#F0EBE3'), data.get('address',''),
         data.get('city',''), data.get('province',''), data.get('zip_code',''),
         data.get('country','España'), lat, lng, bar_slug)
    )
    db.execute("DELETE FROM bar_products WHERE bar_id = ?", (bar['id'],))
    for p in data.get('products', []):
        if p.get('title'):
            # Recuperar image_path existente si no se envía nueva
            import os as _os
            pos = p.get('position', 0)
            img_path = f"/static/clientes/{bar_slug}/product_{pos}.webp"
            image_path = img_path if _os.path.exists(img_path.lstrip('/')) else ''
            db.execute(
                "INSERT INTO bar_products (bar_id, position, title, description, price, image_path, active) VALUES (?,?,?,?,?,?,1)",
                (bar['id'], pos, p['title'], p.get('description',''), p.get('price',''), image_path)
            )
    db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/admin/api/create-user', methods=['POST'])
def admin_create_user():
    data = request.get_json()
    if data.get('secret') != os.environ.get('ADMIN_SECRET', 'nookplay-admin-2026'):
        return jsonify({'ok': False}), 403
    db = get_db()
    try:
        db.execute(
            "INSERT INTO admin_users (email, password_hash, role, bar_slug) VALUES (?,?,?,?)",
            (data['email'].lower(), hash_password(data['password']),
             data.get('role','bar_admin'), data.get('bar_slug',''))
        )
        db.commit()
        db.close()
        return jsonify({'ok': True})
    except Exception as e:
        db.close()
        return jsonify({'ok': False, 'error': str(e)}), 500



with app.app_context():
    init_db()
    migrate_db()
    start_scheduler()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)


@app.route('/<bar_slug>')
def bar(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('bar.html', bar=bar, products=products, products_json=products_json)

@app.route('/<bar_slug>/crimen')
def crimen_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    code = request.args.get('code', '')
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('games/crimen.html', bar=bar, code=code, products_json=products_json)

@app.route('/<bar_slug>/impostor')
def impostor_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    code = request.args.get('code', '')
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('games/impostor.html', bar=bar, code=code, products_json=products_json)

# --------------------------------------------------------------------------
# API — Validación de acceso
# --------------------------------------------------------------------------

@app.route('/api/validate', methods=['POST'])
def validate_code():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()

    if not bar:
        db.close()
        return jsonify({'valid': False, 'message': 'Local no encontrado.'})

    # Buscar código válido esta semana
    valid = db.execute("""
        SELECT code FROM access_codes
        WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?
    """, (bar['id'], code, today, today)).fetchone()

    if not valid:
        db.close()
        return jsonify({'valid': False, 'message': 'Código no válido o caducado.'})

    # Registrar acceso (solo analytics)
    db.execute("INSERT INTO access_log (bar_id, code_used) VALUES (?, ?)", (bar['id'], code))
    db.commit()
    db.close()

    return jsonify({'valid': True, 'bar_name': bar['name']})

# --------------------------------------------------------------------------
# API — Juegos
# --------------------------------------------------------------------------

_game_cache = {}

@app.route('/api/game', methods=['POST'])
def game():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Bar no encontrado'}), 404

    # Verificar código válido
    valid = db.execute("""
        SELECT code FROM access_codes
        WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?
    """, (bar['id'], code, today, today)).fetchone()
    if not valid:
        db.close()
        return jsonify({'error': 'Código no válido'}), 403

    # Buscar en caché BD
    cached = db.execute("""
        SELECT content FROM generated_games
        WHERE bar_id = ? AND game_type = 'crimen' AND game_date = ?
    """, (bar['id'], today)).fetchone()

    if cached:
        db.close()
        return jsonify(json.loads(cached['content']))

    # Generar nuevo juego con contexto dinámico desde BD
    bar_context = build_bar_context(dict(bar))
    products = db.execute(
        "SELECT title FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    bar_context['productos'] = [p['title'] for p in products]
    db.close()

    try:
        game_data = generate_game(bar_context, bar_slug)
        # Guardar en caché BD
        db2 = get_db()
        bar2 = db2.execute("SELECT id FROM bars WHERE slug = ?", (bar_slug,)).fetchone()
        try:
            db2.execute(
                "INSERT INTO generated_games (bar_id, game_type, game_date, content) VALUES (?,?,?,?)",
                (bar2['id'], 'crimen', today, json.dumps(game_data))
            )
            db2.commit()
        except:
            pass
        db2.close()
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/impostor', methods=['POST'])
def impostor():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Bar no encontrado'}), 404

    valid = db.execute("""
        SELECT code FROM access_codes
        WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?
    """, (bar['id'], code, today, today)).fetchone()
    if not valid:
        db.close()
        return jsonify({'error': 'Código no válido'}), 403

    cached = db.execute("""
        SELECT content FROM generated_games
        WHERE bar_id = ? AND game_type = 'impostor' AND game_date = ?
    """, (bar['id'], today)).fetchone()

    if cached:
        db.close()
        return jsonify(json.loads(cached['content']))

    bar_context = build_bar_context(dict(bar))
    db.close()

    try:
        game_data = generate_impostor(bar_context['nombre'], bar_slug)
        db2 = get_db()
        bar2 = db2.execute("SELECT id FROM bars WHERE slug = ?", (bar_slug,)).fetchone()
        try:
            db2.execute(
                "INSERT INTO generated_games (bar_id, game_type, game_date, content) VALUES (?,?,?,?)",
                (bar2['id'], 'impostor', today, json.dumps(game_data))
            )
            db2.commit()
        except:
            pass
        db2.close()
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --------------------------------------------------------------------------
# API — Stats
# --------------------------------------------------------------------------

@app.route('/api/play', methods=['POST'])
def register_play():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    correct = data.get('correct', False)
    game_type = data.get('game_type', 'crimen')
    choice = data.get('choice', -1)
    elapsed = data.get('elapsed', 0)
    today = str(date.today())

    db = get_db()
    played = db.execute(
        "SELECT id FROM plays WHERE code = ? AND played_on = ? AND game_type = ?",
        (code, today, game_type)
    ).fetchone()

    if not played:
        db.execute(
            "INSERT INTO plays (code, bar_slug, played_on, correct, game_type, choice, elapsed) VALUES (?,?,?,?,?,?,?)",
            (code, bar_slug, today, 1 if correct else 0, game_type, choice, elapsed)
        )
        db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/api/stats/<bar_slug>/<game_type>')
def game_stats(bar_slug, game_type):
    today = str(date.today())
    db = get_db()
    try:
        total = db.execute(
            "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on = ? AND game_type = ?",
            (bar_slug, today, game_type)
        ).fetchone()['n']
        correct = db.execute(
            "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on = ? AND game_type = ? AND correct = 1",
            (bar_slug, today, game_type)
        ).fetchone()['n']
        avg_row = db.execute(
            "SELECT AVG(elapsed) as avg_e FROM plays WHERE bar_slug = ? AND played_on = ? AND game_type = ? AND elapsed > 0",
            (bar_slug, today, game_type)
        ).fetchone()
        avg_elapsed = round(avg_row['avg_e']) if avg_row and avg_row['avg_e'] else None
    except:
        total = 0; correct = 0; avg_elapsed = None
    db.close()
    return jsonify({'total': total, 'correct': correct, 'avg_elapsed': avg_elapsed})

@app.route('/api/stats/<bar_slug>')
def stats(bar_slug):
    today = str(date.today())
    db = get_db()
    total_today = db.execute(
        "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on = ?",
        (bar_slug, today)
    ).fetchone()['n']
    correct_today = db.execute(
        "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on = ? AND correct = 1",
        (bar_slug, today)
    ).fetchone()['n']
    total_all = db.execute(
        "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ?",
        (bar_slug,)
    ).fetchone()['n']
    db.close()
    return jsonify({'today': total_today, 'correct_today': correct_today, 'total': total_all})

# --------------------------------------------------------------------------
# Admin — Panel del bar (acceso privado)
# --------------------------------------------------------------------------








@app.route('/<bar_slug>/dilema')
def dilema_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    code = request.args.get('code', '')
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('games/dilema.html', bar=bar, code=code, products_json=products_json)

@app.route('/api/dilema', methods=['POST'])
def dilema_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    bar_name = bar['name']
    bar_id = bar['id']

    cache_key = f"{bar_slug}_dilema_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    # Check pre-generated
    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE bar_id = ? AND game_type = 'dilema' AND game_date = ?",
        (bar_id, today)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()

    try:
        game_data = generate_dilema(bar_name, bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/<bar_slug>/veredicto')
def veredicto_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/veredicto.html', bar=bar, products=products)


@app.route('/api/veredicto', methods=['POST'])
def veredicto_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    bar_name = bar['name']
    bar_id = bar['id']

    cache_key = f"{bar_slug}_veredicto_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE bar_id = ? AND game_type = 'veredicto' AND game_date = ?",
        (bar_id, today)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()

    try:
        game_data = generate_veredicto(bar_name, bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/veredicto-stats/<bar_slug>')
def veredicto_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'total': 0, 'culpables': 0, 'inocentes': 0})
    plays = db.execute(
        "SELECT choice, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'veredicto' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    culpables = sum(1 for p in plays if p['choice'] == 1)
    inocentes = total - culpables
    elapsed_vals = [p['elapsed'] for p in plays if p['elapsed'] and p['elapsed'] > 0]
    avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0
    return jsonify({'total': total, 'culpables': culpables, 'inocentes': inocentes, 'avg_elapsed': avg_elapsed})


@app.route('/<bar_slug>/perfil')
def perfil_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/perfil.html', bar=bar, products=products)


@app.route('/api/perfil', methods=['POST'])
def perfil_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    bar_id = bar['id']
    cache_key = f"{bar_slug}_perfil_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE bar_id = ? AND game_type = 'perfil' AND game_date = ?",
        (bar_id, today)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()

    try:
        game_data = generate_perfil(bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/perfil-stats/<bar_slug>')
def perfil_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT correct, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'perfil' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    acertaron = sum(1 for p in plays if p['correct'] == 1)
    elapsed_vals = [p['elapsed'] for p in plays if p['elapsed'] and p['elapsed'] > 0]
    avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0
    pct_acierto = round((acertaron / total) * 100) if total > 0 else 0
    return jsonify({'total': total, 'acertaron': acertaron, 'pct_acierto': pct_acierto, 'avg_elapsed': avg_elapsed})


@app.route('/<bar_slug>/vestuario')
def vestuario_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/vestuario.html', bar=bar, products=products)


@app.route('/api/vestuario', methods=['POST'])
def vestuario_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    bar_id = bar['id']
    cache_key = f"{bar_slug}_vestuario_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE bar_id = ? AND game_type = 'vestuario' AND game_date = ?",
        (bar_id, today)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()

    try:
        game_data = generate_vestuario(bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/vestuario-stats/<bar_slug>')
def vestuario_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT choice, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'vestuario' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    avg_score = round(sum(p['choice'] for p in plays) / total, 1) if total > 0 else 0
    elapsed_vals = [p['elapsed'] for p in plays if p['elapsed'] and p['elapsed'] > 0]
    avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0
    return jsonify({'total': total, 'avg_score': avg_score, 'avg_elapsed': avg_elapsed})


@app.route('/<bar_slug>/sinopsis')
def sinopsis_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/sinopsis.html', bar=bar, products=products)


@app.route('/api/sinopsis', methods=['POST'])
def sinopsis_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    # Sinopsis es única para todos los bares
    cache_key = f"global_sinopsis_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE game_type = 'sinopsis' AND game_date = ?",
        (today,)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()

    try:
        game_data = generate_sinopsis(bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sinopsis-stats/<bar_slug>')
def sinopsis_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT correct, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'sinopsis' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    acertaron = sum(1 for p in plays if p['correct'] == 1)
    elapsed_vals = [p['elapsed'] for p in plays if p['elapsed'] and p['elapsed'] > 0]
    avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0
    pct_acierto = round((acertaron / total) * 100) if total > 0 else 0
    return jsonify({'total': total, 'acertaron': acertaron, 'pct_acierto': pct_acierto, 'avg_elapsed': avg_elapsed})


@app.route('/<bar_slug>/muertes')
def muertes_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/muertes.html', bar=bar, products=products)


@app.route('/api/muertes', methods=['POST'])
def muertes_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"global_muertes_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE game_type = 'muertes' AND game_date = ?",
        (today,)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()
    try:
        game_data = generate_muertes(bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/muertes-stats/<bar_slug>')
def muertes_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT correct, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'muertes' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    acertaron = sum(1 for p in plays if p['correct'] == 1)
    elapsed_vals = [p['elapsed'] for p in plays if p['elapsed'] and p['elapsed'] > 0]
    avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0
    pct_acierto = round((acertaron / total) * 100) if total > 0 else 0
    return jsonify({'total': total, 'acertaron': acertaron, 'pct_acierto': pct_acierto, 'avg_elapsed': avg_elapsed})


@app.route('/<bar_slug>/letra')
def letra_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/letra.html', bar=bar, products=products)


@app.route('/api/letra', methods=['POST'])
def letra_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"global_letra_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE game_type = 'letra' AND game_date = ?",
        (today,)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()
    try:
        game_data = generate_letra(bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/letra-stats/<bar_slug>')
def letra_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT correct, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'letra' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    acertaron = sum(1 for p in plays if p['correct'] == 1)
    elapsed_vals = [p['elapsed'] for p in plays if p['elapsed'] and p['elapsed'] > 0]
    avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0
    pct_acierto = round((acertaron / total) * 100) if total > 0 else 0
    return jsonify({'total': total, 'acertaron': acertaron, 'pct_acierto': pct_acierto, 'avg_elapsed': avg_elapsed})


@app.route('/<bar_slug>/pensamiento')
def pensamiento_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/pensamiento.html', bar=bar, products=products)


@app.route('/api/pensamiento', methods=['POST'])
def pensamiento_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403
    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403
    cache_key = f"global_pensamiento_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])
    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE game_type = 'pensamiento' AND game_date = ?",
        (today,)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)
    db.close()
    try:
        game_data = generate_pensamiento(bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _normalizar_respuesta(txt):
    """Normaliza para agrupar respuestas similares: minúsculas, sin tildes, sin artículos."""
    import unicodedata
    t = txt.strip().lower()
    t = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    for art in ['el ', 'la ', 'los ', 'las ', 'un ', 'una ', 'unos ', 'unas ']:
        if t.startswith(art):
            t = t[len(art):]
    return t.strip()


@app.route('/api/pensamiento-responder', methods=['POST'])
def pensamiento_responder():
    data = request.get_json()
    bar_slug = data.get('bar_slug', '').strip()
    code = data.get('code', '').strip().upper()
    respuesta = data.get('respuesta', '').strip()[:40]
    elapsed = data.get('elapsed', 0)
    today = str(date.today())
    if not respuesta:
        return jsonify({'error': 'Respuesta vacía'}), 400

    try:
        db = get_db()
        norm = _normalizar_respuesta(respuesta)
        db.execute(
            "INSERT INTO plays (code, bar_slug, game_type, played_on, correct, elapsed, answer_text) VALUES (?,?,?,?,?,?,?)",
            (code, bar_slug, 'pensamiento', today, 1, elapsed, norm)
        )
        db.commit()

        rows = db.execute(
            "SELECT answer_text FROM plays WHERE bar_slug = ? AND game_type = 'pensamiento' AND played_on = ?",
            (bar_slug, today)
        ).fetchall()
        db.close()

        from collections import Counter
        conteo = Counter(r['answer_text'] for r in rows if r['answer_text'])
        total = sum(conteo.values())
        top = conteo.most_common(5)
        mi_count = conteo.get(norm, 1)
        mi_pct = round((mi_count / total) * 100) if total > 0 else 100

        return jsonify({
            'total': total,
            'mi_respuesta': norm,
            'mi_pct': mi_pct,
            'mi_count': mi_count,
            'ranking': [{'respuesta': r, 'count': c, 'pct': round((c/total)*100)} for r, c in top]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/<bar_slug>/poema')
def poema_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/poema.html', bar=bar, products=products)


@app.route('/api/poema', methods=['POST'])
def poema_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403
    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    db.close()
    if not valid_code or valid_code['code'] != code:
        return jsonify({'error': 'Invalid code'}), 403

    nombre = data.get('nombre', '').strip()[:30] or 'alguien'
    sobre = data.get('sobre', 'mi')
    nombre_objeto = data.get('nombre_objeto', '').strip()[:30]
    tono = data.get('tono', 'divertido')
    nivel = data.get('nivel', 'normal')

    try:
        result = generate_poema(nombre, sobre, nombre_objeto, tono, nivel)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/<bar_slug>/menteagil')
def menteagil_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/menteagil.html', bar=bar, products=products)


@app.route('/api/menteagil', methods=['POST'])
def menteagil_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403
    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403
    cache_key = f"global_menteagil_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])
    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE game_type = 'menteagil' AND game_date = ?",
        (today,)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)
    db.close()
    try:
        game_data = generate_menteagil(bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/menteagil-stats/<bar_slug>')
def menteagil_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT correct, choice, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'menteagil' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    acertaron = sum(1 for p in plays if p['correct'] == 1)
    avg_score = round(sum(p['choice'] for p in plays if p['choice'] is not None and p['choice'] >= 0) / total, 1) if total > 0 else 0
    elapsed_vals = [p['elapsed'] for p in plays if p['elapsed'] and p['elapsed'] > 0]
    avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0
    pct_acierto = round((acertaron / total) * 100) if total > 0 else 0
    return jsonify({'total': total, 'acertaron': acertaron, 'pct_acierto': pct_acierto, 'avg_score': avg_score, 'avg_elapsed': avg_elapsed})


@app.route('/<bar_slug>/constitucion')
def constitucion_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/constitucion.html', bar=bar, products=products)


@app.route('/api/constitucion', methods=['POST'])
def constitucion_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403
    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403
    cache_key = f"global_constitucion_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])
    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE game_type = 'constitucion' AND game_date = ?",
        (today,)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)
    db.close()
    try:
        game_data = generate_constitucion(bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/constitucion-stats/<bar_slug>')
def constitucion_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT correct, choice, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'constitucion' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    acertaron = sum(1 for p in plays if p['correct'] == 1)
    avg_score = round(sum(p['choice'] for p in plays if p['choice'] is not None and p['choice'] >= 0) / total, 1) if total > 0 else 0
    elapsed_vals = [p['elapsed'] for p in plays if p['elapsed'] and p['elapsed'] > 0]
    avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0
    pct_acierto = round((acertaron / total) * 100) if total > 0 else 0
    return jsonify({'total': total, 'acertaron': acertaron, 'pct_acierto': pct_acierto, 'avg_score': avg_score, 'avg_elapsed': avg_elapsed})


@app.route('/api/dilema-stats/<bar_slug>')
def dilema_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    try:
        total = db.execute(
            "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on = ? AND game_type = 'dilema'",
            (bar_slug, today)
        ).fetchone()['n']
        votos_a = db.execute(
            "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on = ? AND game_type = 'dilema' AND choice = 0",
            (bar_slug, today)
        ).fetchone()['n']
        votos_b = db.execute(
            "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on = ? AND game_type = 'dilema' AND choice = 1",
            (bar_slug, today)
        ).fetchone()['n']
        try:
            avg_row = db.execute(
                "SELECT AVG(elapsed) as avg_e FROM plays WHERE bar_slug = ? AND played_on = ? AND game_type = 'dilema' AND elapsed > 0",
                (bar_slug, today)
            ).fetchone()
            avg_elapsed = round(avg_row['avg_e']) if avg_row and avg_row['avg_e'] else None
        except:
            avg_elapsed = None
    except:
        total = votos_a = votos_b = 0
        avg_elapsed = None
    db.close()
    return jsonify({'total': total, 'votos_a': votos_a, 'votos_b': votos_b, 'avg_elapsed': avg_elapsed})


@app.route('/api/bars-map')
def bars_map():
    db = get_db()
    bars = db.execute(
        "SELECT name, city, latitude, longitude, slug FROM bars WHERE active = 1 AND latitude IS NOT NULL"
    ).fetchall()
    db.close()
    return jsonify([dict(b) for b in bars])


@app.route('/<bar_slug>/conexiones')
def conexiones_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    code = request.args.get('code', '')
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('games/conexiones.html', bar=bar, code=code, products_json=products_json)

@app.route('/api/conexiones', methods=['POST'])
def conexiones_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"{bar_slug}_conexiones_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE bar_id = ? AND game_type = 'conexiones' AND game_date = ?",
        (bar['id'], today)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()
    try:
        game_data = generate_conexiones(bar['name'], bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/<bar_slug>/oraculo')
def oraculo_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    code = request.args.get('code', '')
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('games/oraculo.html', bar=bar, code=code, products_json=products_json)

@app.route('/api/oraculo', methods=['POST'])
def oraculo_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"oraculo_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE game_type = 'oraculo' AND game_date = ? LIMIT 1",
        (today,)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()
    try:
        game_data = generate_oraculo(bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/<bar_slug>/donde')
def donde_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    code = request.args.get('code', '')
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('games/donde.html', bar=bar, code=code, products_json=products_json)

@app.route('/api/donde', methods=['POST'])
def donde_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"donde_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE game_type = 'donde' AND game_date = ? LIMIT 1",
        (today,)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()
    try:
        game_data = generate_donde(bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/<bar_slug>/carta')
def carta_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    code = request.args.get('code', '')
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('games/carta.html', bar=bar, code=code, products_json=products_json)

@app.route('/api/carta', methods=['POST'])
def carta_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    db.close()
    cache_key = f"{bar_slug}_carta_{today}"
    if cache_key in _game_cache:
        return jsonify(_game_cache[cache_key])

    game_data = generate_carta(bar_slug)
    _game_cache[cache_key] = game_data
    return jsonify(game_data)


@app.route('/<bar_slug>/reinas')
def reinas_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    code = request.args.get('code', '')
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('games/reinas.html', bar=bar, code=code, products_json=products_json)

@app.route('/api/reinas', methods=['POST'])
def reinas_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    db.close()
    cache_key = f"{bar_slug}_reinas_{today}"
    if cache_key in _game_cache:
        return jsonify(_game_cache[cache_key])

    game_data = generate_reinas(bar_slug)
    _game_cache[cache_key] = game_data
    return jsonify(game_data)


@app.route('/<bar_slug>/local')
def local_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    code = request.args.get('code', '')
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('games/local.html', bar=bar, code=code, products_json=products_json)

@app.route('/api/local', methods=['POST'])
def local_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"{bar_slug}_local_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE bar_id = ? AND game_type = 'local' AND game_date = ?",
        (bar['id'], today)
    ).fetchone()
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        # Ensure ciudad is always present
        if 'ciudad' not in game_data:
            game_data['ciudad'] = bar['city'] or ''
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    city = bar['city'] or 'tu ciudad'
    province = bar['province'] or ''
    db.close()
    try:
        game_data = generate_conexion_local(bar['name'], city, province, bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/<bar_slug>/equilibrio')
def equilibrio_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute(
        "SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position",
        (bar['id'],)
    ).fetchall()
    db.close()
    code = request.args.get('code', '')
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('games/equilibrio.html', bar=bar, code=code, products_json=products_json)

@app.route('/api/equilibrio', methods=['POST'])
def equilibrio_api():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    valid_code = db.execute(
        "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], today, today)
    ).fetchone()
    if not valid_code or valid_code['code'] != code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    db.close()
    cache_key = f"{bar_slug}_equilibrio_{today}"
    if cache_key in _game_cache:
        return jsonify(_game_cache[cache_key])

    game_data = generate_equilibrio(bar_slug)
    _game_cache[cache_key] = game_data
    return jsonify(game_data)


@app.route('/api/contact', methods=['POST'])
def contact_api():
    data = request.get_json()
    nombre = data.get('nombre', '').strip()
    negocio = data.get('negocio', '').strip()
    ubicacion = data.get('ubicacion', '').strip()
    telefono = data.get('telefono', '').strip()
    email = data.get('email', '').strip()
    mensaje = data.get('mensaje', '').strip()

    if not nombre or not email:
        return jsonify({'ok': False, 'error': 'Missing fields'}), 400

    try:
        smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        smtp_user = os.environ.get('SMTP_USER', '')
        smtp_pass = os.environ.get('SMTP_PASS', '')
        to_email = os.environ.get('CONTACT_EMAIL', 'nookplay@yamasoto.com')

        body = f"""Nueva solicitud de Nookplay

Nombre: {nombre}
Negocio: {negocio}
Ubicación: {ubicacion}
Teléfono: {telefono}
Email: {email}

Mensaje:
{mensaje}
"""
        msg = MIMEMultipart()
        msg['From'] = smtp_user or to_email
        msg['To'] = to_email
        msg['Subject'] = f'Nueva solicitud Nookplay — {negocio or nombre}'
        msg['Reply-To'] = email
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        if smtp_user and smtp_pass:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            # Log to console if no SMTP configured
            app.logger.info(f'CONTACT REQUEST (no SMTP): {body}')

        return jsonify({'ok': True})
    except Exception as e:
        app.logger.error(f'Contact email error: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Games management
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Plan config — fuente única de verdad
# Para añadir un juego nuevo: añadirlo a ALL_GAMES y a los planes que corresponda.
# El resto de la lógica (admin, API, front) se actualiza solo.
# ─────────────────────────────────────────────────────────────────────────────

# Slugs de todos los juegos del catálogo, en orden de posición
ALL_GAMES = [
    "crimen", "dilema", "reinas", "conexiones",
    "oraculo", "donde", "carta", "equilibrio", "impostor", "local", "veredicto", "perfil", "vestuario", "sinopsis", "muertes", "letra", "pensamiento", "poema", "menteagil", "constitucion", "muertes", "letra", "sinopsis", "vestuario", "perfil",
]

# Starter: 4 fijos siempre activos + 1 elegible a elegir entre STARTER_FREE_GAMES
STARTER_FIXED      = ["crimen", "dilema", "reinas", "conexiones"]
STARTER_FREE_GAMES = ["oraculo", "donde", "carta", "equilibrio", "impostor", "local", "veredicto", "perfil", "vestuario", "sinopsis", "muertes", "letra", "pensamiento", "poema", "menteagil", "constitucion"]
STARTER_MAX_FREE   = 1  # juegos libres simultáneos permitidos

# Pro: hasta PRO_MAX_GAMES a elegir libremente del catálogo completo
PRO_MAX_GAMES = 11  # cuando el catálogo crezca más, Pro sigue limitado aquí

# Premium: acceso a todo ALL_GAMES sin límite

# Gift (interno): acceso a todo, sin coste — no visible en la web pública

PLAN_CFG = {
    "starter": {
        "name":  "Plan Starter",
        "price": "6,95€/mes",
        "desc":  "4 juegos fijos + 1 libre a elegir",
        "stats": "basic",
    },
    "pro": {
        "name":  "Plan Pro",
        "price": "9,95€/mes",
        "desc":  f"Hasta {PRO_MAX_GAMES} juegos a elegir",
        "stats": "basic",
    },
    "premium": {
        "name":  "Plan Premium",
        "price": "14,95€/mes",
        "desc":  "Todos los juegos del catálogo",
        "stats": "advanced",
    },
    "gift": {
        "name":  "Plan Gift",
        "price": "Gratuito",
        "desc":  "Todos los juegos (interno)",
        "stats": "advanced",
    },
    "total": {
        "name":  "Plan Total",
        "price": "—",
        "desc":  "Todos los juegos",
        "stats": "advanced",
    },
}


@app.route("/api/bar-games/<bar_slug>")
def get_bar_games(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({"error": "Not found"}), 404

    plan = bar["plan"] or "starter"
    all_games = db.execute("SELECT * FROM games WHERE active = 1 ORDER BY position").fetchall()
    bar_games_rows = db.execute(
        "SELECT game_slug, active FROM bar_games WHERE bar_id = ?",
        (bar["id"],)
    ).fetchall()

    active_slugs = {bg["game_slug"] for bg in bar_games_rows if bg["active"]}

    # Starter: autoreparación — si hay más de un juego libre activo
    # (datos antiguos), conservar solo el primero y desactivar el resto
    if plan == "starter":
        free_active = [s for s in active_slugs if s not in STARTER_FIXED]
        if len(free_active) > 1:
            keep = free_active[0]
            for extra in free_active[1:]:
                db.execute(
                    "UPDATE bar_games SET active = 0 WHERE bar_id = ? AND game_slug = ?",
                    (bar["id"], extra),
                )
                active_slugs.discard(extra)
            db.commit()
    db.close()

    result = []
    for g in all_games:
        slug = g["slug"]
        is_active = slug in active_slugs

        if plan in ("gift", "total", "premium"):
            # Acceso ilimitado a todo el catálogo
            is_fixed = False
            available = True
            selectable = True
        elif plan == "pro":
            # Hasta PRO_MAX_GAMES juegos a elegir del catálogo completo
            is_fixed = False
            available = True
            active_count = len(active_slugs)
            # Puede seleccionar si no ha llegado al límite, o si ya está activo
            selectable = is_active or active_count < PRO_MAX_GAMES
        else:  # starter
            is_fixed = slug in STARTER_FIXED
            available = is_fixed or slug in STARTER_FREE_GAMES
            selectable = not is_fixed  # fijos no son seleccionables
            if is_fixed:
                is_active = True  # los fijos siempre están activos

        result.append({
            "slug": slug,
            "name": g["name"],
            "description": g["description"],
            "icon": g["icon"],
            "active": is_active,
            "available": available,
            "fixed": is_fixed,
            "selectable": selectable,
        })

    return jsonify(result)


@app.route("/api/admin/bar-games", methods=["POST"])
def save_bar_games():
    if "admin_user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    bar_slug = data.get("bar_slug")
    game_slug = data.get("game_slug")
    active = data.get("active", True)

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ?", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({"error": "Bar not found"}), 404

    user = db.execute("SELECT * FROM admin_users WHERE id = ?", (session["admin_user_id"],)).fetchone()
    if user["role"] != "superadmin" and user["bar_slug"] != bar_slug:
        db.close()
        return jsonify({"error": "Unauthorized"}), 401

    plan = bar["plan"] or "starter"

    # Validaciones de plan (server-side, fuente única de verdad)
    if plan == "starter":
        if game_slug in STARTER_FIXED and not active:
            db.close()
            return jsonify({"error": "Los juegos fijos del plan Starter no se pueden desactivar"}), 400
        if active and game_slug not in STARTER_FIXED and game_slug not in STARTER_FREE_GAMES:
            db.close()
            return jsonify({"error": "Este juego requiere un plan superior"}), 400

    elif plan == "pro" and active:
        # Pro: máximo PRO_MAX_GAMES activos simultáneos
        current_active = db.execute(
            "SELECT COUNT(*) FROM bar_games WHERE bar_id = ? AND active = 1",
            (bar["id"],)
        ).fetchone()[0]
        already_active = db.execute(
            "SELECT active FROM bar_games WHERE bar_id = ? AND game_slug = ?",
            (bar["id"], game_slug)
        ).fetchone()
        is_already_active = already_active and already_active["active"]
        if not is_already_active and current_active >= PRO_MAX_GAMES:
            db.close()
            return jsonify({"error": f"El plan Pro permite un máximo de {PRO_MAX_GAMES} juegos activos"}), 400

    sql = "INSERT INTO bar_games (bar_id, game_slug, active) VALUES (?, ?, ?) ON CONFLICT(bar_id, game_slug) DO UPDATE SET active = excluded.active"
    db.execute(sql, (bar["id"], game_slug, 1 if active else 0))

    # Starter: selección única para juego libre
    if plan == "starter" and active and game_slug not in STARTER_FIXED:
        placeholders = ",".join("?" * len(STARTER_FIXED))
        db.execute(
            f"UPDATE bar_games SET active = 0 WHERE bar_id = ? AND game_slug != ? AND game_slug NOT IN ({placeholders})",
            (bar["id"], game_slug, *STARTER_FIXED),
        )

    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route('/static/og.png')
def og_image():
    from flask import send_file
    return send_file('static/og.svg', mimetype='image/svg+xml')

# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

@app.route('/admin/api/upload-logo', methods=['POST'])
@admin_required
def admin_upload_logo():
    bar_slug = request.form.get('bar_slug', '').strip()
    if session.get('admin_role') != 'superadmin' and session.get('admin_bar_slug') != bar_slug:
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403
    if 'logo' not in request.files:
        return jsonify({'ok': False, 'error': 'No file'})
    file = request.files['logo']
    if file.filename == '':
        return jsonify({'ok': False, 'error': 'Empty filename'})
    import os as _os
    folder = f'static/clientes/{bar_slug}'
    _os.makedirs(folder, exist_ok=True)
    file.save(f'{folder}/logo_header.png')
    return jsonify({'ok': True})


@app.route('/admin/api/upload-product-image', methods=['POST'])
@admin_required
def admin_upload_product_image():
    bar_slug = request.form.get('bar_slug', '').strip()
    position = request.form.get('position', '0').strip()
    if session.get('admin_role') != 'superadmin' and session.get('admin_bar_slug') != bar_slug:
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403
    if 'image' not in request.files:
        return jsonify({'ok': False, 'error': 'No file'})
    file = request.files['image']
    if file.filename == '':
        return jsonify({'ok': False, 'error': 'Empty filename'})
    try:
        from PIL import Image as _Image
        import io as _io
        import os as _os
        folder = f'static/clientes/{bar_slug}'
        _os.makedirs(folder, exist_ok=True)
        img = _Image.open(file.stream).convert('RGB')
        # Redimensionar a máximo 600px manteniendo ratio
        max_size = 600
        if img.width > max_size or img.height > max_size:
            ratio = min(max_size / img.width, max_size / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, _Image.LANCZOS)
        out_path = f'{folder}/product_{position}.webp'
        img.save(out_path, 'WEBP', quality=82, method=6)
        return jsonify({'ok': True, 'path': f'/{out_path}'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/admin/api/delete-product-image', methods=['POST'])
@admin_required
def admin_delete_product_image():
    data = request.get_json()
    bar_slug = data.get('bar_slug', '').strip()
    position = data.get('position', '0')
    if session.get('admin_role') != 'superadmin' and session.get('admin_bar_slug') != bar_slug:
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403
    import os as _os
    path = f'static/clientes/{bar_slug}/product_{position}.webp'
    try:
        if _os.path.exists(path):
            _os.remove(path)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/admin/api/delete-bar', methods=['POST'])
@admin_required
def admin_delete_bar():
    if session.get('admin_role') != 'superadmin':
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403
    data = request.get_json()
    bar_slug = data.get('bar_slug', '').strip()
    if not bar_slug or bar_slug == 'yellow':
        return jsonify({'ok': False, 'error': 'No se puede eliminar este local'})
    db = get_db()
    try:
        bar = db.execute("SELECT id FROM bars WHERE slug = ?", (bar_slug,)).fetchone()
        if not bar:
            db.close()
            return jsonify({'ok': False, 'error': 'Local no encontrado'})
        bar_id = bar['id']
        db.execute("DELETE FROM bar_products WHERE bar_id = ?", (bar_id,))
        db.execute("DELETE FROM access_codes WHERE bar_id = ?", (bar_id,))
        db.execute("DELETE FROM access_log WHERE bar_id = ?", (bar_id,))
        db.execute("DELETE FROM generated_games WHERE bar_id = ?", (bar_id,))
        db.execute("DELETE FROM plays WHERE bar_slug = ?", (bar_slug,))
        db.execute("DELETE FROM admin_users WHERE bar_slug = ?", (bar_slug,))
        db.execute("DELETE FROM bars WHERE id = ?", (bar_id,))
        db.commit()
        db.close()
        return jsonify({'ok': True})
    except Exception as e:
        db.close()
        return jsonify({'ok': False, 'error': str(e)})

# ─────────────────────────────────────────────────────────────────────────────
# Superadmin routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    if session.get('admin_role') != 'superadmin':
        return redirect('/admin')
    db = get_db()
    today = str(date.today())
    from datetime import timedelta
    monday = date.today() - timedelta(days=date.today().weekday())
    bars_raw = db.execute("SELECT * FROM bars WHERE active = 1 ORDER BY created_at DESC").fetchall()
    bars = []
    for bar in bars_raw:
        plays = db.execute("SELECT COUNT(*) as n FROM plays WHERE bar_slug = ?", (bar['slug'],)).fetchone()['n']
        bar_dict = dict(bar)
        bar_dict['plays_count'] = plays
        bars.append(bar_dict)
    stats = {
        'total_bars': len(bars),
        'plays_today': db.execute("SELECT COUNT(*) as n FROM plays WHERE played_on = ?", (today,)).fetchone()['n'],
        'plays_week': db.execute("SELECT COUNT(*) as n FROM plays WHERE played_on >= ?", (str(monday),)).fetchone()['n'],
        'plays_total': db.execute("SELECT COUNT(*) as n FROM plays").fetchone()['n'],
    }
    db.close()
    return render_template('admin/dashboard.html', bars=bars, stats=stats)

@app.route('/admin/api/create-bar', methods=['POST'])
@admin_required
def admin_create_bar():
    if session.get('admin_role') != 'superadmin':
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403
    data = request.get_json()
    name = data.get('name', '').strip()
    slug = data.get('slug', '').strip()
    city = data.get('city', '').strip()
    plan = data.get('plan', 'gift')
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    color = data.get('color_primary', '#C4622D')
    if not all([name, slug, city, email, password]):
        return jsonify({'ok': False, 'error': 'Faltan campos obligatorios'})
    import random as _random
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    new_code = ''.join(_random.choices(chars, k=5))
    db = get_db()
    try:
        color_bg = data.get('color_bg', '#F7F2EB')
        address = data.get('address', '')
        province = data.get('province', '')
        zip_code = data.get('zip_code', '')
        latitude = data.get('latitude', None)
        longitude = data.get('longitude', None)
        try:
            latitude = float(latitude) if latitude else None
            longitude = float(longitude) if longitude else None
        except: pass

        db.execute(
            "INSERT INTO bars (slug, name, city, province, address, zip_code, latitude, longitude, plan, plan_status, color_primary, color_primary_text, color_bg, color_bg_subtle, color_accent_dark, active) VALUES (?,?,?,?,?,?,?,?,?,'active',?,'#FFFFFF',?,'#F0EBE3','#1A1A1A',1)",
            (slug, name, city, province, address, zip_code, latitude, longitude, plan, color, color_bg)
        )
        bar = db.execute("SELECT id FROM bars WHERE slug = ?", (slug,)).fetchone()
        bar_id = bar['id']
        from datetime import timedelta
        today_d = date.today()
        monday = today_d - timedelta(days=today_d.weekday())
        sunday = monday + timedelta(days=6)
        db.execute("UPDATE bars SET access_code = ? WHERE id = ?", (new_code, bar_id))
        db.execute("INSERT INTO access_codes (bar_id, code, valid_from, valid_until) VALUES (?,?,?,?)",
                  (bar_id, new_code, str(monday), str(sunday)))
        db.execute(
            "INSERT INTO admin_users (email, password_hash, role, bar_slug) VALUES (?,?,?,?)",
            (email, hash_password(password), 'bar_admin', slug)
        )

        # Inicializar bar_games según el plan — el bar nace con sus juegos ya activos
        if plan in ('gift', 'total', 'premium'):
            active_slugs = ALL_GAMES
        elif plan == 'pro':
            active_slugs = ALL_GAMES  # Pro empieza con todos disponibles; el admin los filtra
        else:  # starter
            active_slugs = STARTER_FIXED  # Los 4 fijos; el libre lo elige el propietario

        for game_slug in active_slugs:
            db.execute(
                "INSERT OR IGNORE INTO bar_games (bar_id, game_slug, active) VALUES (?,?,1)",
                (bar_id, game_slug)
            )

        db.commit()
        db.close()
        import os as _os
        _os.makedirs(f'static/clientes/{slug}', exist_ok=True)
        return jsonify({'ok': True, 'code': new_code})
    except Exception as e:
        db.rollback()
        db.close()
        return jsonify({'ok': False, 'error': str(e)})
