import requests
import json
from datetime import date
import os
import hashlib

# ─────────────────────────────────────────────────────────────────────────────
# Build bar context dynamically from DB data
# ─────────────────────────────────────────────────────────────────────────────

def build_bar_context(bar_row):
    """
    Construye el contexto del bar para la IA a partir de un dict con los datos de la BD.
    bar_row: dict con los campos de la tabla bars
    """
    return {
        'nombre':       bar_row.get('name', ''),
        'propietaria':  bar_row.get('owner_name', ''),
        'ubicacion':    f"{bar_row.get('city', '')}, {bar_row.get('province', '')}".strip(', '),
        'tipo':         bar_row.get('type', ''),
        'descripcion':  bar_row.get('description', ''),
        'equipo':       [n.strip() for n in bar_row.get('staff_names', '').split(',') if n.strip()],
        'vibe':         bar_row.get('bar_vibe', ''),
        'productos':    [],  # Se rellena desde bar_products en app.py
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
    "cafetería de especialidad en Barcelona",  # Aparece ~1 de cada 20 días
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

def _bloque_evitar(evitar):
    """Construye un bloque de texto para el prompt con los contenidos a no repetir."""
    if not evitar:
        return ""
    lista = "\n".join(f"- {x}" for x in evitar[:30])
    return f"""

IMPORTANTE — NO REPETIR: Estos contenidos ya se han usado en los últimos días. Genera algo CLARAMENTE DISTINTO, con otro tema, enfoque y protagonistas:
{lista}
"""


def get_day_seed(bar_slug):
    """Genera un seed determinístico para el contenido de hoy."""
    today = str(date.today())
    return int(hashlib.md5(f"{today}{bar_slug}".encode()).hexdigest(), 16)

def get_ambient(bar_slug):
    seed = get_day_seed(bar_slug)
    return AMBIENTES[seed % len(AMBIENTES)]

def get_categoria_impostor(bar_slug):
    seed = get_day_seed(bar_slug)
    return CATEGORIAS_IMPOSTOR[(seed + 3) % len(CATEGORIAS_IMPOSTOR)]

# ─────────────────────────────────────────────────────────────────────────────
# Crime generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_game(bar_context, bar_slug):
    """
    bar_context: dict generado por build_bar_context() + productos
    bar_slug: slug del bar para el seed
    """
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    ambiente = get_ambient(bar_slug)

    # Solo referencia el bar ~1 de cada 20 días (cuando el ambiente es la cafetería)
    bar_reference = ""
    if "cafetería" in ambiente.lower() or "café" in ambiente.lower():
        nombre = bar_context.get('nombre', '')
        ubicacion = bar_context.get('ubicacion', '')
        productos = bar_context.get('productos', [])
        if nombre:
            prods_str = ', '.join(productos[:3]) if productos else ''
            bar_reference = f"El local es {nombre} en {ubicacion}."
            if prods_str:
                bar_reference += f" Menciona sutilmente alguno de estos productos: {prods_str}."

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
2. Incluye exactamente 3 pistas — ni más ni menos
3. REGLA DE ORO DE LAS PISTAS:
   - Pista 1: un detalle físico o sensorial ambiguo — puede interpretarse de dos formas
   - Pista 2: una pista engañosa que parece señalar a un inocente
   - Pista 3: el detalle cotidiano aparentemente irrelevante que en retrospectiva lo revela todo
4. Dificultad MEDIA: el jugador atento puede resolverlo, pero no es obvio a la primera
5. El giro final debe ser sorprendente pero inevitable — al leerlo el jugador piensa "¡cómo no lo vi!"
6. Los tres sospechosos deben ser IGUALMENTE creíbles — el jugador no debe poder descartar a ninguno antes de leer todas las pistas
7. Nunca uses veneno como arma — es demasiado predecible
8. El crimen puede ser un robo, una desaparición, un sabotaje, un chantaje o un asesinato
9. El tono es elegante, ligeramente irónico, adulto pero accesible
10. La resolución debe tener un detalle de humor negro sutil
11. El escenario debe estar vivo — detalles sensoriales, atmósfera, época si procede
12. NUNCA menciones explícitamente que una pista es "la clave" o "lo más importante"

Devuelve SOLO un objeto JSON válido, sin markdown:
{{
  "titular": "Titular periodístico elegante y dramático (máx 9 palabras, sin signos de exclamación)",
  "lugar": "Lugar específico y evocador dentro del escenario",
  "introduccion": "4-5 frases que establezcan el escenario, el crimen y la atmósfera. Concreto, sensorial, con un detalle llamativo que enganche. Sin revelar nada clave.",
  "pistas": [
    "Pista 1: detalle físico o sensorial ambiguo — puede apuntar a cualquier sospechoso",
    "Pista 2: dato que parece señalar claramente a un inocente — pista engañosa",
    "Pista 3: detalle cotidiano insignificante que en retrospectiva lo revela todo"
  ],
  "sospechosos": [
    {{"nombre": "Nombre Apellido evocador", "descripcion": "Ocupación precisa, rasgo de carácter y motivo sospechoso en una frase. Debe sonar real."}},
    {{"nombre": "Nombre Apellido evocador", "descripcion": "Ocupación precisa, rasgo de carácter y motivo sospechoso en una frase. Debe sonar real."}},
    {{"nombre": "Nombre Apellido evocador", "descripcion": "Ocupación precisa, rasgo de carácter y motivo sospechoso en una frase. Debe sonar real."}}
  ],
  "culpable": {get_day_seed(bar_slug) % 3},
  "explicacion": "3-4 frases que revelan el método, el motivo real y el detalle que lo delataba. Satisfactorio, con giro, con el toque de ironía final."
}}"""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
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


# ─────────────────────────────────────────────────────────────────────────────
# El Impostor generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_impostor(bar_name, bar_slug):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)
    categoria = CATEGORIAS_IMPOSTOR[(seed + 5) % len(CATEGORIAS_IMPOSTOR)]
    falsa_idx = (seed + 5) % 4

    prompt = """Eres un divulgador cultural experto, riguroso y con humor seco. Creas contenido educativo que sorprende.

FECHA: """ + today + """
CATEGORÍA: """ + categoria + """

Tu misión: crear un reto "El Impostor" donde el jugador debe encontrar el dato falso entre 4 afirmaciones.

REGLAS DE CALIDAD:
1. Las 3 afirmaciones verdaderas deben ser datos reales, verificables y sorprendentes — no obviedades
2. El dato falso debe ser MUY creíble — casi verdadero, plausible, del mismo nivel que los verdaderos
3. El dato falso no debe ser absurdo ni ridículo — debe engañar incluso a alguien informado
4. Al revelar la respuesta, el jugador debe pensar "casi lo sabía" o "qué interesante"
5. Evita datos demasiado conocidos (el agua hierve a 100°, la Torre Eiffel está en París)
6. El tema debe tener un ángulo sorprendente o poco conocido
7. TONO CRUCIAL: Como si se lo contaras a un amigo en un bar mientras tomáis algo. Curioso, ligero, con humor seco.

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "tema": "Título del tema en 4-6 palabras",
  "intro": "Una frase que contextualice el tema. Máx 20 palabras.",
  "afirmaciones": [
    "Afirmación 1",
    "Afirmación 2",
    "Afirmación 3",
    "Afirmación 4"
  ],
  "falsa": """ + str(falsa_idx) + """,
  "explicacion_falsa": "Explica SOLO por qué esa afirmación concreta es falsa y cuál es la realidad. 2 frases máximo.",
  "dato_bonus": "Un dato curioso sobre el tema general. 1-2 frases."
}

