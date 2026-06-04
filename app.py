from flask import Flask, render_template, request, jsonify
from datetime import date
import sqlite3
import os
import json
from ai import generate_game

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

    # Check if already played today
    played = db.execute(
        "SELECT id FROM plays WHERE code = ? AND played_on = ?",
        (code, today)
    ).fetchone()

    if played:
        db.close()
        return jsonify({'valid': False, 'message': 'Este código ya se ha usado hoy. Vuelve mañana con tu café. ☕'})

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

    if not played:
        db.execute(
            "INSERT INTO plays (code, bar_slug, played_on, correct) VALUES (?, ?, ?, ?)",
            (code, bar_slug, today, 1 if correct else 0)
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

# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)

