import requests
import json
from datetime import date
import os

def generate_game(bar_name, bar_slug):
    """Generate daily game content using Anthropic API directly."""
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')

    prompt = f"""Eres el escritor de un juego de misterio diario para bares españoles. Genera un caso policial breve, entretenido y bien construido.

FECHA: {today}
BAR: {bar_name}

REGLAS:
- El culpable siempre tiene motivo, medio y oportunidad
- Una pista debe ser un detalle cotidiano del bar o del entorno
- El giro final debe ser sorprendente pero inevitable
- Tono: accesible, algo de humor, sin violencia explícita
- El caso debe poder resolverse en 5-8 minutos

Devuelve SOLO un objeto JSON válido, sin markdown ni explicaciones:
{{
  "titular": "Titular periodístico dramático (máx 8 palabras)",
  "lugar": "Ciudad y lugar concreto del crimen",
  "introduccion": "3-4 frases describiendo el crimen. Menciona {bar_name} y algún detalle del local.",
  "pistas": [
    "Pista 1: dato concreto y ambiguo",
    "Pista 2: dato concreto y ambiguo",
    "Pista 3: dato concreto y ambiguo"
  ],
  "sospechosos": [
    {{"nombre": "Nombre Apellido", "descripcion": "Ocupación y motivo sospechoso en una frase"}},
    {{"nombre": "Nombre Apellido", "descripcion": "Ocupación y motivo sospechoso en una frase"}},
    {{"nombre": "Nombre Apellido", "descripcion": "Ocupación y motivo sospechoso en una frase"}}
  ],
  "culpable": 1,
  "explicacion": "2-3 frases revelando cómo y por qué se cometió el crimen. Satisfactorio y con giro."
}}

El campo culpable es el índice (0, 1 o 2) del sospechoso culpable. Varía el índice."""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-20250514',
            'max_tokens': 1000,
            'messages': [{'role': 'user', 'content': prompt}]
        },
        timeout=60
    )

    data = response.json()
    text = data['content'][0]['text'].strip()
    text = text.replace('```json', '').replace('```', '').strip()
    return json.loads(text)