La afirmación en la posición """ + str(falsa_idx) + """ (índice 0-3) debe ser la FALSA."""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
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


# ─────────────────────────────────────────────────────────────────────────────
# El Dilema generator
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIAS_DILEMA = [
    "situación cotidiana en la calle o el transporte",
    "decisión en una reunión familiar o con amigos",
    "dilema en el trabajo o con compañeros",
    "situación con un desconocido",
    "decisión sobre dinero o propiedades",
    "dilema de honestidad en el día a día",
    "situación incómoda en un restaurante o tienda",
    "decisión sobre redes sociales o tecnología",
    "dilema con vecinos o en el barrio",
    "situación de vacaciones o viaje",
]

def generate_dilema(bar_name, bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)
    categoria = CATEGORIAS_DILEMA[(seed + 7) % len(CATEGORIAS_DILEMA)]

    prompt = """Eres el animador de una mesa de bar. Propones dilemas cotidianos que hacen que la gente debata mientras toma algo. Tu estilo es cercano, divertido, sin pretensiones.

FECHA: """ + today + """
CATEGORÍA: """ + categoria + """

Crea un dilema del día con estas reglas:
1. La situación debe ser 100% cotidiana y reconocible — algo que le puede pasar a cualquiera
2. Las dos opciones deben ser igualmente defendibles — no hay respuesta obvia
3. Tono casual y cercano, como si lo contara un amigo en un bar
4. Nada de política, religión ni temas divisivos serios
5. La situación en 2-3 frases máximo, directa y con gancho
6. Los botones deben ser cortos y contundentes (máx 5 palabras cada uno)
7. El "dato curioso" al final debe ser una estadística real o un dato sorprendente relacionado con el tema

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "situacion": "Descripción de la situación en 2-3 frases. Directa, con gancho, tono de bar.",
  "opcion_a": "Texto corto del botón A (máx 5 palabras)",
  "opcion_b": "Texto corto del botón B (máx 5 palabras)",
  "dato_curioso": "Un dato real y sorprendente sobre este tipo de situación. 1-2 frases.",
  "contexto_a": "En qué porcentaje aproximado crees que la gente elegiría A? Solo el número, ej: 45",
  "contexto_b": "En qué porcentaje aproximado crees que la gente elegiría B? Solo el número, ej: 55"
}""" + _bloque_evitar(evitar)

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 800,
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


# ─────────────────────────────────────────────────────────────────────────────
# Las Conexiones generator
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIAS_CONEXIONES = [
    "gastronomía y cocina",
    "deportes y juegos",
    "naturaleza y animales",
    "cine y series",
    "música y artistas",
    "viajes y geografía",
    "tecnología y ciencia",
    "historia y cultura",
    "palabras y lenguaje",
    "objetos cotidianos",
]

def generate_conexiones(bar_name, bar_slug):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)
    categoria = CATEGORIAS_CONEXIONES[(seed + 9) % len(CATEGORIAS_CONEXIONES)]

    prompt = """Eres un experto en juegos de palabras y asociaciones. Creas retos de conexiones para grupos de personas en un bar.

FECHA: """ + today + """
CATEGORÍA BASE: """ + categoria + """

Crea un reto "Las Conexiones" con estas reglas:

1. Exactamente 8 palabras en total — 2 grupos de 4
2. Cada grupo tiene una categoría oculta que las conecta
3. TRAMPA OBLIGATORIA: al menos 1 palabra parece pertenecer a ambos grupos pero solo va en uno
4. Las palabras deben ser reconocibles para cualquier persona adulta española
5. Las categorías no pueden ser obvias — tienen que hacer pensar
6. Nivel de dificultad: MEDIO — se puede resolver pero no es inmediato
7. Tono: divertido, sorprendente, con un punto de "¡cómo no lo vi!"
8. Los grupos deben tener nombres cortos y reveladores (máx 4 palabras)

TIPOS DE CONEXIONES que funcionan bien:
- Palabras que van antes/después de otra ("__ de leche", "café __")
- Cosas que comparten una característica inesperada
- Nombres que son también otra cosa (doble significado)
- Partes de algo mayor
- Palabras relacionadas con un concepto poco obvio

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "grupo_a": {
    "nombre": "Nombre corto del grupo A",
    "palabras": ["PALABRA1", "PALABRA2", "PALABRA3", "PALABRA4"],
    "explicacion": "Por qué estas 4 palabras van juntas (1 frase)"
  },
  "grupo_b": {
    "nombre": "Nombre corto del grupo B", 
    "palabras": ["PALABRA5", "PALABRA6", "PALABRA7", "PALABRA8"],
    "explicacion": "Por qué estas 4 palabras van juntas (1 frase)"
  },
  "trampa": "PALABRA_TRAMPA",
  "explicacion_trampa": "Por qué esta palabra engaña y en qué grupo va realmente (1 frase)"
}

IMPORTANTE: Las palabras deben estar en MAYÚSCULAS."""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 800,
            'messages': [{'role': 'user', 'content': prompt}]
        },
        timeout=60
    )

    data = response.json()
    if 'content' not in data:
        raise Exception(f"API error: {data.get('error', data)}")

    text = data['content'][0]['text'].strip()
    text = text.replace('```json', '').replace('```', '').strip()
    result = json.loads(text)
    
    # Mezclar las 8 palabras aleatoriamente
    import random as _random
    todas = result['grupo_a']['palabras'] + result['grupo_b']['palabras']
    _random.shuffle(todas)
    result['palabras_mezcladas'] = todas
    
    return result


# ─────────────────────────────────────────────────────────────────────────────
# El Oráculo — generador de horóscopos con humor
# ─────────────────────────────────────────────────────────────────────────────

SIGNOS = [
    {"nombre": "Aries", "emoji": "♈", "fechas": "21 mar – 19 abr"},
    {"nombre": "Tauro", "emoji": "♉", "fechas": "20 abr – 20 may"},
    {"nombre": "Géminis", "emoji": "♊", "fechas": "21 may – 20 jun"},
    {"nombre": "Cáncer", "emoji": "♋", "fechas": "21 jun – 22 jul"},
    {"nombre": "Leo", "emoji": "♌", "fechas": "23 jul – 22 ago"},
    {"nombre": "Virgo", "emoji": "♍", "fechas": "23 ago – 22 sep"},
    {"nombre": "Libra", "emoji": "♎", "fechas": "23 sep – 22 oct"},
    {"nombre": "Escorpio", "emoji": "♏", "fechas": "23 oct – 21 nov"},
    {"nombre": "Sagitario", "emoji": "♐", "fechas": "22 nov – 21 dic"},
    {"nombre": "Capricornio", "emoji": "♑", "fechas": "22 dic – 19 ene"},
    {"nombre": "Acuario", "emoji": "♒", "fechas": "20 ene – 18 feb"},
    {"nombre": "Piscis", "emoji": "♓", "fechas": "19 feb – 20 mar"},
]

def generate_oraculo(bar_slug):
    today = str(date.today())
    from datetime import datetime
    now = datetime.now()
    dia_semana = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][now.weekday()]
    hora = now.hour
    if hora < 12:
        momento = f"mañana ({hora}h)"
    elif hora < 15:
        momento = f"mediodía ({hora}h)"
    elif hora < 20:
        momento = f"tarde ({hora}h)"
    else:
        momento = f"noche ({hora}h)"
    
    api_key = os.environ.get('ANTHROPIC_API_KEY')

    signos_nombres = [s["nombre"] for s in SIGNOS]

    prompt = """Eres el oráculo más irreverente y divertido del mundo. Escribes horóscopos con humor seco, ironía y referencias cotidianas. Nada de misticismo cursi. Todo con cariño pero sin filtros.

