import sqlite3

db = sqlite3.connect('nookplay.db')
db.executescript('''
    CREATE TABLE IF NOT EXISTS bars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (date('now')),
        color_primary TEXT DEFAULT '#C4622D',
        color_primary_text TEXT DEFAULT '#FFFFFF',
        color_bg TEXT DEFAULT '#F7F2EB',
        color_bg_subtle TEXT DEFAULT '#F0EBE3',
        color_accent_dark TEXT DEFAULT '#1A1A1A',
        welcome_message TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        bar_id INTEGER NOT NULL,
        active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS plays (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        bar_slug TEXT NOT NULL,
        played_on TEXT NOT NULL,
        correct INTEGER DEFAULT 0
    );
''')

bar = db.execute("SELECT id FROM bars WHERE slug = 'yellow'").fetchone()
if not bar:
    db.execute("""INSERT INTO bars (slug, name, color_primary, color_primary_text, color_bg, color_bg_subtle, color_accent_dark, welcome_message)
        VALUES ('yellow', 'Yellow Specialty Koffee', '#FEE25A', '#000000', '#FFFBEA', '#FFF8D6', '#1A1A1A', 'Bienvenido al Yellow. Elige tu pasatiempo de hoy.')""")
    db.commit()
    bar_id = db.execute("SELECT id FROM bars WHERE slug = 'yellow'").fetchone()[0]
    for i in range(1, 11):
        db.execute("INSERT INTO codes (code, bar_id) VALUES (?, ?)", (f'YELLOW{i:02d}', bar_id))
else:
    db.execute("""UPDATE bars SET
        color_primary='#FEE25A', color_primary_text='#000000',
        color_bg='#FFFBEA', color_bg_subtle='#FFF8D6', color_accent_dark='#1A1A1A',
        welcome_message='Bienvenido al Yellow. Elige tu pasatiempo de hoy.'
        WHERE slug='yellow'""")

db.commit()
db.close()
print('DB ready')
