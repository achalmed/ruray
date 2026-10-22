---
tipo: readme
estado: activo
---
# servidor/ — servidor local que vincula los dos editores con el perfil (config.py + servidor.py)

Pieza que **vincula LOS DOS editores** (`editor.html` publicaciones ·
`media.html` fotos y videos) con las carpetas del perfil de marca: banco de
imágenes y videos, marcos, logos, tipografías, salidas por canal y almacén de estado.
Las rutas por defecto de `config.py` salen del kit común (Unancha, `UNANCHA_DIR`: sus recursos, sus plantillas de
marcos y sus tokens); el `perfil.json` al que apunta
`IDENTIDAD_PERFIL` las sustituye por las de su clave `rutas` (`banco`, `fuentes`, `logos`,
`plantillas_media`, `redes`, `transmisiones`, `exports`, `almacen`, `proyectos_media`,
`imgbank`). En Qillqa no corre aparte: la base común de los editores (`ruray/comun.py`) carga
sus funciones en la API (fase 10.2b E5, 2026-10-21; sus lanzadores se retiraron). Suelto, para trabajar en una página sin
Qillqa: `python3 servidor.py`.

## Archivos
- **`config.py`** — todo lo configurable (puerto, HOST, carpetas, exclusiones,
  extensiones de imagen y video). **Edita solo aquí.**
- **`servidor.py`** — la lógica (Python estándar, sin dependencias obligatorias;
  Pillow si está = miniaturas rápidas; ffmpeg = exportar video). No requiere edición.
- **`montaje.py`** — del proyecto de `video.html` a la orden de ffmpeg (función pura, sin E/S; pruebas en
  `../../tests/test_montaje.py`). Reutiliza `../../video/shorts/shorts.py` (subtítulos palabra a palabra, tokens, sonoridad).

