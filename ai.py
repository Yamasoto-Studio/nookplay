import requests
import json
import re
import time
from datetime import date
import os
import hashlib


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de robustez IA: parseo tolerante + llamada con reintento
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ia_json(text):
    """Parsea JSON de una respuesta de IA de forma tolerante.

    1. Limpia fences de markdown (```json ... ```).
    2. Intenta json.loads normal.
    3. Si falla, intenta extraer el primer objeto {...} del texto.
    4. Si sigue fallando, intenta reparar truncamiento (cerrar comillas/llaves).
    Lanza json.JSONDecodeError si todo falla.
    """
    if text is None:
        raise ValueError("Respuesta IA vacía (None)")

    t = text.strip()
    t = t.replace('```json', '').replace('```', '').strip()

    # Intento 1: directo
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass

    # Intento 2: extraer el primer bloque {...} más externo
    inicio = t.find('{')
    fin = t.rfind('}')
    if inicio != -1 and fin != -1 and fin > inicio:
        candidato = t[inicio:fin + 1]
        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            t = t[inicio:]  # quedarnos desde la primera llave para reparar

    # Intento 3: reparar truncamiento (típico "Unterminated string")
    reparado = _reparar_json_truncado(t)
    if reparado is not None:
        return json.loads(reparado)

    # Si nada funcionó, relanzar para que el caller lo capture
    return json.loads(t)


def _reparar_json_truncado(t):
    """Intenta cerrar un JSON cortado a media respuesta.

    Cierra una comilla abierta si la hay, y añade las llaves/corchetes
    que falten según el balance. Devuelve el string reparado o None.
    """
    if not t or '{' not in t:
        return None

    # Contar comillas no escapadas para saber si hay un string abierto
    en_string = False
    escapado = False
    pila = []  # llaves/corchetes abiertos
    for ch in t:
        if escapado:
            escapado = False
            continue
        if ch == '\\':
            escapado = True
            continue
        if ch == '"':
            en_string = not en_string
            continue
        if en_string:
            continue
        if ch in '{[':
            pila.append(ch)
        elif ch == '}':
            if pila and pila[-1] == '{':
                pila.pop()
        elif ch == ']':
            if pila and pila[-1] == '[':
                pila.pop()

    reparado = t
    # Cerrar string abierto
    if en_string:
        reparado += '"'
    # Quitar una posible coma colgante antes de cerrar
    reparado = re.sub(r',\s*$', '', reparado.rstrip())
    # Cerrar contenedores pendientes en orden inverso
    for ch in reversed(pila):
        reparado += '}' if ch == '{' else ']'

    try:
        json.loads(reparado)
        return reparado
    except json.JSONDecodeError:
        return None


_SISTEMA_NOOKPLAY = (
    "Eres el generador de contenido de Nookplay, juegos para clientes de bares y cafeterias. "
    "Reglas transversales que cumples SIEMPRE, en todos los juegos: "
    "(1) Contenido NEUTRO e inclusivo respecto al genero: no asumas el genero del jugador ni de los protagonistas; "
    "evita estereotipos de hombre/mujer; cuando puedas, usa lugares, objetos, animales, naturaleza, inventos y obras en vez de personas concretas marcadas por genero; "
    "usa lenguaje que valga para cualquier persona. "
    "(2) Nada ofensivo, ni politico-partidista, ni morboso, ni sexual; tono divertido y de sobremesa. "
    "(3) Responde SIEMPRE en espanol. "
    "(4) Devuelve EXACTAMENTE el formato que se te pida (JSON valido sin markdown cuando se solicite)."
)


def _post_ia(prompt, max_tokens, api_key, reintentos=2, modelo='claude-sonnet-4-6', event_theme=''):
    """Llama a la API de Anthropic y devuelve el JSON parseado de forma robusta.

    Reintenta ante fallos de red, errores de API o JSON no parseable.
    Lanza Exception con detalle si agota los reintentos.
    Aplica un mensaje de sistema comun (_SISTEMA_NOOKPLAY) con reglas
    transversales (contenido neutro/inclusivo, español, sin contenido sensible).

    Si event_theme está definido (espacios con space_kind='evento'), antepone un
    bloque de contexto temático al prompt para ambientar el contenido en el evento.
    Es opcional y por defecto vacío: cualquier generador que no lo pase se comporta igual.
    """
    if event_theme:
        prompt = _bloque_tematico(event_theme) + "\n" + prompt
    ultimo_error = None
    for intento in range(reintentos + 1):
        try:
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json'
                },
                json={
                    'model': modelo,
                    'max_tokens': max_tokens,
                    'system': _SISTEMA_NOOKPLAY,
                    'messages': [{'role': 'user', 'content': prompt}]
                },
                timeout=60
            )
            data = response.json()
            if 'content' not in data:
                raise Exception(f"API error: {data.get('error', data)}")
            text = data['content'][0]['text']
            return _parse_ia_json(text)
        except Exception as e:
            ultimo_error = e
            if intento < reintentos:
                time.sleep(1.5 * (intento + 1))  # backoff suave
                continue
            raise Exception(f"Generación IA falló tras {reintentos + 1} intentos: {ultimo_error}")


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
        'space_kind':   bar_row.get('space_kind', 'local'),
        'event_theme':  bar_row.get('event_theme', ''),
    }