FECHA: """ + today + """
DÍA: """ + dia_semana + """ por la """ + momento + """

Escribe el horóscopo de HOY para los 12 signos del zodíaco.

REGLAS DE ESTILO:
1. Cada predicción entre 2-3 frases. Directa, con gancho.
2. Tono: como si un amigo muy gracioso te dijera la verdad con humor. Ni cursi ni cruel.
3. Referencia el día de la semana cuando tenga gracia (ej: "Es """ + dia_semana + """, así que...")
4. Al menos 3 signos deben tener una referencia cruzada a otro signo (ej: "Hoy los Leo te van a sacar de quicio", "Evita a los Tauro antes del mediodía")
5. Al menos 2 signos deben tener una referencia a algo muy cotidiano (el café, el móvil, el ascensor, el tráfico, etc.)
6. Una predicción puede ser absurda si tiene lógica interna
7. Usa la personalidad conocida de cada signo pero dándole la vuelta
8. NUNCA uses palabras como "universo", "energía cósmica", "vibración", "manifestar"
9. Acaba siempre con una "predicción concreta" absurda pero específica del día

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "signos": {
    "Aries": {"prediccion": "...", "consejo": "Una frase de consejo absurdo pero concreto"},
    "Tauro": {"prediccion": "...", "consejo": "..."},
    "Géminis": {"prediccion": "...", "consejo": "..."},
    "Cáncer": {"prediccion": "...", "consejo": "..."},
    "Leo": {"prediccion": "...", "consejo": "..."},
    "Virgo": {"prediccion": "...", "consejo": "..."},
    "Libra": {"prediccion": "...", "consejo": "..."},
    "Escorpio": {"prediccion": "...", "consejo": "..."},
    "Sagitario": {"prediccion": "...", "consejo": "..."},
    "Capricornio": {"prediccion": "...", "consejo": "..."},
    "Acuario": {"prediccion": "...", "consejo": "..."},
    "Piscis": {"prediccion": "...", "consejo": "..."}
  },
  "frase_del_dia": "Una frase filosófica absurda que vale para todos los signos hoy"
}"""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 2000,
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


# ─────────────────────────────────────────────────────────────────────────────
# ¿Dónde en el mundo? generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_donde(bar_slug):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres un experto en geografía y cultura mundial. Creas retos de adivinanza de lugares para grupos en un bar.

FECHA: """ + today + """

Crea un reto "¿Dónde en el mundo?" con estas reglas:

1. Elige un lugar real — puede ser una ciudad, país, región, monumento o lugar icónico
2. Crea exactamente 5 pistas progresivas — de más vaga a más reveladora
3. Cada pista usa emojis relevantes al contenido + texto corto y evocador
4. Las primeras 2 pistas son muy vagas (continente, clima, algo cultural genérico)
5. Las pistas 3-4 son más específicas (gastronomía, costumbres, arquitectura)
6. La pista 5 es casi reveladora (algo muy característico del lugar)
7. Crea 4 opciones de respuesta: el lugar correcto + 3 trampas creíbles que podrían encajar con las pistas
8. Las trampas deben ser lugares que comparten alguna característica con el correcto
9. Nivel de dificultad: MEDIO — conocimiento cultural general, no trivia de experto
10. Evita capitales mundiales demasiado obvias (París, Roma, Nueva York) — busca lugares sorprendentes

TIPOS DE PISTAS que funcionan bien:
- Emojis de gastronomía típica
- Emojis de clima o geografía
- Referencias a costumbres o fiestas
- Referencias a arquitectura o paisaje
- Curiosidades culturales

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "lugar": "Nombre del lugar correcto",
  "pais": "País o región",
  "pistas": [
    {"emoji": "🌍🌿", "texto": "Pista 1 muy vaga"},
    {"emoji": "🌶️🎵", "texto": "Pista 2"},
    {"emoji": "🏛️🌊", "texto": "Pista 3"},
    {"emoji": "🍷🧀", "texto": "Pista 4"},
    {"emoji": "🎭🌸", "texto": "Pista 5 casi reveladora"}
  ],
  "opciones": ["Lugar correcto", "Trampa 1", "Trampa 2", "Trampa 3"],
  "correcto": 0,
  "dato_curioso": "Un dato sorprendente sobre este lugar. 1-2 frases.",
  "por_que_interesante": "Por qué vale la pena conocer este lugar. 1 frase."
}

