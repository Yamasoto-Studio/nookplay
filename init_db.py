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

os.makedirs('/data', exist_ok=True)
db_path = '/data/nookplay.db'
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
    "ALTER TABLE bars ADD COLUMN tomorrow_message TEXT DEFAULT ''",
    "ALTER TABLE bars ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))",
    "ALTER TABLE plays ADD COLUMN game_type TEXT DEFAULT 'crimen'",
    "ALTER TABLE plays ADD COLUMN choice INTEGER DEFAULT -1",
    "ALTER TABLE plays ADD COLUMN elapsed INTEGER DEFAULT 0",
    "ALTER TABLE admin_users ADD COLUMN bar_slug TEXT DEFAULT ''",
    "ALTER TABLE bars ADD COLUMN plan TEXT DEFAULT 'gift'",
    "ALTER TABLE bars ADD COLUMN plan_status TEXT DEFAULT 'active'",
    "ALTER TABLE bars ADD COLUMN plan_expires_at TEXT DEFAULT ''",
    "ALTER TABLE bars ADD COLUMN stripe_customer_id TEXT DEFAULT ''",
    "ALTER TABLE bars ADD COLUMN stripe_subscription_id TEXT DEFAULT ''",
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
    # Actualizar coordenadas si no las tiene (BD anterior al campo)
    db.execute("UPDATE bars SET latitude = 41.3175, longitude = 2.0067 WHERE slug = 'yellow' AND (latitude IS NULL OR latitude = 0)")
    db.commit()
    print('Bar Yellow ya existe — coordenadas verificadas.')

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


# ── Tabla games (catálogo maestro) ─────────────────────────────────────────

db.execute("""
    CREATE TABLE IF NOT EXISTS games (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        slug        TEXT UNIQUE NOT NULL,
        name        TEXT NOT NULL,
        description TEXT NOT NULL,
        icon        TEXT NOT NULL,
        plan_min    TEXT NOT NULL DEFAULT 'starter',
        active      INTEGER NOT NULL DEFAULT 1,
        position    INTEGER NOT NULL DEFAULT 0
    )
""")

# ── Tabla bar_games (juegos activos por bar) ────────────────────────────────

db.execute("""
    CREATE TABLE IF NOT EXISTS bar_games (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        bar_id      INTEGER NOT NULL,
        game_slug   TEXT NOT NULL,
        active      INTEGER NOT NULL DEFAULT 1,
        UNIQUE(bar_id, game_slug),
        FOREIGN KEY (bar_id) REFERENCES bars(id)
    )
""")

db.commit()

# ── Seed catálogo de juegos ─────────────────────────────────────────────────

GAMES_CATALOG = [
    ('crimen',      'El Crimen del Día',      'Resuelve el misterio',      '/static/games/crimen.webp',      'starter', 1),
    ('dilema',      'El Dilema',              '¿Tú qué harías?',           '/static/games/dilema.webp',      'starter', 2),
    ('reinas',      'Las Reinas',             'Puzzle de coronas',         '/static/games/reinas.webp',      'starter', 3),
    ('conexiones',  'Las Conexiones',         '8 palabras, 2 grupos',      '/static/games/conexiones.webp',  'starter', 4),
    ('oraculo',     'El Oráculo',             'Horóscopo sin filtros',     '/static/games/oraculo.webp',     'starter_free', 5),
    ('donde',       '¿Dónde en el mundo?',    'Adivina el lugar',          '/static/games/donde.webp',       'starter_free', 6),
    ('carta',       'La Carta',               'Sudoku con emojis',         '/static/games/carta.webp',       'starter_free', 7),
    ('equilibrio',  'Equilibrio',             'Soles y lunas',             '/static/games/equilibrio.webp',  'starter_free', 8),
    ('impostor',    'El Impostor',            '¿Cuál dato es mentira?',    '/static/games/impostor.webp',    'starter_free', 9),
    ('local',       'Conexión Local',         'Trivia de tu ciudad',       '/static/games/local.webp',       'starter_free', 10),
]

for game in GAMES_CATALOG:
    existing = db.execute("SELECT id FROM games WHERE slug = ?", (game[0],)).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO games (slug, name, description, icon, plan_min, position) VALUES (?,?,?,?,?,?)",
            game
        )

