---
tipo: readme
estado: activo
---
# estudio/ — el código de los editores de Prensa

El estudio de Prensa (editor de piezas, de fotos, de video y el kit de OBS) **vive aquí desde la fase 10.2b E0
(2026-10-20)**. Vino de Unancha (`unancha/editor/`, `video/` y `lib/`, en `ed5a3e5`), copiado con la suma de cada uno de
sus archivos. Unancha conserva **lo común de la identidad**: tokens, fuentes y logos, las plantillas de marcos y el
banco de ejemplo. Los editores lo leen por `UNANCHA_DIR`.

Desde E5 (2026-10-21) **no corre aparte**: son cuatro módulos de Tiqsi en el proceso de Qillqa, cada uno con su API, su
cookie, su pantalla y su arranque solo:

| módulo | qué | dónde | solo |
|---|---|---|---|
| **Wayra** | el kit de OBS | `/api/obs/` (público) | `scripts/verde.sh sola-wayra` |
| **Tullpu** | fotos por capas (`foto.html`) y el revelado (`media.html`), desde el 2026-10-21 en su repositorio (`paginas/`) | `/api/fotos/` | `sola-tullpu` |
| **Kuyuy** | video (`video.html`, desde el 2026-10-21 en su repositorio: `paginas/`) y la cola de ffmpeg, que también recorta los videos de `media.html` | `/api/videos/` | `sola-kuyuy` |
| **Awana** | piezas (`editor.html`, desde el 2026-10-21 en su repositorio: `paginas/`) y el registro de las piezas de prensa, en su base | `/api/piezas/editor/`, `/api/piezas` | `sola-awana` |

La base común de los editores (`ruray/comun.py`) porta a FastAPI, una sola vez, el enrutador de
`editor/servidor/servidor.py` y carga sus funciones de aquí; cada editor monta solo sus rutas (las de la tabla de abajo)
y sus páginas, sin tocarlas: piden todo en su propia carpeta. El puente con la Mediateca (el selector con sus fotos, la
foto materializada en el banco, lo exportado y lo subido, la limpieza de su caché y «Usar en Prensa») es
`ruray/mediateca.py`, solo por «medios.v1». `media.html` recorta un video en la carpeta que le
llega por `?video=`; los enlaces de una página a otro editor llevan a `ESTUDIO_OTRAS_PAGINAS` (una carpeta por página).
Prensa, en la web, pinta las pantallas de los editores en su propio marco.

`editor/servidor/servidor.py` sigue pudiendo correr suelto (`python3 editor/servidor/servidor.py`), para trabajar en una
página sin Qillqa. Retirar la copia vieja de Unancha es un cambio estructural aparte (normativa 3.13), con su lista, su
respaldo y su `UNDO.sh`.

## Uso

```bash
UNANCHA_DIR=… IDENTIDAD_PERFIL=…/perfil.json python3 estudio/editor/servidor/servidor.py   # suelto, sin Qillqa (el verde: la API)
python3 -m pytest -q -p no:cacheprovider estudio/tests                                    # 33 pruebas (el kit: UNANCHA_DIR o <DOCS_ROOT>/unancha)
```

## Inventario: cada archivo a su editor

