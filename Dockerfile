FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -c "
import sqlite3
db = sqlite3.connect('nookplay.db')
db.executescript('''
    CREATE TABLE IF NOT EXISTS bars (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL, active INTEGER DEFAULT 1, created_at TEXT DEFAULT (date(\"now\")));
    CREATE TABLE IF NOT EXISTS codes (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, bar_id INTEGER NOT NULL, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS plays (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, bar_slug TEXT NOT NULL, played_on TEXT NOT NULL, correct INTEGER DEFAULT 0);
''')
bar = db.execute(\"SELECT id FROM bars WHERE slug = 'yellow'\").fetchone()
if not bar:
    db.execute(\"INSERT INTO bars (slug, name) VALUES ('yellow', 'Yellow Specialty Koffee')\")
    db.commit()
    bar_id = db.execute(\"SELECT id FROM bars WHERE slug = 'yellow'\").fetchone()[0]
    for i in range(1, 11):
        db.execute(\"INSERT INTO codes (code, bar_id) VALUES (?, ?)\", (f'YELLOW{i:02d}', bar_id))
db.commit()
db.close()
print('DB ready')
"

EXPOSE 80

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:80", "--workers", "2", "--timeout", "120"]
