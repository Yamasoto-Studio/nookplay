"""
init_db.py — Nookplay
Inicialización y migración de la base de datos.
IDEMPOTENTE: seguro de ejecutar múltiples veces sin perder datos.
"""
import sqlite3
import random
import os
from datetime import date, timedelta

def generate_weekly_code():
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(random.choices(chars, k=5))

db_path = '/data/nookplay.db' if os.path.exists('/data') else 'nookplay.db'
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row

# ── Crear tablas si no existen ──────────────────────────────────────────────

db.executescript('''
    CREATE TABLE IF NOT EXISTS bars (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        slug                TEXT UNIQUE NOT NULL,
        name                TEXT NOT NULL,
        type                TEXT DEFAULT \'\',
        logo_path           TEXT DEFAULT \'\',
        address             TEXT DEFAULT \'\',
        city                TEXT DEFAULT \'\',
        province            TEXT DEFAULT \'\',
        zip_code            TEXT DEFAULT \'\',
        country             TEXT DEFAULT \'España\',
        latitude            REAL,
        longitude           REAL,
        google_place_id     TEXT DEFAULT \'\',
        description         TEXT DEFAULT \'\',
        owner_name          TEXT DEFAULT \'\',
        staff_names         TEXT DEFAULT \'\',
        bar_vibe            TEXT DEFAULT \'\',
        welcome_message     TEXT DEFAULT \'\',
        promo_active        INTEGER DEFAULT 0,
        access_code         TEXT DEFAULT \'\',
        access_code_updated_at TEXT DEFAULT \'\',
        whatsapp_phone      TEXT DEFAULT \'\',
        color_primary       TEXT DEFAULT \'#C4622D\',
        color_primary_text  TEXT DEFAULT \'#FFFFFF\',
        color_bg            TEXT DEFAULT \'#F7F2EB\',
        color_bg_subtle     TEXT DEFAULT \'#F0EBE3\',
        color_accent_dark   TEXT DEFAULT \'#1A1A1A\',
        active              INTEGER DEFAULT 1,
        created_at          TEXT DEFAULT (datetime(\'now\')),
        updated_at          TEXT DEFAULT (datetime(\'now\'))
    );

    CREATE TABLE IF NOT EXISTS bar_products (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        bar_id      INTEGER NOT NULL,
        position    INTEGER DEFAULT 1,
        title       TEXT NOT NULL,
        description TEXT DEFAULT \'\',
        price       TEXT DEFAULT \'\',
        image_path  TEXT DEFAULT \'\',
        active      INTEGER DEFAULT 1,
        created_at  TEXT DEFAULT (datetime(\'now\'))
    );

    CREATE TABLE IF NOT EXISTS access_codes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        bar_id      INTEGER NOT NULL,
        code        TEXT NOT NULL,
        valid_from  TEXT NOT NULL,
        valid_until TEXT NOT NULL,
        sent_at     TEXT DEFAULT \'\',
        created_at  TEXT DEFAULT (datetime(\'now\'))
    );

    CREATE TABLE IF NOT EXISTS access_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        bar_id      INTEGER NOT NULL,
        code_used   TEXT NOT NULL,
        accessed_at TEXT DEFAULT (datetime(\'now\'))
    );

    CREATE TABLE IF NOT EXISTS generated_games (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        bar_id          INTEGER NOT NULL,
        game_type       TEXT NOT NULL,
        game_date       TEXT NOT NULL,
        content         TEXT NOT NULL,
        generated_at    TEXT DEFAULT (datetime(\'now\'))
    );

    CREATE TABLE IF NOT EXISTS plays (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        code        TEXT NOT NULL,
        bar_slug    TEXT NOT NULL,
        played_on   TEXT NOT NULL,
        correct     INTEGER DEFAULT 0,
        game_type   TEXT DEFAULT \'crimen\',
        choice      INTEGER DEFAULT -1,
        elapsed     INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS admin_users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        email           TEXT UNIQUE NOT NULL,
        password_hash   TEXT NOT NULL,
        role            TEXT DEFAULT \'bar_admin\',
        bar_id          INTEGER,
        bar_slug        TEXT DEFAULT \'\',
        created_at      TEXT DEFAULT (datetime(\'now\'))
    );
''')

