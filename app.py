from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import date, datetime, timedelta
import sqlite3
from ai import generate_game, generate_impostor, generate_dilema, generate_conexiones, generate_oraculo, generate_donde, generate_carta, generate_reinas, generate_conexion_local, generate_equilibrio, generate_veredicto, generate_perfil, generate_vestuario, generate_trivia, generate_sinopsis, generate_muertes, generate_letra, generate_pensamiento, generate_poema, generate_menteagil, generate_constitucion, generate_orden, generate_titular, generate_definicion, generate_masomenos, generate_escalera, generate_quienmas, build_bar_context, get_day_seed, set_event_theme, reset_event_theme, set_variant_hint
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import random
import string
import time

app = Flask(__name__)

@app.after_request
def _no_cache_admin(resp):
    """El panel de admin NUNCA se cachea: cada visita trae el HTML y el JS del último deploy.
    (Sin esto, el navegador puede servir el panel entero desde caché durante días.)"""
    from flask import request as _rq
    if _rq.path.startswith('/admin'):
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
    return resp
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
    db = get_db()
    game_count = db.execute("SELECT COUNT(*) AS n FROM games WHERE active = 1").fetchone()['n']
    db.close()
    return render_template('home.html', game_count=game_count)

@app.route('/juegos')
def games_catalog():
    db = get_db()
    games = db.execute("SELECT slug, name, description, icon, plan_min FROM games WHERE active = 1 ORDER BY position").fetchall()
    db.close()
    games = [dict(g) for g in games]
    for g in games:
        g['tematizable'] = g['slug'] in EVENT_GAME_TYPES
    return render_template('games.html', games=games)



# ─────────────────────────────────────────────────────────────────────────────
# Scheduled tasks
# ─────────────────────────────────────────────────────────────────────────────

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

_TZ_MADRID = pytz.timezone('Europe/Madrid')

def now_madrid_iso():
    """Devuelve el timestamp actual en hora local de Madrid, formato ISO (YYYY-MM-DD HH:MM:SS)."""
    return datetime.now(_TZ_MADRID).strftime('%Y-%m-%d %H:%M:%S')

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
    # Excluir demos (código permanente), eventos (códigos manuales por día) y
    # locales que el dueño puso en modo manual (él lo cambia cuando quiera).
    bars = db.execute(
        "SELECT id, slug FROM bars WHERE active = 1 AND (plan IS NULL OR plan != 'demo') "
        "AND (space_kind IS NULL OR space_kind != 'evento') AND (code_manual IS NULL OR code_manual = 0)"
    ).fetchall()
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
            "SELECT content FROM generated_games WHERE game_type = ? AND bar_id = (SELECT id FROM bars WHERE slug = ?) AND game_date >= ? AND game_date <= ? ORDER BY game_date DESC",
            (game_type, bar_slug, desde, hoy)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT content FROM generated_games WHERE game_type = ? AND game_date >= ? AND game_date <= ? ORDER BY game_date DESC",
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
            elif campo == 'trivia_preguntas' and 'preguntas' in data:
                # trivia: el enunciado de cada pregunta
                for p in data['preguntas']:
                    if isinstance(p, dict) and p.get('pregunta'):
                        items.append(p['pregunta'][:90])
            elif campo == 'opciones' and 'opciones' in data:
                # sinopsis/letra: la respuesta correcta
                idx = data.get('correcta', 0)
                if isinstance(data['opciones'], list) and idx < len(data['opciones']):
                    items.append(data['opciones'][idx])
            elif campo == 'masomenos_preguntas' and 'rondas' in data:
                # masomenos: la pregunta de cada ronda
                for r in data['rondas']:
                    if isinstance(r, dict) and r.get('pregunta'):
                        items.append(r['pregunta'][:90])
            elif campo == 'afirmaciones' and 'afirmaciones' in data:
                # quienmas: cada afirmación
                for a in data['afirmaciones']:
                    if isinstance(a, str) and a.strip():
                        items.append(a[:90])
            elif campo == 'conexiones_grupos':
                # conexiones: los nombres de los 4 grupos temáticos
                for k in ('grupo_a', 'grupo_b', 'grupo_c', 'grupo_d'):
                    g = data.get(k)
                    if isinstance(g, dict) and g.get('nombre'):
                        items.append(g['nombre'][:60])
            elif campo == 'escalera_enunciados' and 'preguntas' in data:
                # escalera: el enunciado de cada pregunta
                for p in data['preguntas']:
                    if isinstance(p, dict) and p.get('enunciado'):
                        items.append(p['enunciado'][:90])
            elif campo in data and data[campo]:
                items.append(str(data[campo]))
        except Exception:
            continue
    return items[:30]


def _theme_de(bar):
    """Compone el tema completo de un evento: temática + nivel del público +
    datos internos. Devuelve '' si no es un evento o no tiene temática.
    Acepta una fila sqlite3.Row o un dict. Todo lo que devuelve viaja por
    contextvar a TODOS los generadores (pregen y fallbacks) sin tocar firmas.
    La temática es el interruptor maestro: sin ella, no hay ambientación."""
    try:
        b = dict(bar)
    except Exception:
        return ''
    if (b.get('space_kind') or 'local') != 'evento':
        return ''
    tema = (b.get('event_theme', '') or '').strip()
    if not tema:
        return ''
    partes = [tema]

    # Nivel de afición del público: gradúa las referencias (de lo popular al deep cut)
    NIVELES = {
        'general': ("NIVEL DEL PÚBLICO: variado, con mucha gente no experta. Usa referencias "
                    "que cualquiera reconoce; evita guiños de nicho que dejen fuera a la mayoría."),
        'fan': ("NIVEL DEL PÚBLICO: aficionado. Mezcla referencias populares con guiños "
                "que un fan medio reconoce y agradece."),
        'experto': ("NIVEL DEL PÚBLICO: muy entendido. Usa referencias profundas y guiños de "
                    "nicho que solo la comunidad pilla; huye de lo demasiado obvio o trillado."),
    }
    nivel = (b.get('event_fan_level') or 'fan').strip()
    partes.append(NIVELES.get(nivel, NIVELES['fan']))

    # Datos internos: lo que la IA no puede saber (invitados, anécdotas, lugares del evento)
    insider = (b.get('event_insider', '') or '').strip()
    if insider:
        partes.append(
            "DATOS INTERNOS DE ESTE EVENTO (menciónalos cuando encajen de forma natural — "
            "son lo que hace que el contenido se sienta hecho a medida y no genérico; "
            "no los fuerces en todas las piezas, repártelos):\n" + insider
        )
    return "\n\n".join(partes)


def _persistir_generado(bar_id, game_type, game_data, es_global=False):
    """Guarda un juego generado bajo demanda en generated_games (idempotente).

    Usa una conexión propia con commit para que persista entre workers.
    Si es_global=True, solo guarda si no existe ya un registro global para hoy.
    Devuelve True si guardó, False si ya existía o hubo error no crítico.
    """
    import json as _json
    from datetime import date as _date
    hoy = str(_date.today())
    try:
        dbp = get_db()
        if es_global:
            ya = dbp.execute(
                "SELECT id FROM generated_games WHERE game_type = ? AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
                (game_type, hoy)
            ).fetchone()
        else:
            ya = dbp.execute(
                "SELECT id FROM generated_games WHERE bar_id = ? AND game_type = ? AND game_date = ?",
                (bar_id, game_type, hoy)
            ).fetchone()
        if ya:
            dbp.close()
            return False
        dbp.execute(
            "INSERT INTO generated_games (bar_id, game_type, game_date, content) VALUES (?,?,?,?)",
            (bar_id, game_type, hoy, _json.dumps(game_data))
        )
        dbp.commit()
        dbp.close()
        return True
    except Exception as e:
        print(f"[FALLBACK] No se pudo persistir {game_type}/{bar_id}: {e}")
        return False
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


def _intentar_claim_pregen(ttl=300):
    """Intenta tomar el lock de pre-generación de forma atómica (entre workers).

    Devuelve True si este proceso ha tomado el lock, False si ya estaba tomado.
    Usa una transacción IMMEDIATE de SQLite para que solo un worker gane.
    """
    ahora = time.time()
    db = get_db()
    try:
        db.execute("CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT DEFAULT '')")
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT value FROM app_state WHERE key = 'pregen_running'").fetchone()
        ocupado = False
        if row and row['value']:
            try:
                ocupado = (ahora - float(row['value'])) < ttl
            except (ValueError, TypeError):
                ocupado = False
        if ocupado:
            db.execute("ROLLBACK")
            return False
        db.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('pregen_running', ?)", (str(ahora),))
        db.execute("COMMIT")
        return True
    except Exception:
        try:
            db.execute("ROLLBACK")
        except Exception:
            pass
        return False
    finally:
        db.close()


def _liberar_lock_pregen():
    """Libera el lock de pre-generación."""
    try:
        db = get_db()
        db.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('pregen_running', '')", ())
        db.commit()
        db.close()
    except Exception:
        pass


def pregen_daily_games_scheduled():
    """Wrapper del cron diario: toma el lock atómico para que solo un worker
    de gunicorn ejecute la pre-generación de las 6am (evita doble trabajo)."""
    if not _intentar_claim_pregen():
        print("[CRON] Pre-generación ya en curso en otro worker; se omite.")
        return
    try:
        pregen_daily_games()
    finally:
        _liberar_lock_pregen()