| archivo | va a | nota |
|---|---|---|
| `editor.html`, `editor-avanzado.js`, `editor-avanzado.css`, `empaquetar.js`, `qr.js`, `imgbank.js`, `preprensa.py`, `embeber-foto.py`, desde el 2026-10-21 en su repositorio, Awana (`../../awana/paginas/`) | **Awana** (piezas) | `editor.html` guarda las 42 plantillas de marca que Unancha convierte a Inkscape (en Unancha, `editor.py` de sus adaptadores): pasan a Unancha como datos (plantillas base) |
| `foto.html`, `foto-lienzo.html` y miniPaint, desde el 2026-10-21 en su repositorio, Tullpu (`../../tullpu/paginas/`) | **Tullpu** (fotos) | `editor/mejorar_foto.py` queda aquí: es el motor de `POST api/mejorar-foto`, que usan Tullpu y Awana; `editor/lote_gimp.py` (corre dentro de GIMP) también, porque usa `lib/` del estudio; `embeber-foto.py` escribe en `imgbank.js`: va con Awana |
| `video.html` y ffmpeg.wasm, desde el 2026-10-21 en su repositorio, Kuyuy (`../../kuyuy/paginas/`) | **Kuyuy** (videos) | `editor/servidor/montaje.py` y `video/shorts/` (`shorts.py`, `redes.json`) quedan aquí: el servidor del estudio los importa al cargarse (la orden de ffmpeg, los subtítulos, la marca de los títulos y los ajustes por red), y `radio` cita `video/shorts` (`programa.yml`, aún en `identidad-visual`) |
| el kit de OBS (rótulos, tarjetas, overlays y pantallas), desde el 2026-10-21 en su repositorio, Wayra (`kit/`) | **Wayra** (OBS) | estáticos |
| `media.html`, desde el 2026-10-21 en Tullpu (`paginas/`) | **Tullpu** (revelar una foto suelta con plantilla); Kuyuy la abre para recortar un video suelto (`?video=`) | las plantillas siguen en Unancha |
| `editor/estudio-tema.css`, `estudio-iconos.js`, `estudio-movil.js` | **común del estudio** | el aspecto del estudio, que comparten los cuatro (con un bloque generado: abajo) |
| `editor/servidor/servidor.py`, `config.py` | se reparte por rutas (abajo) | `config.py` toma el kit de `UNANCHA_DIR` (único cambio de E0) |
| abrir-editor.sh y cerrar-editor.sh (de `editor/`) | retirados (E5) | lanzadores del servidor aparte |
| `lib/nucleo.py` | común | raíz y registro de `core/`; los nombres de los registros siguen siendo `identidad-visual.*` |
| `lib/herramientas.py` | común | Inkscape o GIMP sin interfaz, APT o Flatpak (`shorts.py portadas`, `lote_gimp.py`): copia mínima de `herramienta()` de los adaptadores de Unancha (2026-10-21) |
| `tests/test_servidor.py`, `test_montaje.py` | con su código | `test_kit.py` y `test_herramientas.py` son nuevas |

## Inventario: cada ruta del servidor

| ruta | va a |
|---|---|
| `GET /api/design` (tokens, formatos, plantillas, zonas seguras), `/plantillas/…`, `/fuentes/…`, `/fuentes-sistema/…`, `GET /api/fuentes`, `/logo/…`, `GET /api/logos` | **kit común**: lo leen los cuatro desde Unancha |
| `GET /api/health`, `GET /api/media`, `POST /api/subir`, `/banco/…`, `/miniatura/…` | **común**: el banco pasa a «medios.v1» (Rikchay); solo, cada editor usa el suyo. Hoy Qillqa intercepta `/api/media` y `/api/imagenes` para sumar la Mediateca |
| `GET\|POST /api/almacen` | **común**: el estado durable de cada editor (cada uno, sus claves) |
| `/exports/…`, `/redes/…`, `/transmisiones/…` | **común**: trabajo y salidas por canal (hoy, a la Mediateca: `/api/exportar-*` los atiende Qillqa) |
| `GET\|POST /api/imagenes` | **Awana** |
| `GET /api/proyectos-foto`, `GET\|POST /api/proyecto-foto`, `POST /api/analizar-foto`, `POST /api/mejorar-foto`, `POST /api/exportar-foto` | **Tullpu** |
| `GET /api/video-config`, `POST /api/exportar-proyecto-video`, `POST /api/plan-video`, `POST /api/subtitular-video`, `GET /api/fotograma`, `POST /api/exportar-video`, `GET /api/trabajo` (la cola de ffmpeg) | **Kuyuy** |
| `GET /api/proyectos-media`, `GET\|POST /api/proyecto-media` | `media.html`: con su parte (Tullpu o Kuyuy) |

El proxy `/estudio/` de Qillqa (api/prensa.py, del backend) y su cookie se retiraron en E5: lo que atendía (`/api/fototeca-pieza`,
`/api/fototeca-video`, lo exportado, «Usar en Prensa») lo atiende cada editor con el puente. Las **piezas de prensa**
(`prensa_piezas`) son de Awana, en `/api/piezas`, con su base.

## El bloque generado de los colores

Los colores de `estudio-tema.css` (y los de `editor.html` y `media.html`, que vigilan Awana y Tullpu en
`../../awana/tests/test_paginas.py` y `../../tullpu/tests/test_paginas.py`) son bloques
**generados** por Unancha (su `generar.py` de adaptadores, desde sus tokens), que hoy los escribe en **su** copia
del editor. `tests/test_kit.py` comprueba que los de aquí sean los que hoy da Unancha: si cambia un token, falla, y los
bloques se copian de allá. Desde E2–E4, cada editor los genera él mismo desde los tokens, y Unancha deja de escribir en
el código de los editores.