def _bloque_tematico(event_theme):
    """Bloque de contexto temático para eventos. Se antepone al prompt de cualquier
    juego IA cuando el espacio es un evento con temática definida. Devuelve '' si no hay tema."""
    if not event_theme or not event_theme.strip():
        return ""
    return f"""
CONTEXTO TEMÁTICO DEL EVENTO (MUY IMPORTANTE): Este contenido se juega en un evento con esta temática:
«{event_theme.strip()}»
Ambienta el juego en ese universo: usa sus referencias, su público y su tono. El contenido debe sentirse hecho a medida para ese evento, no genérico. Mantén el rigor y la jugabilidad; solo cambia la ambientación.
"""

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

    return _post_ia(prompt, 1500, api_key)


# ─────────────────────────────────────────────────────────────────────────────
# El Impostor generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_impostor(bar_name, bar_slug, evitar=None):
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

    return _post_ia(prompt + _bloque_evitar(evitar), 1000, api_key)


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

    return _post_ia(prompt, 800, api_key)


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

def generate_conexiones(bar_name, bar_slug, evitar=None):
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

    result = _post_ia(prompt + _bloque_evitar(evitar), 800, api_key)
    
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

    return _post_ia(prompt, 2500, api_key)


# ─────────────────────────────────────────────────────────────────────────────
# ¿Dónde en el mundo? generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_donde(bar_slug, evitar=None):
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

    result = _post_ia(prompt + _bloque_evitar(evitar), 1000, api_key)

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
# El Orden — ordena 5 elementos por un criterio (tipo Timeline, más ágil)
# Sin IA — banco de rondas curadas que rotan por día. 0 tokens.
#
# Cada ronda:
#   "pregunta": enunciado mostrado al jugador
#   "criterio": de qué va el orden (cronología, tamaño, etc.)
#   "arriba" / "abajo": etiquetas de los extremos de la lista
#   "items": lista de {"texto", "valor" (num para ordenar ASC = arriba), "dato" (lo que se revela)}
#
# El orden correcto = items ordenados por "valor" ascendente (menor arriba).
# generate_orden() devuelve también un "barajado" determinista que nunca coincide
# con el orden correcto, para que el front lo muestre desordenado de salida.
# ─────────────────────────────────────────────────────────────────────────────

