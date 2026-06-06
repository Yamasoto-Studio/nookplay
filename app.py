from flask import Flask, render_template, request, jsonify
from datetime import date
import sqlite3
import os
import json
from ai import generate_game, generate_impostor

app = Flask(__name__)

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

def get_db():
    db = sqlite3.connect('nookplay.db')
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS bars (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slug        TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (date('now'))
        );

        CREATE TABLE IF NOT EXISTS codes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT UNIQUE NOT NULL,
            bar_id      INTEGER NOT NULL,
            active      INTEGER DEFAULT 1,
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        );

        CREATE TABLE IF NOT EXISTS plays (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT NOT NULL,
            bar_slug    TEXT NOT NULL,
            played_on   TEXT NOT NULL,
            correct     INTEGER DEFAULT 0
        );
    ''')
    db.commit()

    # Insert demo bar and codes if not exists
    existing = db.execute("SELECT id FROM bars WHERE slug = 'yellow'").fetchone()
    if not existing:
        db.execute("INSERT INTO bars (slug, name) VALUES ('yellow', 'Yellow Specialty Koffee')")
        db.commit()
        bar_id = db.execute("SELECT id FROM bars WHERE slug = 'yellow'").fetchone()['id']
        demo_codes = ['YELLOW01', 'YELLOW02', 'YELLOW03', 'YELLOW04', 'YELLOW05',
                      'YELLOW06', 'YELLOW07', 'YELLOW08', 'YELLOW09', 'YELLOW10']
        for c in demo_codes:
            db.execute("INSERT INTO codes (code, bar_id) VALUES (?, ?)", (c, bar_id))
        db.commit()

    db.close()

# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/<bar_slug>')
def bar(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    db.close()
    if not bar:
        return render_template('404.html'), 404
    return render_template('bar.html', bar=bar)

@app.route('/api/validate', methods=['POST'])
def validate_code():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()

    # Check code exists and belongs to this bar
    result = db.execute('''
        SELECT c.code, b.slug, b.name, c.active
        FROM codes c
        JOIN bars b ON c.bar_id = b.id
        WHERE c.code = ? AND b.slug = ? AND c.active = 1 AND b.active = 1
    ''', (code, bar_slug)).fetchone()

    if not result:
        db.close()
        return jsonify({'valid': False, 'message': 'Código no válido.'})

    db.close()
    return jsonify({'valid': True, 'bar_name': result['name']})

@app.route('/api/play', methods=['POST'])
def register_play():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    correct = data.get('correct', False)
    today = str(date.today())

    db = get_db()

    # Double-check not already played
    played = db.execute(
        "SELECT id FROM plays WHERE code = ? AND played_on = ?",
        (code, today)
    ).fetchone()

    game_type = data.get('game_type', 'crimen')
    choice = data.get('choice', -1)
    elapsed = data.get('elapsed', 0)
    if not played:
        db.execute(
            "INSERT INTO plays (code, bar_slug, played_on, correct, game_type, choice, elapsed) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, bar_slug, today, 1 if correct else 0, game_type, choice, elapsed)
        )
        db.commit()

    db.close()
    return jsonify({'ok': True})

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
    return jsonify({
        'today': total_today,
        'correct_today': correct_today,
        'total': total_all
    })

# Simple daily cache: one game per bar per day (avoids calling AI every request)
_game_cache = {}

@app.route('/api/game', methods=['POST'])
def game():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    # Verify code is valid and not yet played
    db = get_db()
    result = db.execute('''
        SELECT b.name FROM codes c
        JOIN bars b ON c.bar_id = b.id
        WHERE c.code = ? AND b.slug = ? AND c.active = 1 AND b.active = 1
    ''', (code, bar_slug)).fetchone()
    db.close()

    if not result:
        return jsonify({'error': 'Invalid code'}), 403

    # Return cached game for today if exists
    cache_key = f"{bar_slug}_{today}"
    if cache_key in _game_cache:
        return jsonify(_game_cache[cache_key])

    # Generate new game
    try:
        game_data = generate_game(result['name'], bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/<bar_slug>/impostor')
def impostor_page(bar_slug):
    db = get_db()
    bar = db.execute("SELECT * FROM bars WHERE slug = ? AND active = 1", (bar_slug,)).fetchone()
    db.close()
    if not bar:
        return render_template('404.html'), 404
    return render_template('impostor.html', bar=bar)

@app.route('/api/impostor-stats/<bar_slug>')
def impostor_stats(bar_slug):
    today = str(date.today())
    db = get_db()
    total = db.execute(
        "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on = ? AND game_type = 'impostor'",
        (bar_slug, today)
    ).fetchone()['n']
    correct = db.execute(
        "SELECT COUNT(*) as n FROM plays WHERE bar_slug = ? AND played_on = ? AND game_type = 'impostor' AND correct = 1",
        (bar_slug, today)
    ).fetchone()['n']
    avg_row = db.execute(
        "SELECT AVG(elapsed) as avg_e FROM plays WHERE bar_slug = ? AND played_on = ? AND game_type = 'impostor' AND elapsed > 0",
        (bar_slug, today)
    ).fetchone()
    avg_elapsed = round(avg_row['avg_e']) if avg_row['avg_e'] else None
    db.close()
    return jsonify({'total': total, 'correct': correct, 'avg_elapsed': avg_elapsed})

@app.route('/api/impostor', methods=['POST'])
def impostor():
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    bar_slug = data.get('bar_slug', '').strip()
    today = str(date.today())

    db = get_db()
    result = db.execute('''
        SELECT b.name FROM codes c
        JOIN bars b ON c.bar_id = b.id
        WHERE c.code = ? AND b.slug = ? AND c.active = 1 AND b.active = 1
    ''', (code, bar_slug)).fetchone()
    db.close()

    if not result:
        return jsonify({'error': 'Invalid code'}), 403

    cache_key = f"{bar_slug}_impostor_{today}"
    if cache_key in _game_cache:
        return jsonify(_game_cache[cache_key])

    try:
        game_data = generate_impostor(result['name'], bar_slug)
        _game_cache[cache_key] = game_data
        return jsonify(game_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/static/og.png')
def og_image():
    from flask import send_file
    return send_file('static/og.svg', mimetype='image/svg+xml')

# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

if __name__ == '__main__':
    init_db()
    migrate_db()
    app.run(debug=True, host='0.0.0.0', port=5000)


# Migration: add brand columns to bars table if not exist
def migrate_db():
    db = get_db()
    try:
        db.execute("ALTER TABLE bars ADD COLUMN color_primary TEXT DEFAULT '#C4622D'")
    except: pass
    try:
        db.execute("ALTER TABLE bars ADD COLUMN color_primary_text TEXT DEFAULT '#FFFFFF'")
    except: pass
    try:
        db.execute("ALTER TABLE bars ADD COLUMN color_bg TEXT DEFAULT '#F7F2EB'")
    except: pass
    try:
        db.execute("ALTER TABLE bars ADD COLUMN color_bg_subtle TEXT DEFAULT '#F0EBE3'")
    except: pass
    try:
        db.execute("ALTER TABLE bars ADD COLUMN color_accent_dark TEXT DEFAULT '#1A1A1A'")
    except: pass
    try:
        db.execute("ALTER TABLE bars ADD COLUMN welcome_message TEXT DEFAULT ''")
    except: pass
    try:
        db.execute("ALTER TABLE plays ADD COLUMN game_type TEXT DEFAULT 'crimen'")
    except: pass
    try:
        db.execute("ALTER TABLE plays ADD COLUMN choice INTEGER DEFAULT -1")
    except: pass
    try:
        db.execute("ALTER TABLE plays ADD COLUMN elapsed INTEGER DEFAULT 0")
    except: pass
    # Update Yellow colors
    db.execute("""UPDATE bars SET
        color_primary='#FEE25A',
        color_primary_text='#000000',
        color_bg='#FFFBEA',
        color_bg_subtle='#FFF8D6',
        color_accent_dark='#1A1A1A',
        welcome_message='Bienvenido al Yellow. Elige tu pasatiempo de hoy.'
        WHERE slug='yellow'""")
    db.commit()
    db.close()