IMPORTANTE: El lugar correcto debe estar en la posición 0 del array opciones."""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
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
    result = json.loads(text)

    # Mezclar opciones manteniendo referencia al correcto
    import random as _random
    opciones = result['opciones'][:]
    correcto_nombre = opciones[0]
    _random.shuffle(opciones)
    result['opciones'] = opciones
    result['correcto'] = opciones.index(correcto_nombre)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# La Carta — Sudoku 4x4 con emojis
# No necesita IA — banco de puzzles pre-cargados
# ─────────────────────────────────────────────────────────────────────────────

CARTA_CATEGORIAS = [
    {"nombre": "Cafetería", "items": ["☕", "🥐", "🍩", "🧇"]},
    {"nombre": "Bebidas", "items": ["🧋", "🍵", "🥤", "🍹"]},
    {"nombre": "Frutas", "items": ["🍎", "🍋", "🍇", "🍓"]},
    {"nombre": "Dulces", "items": ["🍰", "🍫", "🍭", "🧁"]},
    {"nombre": "Verano", "items": ["🍦", "🍉", "🥭", "🍑"]},
    {"nombre": "Snacks", "items": ["🥨", "🍿", "🥜", "🫙"]},
    {"nombre": "Brunch", "items": ["🥑", "🥚", "🍞", "🥞"]},
]

CARTA_PUZZLES = [
    {"puzzle": [[1, 0, 4, 2], [4, 0, 0, 0], [0, 0, 0, 1], [0, 1, 0, 4]], "solution": [[1, 3, 4, 2], [4, 2, 1, 3], [2, 4, 3, 1], [3, 1, 2, 4]]},
    {"puzzle": [[4, 0, 0, 3], [0, 0, 1, 4], [1, 4, 0, 2], [0, 0, 4, 0]], "solution": [[4, 1, 2, 3], [3, 2, 1, 4], [1, 4, 3, 2], [2, 3, 4, 1]]},
    {"puzzle": [[0, 3, 1, 4], [1, 4, 0, 0], [0, 0, 4, 0], [0, 0, 0, 2]], "solution": [[2, 3, 1, 4], [1, 4, 2, 3], [3, 2, 4, 1], [4, 1, 3, 2]]},
    {"puzzle": [[0, 2, 0, 4], [1, 4, 3, 0], [2, 3, 0, 0], [0, 0, 2, 0]], "solution": [[3, 2, 1, 4], [1, 4, 3, 2], [2, 3, 4, 1], [4, 1, 2, 3]]},
    {"puzzle": [[0, 4, 0, 0], [3, 2, 4, 1], [0, 0, 0, 0], [0, 3, 0, 4]], "solution": [[1, 4, 2, 3], [3, 2, 4, 1], [4, 1, 3, 2], [2, 3, 1, 4]]},
    {"puzzle": [[0, 0, 4, 3], [4, 0, 2, 1], [1, 0, 3, 0], [0, 0, 0, 4]], "solution": [[2, 1, 4, 3], [4, 3, 2, 1], [1, 4, 3, 2], [3, 2, 1, 4]]},
    {"puzzle": [[0, 4, 0, 1], [0, 1, 0, 0], [4, 3, 0, 2], [0, 2, 0, 0]], "solution": [[3, 4, 2, 1], [2, 1, 3, 4], [4, 3, 1, 2], [1, 2, 4, 3]]},
    {"puzzle": [[0, 0, 0, 1], [0, 3, 4, 0], [3, 1, 0, 4], [2, 4, 0, 0]], "solution": [[4, 2, 3, 1], [1, 3, 4, 2], [3, 1, 2, 4], [2, 4, 1, 3]]},
    {"puzzle": [[0, 2, 0, 0], [0, 4, 1, 0], [0, 3, 2, 0], [2, 0, 3, 0]], "solution": [[1, 2, 4, 3], [3, 4, 1, 2], [4, 3, 2, 1], [2, 1, 3, 4]]},
    {"puzzle": [[0, 4, 1, 0], [3, 1, 4, 0], [1, 0, 3, 0], [4, 0, 0, 0]], "solution": [[2, 4, 1, 3], [3, 1, 4, 2], [1, 2, 3, 4], [4, 3, 2, 1]]},
]

def generate_carta(bar_slug):
    seed = get_day_seed(bar_slug)
    puzzle_idx = seed % len(CARTA_PUZZLES)
    cat_idx = (seed + 2) % len(CARTA_CATEGORIAS)
    
    puzzle_data = CARTA_PUZZLES[puzzle_idx]
    categoria = CARTA_CATEGORIAS[cat_idx]
    
    return {
        "categoria": categoria,
        "puzzle": puzzle_data["puzzle"],
        "solution": puzzle_data["solution"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Las Reinas — puzzle tipo Queens de LinkedIn
# Sin IA — puzzles pre-cargados que rotan por día
# ─────────────────────────────────────────────────────────────────────────────

REINAS_PUZZLES = [
    {
        "size": 5,
        "regions": [[1,0,1,1,1],[2,2,2,1,2],[2,2,2,2,3],[4,4,4,4,3],[4,4,4,4,4]],
        "solution": [[0,1],[1,3],[2,0],[3,4],[4,2]],
        "colors": ["#FF6B6B","#FFA500","#FFD700","#51CF66","#339AF0"],
    },
    {
        "size": 5,
        "regions": [[1,1,1,1,0],[2,1,2,2,2],[3,3,3,2,3],[3,4,4,4,4],[3,3,4,4,4]],
        "solution": [[0,4],[1,1],[2,3],[3,0],[4,2]],
        "colors": ["#FF6B9D","#9775FA","#FFB347","#20C997","#74C0FC"],
    },
    {
        "size": 5,
        "regions": [[1,1,0,1,1],[1,2,2,2,1],[3,2,3,3,3],[4,4,4,3,4],[4,4,4,4,4]],
        "solution": [[0,2],[1,4],[2,1],[3,3],[4,0]],
        "colors": ["#FF8C42","#4DABF7","#F06595","#40C057","#FCC419"],
    },
    {
        "size": 6,
        "regions": [[1,0,1,1,2,2],[1,1,1,1,2,2],[3,3,3,3,3,2],[3,4,4,3,3,3],[3,3,4,3,5,5],[3,3,5,5,5,5]],
        "solution": [[0,1],[1,3],[2,5],[3,0],[4,2],[5,4]],
        "colors": ["#FF6B6B","#FFA94D","#FFD43B","#69DB7C","#4DABF7","#DA77F2"],
    },
    {
        "size": 5,
        "regions": [[0,1,1,2,2],[0,0,1,1,2],[0,0,1,1,2],[0,3,1,2,2],[0,0,0,4,4]],
        "solution": [[0,0],[1,2],[2,4],[3,1],[4,3]],
        "colors": ["#FF6B9D","#63E6BE","#FFA94D","#A9E34B","#74C0FC"],
    },
    {
        "size": 5,
        "regions": [[1,1,1,0,1],[1,2,2,2,2],[1,2,2,3,3],[1,2,3,3,3],[1,4,3,3,3]],
        "solution": [[0,3],[1,0],[2,2],[3,4],[4,1]],
        "colors": ["#FFA94D","#4DABF7","#F06595","#51CF66","#FFD43B"],
    },
    {
        "size": 5,
        "regions": [[1,1,0,1,1],[1,2,2,2,2],[3,3,3,3,2],[3,3,4,4,4],[3,3,3,4,4]],
        "solution": [[0,2],[1,0],[2,4],[3,1],[4,3]],
        "colors": ["#FF6B6B","#74C0FC","#FFA94D","#69DB7C","#DA77F2"],
    },
]

def generate_reinas(bar_slug):
    seed = get_day_seed(bar_slug)
    idx = seed % len(REINAS_PUZZLES)
    return REINAS_PUZZLES[idx]


# ─────────────────────────────────────────────────────────────────────────────
# Conexión Local — juego hiperlocal generado por IA
# ─────────────────────────────────────────────────────────────────────────────

def generate_conexion_local(bar_name, bar_city, bar_province, bar_slug):
    today = str(date.today())
    from datetime import datetime
    dia_semana = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][datetime.now().weekday()]
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    # Rotate between different content types each day
    tipos = ["trivia", "anecdota", "comparativa", "leyenda", "personaje"]
    tipo_hoy = tipos[seed % len(tipos)]

    prompt = """Eres un experto en historia local, geografía y cultura española. Conoces cada rincón de cada pueblo y ciudad. Tu estilo es cercano, divertido y sorprendente — como el que más sabe del bar.

FECHA: """ + today + """
DÍA: """ + dia_semana + """
LOCAL: """ + bar_name + """
CIUDAD: """ + bar_city + """
PROVINCIA: """ + bar_province + """
TIPO DE CONTENIDO HOY: """ + tipo_hoy + """

Crea el contenido de "Conexión Local" para hoy. El juego debe sentirse completamente personalizado para """ + bar_city + """.

REGLAS:
1. El contenido debe ser 100% real y verificable sobre """ + bar_city + """ o su entorno inmediato
2. Debe sorprender — algo que incluso los propios vecinos pueden no saber
3. Tono: como si lo contara un amigo muy curioso en un bar
4. Referencia el bar o el día si tiene gracia natural
5. Debe generar conversación en la mesa — que la gente quiera opinar o debatir