ORDEN_RONDAS = [
    # ── CRONOLOGÍA (eventos / inventos) ─────────────────────────────────────
    {
        "pregunta": "Ordena estos inventos del más antiguo al más reciente",
        "criterio": "Año de invención",
        "arriba": "Más antiguo", "abajo": "Más reciente",
        "items": [
            {"texto": "La imprenta de Gutenberg", "valor": 1440, "dato": "≈1440"},
            {"texto": "El teléfono", "valor": 1876, "dato": "1876"},
            {"texto": "El avión de los Wright", "valor": 1903, "dato": "1903"},
            {"texto": "La televisión", "valor": 1927, "dato": "1927"},
            {"texto": "Internet (ARPANET)", "valor": 1969, "dato": "1969"},
        ],
    },
    {
        "pregunta": "Ordena estos hitos espaciales del primero al último",
        "criterio": "Año del acontecimiento",
        "arriba": "Primero", "abajo": "Último",
        "items": [
            {"texto": "Sputnik, primer satélite", "valor": 1957, "dato": "1957"},
            {"texto": "Yuri Gagarin en el espacio", "valor": 1961, "dato": "1961"},
            {"texto": "Llegada a la Luna (Apolo 11)", "valor": 1969, "dato": "1969"},
            {"texto": "Estación Espacial Internacional", "valor": 1998, "dato": "1998"},
            {"texto": "Aterrizaje del rover Perseverance", "valor": 2021, "dato": "2021"},
        ],
    },
    {
        "pregunta": "Ordena estos acontecimientos históricos del más antiguo al más reciente",
        "criterio": "Año",
        "arriba": "Más antiguo", "abajo": "Más reciente",
        "items": [
            {"texto": "Caída del Imperio Romano de Occidente", "valor": 476, "dato": "476 d.C."},
            {"texto": "Descubrimiento de América", "valor": 1492, "dato": "1492"},
            {"texto": "Revolución Francesa", "valor": 1789, "dato": "1789"},
            {"texto": "Primera Guerra Mundial", "valor": 1914, "dato": "1914"},
            {"texto": "Caída del Muro de Berlín", "valor": 1989, "dato": "1989"},
        ],
    },
    {
        "pregunta": "Ordena estas apps según cuándo se lanzaron",
        "criterio": "Año de lanzamiento",
        "arriba": "Más antigua", "abajo": "Más reciente",
        "items": [
            {"texto": "YouTube", "valor": 2005, "dato": "2005"},
            {"texto": "WhatsApp", "valor": 2009, "dato": "2009"},
            {"texto": "Instagram", "valor": 2010, "dato": "2010"},
            {"texto": "TikTok (internacional)", "valor": 2017, "dato": "2017"},
            {"texto": "ChatGPT", "valor": 2022, "dato": "2022"},
        ],
    },
    {
        "pregunta": "Ordena estas civilizaciones por antigüedad de su apogeo",
        "criterio": "Época",
        "arriba": "Más antigua", "abajo": "Más reciente",
        "items": [
            {"texto": "Antiguo Egipto (pirámides)", "valor": -2560, "dato": "≈2560 a.C."},
            {"texto": "Grecia clásica", "valor": -450, "dato": "≈450 a.C."},
            {"texto": "Imperio Romano", "valor": 100, "dato": "siglo I-II"},
            {"texto": "Imperio Maya clásico", "valor": 600, "dato": "≈600 d.C."},
            {"texto": "Imperio Azteca", "valor": 1450, "dato": "≈1450"},
        ],
    },

    # ── TAMAÑO / SUPERFICIE ─────────────────────────────────────────────────
    {
        "pregunta": "Ordena estos países del más pequeño al más grande",
        "criterio": "Superficie",
        "arriba": "Más pequeño", "abajo": "Más grande",
        "items": [
            {"texto": "Portugal", "valor": 92212, "dato": "92.000 km²"},
            {"texto": "España", "valor": 505990, "dato": "506.000 km²"},
            {"texto": "Francia", "valor": 551695, "dato": "552.000 km²"},
            {"texto": "México", "valor": 1964375, "dato": "1,96 M km²"},
            {"texto": "Rusia", "valor": 17098242, "dato": "17,1 M km²"},
        ],
    },
    {
        "pregunta": "Ordena estos animales del más pequeño al más grande",
        "criterio": "Tamaño / longitud",
        "arriba": "Más pequeño", "abajo": "Más grande",
        "items": [
            {"texto": "Abeja", "valor": 1.5, "dato": "≈1,5 cm"},
            {"texto": "Gato doméstico", "valor": 46, "dato": "≈46 cm"},
            {"texto": "Ser humano", "valor": 170, "dato": "≈1,7 m"},
            {"texto": "Jirafa", "valor": 500, "dato": "≈5 m"},
            {"texto": "Ballena azul", "valor": 2500, "dato": "≈25 m"},
        ],
    },
    {
        "pregunta": "Ordena estos planetas del más pequeño al más grande",
        "criterio": "Diámetro",
        "arriba": "Más pequeño", "abajo": "Más grande",
        "items": [
            {"texto": "Mercurio", "valor": 4879, "dato": "4.879 km"},
            {"texto": "Marte", "valor": 6779, "dato": "6.779 km"},
            {"texto": "La Tierra", "valor": 12742, "dato": "12.742 km"},
            {"texto": "Saturno", "valor": 116460, "dato": "116.460 km"},
            {"texto": "Júpiter", "valor": 139820, "dato": "139.820 km"},
        ],
    },

    # ── ALTURA ──────────────────────────────────────────────────────────────
    {
        "pregunta": "Ordena estos edificios y monumentos del más bajo al más alto",
        "criterio": "Altura",
        "arriba": "Más bajo", "abajo": "Más alto",
        "items": [
            {"texto": "Estatua de la Libertad", "valor": 93, "dato": "93 m"},
            {"texto": "Big Ben", "valor": 96, "dato": "96 m"},
            {"texto": "Torre Eiffel", "valor": 330, "dato": "330 m"},
            {"texto": "Empire State Building", "valor": 443, "dato": "443 m"},
            {"texto": "Burj Khalifa (Dubái)", "valor": 828, "dato": "828 m"},
        ],
    },
    {
        "pregunta": "Ordena estas montañas de la más baja a la más alta",
        "criterio": "Altitud",
        "arriba": "Más baja", "abajo": "Más alta",
        "items": [
            {"texto": "Teide (España)", "valor": 3715, "dato": "3.715 m"},
            {"texto": "Mont Blanc (Alpes)", "valor": 4808, "dato": "4.808 m"},
            {"texto": "Kilimanjaro (África)", "valor": 5895, "dato": "5.895 m"},
            {"texto": "Aconcagua (América)", "valor": 6961, "dato": "6.961 m"},
            {"texto": "Everest (Himalaya)", "valor": 8849, "dato": "8.849 m"},
        ],
    },

    # ── POBLACIÓN ───────────────────────────────────────────────────────────
    {
        "pregunta": "Ordena estas ciudades por población (de menos a más habitantes)",
        "criterio": "Población del área metropolitana",
        "arriba": "Menos gente", "abajo": "Más gente",
        "items": [
            {"texto": "Barcelona", "valor": 5600000, "dato": "≈5,6 M"},
            {"texto": "Madrid", "valor": 6700000, "dato": "≈6,7 M"},
            {"texto": "Londres", "valor": 9500000, "dato": "≈9,5 M"},
            {"texto": "Ciudad de México", "valor": 22000000, "dato": "≈22 M"},
            {"texto": "Tokio", "valor": 37000000, "dato": "≈37 M"},
        ],
    },
    {
        "pregunta": "Ordena estos países por población (de menos a más)",
        "criterio": "Habitantes",
        "arriba": "Menos gente", "abajo": "Más gente",
        "items": [
            {"texto": "Portugal", "valor": 10300000, "dato": "≈10,3 M"},
            {"texto": "España", "valor": 48000000, "dato": "≈48 M"},
            {"texto": "México", "valor": 129000000, "dato": "≈129 M"},
            {"texto": "Estados Unidos", "valor": 335000000, "dato": "≈335 M"},
            {"texto": "India", "valor": 1430000000, "dato": "≈1.430 M"},
        ],
    },

    # ── VELOCIDAD ───────────────────────────────────────────────────────────
    {
        "pregunta": "Ordena por velocidad: del más lento al más rápido",
        "criterio": "Velocidad punta",
        "arriba": "Más lento", "abajo": "Más rápido",
        "items": [
            {"texto": "Usain Bolt corriendo", "valor": 37, "dato": "≈37 km/h"},
            {"texto": "Galgo", "valor": 70, "dato": "≈70 km/h"},
            {"texto": "Guepardo", "valor": 110, "dato": "≈110 km/h"},
            {"texto": "AVE (tren español)", "valor": 310, "dato": "≈310 km/h"},
            {"texto": "Avión comercial", "valor": 900, "dato": "≈900 km/h"},
        ],
    },

    # ── DISTANCIA ───────────────────────────────────────────────────────────
    {
        "pregunta": "Ordena estos planetas por distancia al Sol (del más cercano al más lejano)",
        "criterio": "Distancia media al Sol",
        "arriba": "Más cerca", "abajo": "Más lejos",
        "items": [
            {"texto": "Mercurio", "valor": 58, "dato": "58 M km"},
            {"texto": "Venus", "valor": 108, "dato": "108 M km"},
            {"texto": "La Tierra", "valor": 150, "dato": "150 M km"},
            {"texto": "Marte", "valor": 228, "dato": "228 M km"},
            {"texto": "Júpiter", "valor": 778, "dato": "778 M km"},
        ],
    },

    # ── PRECIO / VALOR ──────────────────────────────────────────────────────
    {
        "pregunta": "Ordena por valor: ¿qué fue más caro?",
        "criterio": "Precio aproximado",
        "arriba": "Más barato", "abajo": "Más caro",
        "items": [
            {"texto": "Un iPhone de gama alta", "valor": 1500, "dato": "≈1.500 €"},
            {"texto": "Un coche utilitario nuevo", "valor": 22000, "dato": "≈22.000 €"},
            {"texto": "Un piso medio en España", "valor": 200000, "dato": "≈200.000 €"},
            {"texto": "Un Ferrari deportivo", "valor": 300000, "dato": "≈300.000 €"},
            {"texto": "Un anuncio en la Super Bowl (30s)", "valor": 6500000, "dato": "≈6,5 M €"},
        ],
    },

    # ── DURACIÓN ────────────────────────────────────────────────────────────
    {
        "pregunta": "Ordena por duración: de lo más corto a lo más largo",
        "criterio": "Duración media",
        "arriba": "Más corto", "abajo": "Más largo",
        "items": [
            {"texto": "Una canción pop", "valor": 3.5, "dato": "≈3,5 min"},
            {"texto": "Un episodio de sitcom", "valor": 22, "dato": "≈22 min"},
            {"texto": "Un partido de fútbol", "valor": 105, "dato": "≈105 min"},
            {"texto": "Una película media", "valor": 120, "dato": "≈120 min"},
            {"texto": "Un vuelo Madrid–Nueva York", "valor": 480, "dato": "≈8 h"},
        ],
    },

    # ── PESO ────────────────────────────────────────────────────────────────
    {
        "pregunta": "Ordena estos animales del más ligero al más pesado",
        "criterio": "Peso medio",
        "arriba": "Más ligero", "abajo": "Más pesado",
        "items": [
            {"texto": "Gato doméstico", "valor": 4, "dato": "≈4 kg"},
            {"texto": "Persona adulta", "valor": 70, "dato": "≈70 kg"},
            {"texto": "Caballo", "valor": 500, "dato": "≈500 kg"},
            {"texto": "Elefante africano", "valor": 6000, "dato": "≈6.000 kg"},
            {"texto": "Ballena azul", "valor": 150000, "dato": "≈150.000 kg"},
        ],
    },

    # ── TEMPERATURA ─────────────────────────────────────────────────────────
    {
        "pregunta": "Ordena de menor a mayor temperatura",
        "criterio": "Temperatura aproximada",
        "arriba": "Más frío", "abajo": "Más caliente",
        "items": [
            {"texto": "Un congelador doméstico", "valor": -18, "dato": "≈-18 ºC"},
            {"texto": "Un día de primavera", "valor": 20, "dato": "≈20 ºC"},
            {"texto": "El cuerpo humano", "valor": 37, "dato": "37 ºC"},
            {"texto": "Agua hirviendo", "valor": 100, "dato": "100 ºC"},
            {"texto": "La lava de un volcán", "valor": 1100, "dato": "≈1.100 ºC"},
        ],
    },

    # ── CRONOLOGÍA CULTURA / ESPAÑA ─────────────────────────────────────────
    {
        "pregunta": "Ordena estos hitos de España del más antiguo al más reciente",
        "criterio": "Año",
        "arriba": "Más antiguo", "abajo": "Más reciente",
        "items": [
            {"texto": "Constitución española", "valor": 1978, "dato": "1978"},
            {"texto": "España entra en la UE (CEE)", "valor": 1986, "dato": "1986"},
            {"texto": "Juegos Olímpicos de Barcelona", "valor": 1992, "dato": "1992"},
            {"texto": "Llega el euro a España", "valor": 2002, "dato": "2002"},
            {"texto": "España gana el Mundial de fútbol", "valor": 2010, "dato": "2010"},
        ],
    },
    {
        "pregunta": "Ordena a estos pintores por orden de nacimiento",
        "criterio": "Año de nacimiento",
        "arriba": "Nació antes", "abajo": "Nació después",
        "items": [
            {"texto": "Velázquez", "valor": 1599, "dato": "1599"},
            {"texto": "Goya", "valor": 1746, "dato": "1746"},
            {"texto": "Picasso", "valor": 1881, "dato": "1881"},
            {"texto": "Dalí", "valor": 1904, "dato": "1904"},
            {"texto": "Frida Kahlo", "valor": 1907, "dato": "1907"},
        ],
    },

    # ── CRONOLOGÍA CINE ─────────────────────────────────────────────────────
    {
        "pregunta": "Ordena estas películas por orden de estreno",
        "criterio": "Año de estreno",
        "arriba": "Más antigua", "abajo": "Más reciente",
        "items": [
            {"texto": "El Padrino", "valor": 1972, "dato": "1972"},
            {"texto": "Star Wars (Episodio IV)", "valor": 1977, "dato": "1977"},
            {"texto": "Titanic", "valor": 1997, "dato": "1997"},
            {"texto": "El Señor de los Anillos (1ª)", "valor": 2001, "dato": "2001"},
            {"texto": "Avatar", "valor": 2009, "dato": "2009"},
        ],
    },

    # ── CANTIDAD ────────────────────────────────────────────────────────────
    {
        "pregunta": "Ordena estas cosas por cantidad de patas",
        "criterio": "Número de patas",
        "arriba": "Menos patas", "abajo": "Más patas",
        "items": [
            {"texto": "Una persona", "valor": 2, "dato": "2"},
            {"texto": "Un perro", "valor": 4, "dato": "4"},
            {"texto": "Un insecto", "valor": 6, "dato": "6"},
            {"texto": "Una araña", "valor": 8, "dato": "8"},
            {"texto": "Un ciempiés común", "valor": 30, "dato": "≈30"},
        ],
    },
]