def pregen_daily_games():
    """Ejecuta cada día a las 6am — pre-genera los juegos del día para todos los bares."""
    today = str(date.today())
    resumen = {'ok': [], 'error': []}
    # Juegos por-bar: los únicos que un evento genera (y en pool si procede)
    POOL_GAME_TYPES = EVENT_GAME_TYPES
    GAME_TYPES = ['crimen', 'impostor', 'dilema', 'conexiones', 'oraculo', 'donde', 'local', 'veredicto', 'perfil', 'vestuario', 'trivia', 'sinopsis', 'muertes', 'letra', 'pensamiento', 'menteagil', 'constitucion', 'titular', 'definicion', 'masomenos', 'escalera', 'quienmas', 'orden']

    db = get_db()
    bars = db.execute("SELECT * FROM bars WHERE active = 1").fetchall()
    # Inicializar el contador de progreso (estimación: juegos x bares)
    _pregen_estado['total'] = len(bars) * len(GAME_TYPES)
    _pregen_estado['hechos'] = 0
    for bar in bars:
        # ── Evento: activar tema temático para todos sus juegos ────────────
        # Cada bar sobrescribe el tema al entrar (evento→su tema, local→''),
        # así ningún espacio hereda el tema del anterior. Los bares normales
        # quedan con tema vacío y su generación es idéntica a la de siempre.
        _bar_d = dict(bar)
        set_event_theme(_theme_de(_bar_d))
        set_variant_hint(0)
        _es_evento_bar = (_bar_d.get('space_kind') or 'local') == 'evento'
        try:
            _pool_n = max(1, min(20, int(_bar_d.get('event_pool_size') or 1))) if _es_evento_bar else 1
        except (TypeError, ValueError):
            _pool_n = 1
        # ── Evento fuera de fechas: no gastar IA a diario ────────────────
        # Genera solo si hoy cae dentro de event_start→event_end, o si el
        # superadmin activó el modo pruebas. Probar sin modo pruebas sigue
        # funcionando: el fallback de cada juego genera bajo demanda.
        if (_bar_d.get('space_kind') or 'local') == 'evento':
            _ev_start = _bar_d.get('event_start') or ''
            _ev_end = _bar_d.get('event_end') or ''
            _hoy_en_evento = bool(_ev_start) and bool(_ev_end) and (_ev_start <= today <= _ev_end)
            if not _hoy_en_evento and not _bar_d.get('event_test_mode'):
                continue
        for game_type in GAME_TYPES:
            # Un evento solo genera juegos por-bar (los tematizables). Los globales
            # compartidos no: irían con la temática del evento a todos los bares.
            if _es_evento_bar and game_type not in POOL_GAME_TYPES:
                continue
            # Pool de variantes: los eventos generan hasta _pool_n piezas por juego.
            # Bares: _target=1 y comportamiento idéntico al de siempre.
            _target = _pool_n if game_type in POOL_GAME_TYPES else 1
            _hechas = db.execute(
                "SELECT COUNT(*) n FROM generated_games WHERE bar_id = ? AND game_type = ? AND game_date = ?",
                (bar['id'], game_type, today)
            ).fetchone()['n']
            for _rep in range(max(0, _target - _hechas)):
                if _target > 1:
                    set_variant_hint(_hechas + _rep + 1)
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
                        ev = get_historial_reciente(db, 'impostor', bar['slug'], campo='tema')
                        game_data = generate_impostor(bar['name'], bar['slug'], evitar=ev)
                    elif game_type == 'dilema':
                        ev = get_historial_reciente(db, 'dilema', bar['slug'], campo='situacion')
                        game_data = generate_dilema(bar['name'], bar['slug'], evitar=ev)
                    elif game_type == 'conexiones':
                        ev = get_historial_reciente(db, 'conexiones', bar['slug'], campo='conexiones_grupos')
                        game_data = generate_conexiones(bar['name'], bar['slug'], evitar=ev)
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
                        ev = get_historial_reciente(db, 'donde', None, campo='lugar')
                        game_data = generate_donde(bar['slug'], evitar=ev)
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
                    elif game_type == 'trivia':
                        ev = get_historial_reciente(db, 'trivia', bar['slug'], campo='trivia_preguntas')
                        game_data = generate_trivia(bar['slug'], evitar=ev)
                    elif game_type == 'sinopsis':
                        # Bares: única global. Eventos: propia y temática (con pool)
                        if not _es_evento_bar:
                            existing = db.execute(
                                "SELECT id FROM generated_games WHERE game_type = 'sinopsis' AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
                                (today,)
                            ).fetchone()
                            if existing:
                                continue
                        ev = get_historial_reciente(db, 'sinopsis', bar['slug'] if _es_evento_bar else None, campo='opciones')
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
                        if not _es_evento_bar:
                            existing = db.execute(
                                "SELECT id FROM generated_games WHERE game_type = 'letra' AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
                                (today,)
                            ).fetchone()
                            if existing:
                                continue
                        ev = get_historial_reciente(db, 'letra', bar['slug'] if _es_evento_bar else None, campo='opciones')
                        game_data = generate_letra(bar['slug'], evitar=ev)
                    elif game_type == 'pensamiento':
                        existing = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'pensamiento' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing:
                            continue
                        ev = get_historial_reciente(db, 'pensamiento', None, campo='categoria')
                        game_data = generate_pensamiento(bar['slug'], evitar=ev)
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
                    elif game_type == 'titular':
                        existing = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'titular' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing:
                            continue
                        ev = get_historial_reciente(db, 'titular', None, campo='titular')
                        game_data = generate_titular(bar['slug'], evitar=ev)
                    elif game_type == 'definicion':
                        existing = db.execute(
                            "SELECT id FROM generated_games WHERE game_type = 'definicion' AND game_date = ?",
                            (today,)
                        ).fetchone()
                        if existing:
                            continue
                        ev = get_historial_reciente(db, 'definicion', None, campo='palabra')
                        game_data = generate_definicion(bar['slug'], evitar=ev)
                    elif game_type == 'masomenos':
                        if not _es_evento_bar:
                            existing = db.execute(
                                "SELECT id FROM generated_games WHERE game_type = 'masomenos' AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
                                (today,)
                            ).fetchone()
                            if existing:
                                continue
                        ev = get_historial_reciente(db, 'masomenos', bar['slug'] if _es_evento_bar else None, campo='masomenos_preguntas')
                        game_data = generate_masomenos(bar['slug'], evitar=ev)
                    elif game_type == 'escalera':
                        if not _es_evento_bar:
                            existing = db.execute(
                                "SELECT id FROM generated_games WHERE game_type = 'escalera' AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
                                (today,)
                            ).fetchone()
                            if existing:
                                continue
                        ev = get_historial_reciente(db, 'escalera', bar['slug'] if _es_evento_bar else None, campo='escalera_enunciados')
                        game_data = generate_escalera(bar['slug'], evitar=ev)
                    elif game_type == 'orden':
                        if not _es_evento_bar:
                            continue  # bares: El Orden se genera bajo demanda, como siempre
                        game_data = generate_orden(bar['slug'])
                    elif game_type == 'quienmas':
                        if not _es_evento_bar:
                            existing = db.execute(
                                "SELECT id FROM generated_games WHERE game_type = 'quienmas' AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
                                (today,)
                            ).fetchone()
                            if existing:
                                continue
                        ev = get_historial_reciente(db, 'quienmas', bar['slug'] if _es_evento_bar else None, campo='afirmaciones')
                        game_data = generate_quienmas(bar['slug'], evitar=ev)
                    
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

def backup_database():
    """Copia de seguridad diaria de la BD usando la API segura de SQLite.

    Usa sqlite3 .backup() (consistente incluso con escrituras en curso, a
    diferencia de copiar el fichero). Guarda en /data/backups y mantiene
    solo los últimos 7 días para no llenar el disco.
    """
    import os as _os
    import glob as _glob
    try:
        backup_dir = '/data/backups'
        _os.makedirs(backup_dir, exist_ok=True)
        hoy = date.today().strftime('%Y-%m-%d')
        destino = _os.path.join(backup_dir, f'nookplay-{hoy}.db')

        origen = sqlite3.connect('/data/nookplay.db', timeout=30)
        dest = sqlite3.connect(destino)
        with dest:
            origen.backup(dest)
        dest.close()
        origen.close()

        # Rotación: conservar solo los 7 backups más recientes
        backups = sorted(_glob.glob(_os.path.join(backup_dir, 'nookplay-*.db')))
        for viejo in backups[:-7]:
            try:
                _os.remove(viejo)
            except OSError:
                pass
        print(f"[BACKUP] Copia creada: {destino} ({len(backups[-7:])} copias conservadas)")
    except Exception as e:
        print(f"[BACKUP] Error al hacer copia de seguridad: {e}")


def start_scheduler():
    scheduler = BackgroundScheduler(timezone=pytz.timezone('Europe/Madrid'))
    # Lunes a las 6am — códigos semanales
    scheduler.add_job(generate_weekly_codes, CronTrigger(day_of_week='mon', hour=6, minute=0))
    # Cada día a las 6am — pre-generación de juegos (con lock atómico entre workers)
    scheduler.add_job(pregen_daily_games_scheduled, CronTrigger(hour=6, minute=0))
    # Cada día a las 4am — copia de seguridad de la BD (antes de la regeneración)
    scheduler.add_job(backup_database, CronTrigger(hour=4, minute=0))
    scheduler.start()
    print("[SCHEDULER] Iniciado — códigos lunes 6am, juegos diarios 6am, backup diario 4am")

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

    # Claim atómico del lock a nivel de BD (compartido y seguro entre los 2 workers
    # de gunicorn). threading.Lock NO basta porque solo aísla hilos del mismo proceso.
    if not _intentar_claim_pregen():
        return jsonify({'ok': True, 'msg': 'Ya hay una regeneración en curso.', 'corriendo': True})

    def _run():
        # El lock ya está tomado (claim atómico arriba). Este hilo solo ejecuta.
        try:
            # Limpiar errores previos y borrar contenido de hoy para regenerar
            dbx = get_db()
            dbx.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('pregen_errores', '')", ())
            dbx.execute("DELETE FROM generated_games WHERE game_date = ?", (today,))
            dbx.commit()
            dbx.close()
            global _game_cache
            for _k in [k for k in _game_cache if today in k]:
                del _game_cache[_k]

            resumen = pregen_daily_games()

            # Guardar errores y éxitos en BD para diagnóstico
            errores = resumen['error'] if resumen else []
            oks = resumen['ok'] if resumen else []
            dbx2 = get_db()
            dbx2.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('pregen_errores', ?)", ('|||'.join(errores),))
            dbx2.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('pregen_ok', ?)", ('|||'.join(oks),))
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
            _liberar_lock_pregen()

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
    generados_lista = []
    try:
        estado_row = db.execute("SELECT value FROM app_state WHERE key = 'pregen_running'").fetchone()
        if estado_row and estado_row['value']:
            try:
                corriendo = (time.time() - float(estado_row['value'])) < 300
            except Exception:
                corriendo = False
        err_row = db.execute("SELECT value FROM app_state WHERE key = 'pregen_errores'").fetchone()
        errores = err_row['value'].split('|||') if (err_row and err_row['value']) else []
        ok_row = db.execute("SELECT value FROM app_state WHERE key = 'pregen_ok'").fetchone()
        generados_lista = ok_row['value'].split('|||') if (ok_row and ok_row['value']) else []
    except Exception:
        generados_lista = []
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
            'generados': [g for g in generados_lista if g][:40],
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