TIPOS de contenido según el tipo asignado:
- "trivia": Una pregunta de trivia sobre """ + bar_city + """ con 4 opciones. Una correcta, tres plausibles pero incorrectas.
- "anecdota": Una anécdota histórica o curiosidad sorprendente sobre """ + bar_city + """. Con un dato que nadie espera.
- "comparativa": Compara """ + bar_city + """ con otra ciudad o pueblo cercano de forma divertida. Datos reales.
- "leyenda": Una leyenda, mito o historia curiosa vinculada a """ + bar_city + """ o la zona.
- "personaje": Un personaje histórico, famoso o curioso vinculado a """ + bar_city + """ que pocos conocen.

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "tipo": "trivia|anecdota|comparativa|leyenda|personaje",
  "titulo": "Título corto y llamativo (máx 6 palabras)",
  "contenido": "El texto principal. 3-4 frases. Directo, con gancho, sorprendente.",
  "pregunta": "Una pregunta para debatir en mesa relacionada con el contenido (solo si tipo != trivia)",
  "opciones": ["Opción A", "Opción B", "Opción C", "Opción D"],
  "correcta": 0,
  "explicacion": "Por qué esta es la respuesta correcta. 1-2 frases con el dato interesante.",
  "dato_bonus": "Un dato extra sorprendente sobre """ + bar_city + """ o la zona. 1-2 frases.",
  "emoji_titulo": "Un emoji que representa el contenido"
}

IMPORTANTE para trivia: opciones y correcta son obligatorios. Para los demás tipos, opciones puede ser null y correcta -1."""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
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
    result = json.loads(text)
    result['ciudad'] = bar_city
    result['bar_name'] = bar_name
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Equilibrio — puzzle soles y lunas tipo Tango
# Sin IA — puzzles pre-cargados y validados
# ─────────────────────────────────────────────────────────────────────────────

EQUILIBRIO_PUZZLES = [
    {
        "size": 6,
        "puzzle":   [[1,0,0,0,0,2],[0,0,2,0,0,0],[0,2,0,0,0,0],[2,0,0,0,0,1],[0,0,0,0,2,0],[0,1,0,0,0,0]],
        "solution": [[1,2,1,2,1,2],[2,1,2,1,2,1],[1,2,2,1,1,2],[2,1,1,2,2,1],[1,2,1,2,2,1],[2,1,2,1,1,2]],
        "clues": [[0,1,"right","neq"],[1,3,"right","neq"],[2,2,"right","neq"],[3,1,"right","eq"],[4,3,"right","eq"]],
    },
    {
        "size": 6,
        "puzzle":   [[0,1,0,0,0,2],[2,0,0,0,0,0],[0,0,1,0,0,0],[0,1,0,0,0,0],[0,0,0,1,0,0],[0,0,1,0,0,2]],
        "solution": [[1,1,2,1,2,2],[2,2,1,2,1,1],[1,2,1,2,2,1],[2,1,2,1,1,2],[1,2,2,1,2,1],[2,1,1,2,1,2]],
        "clues": [[0,0,"right","eq"],[1,4,"right","eq"],[2,3,"right","eq"],[3,3,"right","eq"],[4,1,"right","eq"]],
    },
    {
        "size": 6,
        "puzzle":   [[2,0,0,0,0,0],[0,2,0,0,0,1],[0,0,1,0,0,0],[1,0,0,1,0,0],[0,0,1,0,0,0],[0,0,0,1,0,1]],
        "solution": [[2,1,2,1,1,2],[1,2,1,2,2,1],[2,1,1,2,1,2],[1,2,2,1,2,1],[2,1,1,2,1,2],[1,2,2,1,2,1]],
        "clues": [[0,2,"right","neq"],[1,1,"right","neq"],[2,3,"right","neq"],[3,1,"right","eq"],[4,2,"bottom","neq"]],
    },
    {
        "size": 6,
        "puzzle":   [[1,0,0,0,0,0],[0,1,0,0,0,2],[0,0,0,2,0,0],[2,0,0,0,0,0],[0,0,1,0,0,0],[0,1,0,0,2,0]],
        "solution": [[1,2,2,1,2,1],[2,1,1,2,1,2],[1,2,1,2,2,1],[2,1,2,1,1,2],[1,2,1,2,1,2],[2,1,2,1,2,1]],
        "clues": [[0,1,"right","eq"],[1,2,"right","neq"],[2,2,"right","neq"],[3,1,"right","neq"],[4,3,"right","neq"]],
    },
    {
        "size": 6,
        "puzzle":   [[2,0,0,0,0,1],[0,0,1,0,0,0],[0,2,0,0,0,0],[1,0,0,0,1,0],[0,0,0,1,0,0],[0,0,1,0,0,1]],
        "solution": [[2,1,2,1,2,1],[1,2,1,2,1,2],[2,2,1,1,2,1],[1,1,2,2,1,2],[2,1,2,1,1,2],[1,2,1,2,2,1]],
        "clues": [[0,0,"bottom","neq"],[1,2,"right","neq"],[2,0,"right","eq"],[3,2,"right","eq"],[4,1,"right","neq"]],
    },
    {
        "size": 6,
        "puzzle":   [[1,0,0,0,0,0],[0,0,2,0,1,0],[0,1,0,0,0,0],[2,0,0,1,0,0],[0,0,0,1,0,0],[0,1,0,0,0,2]],
        "solution": [[1,2,1,2,2,1],[2,1,2,1,1,2],[1,1,2,2,1,2],[2,2,1,1,2,1],[1,2,2,1,2,1],[2,1,1,2,1,2]],
        "clues": [[0,0,"bottom","neq"],[1,0,"bottom","neq"],[2,1,"right","neq"],[3,0,"right","eq"],[4,3,"right","neq"]],
    },
]

def generate_equilibrio(bar_slug):
    seed = get_day_seed(bar_slug)
    idx = seed % len(EQUILIBRIO_PUZZLES)
    return EQUILIBRIO_PUZZLES[idx]


# ─────────────────────────────────────────────────────────────────────────────
# El Veredicto generator
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIAS_VEREDICTO = [
    "relaciones y convivencia",
    "trabajo y jefes",
    "dinero entre amigos",
    "familia y obligaciones",
    "tecnología y privacidad",
    "transporte y civismo",
    "vecinos y comunidad",
    "pareja y celos",
    "educación y crianza",
    "salud y hábitos",
    "amistad y lealtad",
    "consumo y medio ambiente",
]

def generate_veredicto(bar_name, bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)
    categoria = CATEGORIAS_VEREDICTO[(seed + 11) % len(CATEGORIAS_VEREDICTO)]

    prompt = """Eres el moderador de un juicio popular en un bar. Presentas casos reales o muy verosímiles donde alguien hizo algo que puede juzgarse. La mesa debate y vota: ¿culpable o inocente?

FECHA: """ + today + """
CATEGORÍA: """ + categoria + """

Crea el caso del día con estas reglas:
1. El caso debe ser cotidiano y reconocible — algo que le puede pasar a cualquiera
2. Debe haber argumentos sólidos para ambos lados — no hay respuesta obvia
3. Tono de crónica informal, como si lo contara alguien en el bar
4. Nada de política, religión ni crímenes graves — solo dilemas morales cotidianos
5. El caso en 3-4 frases máximo, con nombre ficticio y situación concreta
6. La "sentencia popular" debe ser un dato o reflexión sorprendente sobre este tipo de situación
7. Los argumentos de defensa y acusación deben ser concisos y contundentes (1 frase cada uno)

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "titulo": "Título corto y con gancho del caso (ej: 'El que canceló la boda por WhatsApp')",
  "caso": "Descripción del caso en 3-4 frases. Nombre ficticio, situación concreta, tono de bar.",
  "argumento_culpable": "El mejor argumento para declararlo culpable. 1 frase directa.",
  "argumento_inocente": "El mejor argumento para absolverlo. 1 frase directa.",
  "sentencia_popular": "Dato, estadística o reflexión sorprendente sobre este tipo de situación. 1-2 frases.",
  "pct_culpable_estimado": "Porcentaje estimado que lo declararía culpable. Solo el número, ej: 62"
}""" + _bloque_evitar(evitar)

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 800,
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