def generate_orden(bar_slug):
    seed = get_day_seed(bar_slug)
    idx = seed % len(ORDEN_RONDAS)
    ronda = ORDEN_RONDAS[idx]
    n = len(ronda["items"])
    # Orden correcto: índices de items ordenados por "valor" ascendente (menor arriba)
    orden_correcto = sorted(range(n), key=lambda i: ronda["items"][i]["valor"])
    # Barajado inicial determinista que NO coincida con el orden correcto
    rot = (seed % (n - 1)) + 1
    barajado = list(range(n))
    barajado = barajado[rot:] + barajado[:rot]
    s2 = (seed // 7) % n
    s3 = (seed // 13) % n
    barajado[s2], barajado[s3] = barajado[s3], barajado[s2]
    if barajado == orden_correcto:
        barajado = barajado[::-1]
    return {
        "pregunta": ronda["pregunta"],
        "criterio": ronda["criterio"],
        "arriba": ronda["arriba"],
        "abajo": ronda["abajo"],
        "items": ronda["items"],
        "orden_correcto": orden_correcto,
        "barajado": barajado,
    }


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

    result = _post_ia(prompt, 1200, api_key)
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

    return _post_ia(prompt, 800, api_key)


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

    return _post_ia(prompt, 900, api_key)


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

    return _post_ia(prompt, 1200, api_key)


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

    return _post_ia(prompt, 800, api_key)


# ─────────────────────────────────────────────────────────────────────────────
# NUEVOS_JUEGOS_AQUI
# ─────────────────────────────────────────────────────────────────────────────

def generate_titular(bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el creador de un juego para bares llamado "El Titular Imposible". Muestras un titular de noticia surrealista y el jugador decide si es REAL (ocurrio de verdad) o FALSO (inventado).

FECHA: """ + today + """
SEED: """ + str(seed) + """

INSTRUCCIONES - sigue este orden:

PASO 1: Decide al azar (segun el SEED) si el titular del dia sera REAL o FALSO.

PASO 2A - Si es REAL:
- Elige una noticia real, verificable y genuinamente sorprendente o absurda (sucesos curiosos, estudios cientificos raros, records insolitos, hechos historicos extranos).
- Redacta el titular como apareceria en un periodico, sin exagerar ni inventar.
- En "explicacion" cuenta brevemente el contexto real: que paso de verdad, donde y por que. Que el jugador piense "no me lo puedo creer, pero es cierto".

PASO 2B - Si es FALSO:
- Inventa un titular plausible pero falso, en el mismo tono que los reales.
- Que sea creible: ni demasiado obvio ni imposible de descartar.
- En "explicacion" aclara que es inventado y anade una curiosidad REAL relacionada con el tema, para que el jugador igualmente aprenda algo ("Aunque esto no ocurrio, lo que si es cierto es que...").

REGLAS:
- El titular: 1 frase, estilo periodistico, en espanol.
- Nada ofensivo, politico-partidista ni morboso. Tono divertido y de sobremesa.
- La "explicacion": 2-3 frases, amena.

Devuelve SOLO un objeto JSON valido, sin markdown:
{
  "titular": "El titular de la noticia, una sola frase.",
  "es_real": true,
  "explicacion": "Si es real: el contexto veridico. Si es falso: que es inventado + una curiosidad real relacionada.",
  "tema": "palabra o dos que resuman el tema (para no repetir)"
}""" + _bloque_evitar(evitar)

    return _post_ia(prompt, 700, api_key)


def generate_definicion(bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el creador de un juego de vocabulario para bares llamado "La Definicion Falsa". Muestras una palabra real poco conocida del espanol y 4 definiciones; solo una es la verdadera del diccionario. El jugador adivina cual.

FECHA: """ + today + """
SEED: """ + str(seed) + """

INSTRUCCIONES - sigue este orden exacto:

PASO 1: Elige una palabra del espanol REAL y recogida en el diccionario, poco conocida pero bonita o curiosa, que merezca la pena aprender (ej: "gablete", "cazcalear", "bochinche", "albur", "perendengue"). Varia segun el SEED. Evita palabras vulgares o demasiado tecnicas.

PASO 2: Escribe su definicion REAL del diccionario, en lenguaje sencillo y breve.

PASO 3: Inventa 3 definiciones FALSAS pero muy creibles, en el mismo estilo y registro que la real. Que sean plausibles y dificiles de descartar.

PASO 4: Coloca la definicion real en una posicion aleatoria (0-3) e indica su indice en "correcta".

PASO 5: Escribe una frase de ejemplo usando la palabra correctamente, para que el jugador aprenda a "lucirla".

REGLAS:
- Las 4 definiciones deben tener una longitud y un tono parecidos (que no destaque la real por ser mas larga o mas formal).
- Todo en espanol.

Devuelve SOLO un objeto JSON valido, sin markdown:
{
  "palabra": "la palabra del dia",
  "opciones": ["definicion A", "definicion B", "definicion C", "definicion D"],
  "correcta": 2,
  "ejemplo": "Frase de ejemplo usando la palabra correctamente.",
  "origen": "Breve apunte sobre su origen o curiosidad, 1 frase (puede quedar vacio)."
}""" + _bloque_evitar(evitar)

    return _post_ia(prompt, 800, api_key)





# ─────────────────────────────────────────────────────────────────────────────
# Más o Menos (a dobles) — duelo de cifras: ¿cuál es mayor?
# ─────────────────────────────────────────────────────────────────────────────

def generate_masomenos(bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el creador de un juego para bares llamado "Mas o Menos", a dobles. En cada ronda se muestran DOS cosas reales y el jugador apuesta cual tiene la cifra MAYOR de una magnitud.

FECHA: """ + today + """
SEED: """ + str(seed) + """

REGLA DE ORO (CRITICA): la pregunta SIEMPRE pregunta por el valor MAYOR ("¿Que tiene MAS...?", "¿Cual es MAS...?", "¿Cual pesa MAS?", "¿Cual es MAS alto?"). NUNCA preguntes por el menor, el mas antiguo, el primero, el mas corto ni nada que invierta la logica. El campo "mayor" SIEMPRE indica el elemento cuyo VALOR NUMERICO es mas alto. Esto evita confusiones: mas magnitud = la respuesta correcta, sin excepciones.

INSTRUCCIONES:
- Genera 6 rondas. Cada ronda compara dos elementos por una misma magnitud real y verificable.
- Varia las magnitudes entre rondas: habitantes de ciudades, altura de edificios o montanas, peso de animales, duracion de algo, distancia, numero de algo, temperatura, etc.
- IMPORTANTE sobre los anos: si usas fechas, pregunta "¿Cual es MAS RECIENTE?" (ano mayor = mas reciente = respuesta correcta). NUNCA "cual fue antes" (invertiria la logica).
- La pregunta debe ser una frase corta, clara y autoexplicativa que empiece por "¿Que..." o "¿Cual..." y contenga la palabra MAS.
- Que sean de cultura general y curiosas, ni demasiado obvias ni imposibles. La cifra real debe ser objetiva y verificable.
- Contenido NEUTRO e inclusivo: evita ejemplos que dependan del genero (ni "el mas..." referido a hombres/mujeres concretos de forma sesgada). Usa lugares, objetos, animales, naturaleza, inventos, obras.
- "valor": incluye la cifra con su unidad si ayuda (ej. "8.848 m", "688.000", "1994").
- "mayor": 0 si el primero (a) tiene el valor numerico mayor, 1 si el segundo (b).
- "dato": una frase con la curiosidad de la ronda.
- Todo en espanol. Nada ofensivo ni politico-partidista.

Antes de cerrar cada ronda, VERIFICA: el elemento marcado en "mayor" es realmente el de cifra mas alta, y la pregunta pide el MAS (no el menos). Si no, corrigelo.

Devuelve SOLO un objeto JSON valido, sin markdown:
{
  "rondas": [
    {
      "pregunta": "¿Que ciudad tiene MAS habitantes?",
      "magnitud": "habitantes",
      "a": {"nombre": "Sevilla", "valor": "688.000"},
      "b": {"nombre": "Zaragoza", "valor": "675.000"},
      "mayor": 0,
      "dato": "Sevilla supera por poco a Zaragoza como cuarta ciudad de Espana."
    }
  ]
}
Genera exactamente 6 rondas variadas, todas preguntando por el MAS.""" + _bloque_evitar(evitar)

    return _post_ia(prompt, 1500, api_key)




# ─────────────────────────────────────────────────────────────────────────────
# La Escalera — preguntas de dificultad creciente, ¿plantas o sigues?
# ─────────────────────────────────────────────────────────────────────────────

def generate_escalera(bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el creador de un concurso para bares llamado "La Escalera". El jugador responde preguntas de cultura general de dificultad CRECIENTE. Tras cada acierto decide si se planta (y conserva lo ganado) o sigue arriesgando. Un fallo y pierde el bote de esa partida.

FECHA: """ + today + """
SEED: """ + str(seed) + """

Crea 6 preguntas de cultura general con dificultad ESTRICTAMENTE CRECIENTE (peldano 1 = muy facil; peldano 6 = muy dificil):
1. Peldano 1: facilisima, casi todo el mundo la sabe.
2. Peldano 2: facil.
3. Peldano 3: media.
4. Peldano 4: dificil.
5. Peldano 5: muy dificil.
6. Peldano 6: experta, solo aciertan los que saben mucho.

REGLAS:
- Variedad de temas entre peldanos: historia, ciencia, geografia, arte, cine, musica, deporte, naturaleza, lengua... NO repitas tema dos peldanos seguidos.
- Cada pregunta con 4 opciones; solo una correcta. Los distractores, plausibles.
- Cultura general amena y universal (que valga para cualquier publico de bar). Nada de politica partidista ni temas sensibles.
- Una explicacion breve por pregunta (1 frase), para aprender algo al revelar.
- Rigor absoluto: verifica que la opcion correcta es realmente correcta y unica.

Devuelve SOLO un objeto JSON valido, sin markdown:
{
  "preguntas": [
    {"nivel": 1, "tema": "Geografia", "enunciado": "...", "opciones": ["A","B","C","D"], "correcta": 0, "explicacion": "..."},
    {"nivel": 2, "tema": "Cine", "enunciado": "...", "opciones": ["A","B","C","D"], "correcta": 2, "explicacion": "..."}
  ]
}
Genera exactamente 6 preguntas, una por peldano, en orden de dificultad creciente.""" + _bloque_evitar(evitar)

    return _post_ia(prompt, 1800, api_key)


# ─────────────────────────────────────────────────────────────────────────────
# Quién es más probable — afirmaciones para señalar a uno de los dos (a dobles)
# ─────────────────────────────────────────────────────────────────────────────

def generate_quienmas(bar_slug, evitar=None):
    today = str(date.today())
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    seed = get_day_seed(bar_slug)

    prompt = """Eres el animador de un juego para bares llamado "Quien es mas probable que...", para dos personas. Se muestra una afirmacion divertida y cada jugador, en secreto, senala a quien de los dos le pega mas. Luego se compara si coinciden.

FECHA: """ + today + """
SEED: """ + str(seed) + """

Crea 8 afirmaciones del tipo "Quien es mas probable que..." con estas reglas:
- Cotidianas, divertidas, que generen risas y piques sanos entre dos personas (amigos, pareja, companeros).
- Variadas: algunas tiernas, otras gamberras, otras absurdas. Mezcla situaciones de la vida diaria, manias, reacciones, habitos.
- Cortas y con gancho (una frase). Empiezan implicitamente por "Quien es mas probable que..." (NO repitas esa coletilla en cada frase; escribe solo el complemento, ej: "se quede dormido en el cine").
- NEUTRAS respecto al genero: validas para cualquier persona, sin estereotipos de hombre/mujer.
- Nada ofensivo, ni sexual, ni politico, ni que humille. Tono de buen rollo.

Devuelve SOLO un objeto JSON valido, sin markdown:
{
  "afirmaciones": [
    "se quede dormido en el cine",
    "se ria en un momento serio",
    "olvide donde ha aparcado el coche"
  ]
}
Genera exactamente 8 afirmaciones variadas.""" + _bloque_evitar(evitar)

    return _post_ia(prompt, 1000, api_key)


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

    return _post_ia(prompt, 900, api_key)


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

    return _post_ia(prompt, 900, api_key)


# ─────────────────────────────────────────────────────────────────────────────
# El Mismo Pensamiento generator (solo genera la categoría del día)
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIAS_PENSAMIENTO_FALLBACK = [
    "una fruta amarilla", "un país de Europa", "un animal de la selva",
    "una marca de coche", "un color que no sea primario", "un postre típico español",
    "una película de los 90", "un instrumento musical", "una profesión peligrosa",
    "algo que encuentras en una cocina", "un superhéroe", "una ciudad con playa",
]

def generate_pensamiento(bar_slug, evitar=None):
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
        return _post_ia(prompt + _bloque_evitar(evitar), 400, api_key)
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

    return _post_ia(prompt, 1100, api_key)


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

    return _post_ia(prompt, 700, api_key)