def calcular_analytics_bar(db, bar_slug, ventana=None):
    """Calcula métricas de valor para el dueño del local o el organizador del evento.

    ventana=None (bares): ventana semanal lunes-hoy con tendencia vs semana anterior.
    ventana=(desde, hasta) (eventos): todas las métricas se calculan dentro de esa
    ventana (strings YYYY-MM-DD), sin tendencia (no hay "periodo anterior" comparable).
    El comportamiento sin ventana es EXACTAMENTE el de siempre: los bares no cambian.

    Nota sobre los datos: la tabla `plays` deduplica por (device_id, día, juego),
    así que cada registro = "un juego distinto jugado por un dispositivo ese día".
    Es una medida de actividad/cobertura, no de pulsaciones brutas.
    """
    from datetime import timedelta
    hoy = date.today()
    es_ventana = ventana is not None and ventana[0] and ventana[1]
    if es_ventana:
        # Evento: la ventana es event_start→min(event_end, hoy). Días futuros no cuentan.
        try:
            v_desde = datetime.strptime(ventana[0], '%Y-%m-%d').date()
            v_hasta = min(datetime.strptime(ventana[1], '%Y-%m-%d').date(), hoy)
        except (ValueError, TypeError):
            es_ventana = False
    if not es_ventana:
        monday = hoy - timedelta(days=hoy.weekday())
        monday_prev = monday - timedelta(days=7)
        sunday_prev = monday - timedelta(days=1)
        v_desde, v_hasta = monday, hoy

    a = {
        'week': 0, 'today': 0, 'prev_week': 0, 'trend_pct': None, 'trend_dir': 'flat',
        'best_day': None, 'best_day_count': 0,
        'best_hour': None, 'best_hour_count': 0,
        'top_game': None, 'top_game_count': 0,
        'active_days': 0, 'has_data': False, 'has_hour_data': False,
        'daily': [],  # lista de {dia, count} de la semana actual para mini-gráfico
        'people_week': 0, 'has_device_data': False,  # alcance real (dispositivos únicos)
        'total_historico': 0, 'people_historico': 0,  # acumulado desde el inicio
        'avg_day': 0,  # media de partidas por día activo
        'top_games': [],  # top 3 juegos de la semana [{name, count}]
        'ventana_evento': False,  # True si las métricas son de la ventana del evento
    }
    a['ventana_evento'] = bool(es_ventana)

    # Volumen semana actual y hoy
    a['week'] = db.execute(
        "SELECT COUNT(*) n FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=?",
        (bar_slug, str(v_desde), str(v_hasta))).fetchone()['n']
    a['today'] = db.execute(
        "SELECT COUNT(*) n FROM plays WHERE bar_slug=? AND played_on=?",
        (bar_slug, str(hoy))).fetchone()['n']

    # Acumulado histórico (se muestra siempre, da sensación de valor acumulado)
    a['total_historico'] = db.execute(
        "SELECT COUNT(*) n FROM plays WHERE bar_slug=?", (bar_slug,)).fetchone()['n']
    a['people_historico'] = db.execute(
        "SELECT COUNT(DISTINCT device_id) n FROM plays WHERE bar_slug=? AND device_id!=''",
        (bar_slug,)).fetchone()['n']

    if a['week'] == 0:
        return a
    a['has_data'] = True

    # Alcance real de la ventana: dispositivos (personas/mesas) distintos
    a['people_week'] = db.execute(
        "SELECT COUNT(DISTINCT device_id) n FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=? AND device_id!=''",
        (bar_slug, str(v_desde), str(v_hasta))).fetchone()['n']
    a['has_device_data'] = a['people_week'] > 0

    # Tendencia vs periodo anterior: solo tiene sentido en modo semanal (bares)
    if not es_ventana:
        a['prev_week'] = db.execute(
            "SELECT COUNT(*) n FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=?",
            (bar_slug, str(monday_prev), str(sunday_prev))).fetchone()['n']
        if a['prev_week'] > 0:
            diff = (a['week'] - a['prev_week']) / a['prev_week'] * 100
            a['trend_pct'] = round(abs(diff))
            a['trend_dir'] = 'up' if diff > 5 else ('down' if diff < -5 else 'flat')

    # Reparto por día de la ventana
    dias_es = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    por_dia = db.execute(
        "SELECT played_on, COUNT(*) n FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=? GROUP BY played_on",
        (bar_slug, str(v_desde), str(v_hasta))).fetchall()
    conteo_dia = {r['played_on']: r['n'] for r in por_dia}
    a['active_days'] = len(conteo_dia)
    n_dias = min((v_hasta - v_desde).days + 1, 31)  # tope de barras del mini-gráfico
    for i in range(n_dias):
        d = v_desde + timedelta(days=i)
        if d > hoy:
            break
        c = conteo_dia.get(str(d), 0)
        # Etiqueta: día de la semana (bares) o día del mes (eventos, ej. "10")
        etiqueta = dias_es[d.weekday()][:3] if not es_ventana else str(d.day)
        a['daily'].append({'dia': etiqueta, 'count': c})
        if c > a['best_day_count']:
            a['best_day_count'] = c
            a['best_day'] = dias_es[d.weekday()] if not es_ventana else f"{dias_es[d.weekday()]} {d.day}"

    # Franja horaria más activa (requiere played_at; solo registros nuevos lo tienen)
    filas_hora = db.execute(
        "SELECT played_at FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=? AND played_at!=''",
        (bar_slug, str(v_desde), str(v_hasta))).fetchall()
    if filas_hora:
        from collections import Counter
        horas = Counter()
        for r in filas_hora:
            try:
                h = int(r['played_at'][11:13])
                horas[h] += 1
            except (ValueError, IndexError):
                continue
        if horas:
            a['has_hour_data'] = True
            top_h, top_c = horas.most_common(1)[0]
            a['best_hour'] = f"{top_h:02d}:00–{(top_h+1)%24:02d}:00"
            a['best_hour_count'] = top_c

    # Top juegos de la ventana (favorito + top 3)
    top_juegos = db.execute(
        "SELECT game_type, COUNT(*) n FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=? GROUP BY game_type ORDER BY n DESC LIMIT 3",
        (bar_slug, str(v_desde), str(v_hasta))).fetchall()
    if top_juegos:
        a['top_game'] = top_juegos[0]['game_type']
        a['top_game_count'] = top_juegos[0]['n']
        a['top_games'] = [
            {'name': GAME_NOMBRES.get(r['game_type'], r['game_type']), 'count': r['n']}
            for r in top_juegos
        ]

    # Media de partidas por día activo
    if a['active_days'] > 0:
        a['avg_day'] = round(a['week'] / a['active_days'], 1)

    return a


# Nombres legibles de los juegos (para mostrar al dueño del local)
# Juegos por-bar tematizables: los que un evento genera como propios (con pool).
# Única fuente de verdad — la usan el pregen, el panel y la regeneración.
EVENT_GAME_TYPES = {'crimen', 'impostor', 'dilema', 'conexiones', 'veredicto', 'perfil',
                    'vestuario', 'trivia', 'local', 'orden', 'sinopsis', 'letra',
                    'quienmas', 'escalera', 'masomenos'}

GAME_NOMBRES = {
    'crimen': 'El Crimen del Día', 'impostor': 'El Impostor', 'dilema': 'El Dilema',
    'conexiones': 'Conexiones', 'oraculo': 'El Oráculo', 'donde': '¿Dónde está?',
    'local': 'Conexión Local', 'veredicto': 'El Veredicto', 'perfil': 'El Perfil',
    'vestuario': 'El Vestuario', 'trivia': 'La Trivia', 'sinopsis': 'La Sinopsis', 'muertes': 'Muertes Célebres',
    'letra': 'Adivina la Letra', 'pensamiento': 'El Mismo Pensamiento',
    'menteagil': 'Mente Ágil', 'constitucion': '¿Tú la has leído?', 'poema': 'El Poema',
    'freep': 'Freep', 'reinas': 'Las Reinas', 'equilibrio': 'Equilibrio',
    'carta': 'La Carta', 'orden': 'En Orden',
    'titular': 'El Titular Imposible', 'definicion': 'La Definición Falsa',
    'dosverdades': 'Dos Verdades, Una Mentira', 'masomenos': 'Más o Menos',
    'escalera': 'La Escalera', 'quienmas': '¿Quién es más probable?',
}