## Qué expone
| Ruta | Método | Para qué |
|------|--------|----------|
| `/api/health` | GET | Los editores detectan el servidor (`{ok, media, ffmpeg}`). |
| `/api/imagenes` | GET | Lista viva de imágenes: `[{name, url, credito}]`. |
| `/api/media` | GET | Lo mismo + videos y audios: `{imagenes, videos, audios}`. |
| `/api/design` | GET | Tokens de color, formatos, zonas seguras, plantillas y fuentes (para `media.html`; nada se duplica en el JS). Su `marca` trae `organizacion`, `titular`, **`textos`** (los marcadores `{{titular}}`, `{{cargo}}`, `{{region}}`, `{{sede}}`, `{{lugar}}`, `{{organizacion}}`, `{{institucion}}`, `{{entidad}}`, `{{correo}}`, `{{web}}`, `{{lema}}` del perfil, o neutros) y **`logos`** (`[{nombre, name, url}]`, la única lista de logos). |
| `/api/fuentes` | GET | `{fuentes:[{familia, familia_legado, subfamilia, peso, cursiva, escala_ass, ascenso_ass, archivo, url, origen, marca}], familias_marca, textos}`: las tipografías de `rutas.fuentes` y, si una familia de la marca (la que pide el ASS) no está ahí pero sí instalada en la máquina (`fc-list`), ese archivo (`/fuentes-sistema/<id>/<archivo>`, solo los anunciados). `escala_ass` y `ascenso_ass` (de las tablas OS/2 y head) dejan que la vista previa de `video.html` mida como libass. |
| `/fuentes-sistema/<id>/<archivo>` | GET | Una tipografía de la marca instalada en el sistema, de las que listó `/api/fuentes` (nunca una ruta libre). |
| `/api/fotograma?origen=&t=&alto=` | GET | Miniatura JPEG del cuadro `t` (s) de un video servido (24–360 px de alto; caché en `<exports>/tmp/fotogramas`); de una imagen, la imagen. Para las tiras de la línea de tiempo de `video.html`. `404` sin ffmpeg o con un medio desconocido. |
| `/banco/<ruta>` | GET | Archivos del banco — con **Range** (los videos se pueden recorrer). |
| `/miniatura/<ruta>` | GET | Miniatura ligera con caché (o el original si no hay Pillow). |
| `/plantillas/<ruta>` | GET | Overlays PNG de la carpeta de marcos (`rutas.plantillas_media`). |
| `/fuentes/<archivo>` | GET | Tipografías de `rutas.fuentes`. |
| `/exports/<ruta>` | GET | Carpeta de trabajo del editor (ruta `exports` del perfil; descargas de temporales). |
| `/redes/<canal>/<archivo>` | GET | Piezas finales por canal (`rutas.redes/<canal>`). |
| `/transmisiones/<archivo>` | GET | Grabaciones EN VIVO (`rutas.transmisiones`). |
| `/api/imagenes` | POST | Sube imagen `{filename, dataURL}` a `<banco>/subidas-editor/`. |
| `/api/subir` | POST | Sube foto, **video** o audio (cuerpo binario + cabecera `X-Nombre`). |
| `/api/exportar-foto` | POST | Guarda la pieza en el **canal** elegido (`rutas.redes/<canal>`) **y** la copia a `editadas-editor/` del banco con su crédito. |
| `/api/exportar-video` | POST | Recorte + overlay con ffmpeg en segundo plano → `{trabajo}`. |
| `/api/trabajo?id=` | GET | Estado del trabajo de video (`procesando/listo/error`; los de `video.html` traen también `etapa` y `progreso` 0–1). |
| `/api/video-config` | GET | Para `video.html`: redes de `../../video/shorts/redes.json`, canales, colores y tipografías de los títulos (tokens vía `shorts.Marca`), `tipografias` (lo mismo que `/api/fuentes`), `idiomas` de Whisper (`destacados`, `todos`, `sin_soporte`), si hay ffmpeg y Whisper. |
| `/api/exportar-proyecto-video` | POST | `{proyecto, nombre, canal, normalizar, calidad}` → `{trabajo}`. `montaje.py` convierte el proyecto (pistas y clips) en **una** orden de ffmpeg (trim, setpts, recorte, escala, overlay, transiciones, títulos ASS con libass, mezcla con ducking, `loudnorm` a −14 LUFS) que corre en la misma cola (un ffmpeg, `nice`, tiempo máximo); el MP4 cae en `rutas.redes/<canal>`. |
| `/api/plan-video` | POST | `{proyecto}` → la misma orden con nombres del sistema de archivos de ffmpeg.wasm (`/in/…`, `/trabajo/titulos.ass`, `/fuentes`) y qué archivos cargar: el render en el navegador. |
| `/api/subtitular-video` | POST | `{origen, entrada, duracion, modelo, idioma}` → `{trabajo}` con `palabras` y `grupos` (Whisper por palabra, `shorts.transcribir` y `shorts.grupos_de_palabras`). `idioma`: un código de `whisper --language` (`es` por omisión) o `auto` (detección). Whisper **no** reconoce quechua (`qu`) ni aimara (`ay`): no se ofrecen. |
| `/api/proyecto(s)-media` | GET/POST | Guardar/listar/cargar proyectos del editor de medios. |
| `/api/proyecto(s)-foto` | GET/POST | Guardar/listar/cargar proyectos con capas del editor de fotos (`foto.html`, JSON de miniPaint) en `rutas.proyectos_foto`. |
| `/api/logos` | GET | **Alias anterior** de `/api/design` → `marca.logos` (la misma lista, en la forma `[{name, url}]`); se conserva para clientes viejos. Código nuevo: `marca.logos`. |
| `/api/almacen` | GET | Todo el estado durable de los editores en una lectura: `{ok, claves:{clave:datos}}`. |
| `/api/almacen` | POST | Guarda estado en disco (`estado-editor/<clave>.json`): `{clave,datos}` · `{claves:{…}}` (varias) · `{clave,borrar:true}`. Escritura **atómica**; responde **500** si algo no llegó al disco (nunca finge éxito). |
| `/api/analizar-foto` | POST | `{origen\|dataURL}` → veredicto de calidad (`etiqueta`, `motivo`, `necesita`, resolución, ruido, blockiness). |
| `/api/mejorar-foto` | POST | `{origen\|dataURL, nivel, nitidez, ruido, claridad, contraste, color, luz, resolucion}` → realza la foto con el motor `mejorar_foto.py` (subproceso) y devuelve la **URL cacheada** (`/exports/mejoradas/…`). **NO destructivo**: la original no se toca. |
| (resto) | GET | Estáticos del editor (`editor.html`, `media.html`, `imgbank.js`…). |

## Seguridad
- Por defecto escucha **solo en localhost**. Para usarlo desde otras
  computadoras del despacho: `HOST = "0.0.0.0"` en `config.py` (red local
  confiable solamente; no exponer a internet).
