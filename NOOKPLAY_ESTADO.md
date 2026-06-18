# NOOKPLAY — Documento de estado (traspaso entre chats)

> **Última actualización: 18 junio 2026.** Funciona con cualquier modelo (Opus / Sonnet / Haiku).
> Para retomar el proyecto: lee este doc entero ANTES de tocar código. La sección
> "LECCIONES APRENDIDAS" y "CHECKLIST AÑADIR JUEGO" son de lectura obligatoria.

## QUÉ ES
Plataforma SaaS de mini-juegos y pasatiempos diarios para locales (bares, cafeterías, y a futuro clínicas, peluquerías...). El cliente del local escanea un QR en la mesa/cristal, introduce un **código semanal** (5 caracteres alfanuméricos) y accede a una colección de juegos que se renuevan cada día. Sin instalar app, sin registro, sin recoger datos personales. Filosofía: entretenimiento ligero "mientras esperas el café".

Founder: **Daniel Llamas Soto** (Yamasoto, Viladecans, Barcelona).
Email del producto: **nookplay@yamasoto.com**.
Cliente piloto: **Yellow Specialty Koffee** (Viladecans, gestiona Lorena, email `yellow.specialty.koffee@gmail.com`). 2º local de prueba: Bohemian Nature. 3º: Demo (escaparate público sin código).

## DOMINIOS (IMPORTANTE)
- **Producción / app real: `nookplay.app`** ← AQUÍ está la app Flask. El admin, los juegos, todo.
- `nookplay.com` apunta a **Shopify** (NO es el servidor de la app; si entras te manda a login de Shopify). NO confundir.
- Diagnóstico del scheduler: `https://nookplay.app/admin/api/scheduler-status` (logueado como superadmin) → devuelve JSON con juegos generados hoy y errores de pre-generación.

## STACK Y DESPLIEGUE
- Python/Flask + SQLite + Docker en Reliops EasyPanel (IP 217.71.207.76)
- Repo GitHub: **Yamasoto-Studio/nookplay**
- BD siempre en `/data/nookplay.db` (volumen persistente; NUNCA usar fallback local, borra datos en deploy)
- Gunicorn con **2 workers + `--preload`** (importante: el estado en memoria `_game_cache` NO se comparte entre workers tras el fork; la fuente de verdad SIEMPRE es la BD `generated_games`). Dockerfile: `gunicorn app:app --bind 0.0.0.0:80 --workers 2 --timeout 120 --preload`.
- SMTP vía yam01isp01.reliops.net puerto 587
- Pillow en requirements.txt (procesado de imágenes)

## FLUJO DE TRABAJO CON CLAUDE (IMPORTANTE)
1. Claude clona/trabaja en `/home/claude/nookplay` (`git clone https://github.com/Yamasoto-Studio/nookplay.git`), edita y valida sintaxis con `python3 -c "import ast; ast.parse(open('X.py').read())"`.
2. Copia archivos finales a `/mnt/user-data/outputs/` y usa present_files. **SIEMPRE pasar los archivos modificados** para que el usuario los sobrescriba.
3. El usuario descarga, **sobrescribe en su carpeta local nookplay**, y desde el terminal (ya situado en esa carpeta) sube con UN SOLO comando:
   ```
   git add . && git commit -m "..." && git push
   ```
   (NO usar `cp ~/Downloads/...`: el usuario YA reemplaza los archivos manualmente. El comando es solo add+commit+push.)
4. Implementa en EasyPanel (deploy automático o manual según configuración).
- Ruta repo local del usuario: `~/Library/CloudStorage/Dropbox/WORKS - Dropbox/YAMASOTO - PROYECTOS PERSONALES/NOOKPLAY/Repositorio GitHub/nookplay`
- Trabaja en dos máquinas (Mac mini casa, portátil en cafés), sincronizadas por Dropbox.
- Trabajo técnico y de diseño/branding en chats SEPARADOS del proyecto.
- Estilo de trabajo: iterativo y directo. Un cambio confirmado antes del siguiente. Cuando pide "repasar como experto", hacer análisis REAL leyendo el código, no de memoria.