def calcular_analytics_evento(db, bar):
    """Métricas con ventana DEL EVENTO (event_start → min(event_end, hoy)).

    Devuelve un dict con la misma forma que calcular_analytics_bar para
    reutilizar la plantilla del panel; cambia la ventana temporal y añade
    'event_state' ('antes'/'durante'/'despues') para los mensajes.
    Sin tendencia semanal (trend_pct=None): no aplica a un evento.
    Es el informe que justifica el valor: "X asistentes, Y partidas en N días".
    """
    from datetime import timedelta, datetime as _dt
    hoy = date.today()
    bar_slug = bar['slug']

    a = {
        'week': 0, 'today': 0, 'prev_week': 0, 'trend_pct': None, 'trend_dir': 'flat',
        'best_day': None, 'best_day_count': 0,
        'best_hour': None, 'best_hour_count': 0,
        'top_game': None, 'top_game_name': None, 'top_game_count': 0,
        'active_days': 0, 'has_data': False, 'has_hour_data': False,
        'daily': [],
        'people_week': 0, 'has_device_data': False,
        'total_historico': 0, 'people_historico': 0,
        'avg_day': 0,
        'top_games': [],
        'event_state': 'antes',  # antes / durante / despues
    }

    # Acumulado histórico (incluye pruebas pre-evento; siempre visible)
    a['total_historico'] = db.execute(
        "SELECT COUNT(*) n FROM plays WHERE bar_slug=?", (bar_slug,)).fetchone()['n']
    a['people_historico'] = db.execute(
        "SELECT COUNT(DISTINCT device_id) n FROM plays WHERE bar_slug=? AND device_id!=''",
        (bar_slug,)).fetchone()['n']

    # Ventana del evento
    try:
        d0 = _dt.strptime(bar['event_start'], '%Y-%m-%d').date()
        d1 = _dt.strptime(bar['event_end'], '%Y-%m-%d').date()
    except (ValueError, TypeError, KeyError):
        return a  # sin fechas válidas: estado vacío
    if d1 < d0:
        return a

    if hoy < d0:
        a['event_state'] = 'antes'
    elif hoy > d1:
        a['event_state'] = 'despues'
    else:
        a['event_state'] = 'durante'

    fin_ventana = min(d1, hoy)
    if fin_ventana < d0:
        return a  # el evento aún no ha empezado: sin ventana que medir

    ini, fin = str(d0), str(fin_ventana)

    # Volumen del evento y hoy
    a['week'] = db.execute(
        "SELECT COUNT(*) n FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=?",
        (bar_slug, ini, fin)).fetchone()['n']
    a['today'] = db.execute(
        "SELECT COUNT(*) n FROM plays WHERE bar_slug=? AND played_on=?",
        (bar_slug, str(hoy))).fetchone()['n']

    if a['week'] == 0:
        return a
    a['has_data'] = True

    # Asistentes distintos (dispositivos) durante el evento
    a['people_week'] = db.execute(
        "SELECT COUNT(DISTINCT device_id) n FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=? AND device_id!=''",
        (bar_slug, ini, fin)).fetchone()['n']
    a['has_device_data'] = a['people_week'] > 0

    # Reparto por día del evento (etiqueta "Vie 10" = día semana + nº)
    dias_es_abr = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    por_dia = db.execute(
        "SELECT played_on, COUNT(*) n FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=? GROUP BY played_on",
        (bar_slug, ini, fin)).fetchall()
    conteo_dia = {r['played_on']: r['n'] for r in por_dia}
    a['active_days'] = len([v for v in conteo_dia.values() if v > 0])
    n_dias = (fin_ventana - d0).days + 1
    for i in range(min(n_dias, 14)):  # tope visual: 14 barras
        d = d0 + timedelta(days=i)
        c = conteo_dia.get(str(d), 0)
        etiqueta = f"{dias_es_abr[d.weekday()]} {d.day}"
        a['daily'].append({'dia': etiqueta, 'count': c})
        if c > a['best_day_count']:
            a['best_day_count'] = c
            a['best_day'] = etiqueta

    # Franja horaria más activa dentro del evento
    filas_hora = db.execute(
        "SELECT played_at FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=? AND played_at!=''",
        (bar_slug, ini, fin)).fetchall()
    if filas_hora:
        from collections import Counter
        horas = Counter()
        for r in filas_hora:
            try:
                h = int(r['played_at'][11:13])
                horas[h] += 1
            except (ValueError, IndexError):
                continue
        if horas:
            a['has_hour_data'] = True
            top_h, top_c = horas.most_common(1)[0]
            a['best_hour'] = f"{top_h:02d}:00–{(top_h+1)%24:02d}:00"
            a['best_hour_count'] = top_c

    # Top juegos del evento
    top_juegos = db.execute(
        "SELECT game_type, COUNT(*) n FROM plays WHERE bar_slug=? AND played_on>=? AND played_on<=? GROUP BY game_type ORDER BY n DESC LIMIT 3",
        (bar_slug, ini, fin)).fetchall()
    if top_juegos:
        a['top_game'] = top_juegos[0]['game_type']
        a['top_game_name'] = GAME_NOMBRES.get(top_juegos[0]['game_type'], top_juegos[0]['game_type'])
        a['top_game_count'] = top_juegos[0]['n']
        a['top_games'] = [
            {'name': GAME_NOMBRES.get(r['game_type'], r['game_type']), 'count': r['n']}
            for r in top_juegos
        ]

    # Media por día activo
    if a['active_days'] > 0:
        a['avg_day'] = round(a['week'] / a['active_days'], 1)

    return a


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
    # Analytics: los eventos miden su ventana (event_start→event_end); los bares, la semana
    if (bar['space_kind'] or 'local') == 'evento' and bar['event_start'] and bar['event_end']:
        analytics = calcular_analytics_bar(db, bar_slug, ventana=(bar['event_start'], bar['event_end']))
    else:
        analytics = calcular_analytics_bar(db, bar_slug)

    # Códigos por día + código admin permanente (solo eventos)
    event_days = []
    event_admin_code = ''
    if (bar['space_kind'] or 'local') == 'evento':
        rows = db.execute(
            "SELECT valid_from, valid_until, code FROM access_codes WHERE bar_id = ?",
            (bar['id'],)
        ).fetchall()
        # El código admin es la fila con ventana centinela 2000→2099
        for r in rows:
            if r['valid_from'] == '2000-01-01' and r['valid_until'] == '2099-12-31':
                event_admin_code = r['code']
                break
        # Días del evento: una fila por día (valid_from == valid_until == ese día)
        if bar['event_start'] and bar['event_end']:
            try:
                from datetime import datetime as _dt, timedelta as _td
                d0 = _dt.strptime(bar['event_start'], '%Y-%m-%d').date()
                d1 = _dt.strptime(bar['event_end'], '%Y-%m-%d').date()
                if d1 >= d0 and (d1 - d0).days <= 60:  # tope de seguridad
                    por_dia = {r['valid_from']: r['code'] for r in rows
                               if r['valid_from'] == r['valid_until']}
                    n = (d1 - d0).days + 1
                    for i in range(n):
                        dia = str(d0 + _td(days=i))
                        event_days.append({'date': dia, 'code': por_dia.get(dia, '')})
            except (ValueError, TypeError):
                event_days = []

    db.close()
    stats = {'today': stats_today, 'week': stats_week, 'pct_correct': pct_correct}
    # Nombre legible del juego favorito
    if analytics.get('top_game'):
        analytics['top_game_name'] = GAME_NOMBRES.get(analytics['top_game'], analytics['top_game'])
    # Contenido de hoy (solo eventos): estado de generación por juego activo
    contenido_hoy = []
    if (bar['space_kind'] or 'local') == 'evento':
        try:
            _dbc = get_db()
            _activos = [r['game_slug'] for r in _dbc.execute(
                "SELECT game_slug FROM bar_games WHERE bar_id = ? AND active = 1", (bar['id'],)
            ).fetchall()]
            _hoy_ch = str(date.today())
            for _gs in _activos:
                if _gs not in EVENT_GAME_TYPES:
                    continue
                _n = _dbc.execute(
                    "SELECT COUNT(*) n FROM generated_games WHERE bar_id = ? AND game_type = ? AND game_date = ?",
                    (bar['id'], _gs, _hoy_ch)
                ).fetchone()['n']
                contenido_hoy.append({'slug': _gs, 'name': GAME_NOMBRES.get(_gs, _gs), 'count': _n})
            _dbc.close()
        except Exception:
            contenido_hoy = []

    return render_template('admin/bar_panel.html', bar=bar, products=products,
                           current_code=current_code, valid_until=valid_until_str, stats=stats,
                           analytics=analytics, event_days=event_days, event_admin_code=event_admin_code,
                           contenido_hoy=contenido_hoy,
                           admin_role=session.get('admin_role','bar_admin'))

def _normalizar_handle(valor, dominio):
    """Normaliza un usuario de red social. Acepta '@usuario', 'usuario',
    o una URL completa pegada, y devuelve solo el handle limpio (sin @, sin URL).
    Si está vacío devuelve ''."""
    v = (valor or '').strip()
    if not v:
        return ''
    low = v.lower()
    if 'http' in low or dominio in low:
        if dominio in low:
            v = v[low.index(dominio) + len(dominio):]
        v = v.lstrip('/')
        v = v.split('?')[0].split('/')[0]
    v = v.lstrip('@').strip()
    return v[:80]


def _normalizar_url(valor):
    """Normaliza una URL de carta/menú. Si tiene valor y no lleva esquema,
    antepone https://. Si está vacío devuelve ''."""
    v = (valor or '').strip()
    if not v:
        return ''
    if not v.lower().startswith(('http://', 'https://')):
        v = 'https://' + v
    return v[:300]


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

    # Config de evento: solo superadmin puede cambiar tipo de espacio y su config
    if session.get('admin_role') == 'superadmin' and 'space_kind' in data:
        # El tipo es INMUTABLE desde el alta: se ignora cualquier intento de cambio.
        _sk = (bar['space_kind'] or 'local')
        try:
            _pool = int(data.get('event_pool_size', 1) or 1)
        except (TypeError, ValueError):
            _pool = 1
        _pool = max(1, min(20, _pool))
        db.execute(
            "UPDATE bars SET space_kind=?, event_theme=?, event_start=?, event_end=?, event_pool_size=?, event_test_mode=?, event_insider=?, event_fan_level=? WHERE slug=?",
            (_sk, data.get('event_theme', '') or '', data.get('event_start', '') or '',
             data.get('event_end', '') or '', _pool, 1 if data.get('event_test_mode') else 0,
             (data.get('event_insider', '') or '')[:4000],
             data.get('event_fan_level') if data.get('event_fan_level') in ('general', 'fan', 'experto') else 'fan',
             bar_slug)
        )

    db.execute(
        "UPDATE bars SET welcome_message=?, tomorrow_message=?, promo_active=?, description=?, owner_name=?, staff_names=?, color_primary=?, color_primary_text=?, color_bg=?, color_bg_subtle=?, address=?, city=?, province=?, zip_code=?, country=?, latitude=?, longitude=?, social_instagram=?, social_facebook=?, social_tiktok=?, menu_url=?, menu_label=? WHERE slug=?",
        (data.get('welcome_message',''), data.get('tomorrow_message',''), data.get('promo_active',0),
         data.get('description',''), data.get('owner_name',''),
         data.get('staff_names',''), data.get('color_primary','#C4622D'),
         data.get('color_primary_text','#FFFFFF'), data.get('color_bg','#F7F2EB'),
         data.get('color_bg_subtle','#F0EBE3'), data.get('address',''),
         data.get('city',''), data.get('province',''), data.get('zip_code',''),
         data.get('country','España'), lat, lng,
         _normalizar_handle(data.get('social_instagram',''), 'instagram.com'),
         _normalizar_handle(data.get('social_facebook',''), 'facebook.com'),
         _normalizar_handle(data.get('social_tiktok',''), 'tiktok.com'),
         _normalizar_url(data.get('menu_url','')),
         (data.get('menu_label','') or '')[:30],
         bar_slug)
    )
    db.execute("DELETE FROM bar_products WHERE bar_id = ?", (bar['id'],))
    for p in data.get('products', []):
        if p.get('title'):
            # Recuperar image_path existente si no se envía nueva
            import os as _os
            pos = p.get('position', 0)
            # Prioridad: media persistente (/data); respaldo: assets commiteados en el repo
            if _os.path.exists(f"{MEDIA_ROOT}/{bar_slug}/product_{pos}.webp"):
                image_path = f"/media/{bar_slug}/product_{pos}.webp"
            elif _os.path.exists(f"static/clientes/{bar_slug}/product_{pos}.webp"):
                image_path = f"/static/clientes/{bar_slug}/product_{pos}.webp"
            else:
                image_path = ''
            db.execute(
                "INSERT INTO bar_products (bar_id, position, title, description, price, image_path, active) VALUES (?,?,?,?,?,?,1)",
                (bar['id'], pos, p['title'], p.get('description',''), p.get('price',''), image_path)
            )
    db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/admin/informe/<bar_slug>')