- **Host y Origin** (DNS rebinding y CSRF; el servidor no tiene cuentas): `Host` debe ser
  `127.0.0.1`, `localhost` o uno de `IDENTIDAD_ORIGENES` (lista separada por comas; con
  `HOST = "0.0.0.0"`, cualquiera); si llega `Origin`, debe ser el mismo sitio o uno de esa lista.
  Si no, `403`.
- Los POST de JSON exigen `Content-Type: application/json` (`415`): un formulario o un
  `text/plain` de otra página no llegan. Topes de cuerpo: `IDENTIDAD_MAX_JSON_MB` (80) y
  `IDENTIDAD_MAX_SUBIDA_MB` (2048) → `413`.
- Exportar video: **un ffmpeg a la vez** (los demás esperan, `cola: true` en `/api/trabajo`), con
  `nice` y tiempo máximo `IDENTIDAD_TIEMPO_VIDEO` (1800 s); los trabajos terminados se olvidan a la hora.
- Bloquea salir de las carpetas servibles (path traversal → `403`) y no sirve su propio
  código (`/servidor/*` → `404`).
- Los nombres de archivo subidos se sanean; nunca sobrescribe (añade `-1`, `-2`…).

## Detrás de un proxy (prefijo)
Otro sistema puede publicarlo bajo una carpeta (Qillqa lo publica en `/estudio/`, módulo Prensa):
el servidor antepone a **toda URL que emite** (`/banco/`, `/miniatura/`, `/plantillas/`, `/fuentes/`,
`/logo/`, `/exports/`, `/redes/`, `/transmisiones/`) el prefijo de la cabecera `X-Forwarded-Prefix` o,
si falta, de `IDENTIDAD_BASE`; las URL que vuelven del navegador (origen de una mejora o de un video) se
aceptan con o sin él. Los dos editores piden sus rutas relativas a la página (`api()` en `media.html`,
rutas sin `/` inicial en `editor.html`). Sin cabecera ni variable, todo es como siempre. Si el `/api/health` que ve el
editor trae `fototeca: true` (lo añade el proxy de Qillqa), el diálogo Exportar de `editor.html` ofrece
«Guardar en la Fototeca» (`POST api/fototeca-pieza`, que atiende Qillqa, no este servidor); `foto.html` y
`video.html` hacen lo mismo con sus resultados (ver §Fototeca). Pruebas: `../../tests/test_servidor.py`.

## Fototeca (contrato con Qillqa)

Estas rutas las **atiende el proxy de Qillqa**, no este servidor; los editores las piden relativas a la página
(`api/…`) solo si `/api/health` trae `fototeca: true`.

| ruta | quién la llama | cuerpo (JSON) | respuesta |
|------|----------------|---------------|-----------|
| `POST api/fototeca-pieza` | `editor.html`, `foto.html` | `{titulo, dataURL, origenes, fotos}` | `{ok, nueva, numero}` |
| `POST api/fototeca-video` | `video.html` (tras exportar) | `{trabajo, url, archivo, titulo, duracion, ancho, alto, canal}` | `{ok, numero?, nueva?}` |

`api/fototeca-video` (nuevo): el MP4 ya está en disco; el estudio **no** lo reenvía. Qillqa lo localiza por
`url` (pública, con o sin el prefijo `/estudio`: `/redes/<canal>/<archivo>` o `/banco/subidas-editor/<archivo>`
si se compuso en el navegador) o, si prefiere, por `trabajo` con `GET /api/trabajo?id=` (el trabajo vive una
hora: `estado`, `url`, `archivo`, `duracion`); `duracion` (s), `ancho` y `alto` (px) y `canal` son informativos.
Para leer el archivo, Qillqa lo pide a este servidor por esa misma URL (admite `Range`). Respuestas que el
estudio entiende: `200 {ok:true, numero}` → «En la Fototeca (n.º N)»; `404`, `405` o `501` → aviso amable («la
Fototeca todavía no recibe videos»; el video ya quedó en la salida de redes); otro error → `{error|detail}` en
un aviso, y el botón vuelve a quedar disponible.

## Teléfono

`estudio-movil.js` (en los cuatro editores) pasa los paneles a cajones en pantallas de 760 px o menos; no
cambia nada del servidor.

## Comprobación rápida
```bash
python3 -m py_compile editor/servidor/servidor.py editor/servidor/config.py   # sintaxis
curl -s http://127.0.0.1:8099/api/health                                      # con el servidor arriba
```
