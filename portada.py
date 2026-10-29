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

W, H = 1080, 1620   # H es la altura MÍNIMA; la portada crece si el texto lo pide
MARGEN = 72
PAPEL = (251, 247, 241)
TINTA = (26, 26, 26)
GRIS = (74, 66, 60)
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


def _ajustar(draw, texto, fuente, ancho, max_lineas, tam_ini, tam_min, paso=4):
    """Baja el cuerpo hasta que el texto quepa en max_lineas."""
    tam = tam_ini
    while tam >= tam_min:
        f = _font(fuente, tam)
        lineas = _wrap(draw, texto, f, ancho)
        if len(lineas) <= max_lineas:
            return f, lineas
        tam -= paso
    f = _font(fuente, tam_min)
    return f, _wrap(draw, texto, f, ancho)[:max_lineas]


def componer_portada(datos, nombre_espacio, color_primario='#C4622D', es_evento=False, manana=True):
    """Devuelve una imagen PIL (RGB) con la portada, en vertical (2:3), una columna.

    datos: dict con titular, subtitulo, cita, testigo, seccion, foto, pie.
    """
    acento = _hex(color_primario or '#C4622D', (196, 98, 45))
    img = Image.new('RGB', (W, 2600), PAPEL)
    d = ImageDraw.Draw(img)
    x0, x1 = MARGEN, W - MARGEN
    ancho = x1 - x0

    # ── Cabecera ──
    cab = f"El Diario de {nombre_espacio}"
    f_cab, cab_lineas = _ajustar(d, cab, 'playfair-900.ttf', ancho, 2, 60, 40, 2)
    y = 64
    for ln in cab_lineas:
        d.text(((W - d.textlength(ln, font=f_cab)) / 2, y), ln, font=f_cab, fill=TINTA)
        y += int(f_cab.size * 1.1)
    y += 10
    d.line([(x0, y), (x1, y)], fill=TINTA, width=4)
    y += 12
    fecha = date.today()
    f_meta = _font('inter-400.ttf', 30)
    meta_izq = 'Edición de mañana' if manana else 'Edición de hoy'
    meta_der = f"{_DIAS[fecha.weekday()]}, {fecha.day} de {_MESES[fecha.month - 1]} de {fecha.year}"
    d.text((x0, y), meta_izq, font=f_meta, fill=GRIS)
    d.text((x1 - d.textlength(meta_der, font=f_meta), y), meta_der, font=f_meta, fill=GRIS)
    y += 40
    d.line([(x0, y), (x1, y)], fill=TINTA, width=1)
    y += 36

    # ── Sección ──
    f_sec = _font('inter-700.ttf', 27)
    sec = (datos.get('seccion') or 'Sociedad').upper()
    sw = d.textlength(sec, font=f_sec) + 32
    d.rounded_rectangle([x0, y, x0 + sw, y + 44], radius=8, fill=acento)
    d.text((x0 + 16, y + 9), sec, font=f_sec, fill=(255, 255, 255))
    y += 72

    # ── Titular ──
    f_tit, lineas = _ajustar(d, datos.get('titular') or '', 'playfair-900.ttf', ancho, 3, 104, 64)
    for ln in lineas:
        d.text((x0, y), ln, font=f_tit, fill=TINTA)
        y += int(f_tit.size * 1.1)
    y += 20

    # ── Subtítulo ──
    f_sub, sub_lineas = _ajustar(d, datos.get('subtitulo') or '', 'playfair-400-italic.ttf', ancho, 4, 50, 42, 2)
    for ln in sub_lineas:
        d.text((x0, y), ln, font=f_sub, fill=TINTA)
        y += int(f_sub.size * 1.32)
    y += 30

    # ── "Foto": emojis grandes sobre una banda del color del espacio, pálido ──
    foto_h = 360
    palido = tuple(int(c * 0.22 + 255 * 0.78) for c in acento)
    d.rectangle([x0, y, x1, y + foto_h], fill=palido, outline=LINEA, width=2)
    emojis = datos.get('emojis') or ['📰']
    if isinstance(emojis, str):
        emojis = [emojis]
    emojis = [e for e in emojis if e][:2]
    try:
        f_emo = ImageFont.truetype(os.path.join(_FONTS, 'NotoColorEmoji.ttf'), 109)
        tam = 230 if len(emojis) == 1 else 190
        capas = []
        for e in emojis:
            capa = Image.new('RGBA', (140, 140), (0, 0, 0, 0))
            ImageDraw.Draw(capa).text((16, 8), e, font=f_emo, embedded_color=True)
            bb = capa.getbbox()
            if bb:
                capa = capa.crop(bb)
            capa = capa.resize((tam, int(tam * capa.height / capa.width)), Image.LANCZOS)
            capas.append(capa)
        gap = 48
        total = sum(c.width for c in capas) + gap * (len(capas) - 1)
        ex = x0 + (ancho - total) // 2
        for c in capas:
            img.paste(c, (ex, y + (foto_h - c.height) // 2), c)
            ex += c.width + gap
    except Exception:
        pass
    y += foto_h + 14
    f_pie = _font('inter-400.ttf', 31)
    for ln in _wrap(d, datos.get('pie') or '', f_pie, ancho)[:2]:
        d.text((x0, y), ln, font=f_pie, fill=GRIS)
        y += 40
    y += 30

    # ── Cita del testigo ──
    d.line([(x0, y), (x0, y + 1)], fill=LINEA)  # no-op visual anchor
    f_q = _font('playfair-900.ttf', 120)
    d.text((x0 - 8, y - 36), '“', font=f_q, fill=acento)
    cx = x0 + 70
    cw = x1 - cx
    f_cita, cita_lineas = _ajustar(d, datos.get('cita') or '', 'playfair-400-italic.ttf', cw, 5, 48, 40, 2)
    cy = y + 10
    for ln in cita_lineas:
        d.text((cx, cy), ln, font=f_cita, fill=TINTA)
        cy += int(f_cita.size * 1.35)
    cy += 6
    f_test = _font('inter-700.ttf', 30)
    for ln in _wrap(d, '— ' + (datos.get('testigo') or 'un testigo'), f_test, cw)[:3]:
        d.text((cx, cy), ln, font=f_test, fill=acento)
        cy += 38
    y = cy + 40

    # ── Pie de página: debajo del contenido, y como mínimo a la altura H ──
    alto_pie = 110
    fy = max(y + 24, H - alto_pie)
    # Relleno de columnas (texto simulado) solo si sobra sitio
    if fy - y > 120:
        d.line([(x0, y), (x1, y)], fill=LINEA, width=1)
        ly = y + 28
        colw = (ancho - 32) // 2
        i = 0
        while ly < fy - 30:
            for cxx in (x0, x0 + colw + 32):
                wl = colw if (i % 6) else int(colw * 0.55)
                d.line([(cxx, ly), (cxx + wl, ly)], fill=LINEA, width=6)
            ly += 22
            i += 1
    d.line([(x0, fy), (x1, fy)], fill=TINTA, width=2)
    f_foot = _font('inter-400.ttf', 27)
    f_marca = _font('inter-700.ttf', 30)
    marca = 'nookplay.app'
    mw = d.textlength(marca, font=f_marca)
    d.text((x1 - mw, fy + 22), marca, font=f_marca, fill=acento)
    foot = 'El Titular de Mañana · escrita a partir de un hecho real'
    while d.textlength(foot, font=f_foot) > ancho - mw - 30 and f_foot.size > 20:
        f_foot = _font('inter-400.ttf', f_foot.size - 1)
    d.text((x0, fy + 24), foot, font=f_foot, fill=GRIS)
    alto_final = int(fy + alto_pie)
    img = img.crop((0, 0, W, alto_final))
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
