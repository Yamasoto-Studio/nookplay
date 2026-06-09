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

def generate_dilema(bar_name, bar_slug):
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
}"""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        json={
            'model': 'claude-sonnet-4-5',
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
            'model': 'claude-sonnet-4-5',
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
            'model': 'claude-sonnet-4-5',
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