@admin_required
def admin_informe(bar_slug):
    """Informe del evento: documento imprimible (Guardar como PDF) con los
    resultados de la ventana del evento. Pensado para que el organizador lo
    reenvíe a su junta o patrocinadores — y como material comercial del
    siguiente evento. Solo eventos con fechas definidas."""
    if session.get('admin_role') != 'superadmin' and session.get('admin_bar_slug') != bar_slug:
        return redirect('/admin')
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return redirect('/admin')
    if (bar['space_kind'] or 'local') != 'evento' or not (bar['event_start'] and bar['event_end']):
        db.close()
        return redirect(f'/admin/{bar_slug}')
    analytics = calcular_analytics_bar(db, bar_slug, ventana=(bar['event_start'], bar['event_end']))
    db.close()
    max_daily = max([d['count'] for d in analytics.get('daily', [])], default=0)
    # Fechas legibles en español: "12–15 de noviembre de 2026"
    MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
             'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    try:
        d1 = datetime.strptime(bar['event_start'], '%Y-%m-%d').date()
        d2 = datetime.strptime(bar['event_end'], '%Y-%m-%d').date()
        if d1.month == d2.month and d1.year == d2.year:
            fechas_str = f"{d1.day}–{d2.day} de {MESES[d1.month-1]} de {d1.year}"
        else:
            fechas_str = f"{d1.day} de {MESES[d1.month-1]} — {d2.day} de {MESES[d2.month-1]} de {d2.year}"
    except (ValueError, TypeError):
        fechas_str = f"{bar['event_start']} — {bar['event_end']}"
    return render_template('admin/informe.html', bar=bar, a=analytics,
                           max_daily=max_daily, fechas_str=fechas_str, hoy=str(date.today()))


@app.route('/admin/api/regen-game', methods=['POST'])
def admin_regen_game():
    """Descarta el contenido de HOY de un juego del evento para que se genere
    de nuevo (temático) al abrirlo. Reutiliza los fallbacks existentes — un solo
    camino de generación (lección 25). Límite diario por evento para controlar
    el gasto de IA. Endpoint aislado: solo toca generated_games/variant_views."""
    data = request.get_json() or {}
    bar_slug = data.get('bar_slug')
    gt = data.get('game_type')
    if session.get('admin_role') != 'superadmin' and session.get('admin_bar_slug') != bar_slug:
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403
    if gt not in EVENT_GAME_TYPES:
        return jsonify({'ok': False, 'error': 'Este juego no admite regeneración'}), 400
    db = get_db()
    bar = db.execute("SELECT id, space_kind FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'ok': False, 'error': 'No encontrado'}), 404
    if (bar['space_kind'] or 'local') != 'evento':
        db.close()
        return jsonify({'ok': False, 'error': 'Solo disponible en eventos'}), 400

    LIMITE_DIARIO = 10
    hoy = str(date.today())
    key = f"regen_{bar['id']}_{hoy}"
    row = db.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    usadas = int(row['value']) if row and (row['value'] or '').isdigit() else 0
    if usadas >= LIMITE_DIARIO:
        db.close()
        return jsonify({'ok': False, 'error': f'Límite de {LIMITE_DIARIO} regeneraciones diarias alcanzado'}), 429

    gg = db.execute(
        "SELECT id FROM generated_games WHERE bar_id = ? AND game_type = ? AND game_date = ?",
        (bar['id'], gt, hoy)
    ).fetchall()
    ids = [r['id'] for r in gg]
    if ids:
        marcas = ','.join('?' * len(ids))
        db.execute(f"DELETE FROM variant_views WHERE gg_id IN ({marcas})", ids)
        db.execute(f"DELETE FROM generated_games WHERE id IN ({marcas})", ids)
    db.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)", (key, str(usadas + 1)))
    db.commit()
    db.close()
    # Limpiar la caché en memoria de este worker (los pools ya la ignoran)
    _game_cache.pop(f"{bar_slug}_{gt}_{hoy}", None)
    return jsonify({'ok': True, 'descartadas': len(ids), 'restantes': LIMITE_DIARIO - usadas - 1})


