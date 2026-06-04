import requests
import json
from datetime import date
import os

def generate_game(bar_name, bar_slug):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')

    prompt = f"""Eres el escritor de un juego de misterio diario para bares españoles. Genera un caso policial breve, entretenido y bien construido.

FECHA: {today}
BAR: {bar_name}

Devuelve SOLO un objeto JSON válido, sin markdown ni explicaciones:
{{
  "titular": "Titular periodístico dramático (máx 8 palabras)",
  "lugar": "Ciudad y lugar concreto del crimen",
  "introduccion": "3-4 frases describiendo el crimen. Menciona {bar_name}.",
  "pistas": [
    "Pista 1: dato concreto y ambiguo",
    "Pista 2: dato concreto y ambiguo",
    "Pista 3: dato concreto y ambiguo"
  ],
  "sospechosos": [
    {{"nombre": "Nombre Apellido", "descripcion": "Ocupación y motivo sospechoso"}},
    {{"nombre": "Nombre Apellido", "descripcion": "Ocupación y motivo sospechoso"}},
    {{"nombre": "Nombre Apellido", "descripcion": "Ocupación y motivo sospechoso"}}
  ],
  "culpable": 1,
  "explicacion": "2-3 frases revelando el crimen."
}}"""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-5',
            'max_tokens': 1000,
            'messages': [{'role': 'user', 'content': prompt}]
        },
        timeout=60
    )

    data = response.json()
    
    # Handle response
    if 'content' not in data:
        raise Exception(f"API error: {data.get('error', data)}")
    
    text = data['content'][0]['text'].strip()
    text = text.replace('```json', '').replace('```', '').strip()
    return json.loads(text)
