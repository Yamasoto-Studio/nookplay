"""Compositor de portadas para EL TITULAR DE MAÑANA.

Monta con Pillow una portada de periódico (1080×1350, formato historia/WhatsApp)
a partir del JSON que devuelve la IA y de un icono del catálogo como "foto".
No llama a ninguna IA: es determinista y tarda décimas de segundo.
"""
import os
from datetime import date
from PIL import Image, ImageDraw, ImageFont

_BASE = os.path.dirname(os.path.abspath(__file__))
_FONTS = os.path.join(_BASE, 'static', 'fonts')
_GAMES = os.path.join(_BASE, 'static', 'games')

W, H = 1080, 1240
MARGEN = 64
PAPEL = (251, 247, 241)
TINTA = (26, 26, 26)
GRIS = (107, 96, 89)
LINEA = (200, 190, 178)

_MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
          'septiembre', 'octubre', 'noviembre', 'diciembre']
_DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def _font(nombre, tam):
    try:
        return ImageFont.truetype(os.path.join(_FONTS, nombre), tam)
    except Exception:
        return ImageFont.load_default()


def _hex(c, fallback):
    try:
        c = c.lstrip('#')
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


def _wrap(draw, texto, font, ancho):
    """Parte texto en líneas que caben en `ancho` píxeles."""
    palabras = texto.split()
    lineas, actual = [], ''
    for p in palabras:
        prueba = (actual + ' ' + p).strip()
        if draw.textlength(prueba, font=font) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def _ajustar_titular(draw, texto, ancho, max_lineas=3, tam_ini=96, tam_min=56):
    """Baja el cuerpo del titular hasta que quepa en max_lineas."""
    tam = tam_ini
    while tam >= tam_min:
        f = _font('playfair-900.ttf', tam)
        lineas = _wrap(draw, texto, f, ancho)
        if len(lineas) <= max_lineas:
            return f, lineas
        tam -= 4
    f = _font('playfair-900.ttf', tam_min)
    return f, _wrap(draw, texto, f, ancho)[:max_lineas]


