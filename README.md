# Nookplay

**Daily bar entertainment platform. A new game every day.**

Nookplay provides bars and cafés with a daily game experience for their customers. Customers scan a QR code on their table card, enter their unique code, and get access to a new game every day — crime mysteries, horoscopes, trivia, and more.

## Stack

- **Backend:** Python + Flask
- **Database:** SQLite (dev) → PostgreSQL (production)
- **AI:** Anthropic Claude API (daily game generation)
- **Frontend:** HTML + CSS + Vanilla JS

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variable
export ANTHROPIC_API_KEY=your_key_here

# Initialize database
bash init.sh

# Run development server
python app.py
```

## Structure

```
nookplay/
├── app.py              # Main Flask app + routes
├── ai.py               # AI game generation
├── requirements.txt
├── Procfile            # For EasyPanel/gunicorn
├── templates/
│   ├── base.html
│   ├── home.html
│   └── bar.html        # Game interface
└── static/
    └── css/
        └── main.css
```

## How it works

1. Each bar has a unique `slug` (e.g. `yellow`)
2. Each physical card has a unique code (e.g. `YELLOW01`)
3. Customer visits `nookplay.app/yellow`, enters their code
4. System validates: code exists + not used today
5. AI generates the daily game (cached per bar per day)
6. Customer plays, result is recorded

## Adding a new bar

```python
# In Python shell or admin script
from app import get_db, init_db
db = get_db()
db.execute("INSERT INTO bars (slug, name) VALUES ('mybar', 'My Bar Name')")
db.commit()
```

---

Made by [Yamasoto](https://yamasoto.com)
