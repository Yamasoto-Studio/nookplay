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
    {
        "puzzle":   [[1,0,0,2],[0,2,1,0],[2,0,0,1],[0,1,2,0]],
        "solution": [[1,3,4,2],[4,2,1,3],[2,4,3,1],[3,1,2,4]],
    },
    {
        "puzzle":   [[0,1,0,3],[3,0,2,0],[0,4,0,2],[2,0,3,0]],
        "solution": [[4,1,2,3],[3,2,1,4],[1,4,3,2],[2,3,4,1]],
    },
    {
        "puzzle":   [[2,0,1,0],[0,4,0,3],[3,0,4,0],[0,1,0,2]],
        "solution": [[2,3,1,4],[1,4,2,3],[3,2,4,1],[4,1,3,2]],
    },
    {
        "puzzle":   [[0,2,0,4],[1,0,3,0],[0,3,0,1],[4,0,2,0]],
        "solution": [[3,2,1,4],[1,4,3,2],[2,3,4,1],[4,1,2,3]],
    },
    {
        "puzzle":   [[1,0,0,4],[0,3,1,0],[0,1,4,0],[4,0,0,1]],
        "solution": [[1,2,3,4],[4,3,1,2],[2,1,4,3],[4,2,3,1]],
    },
    {
        "puzzle":   [[0,4,0,2],[3,0,4,0],[0,2,0,3],[4,0,1,0]],
        "solution": [[1,4,3,2],[3,2,4,1],[2,1,2,3],[4,3,1,2]],
    },
    {
        "puzzle":   [[3,0,2,0],[0,1,0,4],[4,0,1,0],[0,2,0,3]],
        "solution": [[3,4,2,1],[2,1,3,4],[4,3,1,2],[1,2,4,3]],
    },
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