## ARQUITECTURA DE ARCHIVOS
- **app.py** (raíz): rutas, lógica de planes, scheduler, pre-generación. `_game_cache` en memoria + respaldo en BD `generated_games`. Helpers clave: `get_historial_reciente()`, `_persistir_generado()`, `pregen_daily_games()`, `start_scheduler()`, `hash_password()`.
- **ai.py** (raíz): funciones `generate_X()` por juego. Modelo **claude-sonnet-4-6** (NO usar 4-5, deprecado). `get_day_seed(bar_slug)` para variar contenido diario. Helpers de robustez: `_post_ia()`, `_parse_ia_json()`, `_reparar_json_truncado()`, `_bloque_evitar(evitar)`.
- **init_db.py** (raíz): esquema + seed + migraciones (ALTER TABLE) + orden de juegos (dict ORDEN_JUEGOS). No sobreescribe campos editables de Yellow. Al final incluye migración que corrige el email admin de Yellow.
- **templates/games/*.html**: cada juego, hereda de game_base.html (carga stats.js y share.js).
- **templates/bar.html**: menú del local. `startActivity(slug)` es GENÉRICO (ruta `/${BAR_SLUG}/${slug}`), no tocar al añadir juegos.
- **templates/games.html**: catálogo público /juegos, DINÁMICO desde BD, no tocar al añadir juegos.
- **templates/home.html**: landing. Contador de juegos dinámico.
- **templates/base.html**: layout base. Contiene el flotante de accesibilidad `.a11y-toggle` (botones A | A | A para tamaño de texto) — SOLO debe verse en juegos/menú, NO en admin (en admin se oculta con `.a11y-toggle { display:none !important; }`).
- **templates/admin/**: login.html, dashboard.html, bar_panel.html (panel por local).
- **static/games/*.webp**: iconos (500x500, rediseñados por el usuario en Magnific).
- **static/js/share.js**: `shareGame()`, `nookShareWithImage(txt, slug)` (compartir con imagen), `nookCelebrate(msg, cb)` (overlay victoria puzzles).
- **static/css/games.css**: `.game-tag` centrado por defecto.

## CATÁLOGO DE JUEGOS (22 activos)
Lógica/puzzle: crimen, reinas, equilibrio, carta, orden
Adivinanza/cultura: conexiones, donde, sinopsis, letra, vestuario
Opinión/social: dilema, veredicto, perfil, pensamiento
Curiosidad/lectura: impostor, muertes, oraculo, local
Reto mental: menteagil, constitucion
Creativo: poema
2 jugadores: freep

### Tipos de generación (CRÍTICO para pre-gen y fallbacks):
- **Por-bar con seed** (contenido distinto por local): crimen, impostor, dilema, conexiones, veredicto, perfil, vestuario, local
- **Globales** (mismo contenido para TODOS los locales ese día; se generan UNA vez): oraculo, donde, sinopsis, muertes, letra, pensamiento, menteagil, constitucion
- **Deterministas SIN IA** (no se pre-generan, 0 tokens): reinas, equilibrio, carta, orden, freep
- **Bajo demanda** (no se pre-genera, personalizado, devuelve TEXTO no JSON): poema

### Anti-repetición — qué campo usa cada juego (debe coincidir pregen Y fallback):
- dilema → campo `situacion` (por bar)
- veredicto → campo `titulo` (por bar)
- perfil → campo `nombre` (por bar)
- vestuario → campo `preguntas` (por bar)
- sinopsis → campo `opciones` (global, bar_slug=None)
- muertes → campo `titulo` (global, bar_slug=None)
- letra → campo `opciones` (global, bar_slug=None)
- (los demás globales NO usan evitar: pensamiento, menteagil, constitucion, oraculo, donde; conexiones tampoco)

## PATRÓN UX ESTÁNDAR DE TODOS LOS JUEGOS
tag centrado → contenido → SELECCIÓN (se puede cambiar) → botón CONFIRMAR → resultado con stats (donut + jugadores + tiempo) → compartir (con imagen del juego) → volver al menú → frase de despedida.
- NUNCA auto-avance: siempre botón manual (incluso última pregunta de quizzes, para leer la explicación).
- Frase de despedida administrable por local (campo `tomorrow_message`, default "Vuelve a tomar un café.").
- Quizzes de 3 preguntas (vestuario, menteagil): barra de progreso, nota /3 con mensajes humorísticos.

## ═══════════════════════════════════════════════════════════
## SISTEMA DE GENERACIÓN IA — CÓMO FUNCIONA (LEER ANTES DE TOCAR)
## ═══════════════════════════════════════════════════════════

### Flujo de lectura de un juego (cuando un cliente entra):
1. ¿Está en `_game_cache` (memoria del worker)? → devolver. (OJO: cada worker tiene su copia.)
2. ¿Está pre-generado en BD `generated_games` (hoy)? → cargar, cachear, devolver.
3. FALLBACK: generar bajo demanda con IA → **persistir en BD** → cachear → devolver.

### Pre-generación (lo normal, lo que debe cubrir todo):
- Scheduler diario **6:00 AM Europe/Madrid** (`pregen_daily_games()` vía APScheduler CronTrigger).
- También botón "Forzar pre-generación" (superadmin, dashboard): borra contenidos de hoy y regenera en HILO DE FONDO (background thread; necesario por timeout con ~30 generaciones).
- Estado/progreso en tabla **app_state** (compartida entre los 2 workers), claves: `pregen_running`, `pregen_errores`, `pregen_ok`.
- Frontend hace polling cada 2s y muestra progreso + lista de generados + errores.
- El contador `total = nº_bares × len(GAME_TYPES)`. Cuenta TODOS los game_type×bar aunque los globales solo se generen una vez (por eso "total" parece más alto que lo realmente insertado en BD; es normal).

### Helpers de robustez IA (en ai.py — añadidos 18 jun 2026):
- **`_post_ia(prompt, max_tokens, api_key, reintentos=2)`**: hace la llamada a la API de Anthropic CON REINTENTO (backoff suave) y parseo robusto. TODA función generadora que devuelva JSON debe usar este helper. NO volver a escribir `requests.post` + `json.loads(text)` a mano.
- **`_parse_ia_json(text)`**: parseo tolerante. Limpia fences markdown, extrae el primer `{...}`, y si el JSON viene truncado lo REPARA (cierra comillas/llaves abiertas). Resuelve el error "Unterminated string" que rompía generaciones.
- **`_reparar_json_truncado(t)`**: lógica de reparación (balance de llaves/corchetes/comillas).
- EXCEPCIÓN: `generate_poema` NO usa `_post_ia` porque devuelve TEXTO plano (`{"poema": texto}`), no JSON. Dejarlo como está.

### Persistencia de fallbacks (en app.py — añadido 18 jun 2026):
- **`_persistir_generado(bar_id, game_type, game_data, es_global=False)`**: guarda en `generated_games` con conexión propia + commit (para que persista entre workers). Idempotente (no duplica). Si `es_global=True` solo guarda si no existe ya un global para hoy.
- TODOS los fallbacks bajo demanda llaman a esto antes de devolver. Así un juego se genera UNA vez aunque falle la pre-gen, y el anti-repetición lo ve.

## ═══════════════════════════════════════════════════════════
## LECCIONES APRENDIDAS (errores reales que costaron tiempo)
## ═══════════════════════════════════════════════════════════

1. **El bug de "salen 16 y no 24" NO era de lógica, era de PARSEO IA.** Las generaciones de crimen/yellow y oraculo/yellow fallaban con `json.loads: Unterminated string` porque la IA devolvía JSON truncado (se pasaba de `max_tokens`) o con un string sin cerrar. Era INTERMITENTE (el mismo juego salía bien en un bar y mal en otro). Solución: parseo tolerante + reintento + subir max_tokens (crimen 1200→1500, oraculo 2000→2500). **Lección: si un juego "a veces no se genera", sospecha del parseo de la respuesta IA, no de tu bucle.**

2. **El error SÍ estaba registrado, solo que no se veía a simple vista.** Está en `app_state.pregen_errores` y se consulta en `nookplay.app/admin/api/scheduler-status` (campo `errores`). SIEMPRE mirar ahí antes de teorizar.

3. **Los fallbacks NO persistían** → se regeneraba en cada visita, cada worker duplicaba contenido, y el anti-repetición no veía lo generado bajo demanda. Resuelto con `_persistir_generado()`.

4. **El anti-repetición estaba SOLO en la pre-gen, no en los fallbacks.** Si saltaba el fallback, podía repetir contenido de días previos. Ahora ambos pasan `evitar=`.

5. **DB path es no-negociable:** siempre `/data/nookplay.db`, nunca fallback local (borra datos en deploy).

6. **Multi-worker:** nunca confiar en estado en memoria entre workers. BD o `app_state` como fuente de verdad.

7. **Jinja2 gotcha:** JS/modales colocados DESPUÉS de `{% endblock %}` se ignoran en silencio — deben ir DENTRO del bloque.

8. **Al editar ai.py con scripts regex:** cuidado con regex `DOTALL` codiciosos que crucen fronteras de funciones (`def`). Un regex mal acotado se "comió" parte de generate_poema. Usar lookahead `(?:(?!def generate).)*?` para acotar. SIEMPRE validar con `ast.parse` Y revisar las funciones especiales (poema = texto, no JSON).

9. **Bugs recurrentes a vigilar:** `bar.html` `startActivity` hardcodeado en vez de genérico; INSERT en `plays` sin `code NOT NULL`; endpoints de stats con columnas mal (`bar_id`/`play_date` en vez de `bar_slug`/`played_on`).

## CHECKLIST AÑADIR JUEGO NUEVO (actualizado)
1. **init_db.py**: INSERT en tabla games (slug, name, desc, icon, plan_min, position) + añadir a dict ORDEN_JUEGOS
2. **ai.py**: función `generate_X()`:
   - Si devuelve JSON → usar `return _post_ia(prompt, max_tokens, api_key)` (NO escribir requests.post + json.loads a mano)
   - Si es propenso a repetir → aceptar `evitar=None` y usar `_bloque_evitar(evitar)` en el prompt
   - Ajustar `max_tokens` con margen (mejor sobrar que truncar)
3. **app.py**:
   (a) import de la función
   (b) añadir a `ALL_GAMES`
   (c) `STARTER_FREE_GAMES` si aplica
   (d) añadir a `GAME_TYPES` en `pregen_daily_games()` SI debe pre-generarse (NO si es determinista o bajo demanda)
   (e) `elif` en el bucle de pregen (si es GLOBAL, comprobar `existing` global y `continue`)
   (f) rutas página + API + stats
   (g) en el FALLBACK del endpoint: llamar a `_persistir_generado(bar['id'], 'slug', game_data, es_global=...)` antes de devolver
   (h) si usa anti-repetición: inyectar `evitar=` TANTO en pregen COMO en fallback (mismo campo en ambos)
4. **templates/games/X.html** (patrón UX estándar)
5. **static/games/X.webp** (icono; placeholder hasta el definitivo de Magnific)
- NO tocar: bar.html (ruta genérica), games.html (dinámico).
- Tras deploy: "Forzar pre-generación" en dashboard + revisar `scheduler-status` para confirmar 0 errores.

## PLANES (config en app.py — fuente única de verdad)
- ALL_GAMES, STARTER_FIXED=["crimen","dilema","reinas","conexiones"], STARTER_FREE_GAMES, PRO_MAX_GAMES, PLAN_CFG
- Starter (6,95€): 4 fijos + 2 libres. Pro (9,95€): hasta 12 a elegir. Premium (14,95€): todos. Gift/Total: internos. Demo: escaparate público gestionable por admin (sin código, juegos inactivos bloqueados con candado).
- Colores y logo del local en TODOS los planes.

## ADMIN
- Panel por bar en `/admin/<bar_slug>`. Superadmin tiene acceso a TODOS los bares.
- `admin_role` se pasa al template (`'superadmin'` o `'bar_admin'`).
- **Cambio de contraseña** (añadido 18 jun 2026): ruta `POST /admin/api/change-password`. Valida contraseña actual, concordancia, mínimo 8 caracteres. Cada usuario solo cambia la SUYA (vía `session['admin_user_id']`). La sección en bar_panel.html solo se muestra a `bar_admin` (oculta para superadmin visitando un bar ajeno).
- Botón "Guardar" del panel: FLOTANTE abajo-derecha (`z-index:1000`, por encima del flotante de accesibilidad que en admin se oculta).
- CMS por local: colores, logo, mensaje bienvenida, mensaje despedida (`tomorrow_message`), productos/promo banner.
- Para dar de alta a Lorena: crear usuario con su email + pass temporal, ella la cambia desde su panel.

## BRANDING
- Terracota primario **#C4622D**, CTA **#A8410E** (el violeta/magenta antiguo está DESCARTADO).
- Colores del local (ej. Yellow amarillo #FEE25A / #1A1A1A) se aplican vía variables CSS en toda la experiencia del cliente.
- Paleta neutra a propósito, para adaptarse a la identidad de cada bar.

## PENDIENTES
- Verificar tras deploy que el bug de generación quedó resuelto (forzar pregen → scheduler-status → 0 errores, crimen/yellow y oraculo/yellow presentes).
- Envío automático de código semanal por email (lunes 6am): ruta `GET /api/weekly-code/<bar_slug>` + trigger + plantilla. (WhatsApp queda para cuando haya empresa verificada / eSIM dedicada.)
- Ajustar dificultad de Mente Ágil si sigue fácil (ya se endureció el prompt una vez).
- Vigilar rigor de datos de ¿Tú la has leído? (Constitución) en primeras generaciones.
- Iconos definitivos en Magnific (placeholder actual): sinopsis, muertes, letra, pensamiento, poema, menteagil, constitucion, vestuario, perfil, veredicto.
- OG image y vídeo hero (Figma/Magnific).
- Vinilo/expositores Yellow: 20x20cm cristal, monomérico mate, pegado por dentro (diseño en espejo) o doble cara microperforado. Illustrator. Pixartprinting/360imprimir. QR apunta a nookplay.app/<slug>.
- OEPM/EUIPO registro marca (gestor); Safe Creative (concepto registrado, código fuente pendiente — error "Bad Request" tras pago, soporte contactado). Documentos Safe Creative siempre con nombre completo "Daniel Llamas Soto".
- SECRET_KEY como variable de entorno en EasyPanel (buena práctica).
- Documentación de onboarding para propietarios (cómo acceder admin, cambiar colores, gestionar juegos).
- Stripe Billing (fase 2, cuando escale): suscripciones + webhook activar/suspender bares + alta autoservicio.
- Cartas especiales de Freep (comodín, robo, vida del juego físico).
- Expansión futura a otros negocios con sala de espera (clínicas, peluquerías).

## DECISIONES DESCARTADAS / STANDBY
- Carta digital del local en la app: STANDBY (consolidar entretenimiento primero).
- Valoración de juegos por estrellas: DESCARTADO (fricción). Alternativa: calcular más jugados desde tabla `plays` sin pedir nada al usuario.
- Multijugador en tiempo real: inviable (sin websockets). El Mismo Pensamiento es asíncrono (compara con % del local). Freep es 2 jugadores en el mismo dispositivo.
- Paleta violeta/magenta (#8100DD / #DD00A4): DESCARTADA, no volver a sugerir.

## COSTE TOKENS
Pre-generación diaria con 2-3 locales = <$0.15/día. Con 50 locales ~$60-80/mes. Deterministas (reinas/equilibrio/carta/orden/freep) = 0. Poema escala con uso (bajo demanda, ~500 tokens/uso). El reintento automático (hasta 2) puede duplicar el coste de una generación que falle, pero solo en los pocos casos que petan — impacto despreciable.

## HISTORIAL DE SESIONES (resumen)
- **18 jun 2026:** (1) Admin: email Yellow corregido vía migración, cambio de contraseña para bar_admin, botón guardar flotante, flotante a11y oculto en admin, módulo contraseña centrado en bloque blanco. (2) Análisis experto pre-salida → encontrado y resuelto el bug raíz de generación IA: parseo JSON tolerante + reintento automático + persistencia y anti-repetición en los 14 fallbacks bajo demanda. Archivos tocados: ai.py, app.py, init_db.py, templates/admin/bar_panel.html.