# ─────────────────────────────────────────────────────────────────────────────
# El Perfil generator
# ─────────────────────────────────────────────────────────────────────────────

PREGUNTAS_PERFIL = [
    "¿Cuál crees que es su mayor miedo?",
    "¿Cuál crees que es su sueño secreto?",
    "¿Qué es lo que más valora en la vida?",
    "¿Cuál crees que es su mayor arrepentimiento?",
    "¿Qué es lo que más le cuesta admitir?",
    "¿Qué haría si le tocara la lotería?",
    "¿Cuál crees que es su mayor virtud oculta?",
    "¿Qué es lo que nunca confesaría en una primera cita?",
    "¿Qué le impide ser completamente feliz?",
    "¿Cuál sería su reacción ante una crisis inesperada?",
    "¿Qué es lo que más envidia de los demás?",
    "¿Qué haría diferente si pudiera volver atrás?",
]

def generate_perfil(bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)
    pregunta = PREGUNTAS_PERFIL[(seed + 13) % len(PREGUNTAS_PERFIL)]

    prompt = """Eres el creador de un juego de psicología e intuición para bares. Generas perfiles de personas ficticias con coherencia interna: los datos del perfil contienen pistas sutiles que apuntan a la respuesta correcta, pero sin decirla explícitamente. El jugador debe leer entre líneas.

FECHA: """ + today + """
PREGUNTA DEL DÍA: """ + pregunta + """

Crea el perfil con estas reglas:
1. Persona completamente ficticia pero muy verosímil — nombre español común, edad concreta, profesión real
2. Exactamente 4 datos de su vida cotidiana — específicos, concretos, con detalles que parezcan casuales pero no lo sean
3. Los datos deben contener pistas sutiles hacia la respuesta correcta, sin revelarla directamente
4. Las 4 opciones deben ser todas plausibles — ninguna absurda, pero una claramente más coherente con el perfil
5. La explicación debe revelar qué pistas del perfil apuntaban a la respuesta, de forma que el jugador piense "claro, tenía sentido"
6. Tono cercano, como si hablaras de alguien real que conoces

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "nombre": "Nombre y apellido español ficticio",
  "edad": 34,
  "profesion": "Profesión concreta",
  "datos": ["Dato 1 muy concreto", "Dato 2", "Dato 3", "Dato 4"],
  "pregunta": \"""" + pregunta + """\",
  "opciones": ["Opción A creíble", "Opción B creíble", "Opción C creíble", "Opción D creíble"],
  "correcta": 1,
  "explicacion": "Explicación de por qué esta respuesta tiene sentido con los datos del perfil. 2-3 frases."
}""" + _bloque_evitar(evitar)

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 900,
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


# ─────────────────────────────────────────────────────────────────────────────
# El Vestuario generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_vestuario(bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el creador de un quiz de fútbol para bares. Generas curiosidades absurdas pero 100% reales sobre jugadores de fútbol. El jugador que responde debe adivinar de quién es la curiosidad entre 3 jugadores.

FECHA: """ + today + """
SEED: """ + str(seed) + """

Crea exactamente 3 preguntas con estas reglas:

CURIOSIDADES:
1. Deben ser datos reales, verificables y sorprendentes — el típico "¿en serio?" del bar
2. Mezcla épocas: algún jugador histórico, alguno reciente, alguno actual
3. Evita los datos muy conocidos — nada de "Messi tiene X Balones de Oro"
4. Ejemplos del tono: "anotó un gol con la oreja", "tenía miedo a las palomas", "estudió medicina antes de ser profesional", "marcó en su propio funeral simbólico"

JUGADORES (3 opciones por pregunta):
- Uno correcto: el verdadero protagonista de la curiosidad
- Uno trampa: jugador de perfil similar (mismo país, posición o época) que hace dudar
- Uno señuelo: jugador famoso fácilmente descartable por ser de otro perfil

DIFICULTAD: mezcla — una pregunta fácil, una media, una difícil

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "preguntas": [
    {
      "curiosidad": "Texto de la curiosidad sin revelar el nombre del jugador. Usa 'este jugador' o 'un jugador'.",
      "emoji": "⚽",
      "jugadores": ["Jugador A", "Jugador B", "Jugador C"],
      "correcta": 0,
      "explicacion": "Confirmación del dato con contexto adicional curioso. 1-2 frases."
    },
    {
      "curiosidad": "...",
      "emoji": "🏆",
      "jugadores": ["Jugador A", "Jugador B", "Jugador C"],
      "correcta": 2,
      "explicacion": "..."
    },
    {
      "curiosidad": "...",
      "emoji": "👟",
      "jugadores": ["Jugador A", "Jugador B", "Jugador C"],
      "correcta": 1,
      "explicacion": "..."
    }
  ],
  "mensajes": {
    "0": "0 de 3 — Mejor pide otra ronda y olvida el fútbol. ⚽",
    "1": "1 de 3 — Algo sabes, pero el míster no te convoca. 😅",
    "2": "2 de 3 — Buen partido. Te llaman del banquillo. 👏",
    "3": "3 de 3 — Leyenda del vestuario. Nadie te discute. 🏆"
  }
}""" + _bloque_evitar(evitar)

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
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


# ─────────────────────────────────────────────────────────────────────────────
# La Sinopsis Rara generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_sinopsis(bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el creador de un juego de cine para bares. Describes películas famosas de forma absurda, literal y deliberadamente confusa. El jugador adivina de qué película se trata.

FECHA: """ + today + """
SEED: """ + str(seed) + """

INSTRUCCIONES — sigue este orden exacto:

PASO 1: Elige la película protagonista del día.
- Debe ser una película MUY conocida que casi todo el mundo haya visto
- Varía géneros y épocas según el SEED

PASO 2: Escribe la sinopsis SOLO de esa película.
- Descríbela de forma absurda, literal y sin contexto emocional
- Como si la explicara alguien que no entiende de cine
- No uses el título, nombres de personajes, actores ni lugares reconocibles
- Que provoque el "¡ostras, es verdad!" al revelar la respuesta
- 2-3 frases máximo

PASO 3: Crea las 4 opciones donde la película del PASO 1 es la correcta.
- Pon la película correcta en una posición aleatoria (0, 1, 2 o 3)
- Las otras 3: una del mismo género/director, una que encaje con algún detalle, un señuelo famoso
- La sinopsis del PASO 2 DEBE describir exactamente la película correcta del PASO 3

PASO 4: Escribe un dato curioso real sobre la película correcta.

Devuelve SOLO un objeto JSON válido, sin markdown, donde "correcta" es el índice (0-3) de la película que describes en "sinopsis":
{
  "sinopsis": "Descripción absurda de la película correcta. 2-3 frases.",
  "opciones": ["Película A", "Película B", "Película C", "Película D"],
  "correcta": 2,
  "año": 1994,
  "director": "Nombre del director",
  "dato_extra": "Dato curioso real sobre la película correcta. 1-2 frases."
}""" + _bloque_evitar(evitar)

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 800,
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