@app.route('/admin/qr/<bar_slug>.png')
@admin_required
def admin_qr_png(bar_slug):
    """PNG del QR de acceso del espacio (apunta a nookplay.app/<slug>).

    Generado en servidor para resolución de imprenta garantizada, sin depender
    del navegador ni de CDNs. Cada admin solo puede pedir el QR de su espacio.
    ?size= píxeles del lado (240 vista previa, hasta 2400 para imprenta)."""
    if session.get('admin_role') != 'superadmin' and session.get('admin_bar_slug') != bar_slug:
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403
    db = get_db()
    bar = db.execute("SELECT id FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    db.close()
    if not bar:
        return jsonify({'ok': False, 'error': 'No encontrado'}), 404
    try:
        size = max(160, min(2400, int(request.args.get('size', 240))))
    except (TypeError, ValueError):
        size = 240
    import io as _io
    import qrcode as _qrcode
    qr = _qrcode.QRCode(border=2, error_correction=_qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(f"https://nookplay.app/{bar_slug}")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    # Reescalar al tamaño pedido (NEAREST mantiene los módulos nítidos, sin difuminar)
    img = img.resize((size, size), resample=0)
    buf = _io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    from flask import send_file as _send_file
    resp = _send_file(buf, mimetype='image/png')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/admin/api/local-code', methods=['POST'])
def admin_local_code():
    """Activa/desactiva el código manual de un LOCAL y, si se activa, guarda el
    código que el propio dueño elija. Endpoint aislado del resto del formulario
    (admin_save) a propósito: éste solo toca code_manual y access_codes, para no
    arriesgar pisar el resto de campos del bar con un payload parcial.

    Con code_manual=1: la rotación semanal (lunes 6am) salta este bar. El dueño
    entra cuando quiera y pone el código que quiera, sin caducidad forzada.
    Con code_manual=0: se cierra la ventana del código manual (si había) y la
    rotación automática retoma con normalidad."""
    data = request.get_json() or {}
    bar_slug = data.get('bar_slug')
    if session.get('admin_role') != 'superadmin' and session.get('admin_bar_slug') != bar_slug:
        return jsonify({'ok': False, 'error': 'No autorizado'}), 403

    db = get_db()
    bar = db.execute("SELECT id, space_kind FROM bars WHERE slug = ?", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'ok': False, 'error': 'No encontrado'}), 404
    if (bar['space_kind'] or 'local') == 'evento':
        db.close()
        return jsonify({'ok': False, 'error': 'Los eventos usan su propio sistema de códigos'}), 400

    _cm = 1 if data.get('code_manual') else 0
    db.execute("UPDATE bars SET code_manual=? WHERE slug=?", (_cm, bar_slug))

    if _cm:
        _code = _normalizar_codigo(data.get('manual_code') or '')
        if not _code:
            db.close()
            return jsonify({'ok': False, 'error': 'Escribe un código'}), 400
        # Ventana amplia (centinela): dura hasta que el dueño lo cambie, sin caducar solo.
        existing = db.execute(
            "SELECT id FROM access_codes WHERE bar_id = ? AND valid_from = '2000-01-01' AND valid_until = '2099-12-31'",
            (bar['id'],)
        ).fetchone()
        if existing:
            db.execute("UPDATE access_codes SET code=? WHERE id=?", (_code, existing['id']))
        else:
            db.execute(
                "INSERT INTO access_codes (bar_id, code, valid_from, valid_until) VALUES (?,?,?,?)",
                (bar['id'], _code, '2000-01-01', '2099-12-31')
            )
    else:
        # Vuelta a automático: cerrar el código manual para que no conviva
        # para siempre en paralelo a la rotación semanal.
        db.execute(
            "DELETE FROM access_codes WHERE bar_id = ? AND valid_from = '2000-01-01' AND valid_until = '2099-12-31'",
            (bar['id'],)
        )
    db.commit()
    db.close()
    return jsonify({'ok': True})


@app.route('/admin/api/event-codes', methods=['POST'])
@admin_required
def admin_event_codes():
    """Guarda los códigos por día de un evento (solo superadmin).

    Recibe {bar_slug, admin_code: 'ABC12', codes: [{date: 'YYYY-MM-DD', code: 'ABC12'}, ...]}.
    - admin_code: código permanente que siempre funciona (para pruebas). Se guarda como
      fila con ventana centinela 2000-01-01 → 2099-12-31, que la validación (que filtra
      por ventana de fecha) acepta cualquier día. Vacío = se elimina.
    - codes: un código por día del evento (valid_from = valid_until = ese día).
    Upsert por (bar_id, valid_from). No toca la lógica de validación de acceso."""
    if session.get('admin_role') != 'superadmin':
        return jsonify({'ok': False, 'error': 'Solo superadmin'}), 403
    data = request.get_json() or {}
    bar_slug = data.get('bar_slug')
    codes = data.get('codes', [])
    admin_code = _normalizar_codigo(data.get('admin_code') or '')
    if not isinstance(codes, list):
        return jsonify({'ok': False, 'error': 'Formato inválido'}), 400

    db = get_db()
    bar = db.execute("SELECT id, space_kind FROM bars WHERE slug = ?", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return jsonify({'ok': False, 'error': 'No encontrado'}), 404
    if (bar['space_kind'] or 'local') != 'evento':
        db.close()
        return jsonify({'ok': False, 'error': 'No es un evento'}), 400

    # Ventana centinela del código de admin permanente
    ADMIN_FROM, ADMIN_UNTIL = '2000-01-01', '2099-12-31'
    existing_admin = db.execute(
        "SELECT id FROM access_codes WHERE bar_id = ? AND valid_from = ? AND valid_until = ?",
        (bar['id'], ADMIN_FROM, ADMIN_UNTIL)
    ).fetchone()
    if admin_code:
        if existing_admin:
            db.execute("UPDATE access_codes SET code = ? WHERE id = ?", (admin_code, existing_admin['id']))
        else:
            db.execute("INSERT INTO access_codes (bar_id, code, valid_from, valid_until) VALUES (?,?,?,?)",
                       (bar['id'], admin_code, ADMIN_FROM, ADMIN_UNTIL))
    elif existing_admin:
        db.execute("DELETE FROM access_codes WHERE id = ?", (existing_admin['id'],))

    guardados = 0
    for item in codes:
        fecha = (item.get('date') or '').strip()
        code = _normalizar_codigo(item.get('code') or '')
        # Validar fecha YYYY-MM-DD
        try:
            from datetime import datetime as _dt
            _dt.strptime(fecha, '%Y-%m-%d')
        except (ValueError, TypeError):
            continue
        # Seguridad: no permitir que un "día" use la ventana centinela del admin
        if fecha in (ADMIN_FROM, ADMIN_UNTIL):
            continue
        if not code:
            # Código vacío para ese día: borrar el del día (solo la fila de ese día concreto)
            db.execute("DELETE FROM access_codes WHERE bar_id = ? AND valid_from = ? AND valid_until = ?",
                       (bar['id'], fecha, fecha))
            continue
        existing = db.execute(
            "SELECT id FROM access_codes WHERE bar_id = ? AND valid_from = ? AND valid_until = ?",
            (bar['id'], fecha, fecha)
        ).fetchone()
        if existing:
            db.execute("UPDATE access_codes SET code = ? WHERE id = ?", (code, existing['id']))
        else:
            db.execute("INSERT INTO access_codes (bar_id, code, valid_from, valid_until) VALUES (?,?,?,?)",
                       (bar['id'], code, fecha, fecha))
        guardados += 1
    db.commit()
    db.close()
    return jsonify({'ok': True, 'guardados': guardados})

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


@app.route('/admin/api/change-password', methods=['POST'])
@admin_required
def admin_change_password():
    """Permite a un bar_admin cambiar su propia contraseña."""
    data = request.get_json()
    current_pw = data.get('current_password', '').strip()
    new_pw = data.get('new_password', '').strip()
    confirm_pw = data.get('confirm_password', '').strip()

    if not current_pw or not new_pw or not confirm_pw:
        return jsonify({'ok': False, 'error': 'Rellena todos los campos.'}), 400
    if new_pw != confirm_pw:
        return jsonify({'ok': False, 'error': 'Las contraseñas nuevas no coinciden.'}), 400
    if len(new_pw) < 8:
        return jsonify({'ok': False, 'error': 'La contraseña debe tener al menos 8 caracteres.'}), 400

    db = get_db()
    user = db.execute("SELECT * FROM admin_users WHERE id = ?", (session['admin_user_id'],)).fetchone()
    if not user or user['password_hash'] != hash_password(current_pw):
        db.close()
        return jsonify({'ok': False, 'error': 'La contraseña actual no es correcta.'}), 403

    db.execute("UPDATE admin_users SET password_hash = ? WHERE id = ?",
               (hash_password(new_pw), session['admin_user_id']))
    db.commit()
    db.close()
    return jsonify({'ok': True})


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

    # Demo (plan 'demo'): garantizar un código y entregarlo a la plantilla (acceso sin pedir código)
    demo_code = ''
    is_demo = (bar['plan'] or '') == 'demo'
    if is_demo:
        from datetime import timedelta
        today = str(date.today())
        # Misma consulta (sin ORDER BY) que usan las APIs de los juegos, para que el código coincida
        vigente = db.execute(
            "SELECT code FROM access_codes WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?",
            (bar['id'], today, today)
        ).fetchone()
        if vigente:
            demo_code = vigente['code']
        else:
            demo_code = 'DEMO'
            lejano = str(date.today() + timedelta(days=3650))
            db.execute(
                "INSERT INTO access_codes (bar_id, code, valid_from, valid_until) VALUES (?,?,?,?)",
                (bar['id'], demo_code, today, lejano)
            )
            db.commit()

    db.close()
    import json as json_lib
    products_json = json_lib.dumps([dict(p) for p in products])
    return render_template('bar.html', bar=bar, products=products, products_json=products_json,
                           demo_code=demo_code, is_demo=is_demo)

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

def _normalizar_codigo(raw):
    """Normaliza el código tecleado por el cliente para tolerar errores comunes.

    Los códigos usan el alfabeto ABCDEFGHJKLMNPQRSTUVWXYZ23456789 (sin O, I, 0, 1
    para evitar confusiones visuales). La normalización es deliberadamente
    conservadora: limpia espacios y separadores y pasa a mayúsculas, pero NO
    intenta "adivinar" letras confundibles (mapear O->0, I->1, etc.), porque un
    autocorrección equivocada podría validar un código distinto al real. Es más
    seguro que el cliente reintente que arriesgar un acceso erróneo.
    """
    if not raw:
        return ''
    s = raw.strip().upper()
    for sep in (' ', '-', '_', '.', '·', '\t'):
        s = s.replace(sep, '')
    return s


@app.route('/api/validate', methods=['POST'])
def validate_code():
    data = request.get_json()
    code = _normalizar_codigo(data.get('code', ''))
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()

    if not bar:
        db.close()
        return jsonify({'valid': False, 'message': 'Local no encontrado.'})

    if not code:
        db.close()
        return jsonify({'valid': False, 'message': 'Escribe el código que aparece en la barra.'})

    # Buscar código válido esta semana
    valid = db.execute("""
        SELECT code FROM access_codes
        WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?
    """, (bar['id'], code, today, today)).fetchone()

    if not valid:
        db.close()
        return jsonify({'valid': False,
                        'message': 'Ese código no nos cuadra. Revisa la pizarra de la barra y vuelve a intentarlo — son 5 caracteres.'})

    # Registrar acceso (solo analytics)
    db.execute("INSERT INTO access_log (bar_id, code_used) VALUES (?, ?)", (bar['id'], code))
    db.commit()
    db.close()

    return jsonify({'valid': True, 'bar_name': bar['name']})

# --------------------------------------------------------------------------
# API — Juegos
# --------------------------------------------------------------------------


# ─── Pool de variantes (eventos) ───────────────────────────────────────────
# Un evento con event_pool_size>1 tiene N piezas por juego y día. Cada
# dispositivo recibe la primera variante que no haya visto; si las vio todas,
# la más antigua. Fuente de verdad: BD (multi-worker safe).

_pool_slugs_cache = {'t': 0.0, 'v': set()}

def _pool_slugs():
    """Slugs de espacios con pool de variantes activo (TTL 60s)."""
    import time as _t
    if _t.time() - _pool_slugs_cache['t'] > 60:
        try:
            dbp = get_db()
            rows = dbp.execute(
                "SELECT slug FROM bars WHERE space_kind='evento' AND event_pool_size>1 AND active=1"
            ).fetchall()
            dbp.close()
            _pool_slugs_cache['v'] = {r['slug'] for r in rows}
            _pool_slugs_cache['t'] = _t.time()
        except Exception:
            pass
    return _pool_slugs_cache['v']


def _leer_pregenerado(db, bar_id, game_type, today):
    """Lee el contenido pre-generado de un juego. Devuelve una fila con
    ['content'] o None (compatible con el fetchone() al que sustituye).

    Con una sola pieza (bares, o eventos sin pool): idéntico a antes.
    Con varias (pool de evento): elige variante por dispositivo — la primera
    no vista, o la vista hace más tiempo si ya las vio todas — y registra
    la vista en variant_views."""
    rows = db.execute(
        "SELECT id, content FROM generated_games WHERE bar_id = ? AND game_type = ? AND game_date = ? ORDER BY id",
        (bar_id, game_type, today)
    ).fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    device_id = ''
    try:
        body = request.get_json(silent=True) or {}
        device_id = str(body.get('device_id') or '')[:80]
    except Exception:
        pass
    if not device_id:
        import random as _r
        return rows[_r.randrange(len(rows))]
    ids = [r['id'] for r in rows]
    marcas = ','.join('?' * len(ids))
    vistos = db.execute(
        f"SELECT gg_id, viewed_at FROM variant_views WHERE device_id = ? AND gg_id IN ({marcas})",
        [device_id] + ids
    ).fetchall()
    vistos_map = {v['gg_id']: v['viewed_at'] for v in vistos}
    no_vistas = [r for r in rows if r['id'] not in vistos_map]
    elegido = no_vistas[0] if no_vistas else min(rows, key=lambda r: vistos_map.get(r['id'], ''))
    try:
        db.execute(
            "INSERT OR REPLACE INTO variant_views (device_id, gg_id, viewed_at) VALUES (?,?,?)",
            (device_id, elegido['id'], now_madrid_iso())
        )
        db.commit()
    except Exception:
        pass
    return elegido


class _GameCache(dict):
    """Caché en memoria por worker. Para espacios con pool de variantes se
    desactiva (contains siempre False, set ignorado): cachear una sola
    respuesta impediría servir variantes distintas por dispositivo."""
    @staticmethod
    def _es_pool(key):
        try:
            return key.rsplit('_', 2)[0] in _pool_slugs()
        except Exception:
            return False
    def __contains__(self, key):
        if self._es_pool(key):
            return False
        return super().__contains__(key)
    def __setitem__(self, key, value):
        if self._es_pool(key):
            return
        super().__setitem__(key, value)


_game_cache = _GameCache()


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
    cached = _leer_pregenerado(db, bar['id'], 'crimen', today)

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
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_game(bar_context, bar_slug)
        finally:
            reset_event_theme(_tok)
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

    cached = _leer_pregenerado(db, bar['id'], 'impostor', today)

    if cached:
        db.close()
        return jsonify(json.loads(cached['content']))

    bar_context = build_bar_context(dict(bar))
    db.close()

    try:
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'impostor', bar_slug, campo='tema')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_impostor(bar_context['nombre'], bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
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
    device_id = (data.get('device_id') or '').strip()[:40]
    today = str(date.today())

    db = get_db()
    # Anti-duplicado: si tenemos identificador de dispositivo, contamos UNA vez por
    # (dispositivo, día, juego) -> así personas distintas suman por separado pero la
    # misma persona repitiendo el mismo juego ese día no infla. Sin device_id (cliente
    # antiguo), caemos al comportamiento previo por (código, día, juego).
    if device_id:
        played = db.execute(
            "SELECT id FROM plays WHERE device_id = ? AND played_on = ? AND game_type = ?",
            (device_id, today, game_type)
        ).fetchone()
    else:
        played = db.execute(
            "SELECT id FROM plays WHERE code = ? AND played_on = ? AND game_type = ? AND (device_id IS NULL OR device_id = '')",
            (code, today, game_type)
        ).fetchone()

    if not played:
        db.execute(
            "INSERT INTO plays (code, bar_slug, played_on, correct, game_type, choice, elapsed, played_at, device_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (code, bar_slug, today, 1 if correct else 0, game_type, choice, elapsed, now_madrid_iso(), device_id)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    bar_name = bar['name']
    bar_id = bar['id']

    cache_key = f"{bar_slug}_dilema_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    # Check pre-generated
    pregenerated = _leer_pregenerado(db, bar_id, 'dilema', today)
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()

    try:
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'dilema', bar_slug, campo='situacion')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_dilema(bar_name, bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _bid = bar['id']
        _persistir_generado(_bid, 'dilema', game_data, es_global=False)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    bar_name = bar['name']
    bar_id = bar['id']

    cache_key = f"{bar_slug}_veredicto_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = _leer_pregenerado(db, bar_id, 'veredicto', today)
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()

    try:
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'veredicto', bar_slug, campo='titulo')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_veredicto(bar_name, bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _bid = bar['id']
        _persistir_generado(_bid, 'veredicto', game_data, es_global=False)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    bar_id = bar['id']
    cache_key = f"{bar_slug}_perfil_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = _leer_pregenerado(db, bar_id, 'perfil', today)
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()

    try:
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'perfil', bar_slug, campo='nombre')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_perfil(bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _bid = bar['id']
        _persistir_generado(_bid, 'perfil', game_data, es_global=False)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    bar_id = bar['id']
    cache_key = f"{bar_slug}_vestuario_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = _leer_pregenerado(db, bar_id, 'vestuario', today)
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()

    try:
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'vestuario', bar_slug, campo='preguntas')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_vestuario(bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _bid = bar['id']
        _persistir_generado(_bid, 'vestuario', game_data, es_global=False)
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


@app.route('/<bar_slug>/trivia')
def trivia_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/trivia.html', bar=bar, products=products)


@app.route('/api/trivia', methods=['POST'])
def trivia_api():
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    bar_id = bar['id']
    cache_key = f"{bar_slug}_trivia_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = _leer_pregenerado(db, bar_id, 'trivia', today)
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()

    try:
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'trivia', bar_slug, campo='trivia_preguntas')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_trivia(bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _bid = bar['id']
        _persistir_generado(_bid, 'trivia', game_data, es_global=False)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trivia-stats/<bar_slug>')
def trivia_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT choice, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'trivia' AND played_on = ?",
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    # Sinopsis es única para todos los bares
    _es_ev = (bar['space_kind'] or 'local') == 'evento'
    cache_key = f"{bar_slug}_sinopsis_{today}" if _es_ev else f"global_sinopsis_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    if _es_ev:
        # Evento: contenido propio y temático (con pool por dispositivo)
        pregenerated = _leer_pregenerado(db, bar['id'], 'sinopsis', today)
    else:
        pregenerated = db.execute(
            "SELECT content FROM generated_games WHERE game_type = 'sinopsis' AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
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
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'sinopsis', bar_slug if _es_ev else None, campo='opciones')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_sinopsis(bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _bid = bar['id']
        _persistir_generado(_bid, 'sinopsis', game_data, es_global=(not _es_ev))
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


# ─────────────────────────────────────────────────────────────────────────────
# El Titular Imposible (global)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/<bar_slug>/titular')
def titular_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/titular.html', bar=bar, products=products)


@app.route('/api/titular', methods=['POST'])
def titular_api():
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"global_titular_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE game_type = 'titular' AND game_date = ?",
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
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'titular', None, campo='titular')
        _dbev.close()
        game_data = generate_titular(bar_slug, evitar=_ev)
        _persistir_generado(bar['id'], 'titular', game_data, es_global=True)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/titular-stats/<bar_slug>')
def titular_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT correct, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'titular' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    acertaron = sum(1 for p in plays if p['correct'] == 1)
    elapsed_vals = [p['elapsed'] for p in plays if p['elapsed'] and p['elapsed'] > 0]
    avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0
    pct_acierto = round((acertaron / total) * 100) if total > 0 else 0
    return jsonify({'total': total, 'acertaron': acertaron, 'pct_acierto': pct_acierto, 'avg_elapsed': avg_elapsed})


# ─────────────────────────────────────────────────────────────────────────────
# La Definición Falsa (global)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/<bar_slug>/definicion')
def definicion_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/definicion.html', bar=bar, products=products)


@app.route('/api/definicion', methods=['POST'])
def definicion_api():
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"global_definicion_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = db.execute(
        "SELECT content FROM generated_games WHERE game_type = 'definicion' AND game_date = ?",
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
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'definicion', None, campo='palabra')
        _dbev.close()
        game_data = generate_definicion(bar_slug, evitar=_ev)
        _persistir_generado(bar['id'], 'definicion', game_data, es_global=True)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/definicion-stats/<bar_slug>')
def definicion_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT correct, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'definicion' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    acertaron = sum(1 for p in plays if p['correct'] == 1)
    elapsed_vals = [p['elapsed'] for p in plays if p['elapsed'] and p['elapsed'] > 0]
    avg_elapsed = round(sum(elapsed_vals) / len(elapsed_vals)) if elapsed_vals else 0
    pct_acierto = round((acertaron / total) * 100) if total > 0 else 0
    return jsonify({'total': total, 'acertaron': acertaron, 'pct_acierto': pct_acierto, 'avg_elapsed': avg_elapsed})


# ─────────────────────────────────────────────────────────────────────────────
# Dos Verdades, Una Mentira (a dobles · sin IA, dirigido por jugadores)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/<bar_slug>/dosverdades')
def dosverdades_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/dosverdades.html', bar=bar, products=products)


# ─────────────────────────────────────────────────────────────────────────────
# Más o Menos (a dobles · global con IA)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/<bar_slug>/masomenos')
def masomenos_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/masomenos.html', bar=bar, products=products)


@app.route('/api/masomenos', methods=['POST'])
def masomenos_api():
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    _es_ev = (bar['space_kind'] or 'local') == 'evento'
    cache_key = f"{bar_slug}_masomenos_{today}" if _es_ev else f"global_masomenos_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    if _es_ev:
        pregenerated = _leer_pregenerado(db, bar['id'], 'masomenos', today)
    else:
        pregenerated = db.execute(
            "SELECT content FROM generated_games WHERE game_type = 'masomenos' AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
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
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'masomenos', bar_slug if _es_ev else None, campo='masomenos_preguntas')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_masomenos(bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _persistir_generado(bar['id'], 'masomenos', game_data, es_global=(not _es_ev))
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# La Escalera (1 jugador, global con IA)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/<bar_slug>/escalera')
def escalera_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/escalera.html', bar=bar, products=products)


@app.route('/api/escalera', methods=['POST'])
def escalera_api():
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    _es_ev = (bar['space_kind'] or 'local') == 'evento'
    cache_key = f"{bar_slug}_escalera_{today}" if _es_ev else f"global_escalera_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    if _es_ev:
        pregenerated = _leer_pregenerado(db, bar['id'], 'escalera', today)
    else:
        pregenerated = db.execute(
            "SELECT content FROM generated_games WHERE game_type = 'escalera' AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
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
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'escalera', bar_slug if _es_ev else None, campo='escalera_enunciados')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_escalera(bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _persistir_generado(bar['id'], 'escalera', game_data, es_global=(not _es_ev))
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/escalera-stats/<bar_slug>')
def escalera_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    plays = db.execute(
        "SELECT choice, elapsed FROM plays WHERE bar_slug = ? AND game_type = 'escalera' AND played_on = ?",
        (bar_slug, today)
    ).fetchall()
    db.close()
    total = len(plays)
    # choice guarda el peldano alcanzado (0-6). Media de peldaños.
    peldanos = [p['choice'] for p in plays if p['choice'] is not None and p['choice'] >= 0]
    avg_peldano = round(sum(peldanos) / len(peldanos), 1) if peldanos else 0
    max_peldano = max(peldanos) if peldanos else 0
    return jsonify({'total': total, 'avg_peldano': avg_peldano, 'max_peldano': max_peldano})


# ─────────────────────────────────────────────────────────────────────────────
# Quién es más probable (a dobles, global con IA)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/<bar_slug>/quienmas')
def quienmas_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    if not bar:
        db.close()
        return render_template('404.html'), 404
    products = db.execute("SELECT * FROM bar_products WHERE bar_id = ? AND active = 1 ORDER BY position", (bar['id'],)).fetchall()
    db.close()
    return render_template('games/quienmas.html', bar=bar, products=products)


@app.route('/api/quienmas', methods=['POST'])
def quienmas_api():
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    _es_ev = (bar['space_kind'] or 'local') == 'evento'
    cache_key = f"{bar_slug}_quienmas_{today}" if _es_ev else f"global_quienmas_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    if _es_ev:
        # Evento: contenido propio y temático (con pool por dispositivo)
        pregenerated = _leer_pregenerado(db, bar['id'], 'quienmas', today)
    else:
        pregenerated = db.execute(
            "SELECT content FROM generated_games WHERE game_type = 'quienmas' AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
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
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'quienmas', bar_slug if _es_ev else None, campo='afirmaciones')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_quienmas(bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _persistir_generado(bar['id'], 'quienmas', game_data, es_global=(not _es_ev))
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
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
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'muertes', None, campo='titulo')
        _dbev.close()
        game_data = generate_muertes(bar_slug, evitar=_ev)
        _bid = bar['id']
        _persistir_generado(_bid, 'muertes', game_data, es_global=True)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    _es_ev = (bar['space_kind'] or 'local') == 'evento'
    cache_key = f"{bar_slug}_letra_{today}" if _es_ev else f"global_letra_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    if _es_ev:
        # Evento: contenido propio y temático (con pool por dispositivo)
        pregenerated = _leer_pregenerado(db, bar['id'], 'letra', today)
    else:
        pregenerated = db.execute(
            "SELECT content FROM generated_games WHERE game_type = 'letra' AND game_date = ? AND bar_id NOT IN (SELECT id FROM bars WHERE space_kind = 'evento')",
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
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'letra', bar_slug if _es_ev else None, campo='opciones')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_letra(bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _bid = bar['id']
        _persistir_generado(_bid, 'letra', game_data, es_global=(not _es_ev))
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
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
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'pensamiento', None, campo='categoria')
        _dbev.close()
        game_data = generate_pensamiento(bar_slug, evitar=_ev)
        _bid = bar['id']
        _persistir_generado(_bid, 'pensamiento', game_data, es_global=True)
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
    device_id = (data.get('device_id') or '').strip()[:40]
    today = str(date.today())
    if not respuesta:
        return jsonify({'error': 'Respuesta vacía'}), 400

    try:
        db = get_db()
        norm = _normalizar_respuesta(respuesta)
        db.execute(
            "INSERT INTO plays (code, bar_slug, game_type, played_on, correct, elapsed, answer_text, played_at, device_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (code, bar_slug, 'pensamiento', today, 1, elapsed, norm, now_madrid_iso(), device_id)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    db.close()
    if not valid_code:
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
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
        _bid = bar['id']
        _persistir_generado(_bid, 'menteagil', game_data, es_global=True)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
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
        _bid = bar['id']
        _persistir_generado(_bid, 'constitucion', game_data, es_global=True)
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
        "SELECT name, city, latitude, longitude, slug FROM bars WHERE active = 1 AND latitude IS NOT NULL "
        "AND (space_kind IS NULL OR space_kind != 'evento')"
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"{bar_slug}_conexiones_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = _leer_pregenerado(db, bar['id'], 'conexiones', today)
    if pregenerated:
        import json as _json
        game_data = _json.loads(pregenerated['content'])
        _game_cache[cache_key] = game_data
        db.close()
        return jsonify(game_data)

    db.close()
    try:
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'conexiones', bar_slug, campo='conexiones_grupos')
        _dbev.close()
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_conexiones(bar['name'], bar_slug, evitar=_ev)
        finally:
            reset_event_theme(_tok)
        _bid = bar['id']
        _persistir_generado(_bid, 'conexiones', game_data, es_global=False)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
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
        _bid = bar['id']
        _persistir_generado(_bid, 'oraculo', game_data, es_global=True)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
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
        _dbev = get_db()
        _ev = get_historial_reciente(_dbev, 'donde', None, campo='lugar')
        _dbev.close()
        game_data = generate_donde(bar_slug, evitar=_ev)
        _bid = bar['id']
        _persistir_generado(_bid, 'donde', game_data, es_global=True)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    db.close()
    cache_key = f"{bar_slug}_reinas_{today}"
    if cache_key in _game_cache:
        return jsonify(_game_cache[cache_key])

    game_data = generate_reinas(bar_slug)
    _game_cache[cache_key] = game_data
    return jsonify(game_data)


@app.route('/<bar_slug>/orden')
def orden_page(bar_slug):
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
    return render_template('games/orden.html', bar=bar, code=code, products_json=products_json)

@app.route('/api/orden', methods=['POST'])
def orden_api():
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    _es_ev = (bar['space_kind'] or 'local') == 'evento'
    cache_key = f"{bar_slug}_orden_{today}"
    if not _es_ev and cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    if _es_ev:
        # Evento: contenido propio y temático, persistido en BD (con pool por dispositivo)
        pre = _leer_pregenerado(db, bar['id'], 'orden', today)
        db.close()
        if pre:
            import json as _json
            return jsonify(_json.loads(pre['content']))
        _tok = set_event_theme(_theme_de(bar))
        try:
            game_data = generate_orden(bar_slug)
        finally:
            reset_event_theme(_tok)
        _persistir_generado(bar['id'], 'orden', game_data, es_global=False)
        return jsonify(game_data)

    db.close()
    game_data = generate_orden(bar_slug)
    _game_cache[cache_key] = game_data
    return jsonify(game_data)


@app.route('/<bar_slug>/freep')
def freep_page(bar_slug):
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
    return render_template('games/freep.html', bar=bar, code=code, products_json=products_json)

@app.route('/api/freep', methods=['POST'])
def freep_api():
    """Valida el código y devuelve una baraja Freep barajada (74 numéricas).
    NO se cachea: cada partida es una baraja nueva (es un duelo rejugable)."""
    import random
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403
    db.close()

    # Composición oficial de Freep (solo numéricas en esta versión Lite)
    counts = {1: 6, 2: 8, 3: 8, 4: 10, 5: 10, 6: 10, 7: 8, 8: 8, 9: 6}
    deck = []
    for value, n in counts.items():
        deck.extend([value] * n)
    random.shuffle(deck)
    return jsonify({'deck': deck})


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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
        db.close()
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"{bar_slug}_local_{today}"
    if cache_key in _game_cache:
        db.close()
        return jsonify(_game_cache[cache_key])

    pregenerated = _leer_pregenerado(db, bar['id'], 'local', today)
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
        _persistir_generado(bar['id'], 'local', game_data, es_global=False)
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
        "SELECT code FROM access_codes WHERE bar_id = ? AND code = ? AND valid_from <= ? AND valid_until >= ?",
        (bar['id'], code, today, today)
    ).fetchone()
    if not valid_code:
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
    tipo = data.get('tipo', '').strip()[:20]
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

Tipo: {tipo or 'Sin especificar'}
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
        msg['Subject'] = f"Nueva solicitud Nookplay{(' [' + tipo + ']') if tipo else ''} — {negocio or nombre}"
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
    "oraculo", "donde", "carta", "equilibrio", "impostor", "local", "veredicto", "perfil", "vestuario", "trivia", "sinopsis", "muertes", "letra", "pensamiento", "poema", "menteagil", "constitucion", "orden", "freep", "titular", "definicion", "dosverdades", "masomenos", "escalera", "quienmas",
]

# Starter: 4 fijos siempre activos + 1 elegible a elegir entre STARTER_FREE_GAMES
STARTER_FIXED      = ["crimen", "dilema", "reinas", "conexiones"]
STARTER_FREE_GAMES = ["oraculo", "donde", "carta", "equilibrio", "impostor", "local", "veredicto", "perfil", "vestuario", "sinopsis", "muertes", "letra", "pensamiento", "poema", "menteagil", "constitucion", "orden", "freep", "titular", "definicion", "dosverdades", "masomenos", "escalera", "quienmas"]
STARTER_MAX_FREE   = 2  # juegos libres simultáneos permitidos

# Pro: hasta PRO_MAX_GAMES a elegir libremente del catálogo completo
PRO_MAX_GAMES = 12  # cuando el catálogo crezca más, Pro sigue limitado aquí

# Premium: acceso a todo ALL_GAMES sin límite

# Gift (interno): acceso a todo, sin coste — no visible en la web pública

PLAN_CFG = {
    "starter": {
        "name":  "Plan Starter",
        "price": "6,95€/mes",
        "desc":  "4 juegos fijos + 2 libres a elegir",
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
        if len(free_active) > STARTER_MAX_FREE:
            for extra in free_active[STARTER_MAX_FREE:]:
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

        if plan in ("gift", "total", "premium", "demo"):
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
        if active and game_slug not in STARTER_FIXED:
            # Máximo STARTER_MAX_FREE juegos libres simultáneos
            free_active = db.execute(
                "SELECT game_slug FROM bar_games WHERE bar_id = ? AND active = 1",
                (bar["id"],)
            ).fetchall()
            free_count = len([r for r in free_active if r["game_slug"] not in STARTER_FIXED])
            already = db.execute(
                "SELECT active FROM bar_games WHERE bar_id = ? AND game_slug = ?",
                (bar["id"], game_slug)
            ).fetchone()
            is_already = already and already["active"]
            if not is_already and free_count >= STARTER_MAX_FREE:
                db.close()
                return jsonify({"error": f"El plan Starter permite {STARTER_MAX_FREE} juegos libres. Desactiva uno para cambiarlo."}), 400

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

MEDIA_ROOT = '/data/media'  # volumen persistente: sobrevive a los deploys (misma regla que la BD)

def _slug_seguro(s):
    import re as _re
    return bool(s) and bool(_re.fullmatch(r'[a-z0-9\-_]{1,60}', s))

@app.route('/media/<bar_slug>/<path:filename>')
def serve_media(bar_slug, filename):
    """Sirve logos e imágenes subidos desde el panel (guardados en /data/media)."""
    if not _slug_seguro(bar_slug):
        return ('', 404)
    from flask import send_from_directory
    return send_from_directory(f'{MEDIA_ROOT}/{bar_slug}', filename)


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
    if not _slug_seguro(bar_slug):
        return jsonify({'ok': False, 'error': 'Slug no válido'})
    import os as _os
    folder = f'{MEDIA_ROOT}/{bar_slug}'
    _os.makedirs(folder, exist_ok=True)
    file.save(f'{folder}/logo_header.png')
    return jsonify({'ok': True, 'path': f'/media/{bar_slug}/logo_header.png'})


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
        folder = f'{MEDIA_ROOT}/{bar_slug}'
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
        return jsonify({'ok': True, 'path': f'/media/{bar_slug}/product_{position}.webp'})
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
    space_kind = data.get('space_kind')
    if space_kind not in ('local', 'evento'):
        return jsonify({'ok': False, 'error': 'Elige si es un evento o un local'})
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
            "INSERT INTO bars (slug, name, city, province, address, zip_code, latitude, longitude, plan, plan_status, color_primary, color_primary_text, color_bg, color_bg_subtle, color_accent_dark, active, space_kind, event_pool_size, event_fan_level) VALUES (?,?,?,?,?,?,?,?,?,'active',?,'#FFFFFF',?,'#F0EBE3','#1A1A1A',1,?,?,?)",
            (slug, name, city, province, address, zip_code, latitude, longitude, plan, color, color_bg,
             space_kind, 3 if space_kind == 'evento' else 1, 'fan')
        )
        bar = db.execute("SELECT id FROM bars WHERE slug = ?", (slug,)).fetchone()
        bar_id = bar['id']
        from datetime import timedelta
        today_d = date.today()
        monday = today_d - timedelta(days=today_d.weekday())
        sunday = monday + timedelta(days=6)
        db.execute("UPDATE bars SET access_code = ? WHERE id = ?", (new_code, bar_id))
        if space_kind == 'evento':
            # Eventos: código admin permanente (ventana centinela), no semanal
            db.execute("INSERT INTO access_codes (bar_id, code, valid_from, valid_until) VALUES (?,?,?,?)",
                      (bar_id, new_code, '2000-01-01', '2099-12-31'))
        else:
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
        elif plan == 'demo':
            active_slugs = []  # Demo nace vacío; el admin elige qué juegos enseñar
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
