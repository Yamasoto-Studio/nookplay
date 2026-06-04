import requests
import json
from datetime import date
import os

# Bar context database — detailed info for AI case generation
BAR_CONTEXT = {
    'yellow': {
        'nombre': 'Yellow Specialty Koffee',
        'propietaria': 'Lorena',
        'ubicacion': 'Viladecans, Barcelona',
        'tipo': 'Cafetería de especialidad',
        'descripcion': 'Cafetería moderna de café de especialidad en Viladecans. Local acogedor con clientela variada: familias, profesionales, amigos del barrio. Ambiente cuidado, moderno con toques vintage.',
        'productos': [
            'Café de finca (origen etíope, entre otros)',
            'Frappé artesano',
            'Chocolate suizo',
            'Tartas y postres artesanos (zanahoria, cookies, etc.)',
            'Brunch: tostadas, zumos naturales',
        ],
        'equipo': ['Lorena (propietaria y jefa)'],
        'clientela': 'Variada: madres, padres, amigos, profesionales del barrio',
        'detalles': [
            'El café de finca es su producto estrella y seña de identidad',
            'Toda la repostería es artesana, elaborada en el propio local',
            'Local que cuida mucho la experiencia del cliente',
            'Venden el juego de mesa Oferta de Yamasoto en el local',
        ]
    }
}

def generate_game(bar_name, bar_slug):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')

    # Get bar context
    ctx = BAR_CONTEXT.get(bar_slug, {})
    context_text = ''
    if ctx:
        context_text = f"""
CONTEXTO DEL LOCAL:
- Propietaria: {ctx.get('propietaria', 'la dueña')}
- Ubicación: {ctx.get('ubicacion', bar_name)}
- Tipo: {ctx.get('tipo', '')}
- Descripción: {ctx.get('descripcion', '')}
- Productos destacados: {', '.join(ctx.get('productos', []))}
- Equipo: {', '.join(ctx.get('equipo', []))}
- Clientela: {ctx.get('clientela', '')}
- Detalles clave: {'; '.join(ctx.get('detalles', []))}
"""

    prompt = f"""Eres el escritor de un juego de misterio diario para bares españoles. Genera un caso policial breve, entretenido y bien construido.

FECHA: {today}
BAR: {bar_name}
{context_text}

REGLAS DE ESCRITURA:
- El caso ocurre en o alrededor del propio local
- Usa el nombre real de la propietaria (Lorena) como personaje habitual
- Menciona productos reales del local (café de finca, tartas artesanas, frappé...)
- Sitúa el caso en Viladecans, no en Madrid ni otras ciudades
- El culpable siempre tiene motivo, medio y oportunidad claros
- Una pista debe ser un detalle cotidiano del local reconocible para los clientes
- El giro final debe ser sorprendente pero inevitable
- Tono accesible, con humor ligero, sin violencia explícita
- Duración: 5-8 minutos (el tiempo de un café)

Devuelve SOLO un objeto JSON válido, sin markdown ni explicaciones:
{{
  "titular": "Titular periodístico dramático (máx 8 palabras)",
  "lugar": "Lugar concreto dentro o cerca del local en Viladecans",
  "introduccion": "3-4 frases describiendo el crimen. Menciona el local, a Lorena y algún producto o detalle real.",
  "pistas": [
    "Pista 1: dato concreto y ambiguo relacionado con el local",
    "Pista 2: dato concreto y ambiguo",
    "Pista 3: dato concreto y ambiguo"
  ],
  "sospechosos": [
    {{"nombre": "Nombre Apellido", "descripcion": "Ocupación y motivo sospechoso en una frase"}},
    {{"nombre": "Nombre Apellido", "descripcion": "Ocupación y motivo sospechoso en una frase"}},
    {{"nombre": "Nombre Apellido", "descripcion": "Ocupación y motivo sospechoso en una frase"}}
  ],
  "culpable": 1,
  "explicacion": "2-3 frases revelando cómo y por qué se cometió el crimen. Satisfactorio, con giro, local y creíble."
}}

El campo culpable es el índice (0, 1 o 2). Varía el índice en cada caso para que no sea siempre el mismo."""

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

    if 'content' not in data:
        raise Exception(f"API error: {data.get('error', data)}")

    text = data['content'][0]['text'].strip()
    text = text.replace('```json', '').replace('```', '').strip()
    return json.loads(text)