# ─────────────────────────────────────────────────────────────────────────────
# Muertes Absurdas generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_muertes(bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el narrador de un juego de curiosidades históricas para bares. Cada día presentas una muerte absurda pero REAL y documentada históricamente. El tono es irreverente pero respetuoso — morbo sano, nunca cruento ni gráfico.

FECHA: """ + today + """
SEED: """ + str(seed) + """

Crea la muerte absurda del día con estas reglas:
1. Debe ser un caso REAL y documentado históricamente (personajes históricos, casos célebres)
2. Lo absurdo está en las circunstancias, no en el sufrimiento — evita detalles cruentos o gráficos
3. Tono de anécdota de bar: sorprendente, con un punto de humor negro elegante
4. Incluye el año o época y el nombre real del protagonista
5. Nada de muertes recientes que puedan herir sensibilidades (mínimo 50 años de antigüedad)
6. La pregunta del juego: adivinar UN dato concreto de la historia entre 3 opciones
7. Ejemplos del tipo: Esquilo (águila que dejó caer una tortuga), Hans Steininger (su propia barba), Tycho Brahe (no quiso ir al baño en un banquete)

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "titulo": "Título con gancho (ej: 'El hombre al que mató su propia barba')",
  "historia": "La historia de la muerte absurda. 3-4 frases. Tono irreverente pero elegante. Incluye nombre y época.",
  "pregunta": "Pregunta sobre un detalle concreto de la historia",
  "opciones": ["Opción A", "Opción B", "Opción C"],
  "correcta": 1,
  "dato_extra": "Un dato adicional curioso real sobre el caso o la época. 1-2 frases."
}""" + _bloque_evitar(evitar)

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        json={'model': 'claude-sonnet-4-6', 'max_tokens': 900, 'messages': [{'role': 'user', 'content': prompt}]},
        timeout=60
    )
    data = response.json()
    if 'content' not in data:
        raise Exception(f"API error: {data.get('error', data)}")
    text = data['content'][0]['text'].strip().replace('```json', '').replace('```', '').strip()
    return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# La Letra Traducida generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_letra(bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el creador de un juego musical para bares. Coges una canción MUY famosa y traduces/parafraseas su letra al español de forma ultra literal, sin contexto y deliberadamente absurda, para que el jugador adivine de qué canción se trata.

FECHA: """ + today + """
SEED: """ + str(seed) + """

INSTRUCCIONES — sigue este orden exacto:

PASO 1: Elige una canción MUY conocida internacionalmente (de cualquier época, varía según SEED).

PASO 2: Describe su letra/estribillo de forma literal y absurda EN ESPAÑOL.
- NO uses el título ni el nombre del artista
- NO cites la letra textual en su idioma original (derechos de autor)
- Parafrasea la IDEA de la letra de forma literal y descontextualizada
- Tono gracioso: como si lo explicara un robot sin alma
- Ejemplo: para "Call Me Maybe" → "Una chica acaba de conocer a un chico y, aunque es muy pronto y resulta algo desesperado, le da su número y le insiste en que la llame quizás"

PASO 3: Crea 4 opciones donde la canción del PASO 1 es la correcta.
- Ponla en posición aleatoria (0-3)
- Las otras 3: del mismo género/época o que encajen con algún detalle
- IMPORTANTE: la paráfrasis del PASO 2 debe corresponder EXACTAMENTE a la canción correcta del PASO 3

PASO 4: Dato curioso real sobre la canción.

Devuelve SOLO un objeto JSON válido, sin markdown, donde "correcta" es el índice (0-3) de la canción parafraseada:
{
  "parafrasis": "La paráfrasis literal y absurda de la letra. 2-3 frases. Sin citar letra original.",
  "opciones": ["Canción - Artista", "Canción - Artista", "Canción - Artista", "Canción - Artista"],
  "correcta": 2,
  "año": 2012,
  "dato_extra": "Dato curioso real sobre la canción correcta. 1-2 frases."
}""" + _bloque_evitar(evitar)

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        json={'model': 'claude-sonnet-4-6', 'max_tokens': 900, 'messages': [{'role': 'user', 'content': prompt}]},
        timeout=60
    )
    data = response.json()
    if 'content' not in data:
        raise Exception(f"API error: {data.get('error', data)}")
    text = data['content'][0]['text'].strip().replace('```json', '').replace('```', '').strip()
    return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# El Mismo Pensamiento generator (solo genera la categoría del día)
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIAS_PENSAMIENTO_FALLBACK = [
    "una fruta amarilla", "un país de Europa", "un animal de la selva",
    "una marca de coche", "un color que no sea primario", "un postre típico español",
    "una película de los 90", "un instrumento musical", "una profesión peligrosa",
    "algo que encuentras en una cocina", "un superhéroe", "una ciudad con playa",
]

def generate_pensamiento(bar_slug):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el creador de un juego social para bares llamado "El Mismo Pensamiento". Cada día propones una categoría sencilla y todos los jugadores escriben lo primero que se les ocurre. Ganan si coinciden con la mayoría.

FECHA: """ + today + """
SEED: """ + str(seed) + """

Crea la categoría del día con estas reglas:
1. Debe ser sencilla, universal y con respuesta espontánea — algo que cualquiera responda en 2 segundos
2. Que tenga varias respuestas posibles pero algunas claramente más comunes (eso es lo divertido)
3. Nada ambiguo ni que requiera conocimiento especializado
4. Tono cercano y cotidiano
5. Ejemplos del tipo: "una fruta amarilla", "un país de Europa", "algo que llevarías a una isla desierta"

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "categoria": "La categoría del día (ej: 'una fruta amarilla')",
  "instruccion": "Escribe lo primero que se te ocurra. Ganas si coincides con la mayoría.",
  "pista": "Una frase corta y divertida sobre el reto de hoy"
}"""

    try:
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
            json={'model': 'claude-sonnet-4-6', 'max_tokens': 400, 'messages': [{'role': 'user', 'content': prompt}]},
            timeout=60
        )
        data = response.json()
        if 'content' not in data:
            raise Exception("API error")
        text = data['content'][0]['text'].strip().replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception:
        cat = CATEGORIAS_PENSAMIENTO_FALLBACK[seed % len(CATEGORIAS_PENSAMIENTO_FALLBACK)]
        return {"categoria": cat, "instruccion": "Escribe lo primero que se te ocurra. Ganas si coincides con la mayoría.", "pista": "Piensa rápido, piensa como los demás."}


# ─────────────────────────────────────────────────────────────────────────────
# El Poema generator (personalizado, bajo demanda)
# ─────────────────────────────────────────────────────────────────────────────

def generate_poema(nombre, sobre, nombre_objeto, tono, nivel):
    api_key = os.environ.get('ANTHROPIC_API_KEY')

    nivel_instr = {
        'peques': "Tono para NIÑOS: completamente inocente, tierno y divertido. Temática infantil (amistad, mascotas, familia, juegos). Lenguaje sencillo y alegre. NUNCA contenido romántico-adulto, referencias sexuales, alcohol, violencia ni nada inapropiado para un menor. Es OBLIGATORIO que sea 100% apto para niños.",
        'normal': "Tono apto para todos los públicos: puede ser romántico, divertido o emotivo, pero siempre elegante y sin contenido explícito ni vulgar.",
        'gamberro': "Tono gamberro y atrevido: humor pícaro, exagerado y desvergonzado para reírse entre amigos. Puede haber doble sentido y bromas subidas de tono, pero NUNCA contenido sexual explícito, insultos ofensivos, ni nada que humille de verdad. Gracioso, no hiriente.",
    }.get(nivel, "Tono apto para todos los públicos.")

    sobre_instr = {
        'mi': f"un poema sobre {nombre} (la propia persona que lo pide)",
        'especial': f"un poema dedicado a {nombre_objeto}, una persona especial para {nombre}",
        'amigo': f"un poema sobre {nombre_objeto}, gran amigo/a de {nombre}",
        'odio': f"un poema humorístico sobre algo que {nombre} odia: {nombre_objeto}",
        'dia': f"un poema sobre cómo ha sido el día de {nombre}",
    }.get(sobre, f"un poema sobre {nombre}")

    tono_instr = {
        'romantico': "estilo romántico y emotivo",
        'divertido': "estilo divertido y desenfadado",
        'epico': "estilo épico y grandilocuente, como una gran gesta",
        'melancolico': "estilo melancólico y poético",
        'absurdo': "estilo absurdo y surrealista",
    }.get(tono, "estilo divertido")

    prompt = f"""Eres un poeta de bar ingenioso. Escribe {sobre_instr}, en {tono_instr}.