# ── Migraciones (añadir columnas nuevas sin borrar datos) ───────────────────

migrations = [
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
    "ALTER TABLE plays ADD COLUMN game_type TEXT DEFAULT 'crimen'",
    "ALTER TABLE plays ADD COLUMN choice INTEGER DEFAULT -1",
    "ALTER TABLE plays ADD COLUMN elapsed INTEGER DEFAULT 0",
    "ALTER TABLE admin_users ADD COLUMN bar_slug TEXT DEFAULT ''",
]
for sql in migrations:
    try:
        db.execute(sql)
    except:
        pass

db.commit()

# ── Yellow: insertar o actualizar SOLO datos del bar, nunca usuarios ────────

bar = db.execute("SELECT id FROM bars WHERE slug = 'yellow'").fetchone()
if not bar:
    db.execute("""
        INSERT INTO bars (slug, name, type, city, province, description, owner_name, staff_names,
            bar_vibe, welcome_message, promo_active,
            color_primary, color_primary_text, color_bg, color_bg_subtle, color_accent_dark)
        VALUES ('yellow', 'Yellow Specialty Koffee', 'Cafetería de especialidad',
            'Viladecans', 'Barcelona',
            'Cafetería moderna de café de especialidad. Local acogedor con clientela variada.',
            'Lorena', 'Carla', 'acogedor, moderno, especialidad, barrio',
            'Bienvenido al Yellow.', 1,
            '#FEE25A', '#000000', '#FFFBEA', '#FFF8D6', '#1A1A1A')
    """)
    db.commit()
    print('Bar Yellow creado.')
else:
    print('Bar Yellow ya existe — no se modifica.')

# ── Productos de Yellow (solo si no existen) ────────────────────────────────

bar = db.execute("SELECT id FROM bars WHERE slug = 'yellow'").fetchone()
bar_id = bar['id']

existing_products = db.execute("SELECT id FROM bar_products WHERE bar_id = ?", (bar_id,)).fetchone()
if not existing_products:
    products = [
        (bar_id, 1, 'Café de finca etíope', 'Single origin tostado en casa.', '2,50 €'),
        (bar_id, 2, 'Frappé artesano', 'Preparado al momento con café de especialidad.', '4,00 €'),
        (bar_id, 3, 'Leche con tostada', 'Pan artesano con mantequilla y mermelada.', '3,00 €'),
    ]
    for p in products:
        db.execute("INSERT INTO bar_products (bar_id, position, title, description, price) VALUES (?,?,?,?,?)", p)
    db.commit()
    print('Productos de Yellow insertados.')

# ── Código semanal (solo si no existe para esta semana) ─────────────────────

today = date.today()
monday = today - timedelta(days=today.weekday())
sunday = monday + timedelta(days=6)

existing_code = db.execute("""
    SELECT code FROM access_codes
    WHERE bar_id = ? AND valid_from <= ? AND valid_until >= ?
""", (bar_id, str(today), str(today))).fetchone()

if not existing_code:
    new_code = generate_weekly_code()
    db.execute("UPDATE bars SET access_code = ?, access_code_updated_at = ? WHERE id = ?",
              (new_code, str(monday), bar_id))
    db.execute("INSERT INTO access_codes (bar_id, code, valid_from, valid_until) VALUES (?,?,?,?)",
              (bar_id, new_code, str(monday), str(sunday)))
    db.commit()
    print(f'Código semanal: {new_code} ({monday} → {sunday})')
else:
    print(f'Código semanal ya existe: {existing_code["code"]}')

db.close()
print('✅ DB lista.')