def componer_portada(datos, nombre_espacio, color_primario='#C4622D', es_evento=False, manana=True):
    """Devuelve una imagen PIL (RGB) con la portada.

    datos: dict con titular, subtitulo, cita, testigo, seccion, foto, pie.
    """
    acento = _hex(color_primario or '#C4622D', (196, 98, 45))
    img = Image.new('RGB', (W, H), PAPEL)
    d = ImageDraw.Draw(img)
    x0, x1 = MARGEN, W - MARGEN
    ancho = x1 - x0

    # ── Cabecera: nombre del periódico ──
    cab = f"El Diario de {nombre_espacio}"
    f_cab = _font('playfair-900.ttf', 54)
    while d.textlength(cab, font=f_cab) > ancho and f_cab.size > 30:
        f_cab = _font('playfair-900.ttf', f_cab.size - 2)
    y = 56
    d.text(((W - d.textlength(cab, font=f_cab)) / 2, y), cab, font=f_cab, fill=TINTA)
    y += f_cab.size + 14

    # Línea de datos: edición, fecha, precio
    fecha = date.today()
    f_meta = _font('inter-400.ttf', 22)
    meta_izq = 'Edición de mañana' if manana else 'Edición de hoy'
    meta_c = f"{_DIAS[fecha.weekday()]}, {fecha.day} de {_MESES[fecha.month - 1]} de {fecha.year}"
    meta_der = 'Gratis con tu consumición' if not es_evento else 'Ejemplar gratuito'
    d.line([(x0, y), (x1, y)], fill=TINTA, width=3)
    y += 10
    d.text((x0, y), meta_izq, font=f_meta, fill=GRIS)
    d.text(((W - d.textlength(meta_c, font=f_meta)) / 2, y), meta_c, font=f_meta, fill=GRIS)
    d.text((x1 - d.textlength(meta_der, font=f_meta), y), meta_der, font=f_meta, fill=GRIS)
    y += 34
    d.line([(x0, y), (x1, y)], fill=TINTA, width=1)
    y += 26

    # ── Sección ──
    f_sec = _font('inter-700.ttf', 22)
    sec = (datos.get('seccion') or 'Sociedad').upper()
    sw = d.textlength(sec, font=f_sec) + 28
    d.rounded_rectangle([x0, y, x0 + sw, y + 38], radius=6, fill=acento)
    d.text((x0 + 14, y + 7), sec, font=f_sec, fill=(255, 255, 255))
    y += 60

    # ── Titular ──
    f_tit, lineas = _ajustar_titular(d, datos.get('titular') or '', ancho)
    for ln in lineas:
        d.text((x0, y), ln, font=f_tit, fill=TINTA)
        y += int(f_tit.size * 1.08)
    y += 18

    # ── Subtítulo ──
    f_sub = _font('playfair-400-italic.ttf', 34)
    for ln in _wrap(d, datos.get('subtitulo') or '', f_sub, ancho)[:3]:
        d.text((x0, y), ln, font=f_sub, fill=GRIS)
        y += 44
    y += 22
    d.line([(x0, y), (x1, y)], fill=LINEA, width=1)
    y += 24

    # ── Foto (icono del catálogo) + columna de texto ──
    foto_w = 470
    foto = None
    try:
        foto = Image.open(os.path.join(_GAMES, f"{datos.get('foto') or 'trivia'}.webp")).convert('RGB')
    except Exception:
        try:
            foto = Image.open(os.path.join(_GAMES, 'trivia.webp')).convert('RGB')
        except Exception:
            foto = None
    col_x = x0
    if foto is not None:
        foto = foto.resize((foto_w, foto_w), Image.LANCZOS)
        # marco fino de prensa
        d.rectangle([x0 - 1, y - 1, x0 + foto_w + 1, y + foto_w + 1], outline=LINEA, width=2)
        img.paste(foto, (x0, y))
        # pie de foto
        f_pie = _font('inter-400.ttf', 20)
        py = y + foto_w + 10
        for ln in _wrap(d, datos.get('pie') or '', f_pie, foto_w)[:2]:
            d.text((x0, py), ln, font=f_pie, fill=GRIS)
            py += 26
        col_x = x0 + foto_w + 36
    col_w = x1 - col_x

    # Cita del testigo en la columna derecha
    f_q = _font('playfair-900.ttf', 110)
    d.text((col_x - 6, y - 30), '“', font=f_q, fill=acento)
    f_cita = _font('playfair-400-italic.ttf', 30)
    cy = y + 62
    for ln in _wrap(d, datos.get('cita') or '', f_cita, col_w)[:6]:
        d.text((col_x, cy), ln, font=f_cita, fill=TINTA)
        cy += 40
    cy += 10
    f_test = _font('inter-700.ttf', 20)
    for ln in _wrap(d, '— ' + (datos.get('testigo') or 'un testigo'), f_test, col_w)[:2]:
        d.text((col_x, cy), ln, font=f_test, fill=acento)
        cy += 26

    # Columnas de "texto" simulado bajo la cita (líneas grises, como un periódico)
    ly = cy + 28
    bottom_cols = y + (foto_w if foto is not None else 420)
    while ly < bottom_cols - 8:
        ancho_l = col_w if (int(ly) // 18) % 7 else int(col_w * 0.6)
        d.line([(col_x, ly), (col_x + ancho_l, ly)], fill=LINEA, width=6)
        ly += 18

    # ── Pie de página ──
    fy = H - 84
    d.line([(x0, fy), (x1, fy)], fill=TINTA, width=2)
    f_foot = _font('inter-400.ttf', 20)
    foot = f"Portada escrita a partir de un hecho real · El Titular de Mañana"
    d.text((x0, fy + 16), foot, font=f_foot, fill=GRIS)
    marca = 'nookplay.app'
    f_marca = _font('inter-700.ttf', 22)
    d.text((x1 - d.textlength(marca, font=f_marca), fy + 14), marca, font=f_marca, fill=acento)
    return img


if __name__ == '__main__':
    demo = {
        'titular': 'Marta pide el café con hielo y desata el caos',
        'subtitulo': 'La barra del local vivió minutos de incertidumbre mientras el personal buscaba un vaso a la altura del momento.',
        'cita': 'Nunca había visto a nadie tan segura de lo que quería. Nos ha cambiado la mañana.',
        'testigo': 'un camarero que prefiere no dar su nombre',
        'seccion': 'Sucesos',
        'foto': 'carta',
        'pie': 'Momento exacto en que el hielo toca el café.',
    }
    componer_portada(demo, 'Yellow Specialty Koffee').save('/tmp/portada_demo.png')
    print('ok')