NIVEL DE CONTENIDO: {nivel_instr}

REGLAS:
1. El poema debe tener entre 4 y 8 versos
2. Que rime de forma natural (no forzada)
3. Personalizado: usa los nombres que te he dado
4. Que tenga gracia, encanto o emoción según el tono pedido
5. En español
6. Devuelve SOLO el poema, sin título, sin comillas, sin explicaciones. Cada verso en su línea."""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        json={'model': 'claude-sonnet-4-6', 'max_tokens': 500, 'messages': [{'role': 'user', 'content': prompt}]},
        timeout=60
    )
    data = response.json()
    if 'content' not in data:
        raise Exception(f"API error: {data.get('error', data)}")
    return {"poema": data['content'][0]['text'].strip()}


# ─────────────────────────────────────────────────────────────────────────────
# Mente Ágil generator (psicotécnico, 3 preguntas)
# ─────────────────────────────────────────────────────────────────────────────

def generate_menteagil(bar_slug):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el creador de un test psicotécnico para bares, del estilo de las pruebas de acceso y oposiciones. Generas 3 ejercicios de lógica con dificultad progresiva.

FECHA: """ + today + """
SEED: """ + str(seed) + """

Crea 3 preguntas psicotécnicas con estas reglas:
1. Variedad de tipos: series numéricas, series de letras, analogías, lógica deductiva, matrices, dominó/numéricas con varias operaciones
2. NIVEL DE DIFICULTAD — IMPORTANTE, sé exigente como en una oposición real:
   - Pregunta 1 (media): no trivial. Requiere identificar un patrón con 2 operaciones combinadas. NO uses progresiones obvias como "2,4,8,16". Ejemplo de este nivel: "3, 5, 9, 17, 33, ?" (x2-1) o "Si A=1, C=9, E=25... ¿cuánto vale G?" (posición al cuadrado).
   - Pregunta 2 (difícil): combina dos reglas o requiere razonamiento abstracto. Ejemplo: series alternas (dos series intercaladas), analogías con doble relación, silogismos con negaciones.
   - Pregunta 3 (muy difícil): nivel oposición exigente. Patrones no evidentes, varios pasos lógicos, o relaciones que requieren descartar opciones. Que haga pensar de verdad incluso a alguien hábil.
3. Cada una con 4 opciones donde solo una es correcta, y los distractores deben ser plausibles (resultados de errores comunes de razonamiento)
4. Resolubles mentalmente pero NO obvias — el reto es que piques, no que aciertes a la primera
5. La explicación debe enseñar el razonamiento de forma clara y breve
6. Rigor absoluto: verifica que la respuesta correcta es realmente correcta y única

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "preguntas": [
    {
      "tipo": "Serie numérica",
      "enunciado": "El ejercicio. Claro y conciso.",
      "opciones": ["A", "B", "C", "D"],
      "correcta": 0,
      "explicacion": "El razonamiento para llegar a la solución. 1-2 frases."
    },
    { "tipo": "Analogía", "enunciado": "...", "opciones": ["A","B","C","D"], "correcta": 2, "explicacion": "..." },
    { "tipo": "Lógica", "enunciado": "...", "opciones": ["A","B","C","D"], "correcta": 1, "explicacion": "..." }
  ],
  "mensajes": {
    "0": "0 de 3 — Hoy la mente está de resaca. 😴",
    "1": "1 de 3 — Algo despiertas. Sigue entrenando. 🧠",
    "2": "2 de 3 — Buen nivel. Casi opositor. 💪",
    "3": "3 de 3 — Mente prodigiosa. Te fichan. 🏆"
  }
}"""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        json={'model': 'claude-sonnet-4-6', 'max_tokens': 1100, 'messages': [{'role': 'user', 'content': prompt}]},
        timeout=60
    )
    data = response.json()
    if 'content' not in data:
        raise Exception(f"API error: {data.get('error', data)}")
    text = data['content'][0]['text'].strip().replace('```json', '').replace('```', '').strip()
    return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# ¿Tú la has leído? generator (Constitución — verdad o trampa)
# ─────────────────────────────────────────────────────────────────────────────

def generate_constitucion(bar_slug):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el creador de un juego sobre la Constitución Española de 1978 para bares. Presentas una afirmación sobre la Constitución y el jugador debe decir si es VERDADERA (real) o FALSA (inventada pero plausible). Tono divertido, de complicidad con quien estudia oposiciones o quien presume de saber.

FECHA: """ + today + """
SEED: """ + str(seed) + """

Crea la afirmación del día con estas reglas:
1. Si es VERDADERA: un dato real y verificable de la Constitución Española de 1978 (artículos, derechos, estructura, datos históricos)
2. Si es FALSA: algo inventado pero MUY plausible — que haga dudar a cualquiera
3. Alterna entre verdaderas y falsas según el SEED (no siempre el mismo tipo)
4. Rigor absoluto: si dices que es verdad, debe serlo de verdad
5. La explicación debe aclarar el dato real con tono didáctico pero ameno
6. Incluye el número de artículo cuando sea relevante

Devuelve SOLO un objeto JSON válido, sin markdown:
{
  "afirmacion": "La afirmación sobre la Constitución que el jugador debe juzgar.",
  "es_verdadera": true,
  "explicacion": "La aclaración del dato real, con tono ameno. 2-3 frases.",
  "dato_extra": "Una curiosidad adicional real sobre la Constitución. 1 frase."
}"""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        json={'model': 'claude-sonnet-4-6', 'max_tokens': 700, 'messages': [{'role': 'user', 'content': prompt}]},
        timeout=60
    )
    data = response.json()
    if 'content' not in data:
        raise Exception(f"API error: {data.get('error', data)}")
    text = data['content'][0]['text'].strip().replace('```json', '').replace('```', '').strip()
    return json.loads(text)
