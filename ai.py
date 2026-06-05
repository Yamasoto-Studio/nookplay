import requests
import json
from datetime import date
import os
import hashlib

# ─────────────────────────────────────────────────────────────────────────────
# Bar context — detailed info for personalized case generation
# ─────────────────────────────────────────────────────────────────────────────

BAR_CONTEXT = {
    'yellow': {
        'nombre': 'Yellow Specialty Koffee',
        'propietaria': 'Lorena',
        'ubicacion': 'Viladecans, Barcelona',
        'tipo': 'Cafetería de especialidad',
        'descripcion': 'Cafetería moderna de café de especialidad. Local acogedor, clientela variada: familias, profesionales, amigos del barrio.',
        'productos': ['Café de finca etíope', 'Frappé artesano', 'Chocolate suizo', 'Tartas artesanas', 'Cookies', 'Brunch'],
        'equipo': ['Lorena (propietaria)'],
        'clientela': 'Familias, madres, padres, amigos, profesionales del barrio',
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Ambiente rotation — ensures variety across days
# ─────────────────────────────────────────────────────────────────────────────

AMBIENTES = [
    "hotel de lujo de los años 30",
    "crucero trasatlántico",
    "mansión victoriana en el campo inglés",
    "biblioteca universitaria antigua",
    "teatro de ópera",
    "tren nocturno entre ciudades europeas",
    "galería de arte contemporáneo",
    "club privado de caballeros londinense",
    "hacienda andaluza",
    "restaurante con estrella Michelin",
    "museo de historia natural",
    "villa italiana frente al lago",
    "casino de Montecarlo",
    "hospital psiquiátrico de época",
    "finca cafetera en Colombia",
    "castillo escocés",
    "mercado de antigüedades parisino",
    "club de jazz de Nueva Orleans",
    "laboratorio farmacéutico",
    "palacio de congresos durante un simposio",
    "cafetería de especialidad en Barcelona",  # Local appearance ~1 in 20
]

CATEGORIAS_IMPOSTOR = [
    "ciencia y naturaleza",
    "historia universal",
    "gastronomía y cultura culinaria",
    "geografía y países",
    "arte y literatura",
    "deportes y récords",
    "tecnología e inventos",
    "mitología y leyendas",
    "economía y negocios",
    "cine y música",
]

def get_day_seed(bar_slug):
    """Generate a deterministic seed for today's content."""
    today = str(date.today())
    return int(hashlib.md5(f"{today}{bar_slug}".encode()).hexdigest(), 16)

def get_ambient(bar_slug):
    seed = get_day_seed(bar_slug)
    return AMBIENTES[seed % len(AMBIENTES)]

def get_categoria_impostor(bar_slug):
    seed = get_day_seed(bar_slug)
    return CATEGORIAS_IMPOSTOR[(seed + 3) % len(CATEGORIAS_IMPOSTOR)]

# ─────────────────────────────────────────────────────────────────────────────
# Crime generator — master prompt
# ─────────────────────────────────────────────────────────────────────────────

def generate_game(bar_name, bar_slug):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    ctx = BAR_CONTEXT.get(bar_slug, {})
    ambiente = get_ambient(bar_slug)

    # Only reference the bar ~1 in 20 days (when ambiente is the café)
    bar_reference = ""
    if "cafetería" in ambiente.lower() or "café" in ambiente.lower():
        if ctx:
            bar_reference = f"El local es {ctx.get('nombre', bar_name)} en {ctx.get('ubicacion', '')}. Menciona sutilmente algún producto o detalle del local."

    prompt = f"""Eres un escritor experto en novela negra y misterio clásico. Tu estilo combina:
- La estructura de Agatha Christie: el culpable siempre está presente desde el principio, visible pero no obvio
- La lógica de Sherlock Holmes: un detalle cotidiano e insignificante revela la verdad
- La tensión de Black Stories: premisa perturbadora con explicación perfectamente lógica
- El fair play de Ellery Queen: el lector tiene TODA la información para resolver el caso

FECHA: {today}
ESCENARIO: {ambiente}
{bar_reference}

REGLAS ABSOLUTAS DE CALIDAD:
1. El culpable debe tener motivo claro, medio físico posible y oportunidad real
2. Las 3 pistas deben ser coherentes entre sí y apuntar inequívocamente al culpable — pero solo en retrospectiva
3. Una pista debe ser un detalle cotidiano aparentemente irrelevante que lo cambia todo
4. El giro final debe ser sorprendente pero inevitable — al leerlo el jugador piensa "¡cómo no lo vi!"
5. Los tres sospechosos deben ser igualmente creíbles antes de revelar las pistas
6. Nunca uses veneno como arma — es demasiado predecible
7. El crimen puede ser un robo, una desaparición, un sabotaje, un chantaje o un asesinato
8. El tono es elegante, ligeramente irónico, adulto pero accesible
9. La resolución debe tener un detalle de humor negro sutil
10. El escenario debe estar vivo — detalles sensoriales, atmósfera, época si procede

Devuelve SOLO un objeto JSON válido, sin markdown:
{{
  "titular": "Titular periodístico elegante y dramático (máx 9 palabras, sin signos de exclamación)",
  "lugar": "Lugar específico y evocador dentro del escenario",
  "introduccion": "4-5 frases que establezcan el escenario, el crimen y la atmósfera. Concreto, sensorial, con un detalle llamativo que enganche. Sin revelar nada clave.",
  "pistas": [
    "Pista 1: detalle físico concreto del escenario o los personajes",
    "Pista 2: dato sobre comportamiento o coartada de alguien",
    "Pista 3: el detalle aparentemente irrelevante que lo revela todo"
  ],
  "sospechosos": [
    {{"nombre": "Nombre Apellido evocador", "descripcion": "Ocupación precisa, rasgo de carácter y motivo sospechoso en una frase. Debe sonar real."}},
    {{"nombre": "Nombre Apellido evocador", "descripcion": "Ocupación precisa, rasgo de carácter y motivo sospechoso en una frase. Debe sonar real."}},
    {{"nombre": "Nombre Apellido evocador", "descripcion": "Ocupación precisa, rasgo de carácter y motivo sospechoso en una frase. Debe sonar real."}}
  ],
  "culpable": 1,
  "explicacion": "3-4 frases que revelan el método, el motivo real y el detalle que lo delataba. Satisfactorio, con giro, con el toque de ironía final."
}}

El índice culpable varía cada día: hoy usa {get_day_seed(bar_slug) % 3}."""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-5',
            'max_tokens': 1200,
            'messages': [{'role': 'user', 'content': prompt}]
        },
        timeout=60
    )

    data = response.json()

    if 'content' not in data:
        raise Exception(f"API error: {data.get('error', data)}")

    text = data['content'][0]['text'].strip()
    text = text.replace('```json', '').replace('```', '').strip()
    return json.loads(text)
