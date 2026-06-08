from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import date, datetime, timedelta
import sqlite3
from ai import generate_game, generate_impostor, generate_dilema, build_bar_context, get_day_seed
import os
import json
import random
import string

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nookplay-secret-2026')

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

def get_db():
    import os as _os
    _db_path = '/data/nookplay.db' if _os.path.exists('/data') else 'nookplay.db'
    db = sqlite3.connect(_db_path)
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
        "ALTER TABLE bars ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))",
        # Nuevas columnas en plays
        "ALTER TABLE plays ADD COLUMN game_type TEXT DEFAULT 'crimen'",
        "ALTER TABLE plays ADD COLUMN choice INTEGER DEFAULT -1",
        "ALTER TABLE plays ADD COLUMN elapsed INTEGER DEFAULT 0",
    ]
    for sql in migrations:
        try:
            db.execute(sql)
        except:
            pass  # Columna ya existe, ignorar

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
    db.execute("""
        UPDATE bars SET
            name                = 'Yellow Specialty Koffee',
            type                = 'Cafetería de especialidad',
            city                = 'Viladecans',
            province            = 'Barcelona',
            country             = 'España',
            description         = 'Cafetería moderna de café de especialidad. Local acogedor con clientela variada: familias, profesionales y amigos del barrio. Especializados en café de origen etíope, frappés artesanos y repostería propia.',
            owner_name          = 'Lorena',
            staff_names         = 'Carla',
            bar_vibe            = 'acogedor, moderno, especialidad, barrio',
            welcome_message     = 'Bienvenido al Yellow. Elige tu pasatiempo de hoy.',
            color_primary       = '#FEE25A',
            color_primary_text  = '#000000',
            color_bg            = '#FFFBEA',
            color_bg_subtle     = '#FFF8D6',
            color_accent_dark   = '#1A1A1A'
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

def pregen_daily_games():
    """Ejecuta cada día a las 6am — pre-genera los juegos del día para todos los bares."""
    today = str(date.today())

    db = get_db()
    bars = db.execute("SELECT * FROM bars WHERE active = 1").fetchall()
    for bar in bars:
        for game_type in ['crimen', 'impostor']:
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
                    else:
                        game_data = generate_impostor(bar['name'], bar['slug'])
                    
                    import json as _json
                    db.execute(
                        "INSERT INTO generated_games (bar_id, game_type, game_date, content) VALUES (?,?,?,?)",
                        (bar['id'], game_type, today, _json.dumps(game_data))
                    )
                    db.commit()
                    print(f"[CRON] Pre-generado {game_type} para {bar['slug']}")
                except Exception as e:
                    print(f"[CRON] Error generando {game_type} para {bar['slug']}: {e}")
    db.close()

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
    db.execute(
        "UPDATE bars SET welcome_message=?, promo_active=?, description=?, owner_name=?, staff_names=?, color_primary=?, color_primary_text=?, color_bg=?, color_bg_subtle=? WHERE slug=?",
        (data.get('welcome_message',''), data.get('promo_active',0),
         data.get('description',''), data.get('owner_name',''),
         data.get('staff_names',''), data.get('color_primary','#C4622D'),
         data.get('color_primary_text','#FFFFFF'), data.get('color_bg','#F7F2EB'),
         data.get('color_bg_subtle','#F0EBE3'), bar_slug)
    )
    db.execute("DELETE FROM bar_products WHERE bar_id = ?", (bar['id'],))
    for p in data.get('products', []):
        if p.get('title'):
            db.execute(
                "INSERT INTO bar_products (bar_id, position, title, description, price) VALUES (?,?,?,?,?)",
                (bar['id'], p['position'], p['title'], p.get('description',''), p.get('price',''))
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
        db.commit()
        db.close()
        import os as _os
        _os.makedirs(f'static/clientes/{slug}', exist_ok=True)
        return jsonify({'ok': True, 'code': new_code})
    except Exception as e:
        db.rollback()
        db.close()
        return jsonify({'ok': False, 'error': str(e)})
