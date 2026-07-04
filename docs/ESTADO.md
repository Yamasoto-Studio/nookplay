# NOOKPLAY — Documento de estado exhaustivo

> **Última actualización: 2 julio 2026.** Actualiza el documento del 30 de junio con todo
> el trabajo del vertical de **eventos** (modelo completo), el juego **La Trivia**, el
> **pool de variantes por dispositivo** y varios fixes críticos. Leer entero ANTES de
> tocar archivos. Las secciones "EVENTOS", "ANTI-REPETICIÓN", "LECCIONES APRENDIDAS"
> son de lectura obligatoria.

---

## 1. QUÉ ES

Plataforma SaaS de mini-juegos y pasatiempos diarios con **dos verticales**:

- **Locales** (bares, cafeterías): QR fijo + código semanal rotativo. Fidelización.
- **Eventos** (festivales, ferias, jornadas): QR + códigos por día fijados a mano +
  temática que ambienta todos los juegos IA + pool de variantes. Experiencia memorable.

El cliente escanea un QR, introduce un código y accede a juegos que se renuevan cada día.
Sin instalar app, sin registro, sin datos personales. Filosofía: entretenimiento ligero
"mientras esperas el café" (locales) o "mientras haces cola" (eventos).

- **Founder:** Daniel Llamas Soto (Yamasoto, Viladecans, Barcelona).
- **Email producto:** nookplay@yamasoto.com · **WhatsApp empresa:** 623795080 (eSIM Pepephone dedicada).
- **Cliente piloto (local):** Yellow Specialty Koffee (Viladecans; gestiona Lorena, `yellow.specialty.koffee@gmail.com`).
- **Evento piloto:** Vilafrik (manga/anime/cómic, Viladecans, octubre 2026). Slug `vilafrik`, código admin `VFRIK`.
- **Locales de prueba:** Bohemian Nature; Demo (escaparate público sin código).

---

## 2. DOMINIOS Y DESPLIEGUE

- **Producción / app real: `nookplay.app`** ← app Flask (admin, juegos, todo).
- `nookplay.com` → Shopify (NO es el servidor de la app). No confundir.
- Diagnóstico scheduler: `https://nookplay.app/admin/api/scheduler-status` (superadmin).

### Stack
- Python/Flask + SQLite + Docker en **Reliops EasyPanel** (IP 217.71.207.76).
- Repo GitHub: **Yamasoto-Studio/nookplay** (rama `main`).
- **BD siempre en `/data/nookplay.db`** (volumen persistente; NUNCA fallback local).
- Gunicorn 2 workers + `--preload`: el estado en memoria NO se comparte entre workers;
  la fuente de verdad SIEMPRE es la BD.
- requirements: flask 3.0.3, gunicorn 22.0.0, anthropic 0.28.0, APScheduler 3.10.4, requests 2.31.0, Pillow 10.3.0.
- SMTP vía yam01isp01.reliops.net:587.

### Flujo de trabajo con Claude
1. Claude clona en `/home/claude/nookplay` (git pull del último commit ANTES de cada sesión),
   edita, valida con `ast.parse` + prueba Jinja2 + test de importación completa de app.py +
   tests funcionales con BD temporal.
2. Copia archivos finales a `/mnt/user-data/outputs/` y usa present_files.
3. El usuario descarga, sobrescribe en local, y sube con:
   `git add . && git commit -m "..." && git push` → deploy en EasyPanel.
- Ruta local: `~/Library/CloudStorage/Dropbox/WORKS - Dropbox/YAMASOTO - PROYECTOS PERSONALES/NOOKPLAY/Repositorio GitHub/nookplay`.
- Trabajo técnico y de diseño/branding en chats SEPARADOS.

---

## 3. ARQUITECTURA DE ARCHIVOS

- **app.py** (~4200 líneas): rutas, planes, scheduler, pre-generación con pool, analytics
  con ventana, eventos, demo.
- **ai.py**: `generate_X()` por juego. Modelo **claude-sonnet-4-6**. Sistema común
  `_SISTEMA_NOOKPLAY` en `_post_ia()`. Contextvars: `set_event_theme` (temática) y
  `set_variant_hint` (pool) inyectan en TODOS los generadores sin tocar firmas.