db.commit()
# Añadir veredicto si no existe
veredicto_exists = db.execute("SELECT id FROM games WHERE slug = 'veredicto'").fetchone()
if not veredicto_exists:
    db.execute(
        "INSERT INTO games (slug, name, description, icon, plan_min, position) VALUES (?,?,?,?,?,?)",
        ('veredicto', 'El Veredicto', 'Culpable o inocente', '/static/games/veredicto.webp', 'starter_free', 11)
    )
    db.commit()
    print('Juego El Veredicto añadido.')

# Añadir perfil si no existe
perfil_exists = db.execute("SELECT id FROM games WHERE slug = 'perfil'").fetchone()
if not perfil_exists:
    db.execute(
        "INSERT INTO games (slug, name, description, icon, plan_min, position) VALUES (?,?,?,?,?,?)",
        ('perfil', 'El Perfil', '¿Sabes leer entre líneas?', '/static/games/perfil.webp', 'starter_free', 12)
    )
    db.commit()
    print('Juego El Perfil añadido.')

# Añadir vestuario si no existe
if not db.execute("SELECT id FROM games WHERE slug = 'vestuario'").fetchone():
    db.execute(
        "INSERT INTO games (slug, name, description, icon, plan_min, position) VALUES (?,?,?,?,?,?)",
        ('vestuario', 'El Vestuario', 'Quiz de fútbol', '/static/games/vestuario.webp', 'starter_free', 13)
    )
    db.commit()
    print('Juego El Vestuario añadido.')

# Añadir sinopsis si no existe
if not db.execute("SELECT id FROM games WHERE slug = 'sinopsis'").fetchone():
    db.execute(
        "INSERT INTO games (slug, name, description, icon, plan_min, position) VALUES (?,?,?,?,?,?)",
        ('sinopsis', 'La Sinopsis Rara', 'Adivina la película', '/static/games/sinopsis.webp', 'starter_free', 14)
    )
    db.commit()
    print('Juego La Sinopsis Rara añadido.')

# Añadir muertes y letra si no existen
for slug, name, desc, pos in [
    ('muertes', 'Muertes Absurdas', 'Historias reales increíbles', 15),
    ('letra', 'La Letra Traducida', 'Adivina la canción', 16),
]:
    if not db.execute("SELECT id FROM games WHERE slug = ?", (slug,)).fetchone():
        db.execute(
            "INSERT INTO games (slug, name, description, icon, plan_min, position) VALUES (?,?,?,?,?,?)",
            (slug, name, desc, f'/static/games/{slug}.webp', 'starter_free', pos)
        )
        db.commit()
        print(f'Juego {name} añadido.')

# Reordenar juegos por tipo de experiencia (orden lógico de UX)
ORDEN_JUEGOS = {
    # Lógica / puzzle (4 fijos starter primero)
    'crimen': 1, 'reinas': 2, 'equilibrio': 3, 'carta': 4,
    # Adivinanza / cultura
    'conexiones': 5, 'donde': 6, 'sinopsis': 7, 'letra': 8, 'vestuario': 9,
    # Opinión / social
    'dilema': 10, 'veredicto': 11, 'perfil': 12,
    # Curiosidad / lectura
    'impostor': 13, 'muertes': 14, 'oraculo': 15, 'local': 16,
}
for slug, pos in ORDEN_JUEGOS.items():
    db.execute("UPDATE games SET position = ? WHERE slug = ?", (pos, slug))
db.commit()
print('Orden de juegos actualizado.')

print('Catálogo de juegos listo.')

# ── Asignar juegos por defecto a Yellow (plan gift = todos activos) ─────────

bar_yellow = db.execute("SELECT id FROM bars WHERE slug = 'yellow'").fetchone()
if bar_yellow:
    all_games = db.execute("SELECT slug FROM games").fetchall()
    for g in all_games:
        existing = db.execute(
            "SELECT id FROM bar_games WHERE bar_id = ? AND game_slug = ?",
            (bar_yellow['id'], g['slug'])
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO bar_games (bar_id, game_slug, active) VALUES (?,?,1)",
                (bar_yellow['id'], g['slug'])
            )
    db.commit()
    print('Juegos de Yellow asignados.')


db.close()
print('✅ DB lista.')