- **init_db.py**: esquema + migraciones idempotentes + seed `games` + `ORDEN_JUEGOS`.
- **templates/**: `base.html`, `home.html`, `bar.html` (menú cliente con ✓ de jugado),
  `game_base.html` (wrapper device_id + marcado de jugados), `games.html`, `404.html`.
- **templates/games/**: 29 archivos (uno por juego).
- **templates/admin/**: `bar_panel.html` (panel context-aware local/evento),
  `dashboard.html` (badge 🎪 EVENTO), `login.html`.
- **static/games/*.webp**: iconos 500×500 (trivia.webp ya subido).

### Helpers clave de app.py
`get_db()`, `get_historial_reciente()` (AHORA INCLUYE HOY — clave para el pool),
`_persistir_generado()`, `_theme_de(bar)`, `_leer_pregenerado(db, bar_id, game_type, today)`
(elige variante por dispositivo), `_pool_slugs()` (TTL 60s), `_GameCache` (caché que ignora
pools), `pregen_daily_games()`, `calcular_analytics_bar(db, slug, ventana=None)`,
`generate_weekly_codes()` (excluye demos Y eventos), `_normalizar_codigo()`, `build_bar_context()`.

### Helpers de ai.py
`_post_ia(prompt, max_tokens, api_key, reintentos=2, modelo, event_theme=None)` — lee
tema y hint de variante de contextvars automáticamente. `_bloque_tematico()`,
`_bloque_evitar()`, `set_event_theme()/reset_event_theme()/get_event_theme()`,
`set_variant_hint()/get_variant_hint()`, `_parse_ia_json()`, `get_day_seed(bar_slug)`.

---

## 4. ESQUEMA DE BASE DE DATOS (11 tablas)

### `bars` — el espacio (local O evento)
Todo lo anterior MÁS los campos de evento:
`space_kind` (TEXT DEFAULT 'local'; 'local'/'evento' — discriminador; NO confundir con
`type`, que es descripción libre para la IA), `event_theme` (TEXT; temática libre que
ambienta todos los juegos IA), `event_start`, `event_end` (TEXT YYYY-MM-DD),
`event_pool_size` (INTEGER DEFAULT 1; variantes por juego), `event_test_mode`
(INTEGER DEFAULT 0; generar a diario aunque no sea fecha del evento).

### `variant_views` — NUEVA: vistas de variantes del pool
`id, device_id, gg_id (id de generated_games), viewed_at, UNIQUE(device_id, gg_id)`
Registra qué variante ha visto cada dispositivo para servir sin repetir.

### Resto de tablas
`bar_products` (en eventos = actividades destacadas; `price` = horario/lugar),
`access_codes` (eventos: fila por día con valid_from=valid_until=día + fila admin con
ventana centinela **2000-01-01 → 2099-12-31**), `access_log`, `generated_games`
(pool: N filas por bar+juego+día), `app_state`, `plays`, `admin_users`, `games`, `bar_games`.

---

## 5. CATÁLOGO DE JUEGOS (29 en ALL_GAMES)

Todo lo del documento anterior MÁS:

| Slug | Nombre | Tipo | Anti-rep | Notas |
|------|--------|------|----------|-------|
| trivia | La Trivia | IA por-bar (seed) | ✅ trivia_preguntas | Quiz 5×4 cultura general, dificultad progresiva, explicación por pregunta. En eventos se tematiza solo. |

### Clasificación relevante para eventos
- **POOL_GAME_TYPES (por-bar, tematizables, los únicos que un evento genera):**
  crimen, impostor, dilema, conexiones, veredicto, perfil, vestuario, trivia, local.
- **Los eventos NO generan juegos globales** (oraculo, donde, sinopsis, etc.): irían con
  la temática del evento a todos los bares. Si un evento los activa, lee el global común
  (sin tema). Recomendación: un evento activa solo juegos por-bar.

### ANTI-REPETICIÓN — estado (17 juegos)
Los 16 anteriores + **trivia** (campo especial `trivia_preguntas` → enunciados).
**CAMBIO CLAVE:** `get_historial_reciente` ahora incluye HOY (`game_date <= hoy`).
Para bares es idéntico (cuando generan aún no hay fila de hoy). Para el pool hace que
la variante 2 evite automáticamente lo generado en la variante 1 de la misma tanda.

---

## 6. EVENTOS (vertical completo) — LEER ANTES DE TOCAR

### Modelo
Un evento es una fila en `bars` con `space_kind='evento'`. Reutiliza TODO el sistema
(juegos, planes, admin, colores, stats) con comportamiento condicionado.

### Temática (`event_theme`)
Texto libre (describir público + referencias + tono, no solo el nombre). Se inyecta vía
contextvar en `_post_ia`, cubriendo TODOS los generadores presentes y futuros sin tocar
firmas. Se activa: (a) en pregen al entrar a cada bar (cada bar sobrescribe, sin fugas);
(b) en los fallbacks de los juegos por-bar con `set_event_theme(_theme_de(bar))` + try/finally.
VERIFICADO con prompts interceptados: el bloque temático viaja antes del prompt del juego.

### Generación y ahorro
- **Durante fechas del evento:** el pregen 6am genera normal (con pool si procede).
- **Fuera de fechas + modo pruebas OFF:** el pregen lo salta (cero coste diario).
  Probar sigue funcionando: los fallbacks generan bajo demanda con temática.
- **Fuera de fechas + modo pruebas ON:** genera a diario como un bar.
- Un evento terminado deja de generar solo.

### Pool de variantes (modelo C)
- `event_pool_size` = N variantes por juego por-bar y día (bares: 1, sin cambios).
- Pregen: cuenta existentes y genera las que falten. Cada variante lleva hint
  "VARIANTE N: sé claramente distinta" (contextvar) + anti-rep de tanda vía historial-con-hoy.
- Servido: `_leer_pregenerado()` — 1 pieza → idéntico a antes; N piezas → primera variante
  no vista por el device_id (tabla `variant_views`); agotadas → cicla desde la más antigua.
- `_GameCache` ignora los slugs con pool (si cacheara, todos verían la misma variante).
  `_pool_slugs()` con TTL 60s. Los fallbacks generan 1 pieza (el pool lo llena el pregen).
- El wrapper de `game_base.html` inyecta `device_id` en TODAS las llamadas `/api/` POST.

### Códigos de acceso
- **Código admin permanente:** fila con ventana centinela 2000-01-01→2099-12-31.
  Siempre válido (para probar cuando sea). Vilafrik: `VFRIK`.
- **Códigos por día:** una fila por día (valid_from=valid_until=día), fijados A MANO
  desde el panel (el organizador los conoce por adelantado → entradas, cartelería).
  Botón 🎲 rellena vacíos. **Hojas imprimibles**: una página por día con código grande.
- `generate_weekly_codes` (lunes 6am) EXCLUYE eventos (no pisa los manuales).
- **BUG CRÍTICO RESUELTO:** las 26 APIs de juego validaban cogiendo "el primer código
  válido de hoy" y comparando — con multi-código (admin + días) fallaba aleatoriamente
  con 403. Ahora todas validan `WHERE bar_id=? AND code=? AND ventana` (como la entrada).

### Panel admin (solo superadmin ve la config de evento)
Selector Local/Evento (radio) → despliega: temática (textarea con placeholder-guía),
fechas, piezas por juego, modo pruebas, código admin, códigos por día + imprimibles.
Etiquetas del formulario context-aware con Jinja (estado inicial) + JS en vivo
(`onSpaceKindChange`): Enlaces del evento, Web/Programa, Actividades destacadas
(price→Horario/Lugar), Logo/Sobre/Colores del evento, onboarding propio de evento.
Doble protección: frontend no envía + backend rechaza si no superadmin.
Dashboard: badge 🎪 EVENTO + fechas junto al nombre.

### Cliente
- Pantalla de código: "🎟️ Encontrarás el código en tu entrada o en la cartelería del
  evento. Cada día tiene su código." (bares mantienen su texto de ticket/personal).
- Los eventos NO salen en el mapa "Ya en tu ciudad" de la home.

### Analytics con ventana
`calcular_analytics_bar(db, slug, ventana=(start, end))` — sin ventana = semanal exacto
de siempre (bares intactos). Con ventana: partidas/asistentes del evento, gráfico por día
del mes, mejor día "Viernes 10", SIN tendencia (no hay periodo comparable), días futuros
recortados a hoy. Flag `ventana_evento` condiciona etiquetas del panel.

---

## 7. UX CLIENTE — NOVEDADES

- **✓ de jugado hoy (ambos verticales):** al terminar un juego, el wrapper lo apunta en
  localStorage (`nook_played_<fecha>`, se autolimpia). El menú marca la tarjeta: badge ✓
  verde, opacidad 0.72, descripción "Hecho · mañana hay nuevo". Excluidos: los 4 a dobles
  y poema (rejugables por naturaleza). Por dispositivo, no por mesa.
- Copy home/games/base actualizado a dos verticales (sección "No solo bares." en home,
  metadatos og/twitter orientados a comprador, modal de contacto neutro).

---

## 8. PLANES / ADMIN / ESTADÍSTICAS / ACCESO FÍSICO / BRANDING

Sin cambios respecto al documento del 30 de junio, salvo lo descrito en las secciones
6 y 7 (panel context-aware, analytics con ventana, textos del cliente). Los eventos se
cobran por evento (precio manual, según días/generaciones/juegos), plan tipo `gift`.

---

## 9. LECCIONES APRENDIDAS (añadidas a las 17 anteriores, que siguen vigentes)

18. **Multi-código rompe validaciones de "primera fila":** un SELECT sin filtrar por el
    código introducido y sin ORDER BY devuelve una fila arbitraria. Con eventos
    (admin + días válidos a la vez) produce 403 intermitentes. Validar SIEMPRE
    `WHERE code = ?`. El orden de filas de SQLite NO es determinista.
19. **`{% set %}` de Jinja solo aplica de su línea hacia abajo.** Declarar variables
    compartidas (`es_evento`) al INICIO del bloque content, o las secciones anteriores
    las verán como undefined (falsy) en silencio.
20. **Contextvars es el patrón para inyectar en 21+ generadores sin tocar firmas**
    (tema de evento, hint de variante). Cada bar sobrescribe al entrar al bucle del
    pregen → sin fugas entre espacios. En fallbacks: try/finally con reset.
21. **`from ai import X` vs `ai.X`:** si el import es de nombres sueltos, `ai.set_...`
    peta con NameError. Verificar SIEMPRE con importación completa de app.py antes de
    entregar (cazó este bug antes de producción).
22. **La caché en memoria envenena el pool:** cachear por (bar, juego, día) sirve la
    misma variante a todos. Solución: subclase de dict que ignora slugs con pool.
    Y ojo: reasignar `_game_cache = {...comprehension...}` destruye la subclase —
    limpiar in-place.
23. **`web_fetch` devuelve caché:** no sirve para verificar deploys recientes. La
    verificación de producción es la observación directa de Daniel en su navegador
    (y un estático o el texto del hero como indicador).
24. **`get_historial_reciente` incluye hoy** desde el modelo C. Cualquier razonamiento
    sobre anti-repetición debe contar con ello (para bares es equivalente porque
    generan antes de que exista la fila de hoy).
25. **El pregen y los endpoints leen contenido por caminos distintos:** arreglar solo
    uno deja el bug en el otro. Los juegos globales se comprueban sin bar_id en AMBOS
    lados. Los eventos ya no generan globales (evita contaminación temática).

---

## 10. CHECKLIST AÑADIR JUEGO NUEVO

El del documento anterior sigue válido, con un matiz: el paso (g) del fallback debe
incluir también `set_event_theme(_theme_de(bar))` + try/finally si el juego es por-bar
(ver trivia como ejemplo canónico completo). La lectura del pre-generado debe usar
`_leer_pregenerado(db, bar_id, 'slug', today)` para ser compatible con el pool.

---

## 11. PENDIENTES

- **Vilafrik:** simulacro completo (temática definitiva, juegos activos, fechas y códigos
  reales, modo pruebas, jugarlo de arriba a abajo). Hablar con organizadores.
- **Mensaje "ya has visto todas las variantes de hoy"** en cliente (el pool cicla en
  silencio; comunicarlo es pulido pendiente).
- Iconos definitivos de dosverdades y masomenos (placeholders "2P").
- Verificar en cliente el render de actividades con Horario/Lugar cuando Vilafrik tenga
  contenido real.
- **Stripe Billing (fase 2)**; envío automático del código semanal por email (lunes 6am);
  SECRET_KEY como variable de entorno; WhatsApp API (~15 clientes); "El retrato del local";
  documentación de onboarding; cartas especiales Freep; dificultad Mente Ágil; rigor
  Constitución/Titular. OEPM/EUIPO en curso; Safe Creative código fuente pendiente.

---

## 12. HISTORIAL DE SESIONES (1-2 julio 2026)

- **Copy dos verticales:** home (sección eventos "No solo bares."), games, metadatos, modal.
- **Eventos fase 1:** columnas de evento + inyección temática (contextvars) en pregen y
  7 fallbacks por-bar.
- **Panel de eventos:** selector tipo de espacio, temática, fechas, pool, modo pruebas,
  etiquetas context-aware, bug colores Yellow resuelto, onboarding de evento.
- **Códigos:** por día manuales + código admin permanente + hojas imprimibles + exclusión
  de rotación semanal + FIX crítico de validación multi-código en 26 APIs.
- **La Trivia:** juego 29, quiz 5×4 tematizable, checklist completo.
- **Ahorro:** eventos fuera de fechas no generan (modo pruebas opcional); fuera del mapa
  de la home; badge 🎪 en dashboard.
- **Analytics con ventana del evento** (partidas/asistentes del evento, sin tendencia).
- **✓ de jugado hoy** en el menú (localStorage por dispositivo).
- **Modelo C:** pool de variantes por dispositivo (variant_views, _leer_pregenerado,
  caché selectiva, hint de variante, eventos sin globales).

*Documento actualizado el 2 de julio de 2026 tras las sesiones del vertical de eventos.*
