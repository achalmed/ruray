#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Servidor local del Editor de piezas (publicaciones) y del Editor de fotos/videos.

Sirve los dos editores y los VINCULA con las carpetas reales del despacho:
banco de imágenes/videos, plantillas de marcos, tokens y tipografías.

Endpoints del editor de publicaciones (editor.html) — sin cambios:
  GET  /api/health     -> {"ok": true, ...}
  GET  /api/imagenes   -> [ {name, url, credito}, ... ]
  GET  /banco/<ruta>   -> archivo del banco (ahora también videos, con Range)
  POST /api/imagenes   -> guarda una imagen subida ({filename, dataURL})

Endpoints del editor de fotos/videos (media.html):
  GET  /api/design           -> tokens + formatos + plantillas + zonas seguras
  GET  /api/media            -> {imagenes: [...], videos: [...]} del banco
  GET  /plantillas/<ruta>    -> overlays PNG de plantillas/marco_foto_video
  GET  /fuentes/<archivo>    -> tipografías (tipografia)
  GET  /exports/<ruta>       -> carpeta de trabajo del editor (../_trabajo)
  GET  /redes/<canal>/<f>    -> pieza final por canal · /transmisiones/<f> -> EN VIVO
  POST /api/subir            -> sube foto o VIDEO al banco (cuerpo binario,
                                cabeceras X-Nombre y Content-Type)
  POST /api/exportar-foto    -> guarda el PNG/JPG final en el canal elegido (prensa/redes/<canal>) y lo copia
                                al banco (editadas-editor/) con su crédito
  POST /api/exportar-video   -> recorta + superpone overlay con ffmpeg (en
                                segundo plano); devuelve {trabajo}
  GET  /api/trabajo?id=...   -> estado del trabajo de video
  POST /api/proyecto-media   -> guarda un proyecto {nombre, datos}
  GET  /api/proyectos-media  -> lista de proyectos guardados
  GET  /api/proyecto-media?nombre=... -> contenido de un proyecto

Endpoints del editor de video (video.html, línea de tiempo con pistas; montaje.py arma la orden):
  GET  /api/video-config     -> redes, canales, marca de los títulos, ffmpeg/whisper disponibles
  POST /api/exportar-proyecto-video -> {proyecto, nombre, canal, normalizar, calidad} → {trabajo}
                                (un ffmpeg a la vez, nice, tiempo máximo; progreso en /api/trabajo)
  POST /api/plan-video       -> {proyecto} → orden para ffmpeg.wasm (render en el navegador)
  POST /api/subtitular-video -> {origen, entrada, duracion, modelo} → {trabajo} con palabras y grupos
                                (Whisper, como video/shorts/shorts.py subtitular)
  (/api/media lista también «audios»; /api/subir acepta audio)

Endpoints del editor de fotos (foto.html, miniPaint con capas):
  GET  /api/logos            -> [ {name, url}, ... ] imágenes de la carpeta de logos del perfil
  POST /api/proyecto-foto    -> guarda un proyecto con capas {nombre, datos}
  GET  /api/proyectos-foto   -> lista de proyectos de fotos guardados
  GET  /api/proyecto-foto?nombre=... -> contenido de un proyecto de fotos

Almacén durable de estado (ambos editores) — reemplaza a localStorage como
FUENTE DE VERDAD (permanente, sobrevive a cerrar el navegador/limpiar su caché):
  GET  /api/almacen          -> {ok, claves:{clave:datos,...}} todo el estado
  POST /api/almacen          -> guarda {clave,datos} | {claves:{...}} | {clave,borrar:true}
                                (responde 500 si algo no se pudo escribir en disco)

Mejora automática de fotos (motor mejorar_foto.py como subproceso; NO destructivo):
  POST /api/analizar-foto    -> {origen|dataURL} -> veredicto de calidad (¿mejorar?)
  POST /api/mejorar-foto     -> {origen|dataURL, nivel, sliders} -> {url mejorada cacheada}

Detrás de un proxy (p. ej. Qillqa en /estudio/): toda URL emitida lleva el prefijo de
X-Forwarded-Prefix (o IDENTIDAD_BASE). Seguridad: Host y Origin locales o de
IDENTIDAD_ORIGENES, POST JSON solo con application/json, topes de cuerpo
(IDENTIDAD_MAX_JSON_MB, IDENTIDAD_MAX_SUBIDA_MB) y un ffmpeg a la vez con nice y tiempo
máximo (IDENTIDAD_TIEMPO_VIDEO). Sin esas variables, todo funciona como siempre.

Sin dependencias externas (solo librería estándar; ffmpeg como programa).
Escucha en config.HOST (127.0.0.1 por defecto; "0.0.0.0" para la red local).
Para configurar rutas/puerto usa config.py, no este archivo.
"""
import os
import sys
import json
import base64
import re
import shutil
import subprocess
import threading
import time
import mimetypes
import unicodedata
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, quote, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # raíz del repo: lib/nucleo
from lib import nucleo  # noqa: E402  raíz y logger de core/ (RQ-COD-06)

log = nucleo.registro("identidad-visual.servidor")

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import config  # noqa: E402

# Pillow es OPCIONAL: si está, el banco sirve miniaturas ligeras (rápido);
# si no, se sirven los archivos originales (el editor sigue funcionando).
try:
    from PIL import Image as _PILImage, ImageOps as _PILImageOps
except Exception:
    _PILImage = None


def ruta_abs(rel):
    return os.path.normpath(os.path.join(AQUI, rel))


def _cfg(nombre, defecto):
    return getattr(config, nombre, defecto)


DIR_EDITOR = ruta_abs(config.CARPETA_EDITOR)
DIR_BANCO = ruta_abs(config.CARPETA_BANCO)
DIR_SUBIDAS = os.path.join(DIR_BANCO, config.SUBCARPETA_SUBIDAS)
DIR_PLANTILLAS = ruta_abs(_cfg("CARPETA_PLANTILLAS_MEDIA",
                               "../../plantillas/marco_foto_video"))
DIR_TOKENS = ruta_abs(_cfg("CARPETA_TOKENS", "../../tokens"))
DIR_FUENTES = ruta_abs(_cfg("CARPETA_FUENTES", "../../logos-y-tipografias"))
DIR_EXPORTS = ruta_abs(_cfg("CARPETA_EXPORTS", "../_trabajo"))
DIR_REDES = ruta_abs(_cfg("CARPETA_REDES", "../../prensa/redes"))
DIR_TRANSMISIONES = ruta_abs(_cfg("CARPETA_TRANSMISIONES", "../../prensa/transmisiones"))
CANALES = _cfg("CANALES", ["facebook", "instagram", "tiktok", "estados", "x", "youtube", "linkedin"])
DIR_PROYECTOS = os.path.join(DIR_EDITOR, _cfg("CARPETA_PROYECTOS_MEDIA",
                                              "proyectos-media"))
DIR_ALMACEN = os.path.join(DIR_EDITOR, _cfg("CARPETA_ALMACEN", "estado-editor"))
DIR_PROYECTOS_FOTO = os.path.join(DIR_EDITOR, _cfg("CARPETA_PROYECTOS_FOTO", "proyectos-foto"))
# Mejora automática de fotos: motor (script) y caché NO destructiva de resultados.
SCRIPT_MEJORA = os.path.join(DIR_EDITOR, "mejorar_foto.py")
DIR_MEJORADAS = os.path.join(DIR_EXPORTS, _cfg("SUBCARPETA_MEJORADAS", "mejoradas"))
DIR_LOGOS = ruta_abs(_cfg("CARPETA_LOGOS", "../../logos-y-tipografias"))
DIR_EDITADAS = os.path.join(DIR_BANCO, _cfg("SUBCARPETA_EDITADAS",
                                            "editadas-editor"))

EXTS = tuple(e.lower() for e in config.EXTENSIONES)
EXTS_VIDEO = tuple(e.lower() for e in _cfg("VIDEO_EXTENSIONES",
                                           [".mp4", ".mov", ".webm", ".m4v"]))
EXTS_AUDIO = tuple(e.lower() for e in _cfg("AUDIO_EXTENSIONES",
                                           [".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac"]))

mimetypes.add_type("image/avif", ".avif")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/quicktime", ".mov")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/otf", ".otf")
# Editor de video: audio del banco y ffmpeg.wasm (módulos ES y WebAssembly).
for _t, _e in (("audio/mpeg", ".mp3"), ("audio/mp4", ".m4a"), ("audio/wav", ".wav"), ("audio/ogg", ".ogg"),
               ("audio/aac", ".aac"), ("audio/flac", ".flac"), ("application/wasm", ".wasm"),
               ("text/javascript", ".js"), ("text/javascript", ".mjs")):
    mimetypes.add_type(_t, _e)

# Trabajos de exportación de video en segundo plano: {id: {...}}
TRABAJOS = {}
TRABAJOS_LOCK = threading.Lock()
# Un solo ffmpeg a la vez (los demás esperan su turno), con prioridad baja y tiempo máximo:
# varios videos en paralelo saturaban la máquina que además sirve otros sistemas.
SEMAFORO_VIDEO = threading.BoundedSemaphore(1)
TIEMPO_MAX_VIDEO = int(os.environ.get("IDENTIDAD_TIEMPO_VIDEO", "1800"))   # segundos por exportación
VIDA_TRABAJO = 3600            # un trabajo terminado se olvida una hora después
# Topes del cuerpo de una petición: JSON (piezas y overlays en dataURL) y subida binaria.
MAX_JSON = int(os.environ.get("IDENTIDAD_MAX_JSON_MB", "80")) * 1024 * 1024
MAX_SUBIDA = int(os.environ.get("IDENTIDAD_MAX_SUBIDA_MB", "2048")) * 1024 * 1024


# ------------------------------------------------- prefijo público y orígenes
#
# Detrás de un proxy que lo publica bajo una carpeta (p. ej. Qillqa en /estudio/), toda
# URL que emite el servidor lleva ese prefijo: lo da la cabecera X-Forwarded-Prefix de la
# petición o, si falta, IDENTIDAD_BASE. Sin ninguno de los dos, nada cambia («/banco/…»).
# Las URL que vuelven del navegador (origen de una mejora o de un video) se aceptan con
# el prefijo o sin él.

_LOCAL = threading.local()
_PREFIJO_RE = re.compile(r"^(/[A-Za-z0-9._~\-]+)+$")


def normalizar_prefijo(valor):
    """'/estudio/' → '/estudio'; '' o algo raro (.., //, espacios) → ''."""
    v = (valor or "").strip().rstrip("/")
    if not v or ".." in v or not _PREFIJO_RE.match(v):
        return ""
    return v


BASE_ENTORNO = normalizar_prefijo(os.environ.get("IDENTIDAD_BASE", ""))


def prefijo():
    """El prefijo de la petición en curso (hilo actual) o el de IDENTIDAD_BASE."""
    return getattr(_LOCAL, "prefijo", BASE_ENTORNO)


def pub(url):
    """URL pública: «/banco/x» → «<prefijo>/banco/x»."""
    return prefijo() + url


def sin_prefijo(url, pref=None):
    """Quita el prefijo público de una URL recibida del navegador (si lo trae)."""
    pref = prefijo() if pref is None else pref
    url = url or ""
    for p in {pref, BASE_ENTORNO}:
        if p and (url == p or url.startswith(p + "/")):
            return url[len(p):]
    return url


def _hosts_permitidos():
    """Nombres de host aceptados (Host y Origin): locales + IDENTIDAD_ORIGENES."""
    extra = [h.strip() for h in os.environ.get("IDENTIDAD_ORIGENES", "").split(",") if h.strip()]
    hosts = {"127.0.0.1", "localhost", "::1", "[::1]"}
    for h in extra:
        h = re.sub(r"^https?://", "", h).split("/", 1)[0]
        hosts.add(h.rsplit(":", 1)[0] if not h.startswith("[") else h.split("]")[0] + "]")
    return hosts


def nombre_host(valor):
    """'127.0.0.1:8099' → '127.0.0.1'; 'http://localhost:8099' → 'localhost'; '[::1]:80' → '[::1]'."""
    v = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", (valor or "").strip().lower()).split("/", 1)[0]
    if v.startswith("["):
        return v.split("]")[0] + "]"
    return v.rsplit(":", 1)[0] if ":" in v else v


def peticion_permitida(metodo, host, origen, red_local=False):
    """Defensa contra DNS rebinding y CSRF (el servidor no tiene cuentas):
    · Host debe ser local o de IDENTIDAD_ORIGENES (en modo red local, HOST=0.0.0.0, cualquiera);
    · si llega Origin (el navegador lo pone en todo POST), debe ser el mismo sitio que Host o
      uno de IDENTIDAD_ORIGENES; «null» (archivo local, iframe aislado) se rechaza al escribir."""
    permitidos = _hosts_permitidos()
    if not red_local and nombre_host(host) not in permitidos:
        return False
    if origen:
        if origen == "null":
            return metodo == "GET"
        o = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", origen.strip().lower()).split("/", 1)[0]
        if o != (host or "").strip().lower() and nombre_host(origen) not in permitidos:
            return False
    return True


def es_json(content_type):
    return (content_type or "").split(";", 1)[0].strip().lower() == "application/json"


def limpiar_trabajos(ahora=None):
    """Olvida los trabajos de video terminados hace más de VIDA_TRABAJO segundos."""
    ahora = ahora or time.time()
    with TRABAJOS_LOCK:
        for k in [k for k, t in TRABAJOS.items()
                  if t.get("estado") in ("listo", "error") and ahora - t.get("fin", ahora) > VIDA_TRABAJO]:
            del TRABAJOS[k]


def dentro_de(base, objetivo):
    """True si 'objetivo' queda dentro de 'base' (blindaje contra path traversal)."""
    base = os.path.abspath(base)
    objetivo = os.path.abspath(objetivo)
    return objetivo == base or objetivo.startswith(base + os.sep)


def slug(texto):
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return s.lower().replace(" ", "_").replace("/", "-")


def cargar_creditos():
    p = os.path.join(DIR_BANCO, config.ARCHIVO_CREDITOS)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def anotar_credito(rel, texto):
    """Añade el crédito de una pieza exportada a creditos.json (regla F10)."""
    p = os.path.join(DIR_BANCO, config.ARCHIVO_CREDITOS)
    try:
        creditos = cargar_creditos()
        if rel not in creditos:
            creditos[rel] = texto
            with open(p, "w", encoding="utf-8") as f:
                json.dump(creditos, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # el crédito es deseable, no bloqueante


def _recorrer_banco(extensiones):
    creditos = cargar_creditos()
    items = []
    if not os.path.isdir(DIR_BANCO):
        return items
    for raiz, dirs, archivos in os.walk(DIR_BANCO):
        dirs[:] = sorted(d for d in dirs
                         if d not in config.EXCLUIR and not d.startswith("."))
        if not config.RECURSIVO and raiz != DIR_BANCO:
            continue
        for nombre in sorted(archivos):
            if not nombre.lower().endswith(extensiones):
                continue
            abs_ = os.path.join(raiz, nombre)
            rel = os.path.relpath(abs_, DIR_BANCO)
            rel_url = "/".join(quote(seg) for seg in rel.split(os.sep))
            partes = rel.split(os.sep)
            carpeta = partes[0] if len(partes) > 1 else ""
            items.append({
                "name": rel.replace(os.sep, " / "),
                "url": pub("/banco/" + rel_url),
                "credito": creditos.get(nombre) or creditos.get(rel) or "",
                "carpeta": carpeta,
            })
    return items


def listar_imagenes():
    return _recorrer_banco(EXTS)


def listar_media():
    return {"imagenes": _recorrer_banco(EXTS),
            "videos": _recorrer_banco(EXTS_VIDEO),
            "audios": _recorrer_banco(EXTS_AUDIO)}


def listar_logos(tope=200):
    """Imágenes de la carpeta de logos (la del perfil o la del repo): UNA sola lista para los editores.
    La sirven `/api/design` → `marca.logos` (la vigente) y `/api/logos` (alias anterior, misma lista).
    Cada logo: {nombre (sin extensión), name (ruta relativa legible), url}."""
    items = []
    if not os.path.isdir(DIR_LOGOS):
        return items
    for raiz, dirs, archivos in os.walk(DIR_LOGOS):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for nombre in sorted(archivos):
            if nombre.lower().endswith((".png", ".svg", ".webp", ".jpg", ".jpeg")) and len(items) < tope:
                rel = os.path.relpath(os.path.join(raiz, nombre), DIR_LOGOS)
                items.append({"nombre": os.path.splitext(nombre)[0], "name": rel.replace(os.sep, " / "),
                              "url": pub("/logo/" + "/".join(quote(s) for s in rel.split(os.sep)))})
    return items


def listar_proyectos(carpeta):
    """[{nombre, fecha}] de los proyectos .json de una carpeta (editor de medios o de fotos)."""
    items = []
    if os.path.isdir(carpeta):
        for n in sorted(os.listdir(carpeta)):
            if n.endswith(".json"):
                p = os.path.join(carpeta, n)
                items.append({"nombre": os.path.splitext(n)[0],
                              "fecha": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")})
    return items


def sanear_nombre(nombre):
    """Deja solo el nombre de archivo, sin rutas ni caracteres raros (conserva acentos)."""
    nombre = os.path.basename(nombre or "").strip() or "imagen.png"
    nombre = re.sub(r"[^\w.\- ]", "_", nombre, flags=re.UNICODE)
    return nombre


def ruta_libre(path):
    """Si 'path' ya existe, devuelve path-1, path-2, ... para no sobrescribir."""
    if not os.path.exists(path):
        return path
    raiz, ext = os.path.splitext(path)
    i = 1
    while os.path.exists("%s-%d%s" % (raiz, i, ext)):
        i += 1
    return "%s-%d%s" % (raiz, i, ext)


def dir_canal(canal):
    """Carpeta de SALIDA para un canal: prensa/redes/<canal> (o prensa/transmisiones)."""
    c = slug(canal or "")
    if c == "transmisiones":
        return DIR_TRANSMISIONES
    if c in CANALES:
        return os.path.join(DIR_REDES, c)
    return DIR_REDES  # canal no reconocido → raíz de redes


def url_canal(salida, canal):
    """URL para servir un archivo guardado en el canal indicado."""
    c = slug(canal or "")
    nombre = quote(os.path.basename(salida))
    if c == "transmisiones":
        return pub("/transmisiones/" + nombre)
    if c in CANALES:
        return pub("/redes/" + quote(c) + "/" + nombre)
    return pub("/redes/" + nombre)


# ----------------------------------------------------------- design (tokens)


def _leer_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _listar_plantillas():
    """URLs de los overlays PNG generados en plantillas/marco_foto_video."""
    out = {"marcos": {}, "bandas": {}, "rotulos_16x9": {}, "rotulos_tiktok": {},
           "mosca": "", "monograma": ""}

    def url(rel):
        return pub("/plantillas/" + "/".join(quote(s) for s in rel.split(os.sep)))

    # El MODO es el sufijo del nombre: marco_<formato>[_<modo>].png (sin sufijo
    # = "tinta"). El formato siempre termina en <ancho>x<alto> (o 16x9/9x16 en
    # bandas), lo que permite separar formato de modo sin lista cerrada: los
    # estilos nuevos de generar_marcos.py se descubren solos.
    d = os.path.join(DIR_PLANTILLAS, "marcos_foto")
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            m = re.match(r"marco_(.+?_\d+x\d+)(?:_([a-z0-9]+))?\.png$", n)
            if m:
                clave, modo = m.group(1), (m.group(2) or "tinta")
                out["marcos"].setdefault(clave, {})[modo] = url("marcos_foto/" + n)

    d = os.path.join(DIR_PLANTILLAS, "overlays_video", "bandas")
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            m = re.match(r"marco_(banda\w*?(?:16x9|9x16))(?:_([a-z0-9]+))?\.png$", n)
            if m:
                clave, modo = m.group(1), (m.group(2) or "tinta")
                out["bandas"].setdefault(clave, {})[modo] = \
                    url("overlays_video/bandas/" + n)

    d = os.path.join(DIR_PLANTILLAS, "overlays_video", "rotulos")
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            u = url("overlays_video/rotulos/" + n)
            m = re.match(r"rotulo_16x9(?:_(.+))?\.png$", n)
            if m:
                out["rotulos_16x9"][m.group(1) or ""] = u
                continue
            m = re.match(r"rotulo_tiktok_9x16(?:_(.+))?\.png$", n)
            if m:
                out["rotulos_tiktok"][m.group(1) or ""] = u

    d = os.path.join(DIR_PLANTILLAS, "overlays_video", "mosca")
    if os.path.isdir(d):
        if os.path.exists(os.path.join(d, "mosca_horizontal.png")):
            out["mosca"] = url("overlays_video/mosca/mosca_horizontal.png")
        if os.path.exists(os.path.join(d, "monograma_am.png")):
            out["monograma"] = url("overlays_video/mosca/monograma_am.png")
    return out


def api_design():
    """Todo lo que el editor de medios necesita, derivado de las fuentes de
    verdad: tokens (colores/layout), config.json de las plantillas, y los
    overlays generados. Nada de esto se duplica en el JS."""
    colores = _leer_json(os.path.join(DIR_TOKENS, "colors.json"))
    layout = _leer_json(os.path.join(DIR_TOKENS, "layout.json"))
    cfg_marco = _leer_json(os.path.join(DIR_PLANTILLAS, "config.json"))

    # Sin valores de reserva: tokens/colors.json es el único maestro (I1); si falta una clave, es un error.
    e = colores["escalas"]
    fondos = colores["fondos"]
    col = {
        "puka": e["puka"]["600"],
        "qillu": e["qillu"]["400"],
        "vino": e["puka"]["800"],
        "tinta": fondos["tinta"]["hex"],
        "papel": fondos["papel"]["hex"],
        "blanco": fondos["blanco"]["hex"],
        "texto": colores["roles"]["texto_principal"]["hex"],
        "neutral300": e["neutral"]["300"],
        "neutral600": e["neutral"]["600"],
        # pasos extra que usan los MARCOS NATIVOS del editor de medios
        "puka700": e["puka"]["700"],
        "qillu300": e["qillu"]["300"],
        "qillu900": e["qillu"]["900"],
        "neutral200": e["neutral"]["200"],
    }

    # Insumos gráficos para los marcos nativos (solo los que existan en disco)
    insumos = {}
    for clave, (base_dir, rel, url_pref) in {
        "logo_color": (DIR_LOGOS, "isotipo/imagotipo-congreso-edificio.png", "/logo/"),
        "logo_blanco": (DIR_LOGOS, "isotipo/imagotipo-congreso-edificio-blanco.png", "/logo/"),
        "obelisco": (DIR_BANCO, "_recursos/ilustraciones/obelisco-quinua-blanco.png", "/banco/"),
        "lema": (DIR_BANCO, "_recursos/ilustraciones/lema-solo-el-pueblo.png", "/banco/"),
        "lema_oscuro": (DIR_BANCO, "_recursos/ilustraciones/lema-solo-el-pueblo-oscuro.png", "/banco/"),
        "recorte": (DIR_BANCO, "titular-cuerpo-transparente.png", "/banco/"),
    }.items():
        if os.path.exists(os.path.join(base_dir, rel)):
            insumos[clave] = pub(url_pref + "/".join(quote(s) for s in rel.split("/")))

    story = layout.get("formatos", {}).get("story_1080x1920", {})
    zonas = {
        "story_sup": story.get("zona_segura_superior_px", 250),
        "story_inf": story.get("zona_segura_inferior_px", 340),
        "story_lat": story.get("margen_lateral_px", 96),
        # La franja derecha que ocupa la botonera de TikTok no está en los
        # tokens (dato de la app, no de la marca): se fija aquí.
        "tiktok_der": 140,
        "margen_post": layout.get("formatos", {}).get("social_1080", {})
                             .get("margen_seguridad_px", 80),
    }

    fuentes = {}
    if os.path.isdir(DIR_FUENTES):
        for n in sorted(os.listdir(DIR_FUENTES)):
            if n.lower().endswith((".ttf", ".otf")):
                fuentes[os.path.splitext(n)[0]] = pub("/fuentes/" + quote(n))

    return {
        "ok": True,
        "colores": col,
        "zonas": zonas,
        "textos": cfg_marco.get("textos", {}),
        "formatos_foto": {k: v for k, v in
                          cfg_marco.get("formatos_foto", {}).items()
                          if not k.startswith("_")},
        "formatos_video": {k: v for k, v in
                           cfg_marco.get("formatos_video", {}).items()
                           if not k.startswith("_")},
        "plantillas": _listar_plantillas(),
        "insumos": insumos,
        "fuentes": fuentes,                 # {nombre de archivo: url} (forma anterior; la vigente es /api/fuentes)
        "marca": _marca_perfil(),
    }


# Textos del perfil que rellenan los marcadores {{…}} de las plantillas y del editor de piezas. Si el perfil
# no trae una clave, vale el texto neutro: el repo no conoce a ningún cliente (docs/decisiones.md §3.1).
TEXTOS_NEUTROS = {"titular": "Nombre Apellido", "cargo": "Cargo o circunscripción",
                  "organizacion": "Nombre del despacho", "region": "Región", "sede": "Ciudad",
                  "lugar": "Lugar del evento", "lema": "Lema del despacho", "institucion": "Institución",
                  "entidad": "Entidad u organismo", "correo": "correo@institucion.gob", "web": "www.institucion.gob"}


def textos_perfil(perfil=None):
    """{{titular}}, {{cargo}}, {{region}}… del perfil (claves `titular.nombre`, `titular.rol`, `organizacion`,
    `region`, `sede`, `lugar`, `lema`, `institucion`, `entidad`, `correo`, `web` o el bloque `textos`), con los
    neutros de reserva. Los mismos neutros están en editor.html y media.html (TEXTOS_NEUTROS)."""
    perfil = _cfg("PERFIL", {}) if perfil is None else perfil
    perfil = perfil or {}
    titular = perfil.get("titular") if isinstance(perfil.get("titular"), dict) else {}
    out = dict(TEXTOS_NEUTROS)
    for clave, valor in (("titular", titular.get("nombre")), ("cargo", titular.get("rol")),
                         ("organizacion", perfil.get("organizacion")), ("region", perfil.get("region")),
                         ("sede", perfil.get("sede")), ("lugar", perfil.get("lugar")),
                         ("lema", perfil.get("lema")), ("institucion", perfil.get("institucion")),
                         ("entidad", perfil.get("entidad")), ("correo", perfil.get("correo")), ("web", perfil.get("web"))):
        if isinstance(valor, str) and valor.strip():
            out[clave] = valor.strip()
    for clave, valor in (perfil.get("textos") or {}).items():
        if isinstance(valor, str) and re.match(r"^[a-z_]{1,40}$", clave):
            out[clave] = valor
    return out


def _marca_perfil():
    """Kit de marca de los editores: organización, titular, textos de los marcadores y logos (/logo/)."""
    perfil = _cfg("PERFIL", {}) or {}
    return {"organizacion": perfil.get("organizacion", ""), "titular": perfil.get("titular", {}),
            "textos": textos_perfil(perfil), "logos": listar_logos(60)}


# ------------------------------------------------------- tipografías (/api/fuentes)
#
# Una sola lista de tipografías para los cuatro editores: las de `rutas.fuentes` del perfil y, si una familia
# de la marca (tokens/typography.json, la que pide el ASS de los títulos) no está ahí pero sí instalada en esta
# computadora, también ese archivo (lo que libass usará al exportar). Así la vista previa del navegador mide con
# el MISMO archivo que el render. Nada se pide fuera: miniPaint y video.html las cargan con FontFace.

_FUENTES_SISTEMA = {}      # id → ruta absoluta (solo las que /api/fuentes anunció)
_EXTS_FUENTE = (".ttf", ".otf")


def metricas_fuente(ruta):
    """{familia, familia_legado, subfamilia, peso, cursiva, escala_ass, ascenso_ass} de un .ttf/.otf sin
    dependencias (tablas name, OS/2, head). `escala_ass` = unitsPerEm / (usWinAscent + usWinDescent): el cuerpo
    en px que libass usa para un \\fs dado (libass toma el alto de línea de Windows como tamaño), para que el
    lienzo mida igual; `ascenso_ass` = usWinAscent / (usWinAscent + usWinDescent): dónde cae la línea base."""
    import struct
    try:
        with open(ruta, "rb") as f:
            datos = f.read()
        n = struct.unpack(">H", datos[4:6])[0]
        tablas = {}
        for i in range(n):
            etiqueta, _, desp, largo = struct.unpack(">4sLLL", datos[12 + 16 * i:28 + 16 * i])
            tablas[etiqueta] = (desp, largo)
        nombres = {}
        if b"name" in tablas:
            desp = tablas[b"name"][0]
            _, cuenta, cadenas = struct.unpack(">HHH", datos[desp:desp + 6])
            for k in range(cuenta):
                plat, _, idioma, nid, largo, off = struct.unpack(">6H", datos[desp + 6 + 12 * k:desp + 18 + 12 * k])
                if nid in (1, 2, 16, 17):
                    crudo = datos[desp + cadenas + off:desp + cadenas + off + largo]
                    texto = crudo.decode("utf-16-be" if plat in (0, 3) else "latin-1", "ignore")
                    if nid not in nombres or (plat == 3 and idioma == 0x409):
                        nombres[nid] = texto
        peso, cursiva, escala, ascenso = 400, False, None, None
        upem = struct.unpack(">H", datos[tablas[b"head"][0] + 18:tablas[b"head"][0] + 20])[0] if b"head" in tablas else 1000
        if b"OS/2" in tablas:
            d = tablas[b"OS/2"][0]
            peso = struct.unpack(">H", datos[d + 4:d + 6])[0] or 400
            cursiva = bool(struct.unpack(">H", datos[d + 62:d + 64])[0] & 1)
            asc, desc = struct.unpack(">HH", datos[d + 74:d + 78])
            if asc + desc:
                escala = round(upem / float(asc + desc), 5)
                ascenso = round(asc / float(asc + desc), 5)
        sub = nombres.get(17) or nombres.get(2) or "Regular"
        # Familia «de legado» (id 1, la que ven fontconfig y libass además de la tipográfica): «Archivo Black»
        # es la familia 1 del archivo cuya familia 16 es «Archivo».
        legado = nombres.get(1)
        return {"familia": nombres.get(16) or legado, "subfamilia": sub, "peso": int(peso),
                "cursiva": cursiva or "italic" in sub.lower(), "escala_ass": escala, "ascenso_ass": ascenso,
                "familia_legado": legado if legado and legado != (nombres.get(16) or legado) else None}
    except Exception:
        return {}


def familia_fuente(ruta):
    """Familia tipográfica de un .ttf/.otf (tabla «name», id 16 o 1), sin dependencias; None si no se lee."""
    return metricas_fuente(ruta).get("familia")


def _archivos_sistema(familia):
    """Archivos .ttf/.otf instalados de una familia (fc-list), o [] si no hay fontconfig."""
    if not familia or not shutil.which("fc-list"):
        return []
    try:
        r = subprocess.run(["fc-list", familia, "file"], capture_output=True, text=True, timeout=10)
    except Exception:
        return []
    rutas = sorted({l.split(":", 1)[0].strip() for l in r.stdout.splitlines() if l.strip()})
    return [p for p in rutas if p.lower().endswith(_EXTS_FUENTE) and os.path.isfile(p)][:12]


def listar_fuentes():
    """[{archivo, url, familia, subfamilia, peso, cursiva, escala_ass, origen: perfil|sistema, marca}]."""
    marca = _marca_video()
    familias_marca = [f for f in (marca.get("fuente_titular"), marca.get("fuente_texto")) if f]
    out, vistas = [], set()
    if os.path.isdir(DIR_FUENTES):
        for raiz, dirs, archivos in os.walk(DIR_FUENTES):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for n in sorted(archivos):
                if not n.lower().endswith(_EXTS_FUENTE):
                    continue
                ruta = os.path.join(raiz, n)
                rel = os.path.relpath(ruta, DIR_FUENTES)
                m = metricas_fuente(ruta)
                if not m.get("familia"):
                    continue
                vistas.update({m["familia"], m.get("familia_legado")})
                out.append(dict(m, archivo=n, origen="perfil",
                                marca=bool({m["familia"], m.get("familia_legado")} & set(familias_marca)),
                                url=pub("/fuentes/" + "/".join(quote(s) for s in rel.split(os.sep)))))
    for fam in familias_marca:
        if fam in vistas:
            continue
        for ruta in _archivos_sistema(fam):
            m = metricas_fuente(ruta)
            if fam not in (m.get("familia"), m.get("familia_legado")):
                continue
            ident = "%08x" % (abs(hash(ruta)) & 0xFFFFFFFF)
            _FUENTES_SISTEMA[ident] = ruta
            out.append(dict(m, archivo=os.path.basename(ruta), origen="sistema", marca=True,
                            url=pub("/fuentes-sistema/%s/%s" % (ident, quote(os.path.basename(ruta))))))
    return out


# ------------------------------------------------------- exportación de video


def _ffmpeg_disponible():
    return shutil.which("ffmpeg") is not None


def exportar_video_en_hilo(id_trabajo, datos, pref=""):
    """Hilo: recorta el video, aplica recuadre (crop de origen) y superpone
    el overlay compuesto por el editor. Paridad total con la vista previa.
    Espera su turno (un ffmpeg a la vez); `pref` es el prefijo público de la petición."""
    _LOCAL.prefijo = pref
    with SEMAFORO_VIDEO:
        _exportar_video(id_trabajo, datos)
    limpiar_trabajos()


def _exportar_video(id_trabajo, datos):
    with TRABAJOS_LOCK:
        TRABAJOS[id_trabajo]["cola"] = False
    try:
        origen_rel = sin_prefijo(unquote(datos.get("origen", ""))).replace("/banco/", "", 1)
        origen = os.path.normpath(os.path.join(DIR_BANCO, origen_rel))
        if not (dentro_de(DIR_BANCO, origen) and os.path.exists(origen)):
            raise ValueError("video de origen no válido")

        W = int(datos["w"]); H = int(datos["h"])
        ini = max(0.0, float(datos.get("inicio", 0)))
        fin = float(datos.get("fin", 0))
        dur = max(0.1, fin - ini) if fin > ini else None

        # Recuadre elegido en el editor (rectángulo del video de origen).
        rc = datos.get("recuadre") or {}
        sx, sy = int(rc.get("x", 0)), int(rc.get("y", 0))
        sw, sh = int(rc.get("w", 0)), int(rc.get("h", 0))

        # Overlay PNG compuesto en el navegador (lo que se ve es lo que sale).
        overlay_b64 = datos.get("overlay", "").split(",", 1)[-1]
        os.makedirs(os.path.join(DIR_EXPORTS, "tmp"), exist_ok=True)
        ruta_overlay = os.path.join(DIR_EXPORTS, "tmp",
                                    "overlay-%s.png" % id_trabajo)
        with open(ruta_overlay, "wb") as f:
            f.write(base64.b64decode(overlay_b64))

        nombre = sanear_nombre(datos.get("nombre") or "video.mp4")
        if not nombre.lower().endswith(".mp4"):
            nombre += ".mp4"
        # El video FINAL va a la SALIDA por canal (prensa/redes/<canal> o transmisiones).
        # El overlay temporal sí vive en DIR_EXPORTS/tmp (working dir).
        canal = datos.get("canal", "")
        dest = dir_canal(canal)
        os.makedirs(dest, exist_ok=True)
        salida = ruta_libre(os.path.join(
            dest,
            "%s-%s" % (datetime.now().strftime("%Y-%m-%d"), nombre)))

        if sw > 0 and sh > 0:
            recuadre = "crop=%d:%d:%d:%d,scale=%d:%d" % (sw, sh, sx, sy, W, H)
        else:
            recuadre = ("scale=%d:%d:force_original_aspect_ratio=increase,"
                        "crop=%d:%d" % (W, H, W, H))

        # Revelado (brillo/contraste/saturación/tono del editor): filtro eq/hue
        # de ffmpeg, mismo resultado que la vista previa del navegador.
        aj = datos.get("ajustes") or {}
        try:
            br = (float(aj.get("br", 100)) - 100) / 100.0     # eq: -1..1
            ct = float(aj.get("ct", 100)) / 100.0             # eq: 0..2
            sat = float(aj.get("sat", 100)) / 100.0           # eq: 0..3
            hue = float(aj.get("hue", 0))                     # grados
            if abs(br) > 0.005 or abs(ct - 1) > 0.005 or abs(sat - 1) > 0.005:
                recuadre += ",eq=brightness=%.3f:contrast=%.3f:saturation=%.3f" % (
                    max(-1, min(1, br)), max(0, min(2, ct)), max(0, min(3, sat)))
            if abs(hue) > 0.5:
                recuadre += ",hue=h=%.1f" % hue
        except (TypeError, ValueError):
            pass

        # ¿El video de origen tiene audio? (para recortarlo junto al video)
        pa = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                             "-show_entries", "stream=index", "-of", "csv=p=0",
                             origen], capture_output=True, text=True, timeout=60)
        con_audio = bool(pa.stdout.strip())

        # Recorte de tiempo EXACTO con trim/atrim dentro del filtro (los saltos
        # con -ss dependen de los fotogramas clave y desvían la duración).
        # MULTICORTE: si el editor manda varios tramos (segmentos), cada uno se
        # recorta y se UNEN en orden (concat); con un solo tramo, ruta clásica.
        segs = []
        for s in (datos.get("segmentos") or []):
            try:
                a, b = float(s.get("ini", 0)), float(s.get("fin", 0))
            except (TypeError, ValueError, AttributeError):
                continue
            if b > a + 0.05:
                segs.append((max(0.0, a), b))
        segs.sort()
        segs = segs[:50]
        if len(segs) >= 2:
            pv, pa, ev, ea = [], [], [], []
            for i, (a, b) in enumerate(segs):
                pv.append("[0:v]trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS[v%d];"
                          % (a, b, i))
                ev.append("[v%d]" % i)
                if con_audio:
                    pa.append("[0:a]atrim=start=%.3f:end=%.3f,"
                              "asetpts=PTS-STARTPTS[a%d];" % (a, b, i))
                    ea.append("[a%d]" % i)
            fv = ("".join(pv) + "".join(ev)
                  + "concat=n=%d:v=1:a=0[vc];[vc]%s[v];"
                    "[v][1:v]overlay=0:0:format=auto[out]"
                    % (len(segs), recuadre))
            mapas = ["-map", "[out]"]
            if con_audio:
                fv += (";" + "".join(pa) + "".join(ea)
                       + "concat=n=%d:v=0:a=1[aud]" % len(segs))
                mapas += ["-map", "[aud]"]
        else:
            if len(segs) == 1:
                ini = segs[0][0]
                dur = max(0.1, segs[0][1] - ini)
            fin_f = ini + dur if dur else 10**8
            fv = ("[0:v]trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS,%s[v];"
                  "[v][1:v]overlay=0:0:format=auto[out]" % (ini, fin_f, recuadre))
            mapas = ["-map", "[out]"]
            if con_audio:
                fv += (";[0:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS[aud]"
                       % (ini, fin_f))
                mapas += ["-map", "[aud]"]

        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", origen, "-i", ruta_overlay,
               "-filter_complex", fv, *mapas,
               "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
               "-pix_fmt", "yuv420p"]
        if con_audio:
            cmd += ["-c:a", "aac", "-b:a", "128k"]
        cmd += ["-movflags", "+faststart", salida]

        if shutil.which("nice"):
            cmd = ["nice", "-n", "10"] + cmd       # prioridad baja: la máquina sirve otras cosas
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIEMPO_MAX_VIDEO)
        except subprocess.TimeoutExpired:
            raise RuntimeError("ffmpeg superó %d s y se detuvo" % TIEMPO_MAX_VIDEO)
        finally:
            try:
                os.remove(ruta_overlay)
            except OSError:
                pass
        if r.returncode != 0:
            raise RuntimeError((r.stderr or "ffmpeg falló").strip()[-400:])

        url = url_canal(salida, canal)
        with TRABAJOS_LOCK:
            TRABAJOS[id_trabajo].update(estado="listo", url=url, fin=time.time(),
                                        archivo=os.path.basename(salida))
    except Exception as e:
        with TRABAJOS_LOCK:
            TRABAJOS[id_trabajo].update(estado="error", error=str(e), fin=time.time())


# --------------------------------------- editor de video (video.html): montaje y subtítulos
#
# El proyecto del editor (pistas y clips) se convierte en UNA orden de ffmpeg con montaje.py
# (puro, con pruebas en tests/test_montaje.py); aquí solo se resuelven los medios a disco,
# se sondean con ffprobe y se corre la orden en la misma cola que el resto del video (un ffmpeg
# a la vez, nice, tiempo máximo), con progreso. Los subtítulos automáticos usan la transcripción
# de video/shorts/shorts.py (Whisper, palabra a palabra).

import montaje  # noqa: E402  (editor/servidor/montaje.py)

_SONDEOS = {}
MODELOS_WHISPER = ("tiny", "base", "small", "medium")
# Idiomas que Whisper reconoce (códigos de `whisper --language`, openai-whisper 2023+). El quechua (qu) y el
# aimara (ay) NO están: para ellos no hay transcripción automática (se escribe el texto a mano o se usa
# «detectar», que suele confundirlo con español). «auto» deja que Whisper detecte el idioma.
IDIOMAS_WHISPER = ("af", "am", "ar", "as", "az", "ba", "be", "bg", "bn", "bo", "br", "bs", "ca", "cs", "cy",
                   "da", "de", "el", "en", "es", "et", "eu", "fa", "fi", "fo", "fr", "gl", "gu", "ha", "haw",
                   "he", "hi", "hr", "ht", "hu", "hy", "id", "is", "it", "ja", "jw", "ka", "kk", "km", "kn",
                   "ko", "la", "lb", "ln", "lo", "lt", "lv", "mg", "mi", "mk", "ml", "mn", "mr", "ms", "mt",
                   "my", "ne", "nl", "nn", "no", "oc", "pa", "pl", "ps", "pt", "ro", "ru", "sa", "sd", "si",
                   "sk", "sl", "sn", "so", "sq", "sr", "su", "sv", "sw", "ta", "te", "tg", "th", "tk", "tl",
                   "tr", "tt", "uk", "ur", "uz", "vi", "yi", "yo", "yue", "zh")
# Los que video.html ofrece primero, con su nombre (el resto se elige por código).
IDIOMAS_DESTACADOS = (("es", "Español"), ("en", "Inglés"), ("pt", "Portugués"), ("fr", "Francés"),
                      ("it", "Italiano"), ("de", "Alemán"), ("auto", "Detectar el idioma"))
IDIOMAS_SIN_SOPORTE = (("qu", "Quechua"), ("ay", "Aimara"))


def idioma_whisper(valor):
    """Código válido para `whisper --language` ('es' por defecto); 'auto' → None (detección)."""
    if valor == "auto":
        return None
    return valor if valor in IDIOMAS_WHISPER else "es"


def ruta_de_medio(url):
    """Ruta en disco de un medio que el navegador nombra por su URL servida (banco, trabajo, redes,
    transmisiones, plantillas de marcos o logos), o None si no es válida o no existe."""
    rel = sin_prefijo(unquote((url or "").split("?", 1)[0].split("#", 1)[0]))
    bases = dict(_prefijos_origen())
    bases.update({"/plantillas/": DIR_PLANTILLAS, "/logo/": DIR_LOGOS})
    for pref, base in bases.items():
        if rel.startswith(pref):
            p = os.path.normpath(os.path.join(base, rel[len(pref):]))
            if dentro_de(base, p) and os.path.isfile(p):
                return p
    return None


def sondear(ruta):
    """{w, h, dur, audio} de un medio con ffprobe (con caché por fecha de modificación)."""
    try:
        clave = (ruta, os.path.getmtime(ruta))
    except OSError:
        return {}
    if clave in _SONDEOS:
        return _SONDEOS[clave]
    info = {}
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "stream=codec_type,width,height:format=duration", "-of", "json", ruta],
                           capture_output=True, text=True, timeout=60)
        d = json.loads(r.stdout or "{}")
        for s in d.get("streams", []):
            if s.get("codec_type") == "video" and "w" not in info:
                info.update(w=int(s.get("width") or 0), h=int(s.get("height") or 0))
            if s.get("codec_type") == "audio":
                info["audio"] = True
        info["dur"] = float((d.get("format") or {}).get("duration") or 0)
    except Exception:
        pass
    _SONDEOS[clave] = info
    return info


SEMAFORO_FOTOGRAMA = threading.BoundedSemaphore(2)


def fotograma(ruta, t, alto=72):
    """Ruta de un JPEG (caché) con el cuadro del segundo `t` de un video, `alto` px de alto, para las
    miniaturas de los clips en la línea de tiempo de video.html. None si ffmpeg no lo pudo sacar."""
    alto = int(min(max(alto, 24), 360))
    t = max(0.0, round(float(t), 1))
    try:
        mt = int(os.path.getmtime(ruta))
    except OSError:
        return None
    cache = os.path.join(DIR_EXPORTS, "tmp", "fotogramas")
    clave = "%s-%d-%.1f-%d.jpg" % (re.sub(r"[^\w]", "_", os.path.basename(ruta))[:60],
                                   abs(hash((ruta, mt))) & 0xFFFFFF, t, alto)
    destino = os.path.join(cache, clave)
    if os.path.exists(destino):
        return destino
    if not _ffmpeg_disponible():
        return None
    os.makedirs(cache, exist_ok=True)
    tmp = destino + ".part.jpg"
    with SEMAFORO_FOTOGRAMA:
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.2f" % t, "-i", ruta, "-frames:v", "1",
                            "-vf", "scale=-2:%d" % alto, "-q:v", "6", tmp], check=True, timeout=30,
                           stdin=subprocess.DEVNULL, capture_output=True)
            os.replace(tmp, destino)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return None
    return destino


def _redes_video():
    """Ajustes de exportación por red de video/shorts/redes.json (los mismos que los cortes verticales)."""
    return _leer_json(os.path.join(DIR_EDITOR, "..", "video", "shorts", "redes.json")) or None


def _marca_video():
    """Colores por papel y tipografías de los títulos, de los tokens (shorts.Marca y su PALETA)."""
    try:
        s = montaje.shorts()
        m = s.Marca()
        return {"colores": {k: m.hex(v) for k, v in s.PALETA.items()},
                "fuente_titular": m.fuente_titular, "fuente_texto": m.fuente_texto}
    except Exception:
        return {}


def api_video_config():
    """Lo que video.html necesita además de /api/design: redes, canales, marca de los títulos,
    herramientas disponibles y tipografías."""
    redes = _redes_video() or {}
    fuentes = []
    if os.path.isdir(DIR_FUENTES):
        fuentes = [{"nombre": n, "url": pub("/fuentes/" + quote(n))} for n in sorted(os.listdir(DIR_FUENTES))
                   if n.lower().endswith((".ttf", ".otf"))]
    return {"ok": True, "ffmpeg": _ffmpeg_disponible(), "whisper": shutil.which("whisper") is not None,
            "redes": redes.get("redes", {}), "sonoridad": (redes.get("comun") or {}).get("sonoridad", {}),
            "canales": list(CANALES) + ["transmisiones"], "marca": _marca_video(), "fuentes": fuentes,
            "tipografias": listar_fuentes(), "tiempo_max": TIEMPO_MAX_VIDEO,
            "idiomas": {"destacados": [{"codigo": c, "nombre": n} for c, n in IDIOMAS_DESTACADOS],
                        "todos": list(IDIOMAS_WHISPER),
                        "sin_soporte": [{"codigo": c, "nombre": n} for c, n in IDIOMAS_SIN_SOPORTE]}}


def _sondeos_de(proyecto):
    sondeos = {}
    for c in (proyecto.get("clips") or []) if isinstance(proyecto, dict) else []:
        o = c.get("origen") if isinstance(c, dict) else None
        if o and o not in sondeos and c.get("tipo") in ("video", "imagen", "audio"):
            ruta = ruta_de_medio(o)
            sondeos[o] = sondear(ruta) if ruta else {}
    return sondeos


def plan_video_wasm(proyecto, normalizar_audio=True):
    """Plan para ffmpeg.wasm en el navegador: la MISMA orden de montaje.py con nombres del sistema de
    archivos virtual (/in/0.mp4, /trabajo/titulos.ass, /fuentes, /out/salida.mp4)."""
    nombres = {}

    def resolver(url):
        if not ruta_de_medio(url):
            return None
        if url not in nombres:
            ext = os.path.splitext(unquote(url.split("?", 1)[0]))[1].lower() or ".bin"
            nombres[url] = "/in/%d%s" % (len(nombres), re.sub(r"[^a-z0-9.]", "", ext))
        return nombres[url]

    plan = montaje.construir(proyecto, _sondeos_de(proyecto), resolver, "/out/salida.mp4", ajustes=_redes_video(),
                             marca=_marca_video(), ass_ruta="/trabajo/titulos.ass", fuentes_dir="/fuentes",
                             normalizar_audio=normalizar_audio, wasm=True)
    fuentes, familias = [], []
    if plan["ass"]:
        # Las mismas de /api/fuentes (perfil y, si faltan ahí, las de la marca instaladas en esta computadora).
        for i, f in enumerate(listar_fuentes()):
            fuentes.append({"url": f["url"], "nombre": "/fuentes/%02d-%s" % (i, re.sub(r"[^\w.\-]", "_", f["archivo"]))})
            familias.append(f["familia"])
    ass = plan["ass"]
    if ass and fuentes:
        # Sin fontconfig, libass (en ffmpeg.wasm) solo usa las fuentes de /fuentes y las busca por familia:
        # una familia de la marca que no esté se cambia por una que sí viaja (la de texto, si está).
        marca = _marca_video()
        for buscada in {marca.get("fuente_titular"), marca.get("fuente_texto")} - {None}:
            if familias and buscada not in familias:
                sustituta = marca.get("fuente_texto") if marca.get("fuente_texto") in familias else familias[0]
                ass = ass.replace("\\fn" + buscada + "\\", "\\fn" + sustituta + "\\").replace(
                    "," + buscada + ",", "," + sustituta + ",")
    return {"ok": True, "args": plan["args"], "ass": ass, "duracion": plan["duracion"],
            "entradas": [{"url": u, "nombre": n} for u, n in nombres.items()], "fuentes": fuentes}


def _correr_ffmpeg(id_trabajo, args, total):
    """Corre ffmpeg con nice y tiempo máximo, publicando el progreso (out_time) en el trabajo."""
    cmd = ["ffmpeg"] + args[:-1] + ["-progress", "pipe:1", args[-1]]
    if shutil.which("nice"):
        cmd = ["nice", "-n", "10"] + cmd
    err = os.path.join(DIR_EXPORTS, "tmp", "ffmpeg-%s.log" % id_trabajo)
    with open(err, "w+", encoding="utf-8") as ferr:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=ferr, text=True)
        reloj = threading.Timer(TIEMPO_MAX_VIDEO, proc.kill)
        reloj.start()
        try:
            for linea in proc.stdout:
                if linea.startswith("out_time_us=") or linea.startswith("out_time_ms="):
                    try:
                        seg = int(linea.split("=", 1)[1]) / 1e6
                    except ValueError:
                        continue
                    with TRABAJOS_LOCK:
                        TRABAJOS[id_trabajo]["progreso"] = round(max(0.0, min(0.99, seg / max(total, 0.1))), 3)
            proc.wait()
        finally:
            vencido = not reloj.is_alive() and proc.returncode not in (0, None)
            reloj.cancel()
        ferr.seek(0)
        detalle = ferr.read()
    try:
        os.remove(err)
    except OSError:
        pass
    if proc.returncode != 0:
        if vencido:
            raise RuntimeError("ffmpeg superó %d s y se detuvo" % TIEMPO_MAX_VIDEO)
        raise RuntimeError((detalle or "ffmpeg falló").strip()[-600:])


def exportar_proyecto_en_hilo(id_trabajo, datos, pref=""):
    _LOCAL.prefijo = pref
    with SEMAFORO_VIDEO:
        with TRABAJOS_LOCK:
            TRABAJOS[id_trabajo].update(cola=False, etapa="componiendo")
        ass_ruta = os.path.join(DIR_EXPORTS, "tmp", "titulos-%s.ass" % id_trabajo)
        try:
            proyecto = datos.get("proyecto") or {}
            nombre = sanear_nombre(datos.get("nombre") or "video.mp4")
            if not nombre.lower().endswith(".mp4"):
                nombre += ".mp4"
            canal = datos.get("canal", "")
            dest = dir_canal(canal)
            os.makedirs(dest, exist_ok=True)
            os.makedirs(os.path.join(DIR_EXPORTS, "tmp"), exist_ok=True)
            salida = ruta_libre(os.path.join(dest, "%s-%s" % (datetime.now().strftime("%Y-%m-%d"), nombre)))
            plan = montaje.construir(proyecto, _sondeos_de(proyecto), ruta_de_medio, salida, ajustes=_redes_video(),
                                     marca=_marca_video(), ass_ruta=ass_ruta,
                                     fuentes_dir=DIR_FUENTES if os.path.isdir(DIR_FUENTES) else None,
                                     normalizar_audio=datos.get("normalizar", True) is not False,
                                     calidad="rapida" if datos.get("calidad") == "rapida" else "alta")
            if plan["ass"]:
                with open(ass_ruta, "w", encoding="utf-8") as f:
                    f.write(plan["ass"])
            with TRABAJOS_LOCK:
                TRABAJOS[id_trabajo]["duracion"] = plan["duracion"]
            _correr_ffmpeg(id_trabajo, plan["args"], plan["duracion"])
            with TRABAJOS_LOCK:
                TRABAJOS[id_trabajo].update(estado="listo", progreso=1, url=url_canal(salida, canal),
                                            archivo=os.path.basename(salida), fin=time.time())
        except Exception as e:
            with TRABAJOS_LOCK:
                TRABAJOS[id_trabajo].update(estado="error", error=str(e), fin=time.time())
        finally:
            try:
                os.remove(ass_ruta)
            except OSError:
                pass
    limpiar_trabajos()


def subtitular_en_hilo(id_trabajo, datos, pref=""):
    """Transcribe el tramo del clip (Whisper por palabra, como shorts.py subtitular) y devuelve las
    palabras (tiempos desde la entrada del clip) y los grupos de subtítulo de shorts.grupos_de_palabras."""
    _LOCAL.prefijo = pref
    with SEMAFORO_VIDEO:
        with TRABAJOS_LOCK:
            TRABAJOS[id_trabajo].update(cola=False, etapa="transcribiendo", inicio_real=time.time())
        try:
            ruta = ruta_de_medio(datos.get("origen"))
            if not ruta:
                raise ValueError("medio de origen no válido")
            entrada = max(0.0, float(datos.get("entrada") or 0))
            dur = float(datos.get("duracion") or 0) or (sondear(ruta).get("dur", 0) - entrada)
            if dur <= 0.2:
                raise ValueError("el tramo es demasiado corto")
            modelo = datos.get("modelo") if datos.get("modelo") in MODELOS_WHISPER else "small"
            idioma = idioma_whisper(datos.get("idioma") or "es")
            s = montaje.shorts()
            palabras = s.transcribir(ruta, entrada, min(dur, 3 * 3600), modelo, idioma=idioma,
                                     tiempo_max=TIEMPO_MAX_VIDEO, prioridad_baja=True)
            grupos = [[dict(p) for p in g] for g in s.grupos_de_palabras(palabras)]
            with TRABAJOS_LOCK:
                TRABAJOS[id_trabajo].update(estado="listo", progreso=1, palabras=palabras, grupos=grupos,
                                            fin=time.time())
        except subprocess.TimeoutExpired:
            with TRABAJOS_LOCK:
                TRABAJOS[id_trabajo].update(estado="error", fin=time.time(),
                                            error="la transcripción superó %d s" % TIEMPO_MAX_VIDEO)
        except Exception as e:
            with TRABAJOS_LOCK:
                TRABAJOS[id_trabajo].update(estado="error", error=str(e)[-400:], fin=time.time())
    limpiar_trabajos()


# ----------------------------------------------- almacén durable (estado editor)
#
# Persistencia EN DISCO de lo que antes vivía solo en localStorage del navegador:
# ediciones, «mis plantillas», la predeterminada, la variante/edición actual, etc.
# Un archivo <clave>.json por clave. El navegador es solo un espejo: ESTO es la
# fuente de verdad (permanente y portable). Regla de oro: un guardado que falla
# nunca debe pasar por exitoso, así que estas funciones devuelven True/False y el
# endpoint responde 500 cuando algo no se pudo escribir (el editor lo hace visible).

_CLAVE_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")


def _almacen_path(clave):
    """Ruta segura de una clave, o None si es inválida o se saldría de la carpeta."""
    if not clave or not _CLAVE_RE.match(str(clave)):
        return None
    p = os.path.normpath(os.path.join(DIR_ALMACEN, str(clave) + ".json"))
    return p if dentro_de(DIR_ALMACEN, p) else None


def almacen_leer_todo():
    """{clave: datos} con TODAS las claves guardadas (una sola lectura al arrancar).
    Ignora archivos ilegibles sin romper el resto."""
    out = {}
    if not os.path.isdir(DIR_ALMACEN):
        return out
    for n in sorted(os.listdir(DIR_ALMACEN)):
        if not n.endswith(".json") or not _CLAVE_RE.match(n[:-5]):
            continue
        try:
            with open(os.path.join(DIR_ALMACEN, n), encoding="utf-8") as f:
                doc = json.load(f)
            out[n[:-5]] = doc["datos"] if isinstance(doc, dict) and "datos" in doc else doc
        except Exception:
            continue
    return out


def almacen_guardar(clave, datos):
    """Escribe <clave>.json de forma ATÓMICA (tmp + fsync + os.replace): un corte a
    mitad de escritura nunca deja un JSON a medias. Devuelve True/False."""
    p = _almacen_path(clave)
    if p is None:
        return False
    try:
        os.makedirs(DIR_ALMACEN, exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"clave": clave, "datos": datos,
                       "guardado": datetime.now().isoformat(timespec="seconds")},
                      f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def almacen_borrar(clave):
    p = _almacen_path(clave)
    if p and os.path.exists(p):
        try:
            os.remove(p)
        except OSError:
            return False
    return True


# ------------------------------------------------ mejora automática de fotos
#
# Corre el motor `mejorar_foto.py` como SUBPROCESO (misma idea que el export de
# video). NO destructivo: la foto original nunca se toca; el resultado se cachea
# en DIR_MEJORADAS por (origen+parámetros), así reabrir/reintentar es instantáneo.

_PREFIJOS_ORIGEN = None  # se llena tarde (depende de dirs ya definidos)


def _prefijos_origen():
    global _PREFIJOS_ORIGEN
    if _PREFIJOS_ORIGEN is None:
        _PREFIJOS_ORIGEN = {
            "/banco/": DIR_BANCO, "/exports/": DIR_EXPORTS,
            "/redes/": DIR_REDES, "/transmisiones/": DIR_TRANSMISIONES,
        }
    return _PREFIJOS_ORIGEN


def _resolver_origen(cuerpo):
    """Devuelve (ruta_en_disco, identidad) de la foto a mejorar. Acepta una URL
    servida ({origen:'/banco/…'}) o una imagen incrustada ({dataURL:'…'}); en el
    segundo caso la escribe a un archivo temporal en la caché. identidad sirve de
    clave de caché estable. Devuelve (None, None) si no es válida/segura."""
    origen = cuerpo.get("origen") or ""
    if origen:
        ruta_rel = sin_prefijo(unquote(origen.split("?", 1)[0]))
        for pref, base in _prefijos_origen().items():
            if ruta_rel.startswith(pref):
                p = os.path.normpath(os.path.join(base, ruta_rel[len(pref):]))
                if dentro_de(base, p) and os.path.isfile(p):
                    try:
                        mt = int(os.path.getmtime(p))
                    except OSError:
                        mt = 0
                    return p, "%s@%d" % (ruta_rel, mt)
        return None, None
    data_url = cuerpo.get("dataURL") or ""
    if data_url:
        b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
        try:
            datos = base64.b64decode(b64)
        except Exception:
            return None, None
        h = __import__("hashlib").sha1(datos).hexdigest()[:16]
        os.makedirs(DIR_MEJORADAS, exist_ok=True)
        ext = ".png" if data_url[:14].lower().startswith("data:image/png") else ".jpg"
        p = os.path.join(DIR_MEJORADAS, "_src_" + h + ext)
        if not os.path.exists(p):
            try:
                with open(p, "wb") as f:
                    f.write(datos)
            except OSError:
                return None, None
        return p, "data:" + h
    return None, None


def _clave_mejora(identidad, nivel, params):
    import hashlib
    crudo = identidad + "|" + nivel + "|" + json.dumps(params, sort_keys=True)
    return hashlib.sha1(crudo.encode("utf-8")).hexdigest()[:16]


def analizar_foto(ruta):
    """Corre el motor en modo --analizar y devuelve su JSON (o error)."""
    try:
        r = subprocess.run([sys.executable, SCRIPT_MEJORA, "--analizar", ruta],
                           capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"ok": False, "error": "no se pudo analizar: %s" % e}


def mejorar_foto(ruta, salida, nivel, params):
    """Corre el motor (subproceso) escribiendo `salida`. Devuelve el JSON del
    motor o un dict de error. No toca la foto original."""
    cmd = [sys.executable, SCRIPT_MEJORA, ruta, salida, "--nivel", nivel]
    for k, v in params.items():
        if v is not None and int(v) >= 0:
            cmd += ["--" + k, str(int(v))]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as e:
        return {"ok": False, "error": "el proceso de mejora falló: %s" % e}
    if r.returncode != 0 or not os.path.exists(salida):
        return {"ok": False, "error": (r.stderr or "la mejora no produjo salida").strip()[-300:]}
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"ok": True}


# --------------------------------------------------------------------- HTTP


class Handler(BaseHTTPRequestHandler):
    server_version = "EditorIdentidad/2.0"

    # -- helpers de respuesta --------------------------------------------
    def _json(self, obj, code=200):
        cuerpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _archivo(self, path, cache=False):
        """Sirve un archivo con soporte de rangos (necesario para que el
        navegador pueda saltar dentro de un video al recortarlo). `cache`: derivados inmutables
        (fotogramas, tipografías del sistema) que el navegador puede guardar una hora."""
        try:
            tam = os.path.getsize(path)
            f = open(path, "rb")
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            return self.send_error(404, "No encontrado")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        rango = self.headers.get("Range")
        try:
            if rango:
                m = re.match(r"bytes=(\d*)-(\d*)", rango)
                ini = int(m.group(1)) if m and m.group(1) else 0
                fin = int(m.group(2)) if m and m.group(2) else tam - 1
                fin = min(fin, tam - 1)
                if ini > fin or ini >= tam:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % tam)
                    self.end_headers()
                    return
                self.send_response(206)
                self.send_header("Content-Range",
                                 "bytes %d-%d/%d" % (ini, fin, tam))
                largo = fin - ini + 1
                f.seek(ini)
            else:
                self.send_response(200)
                largo = tam
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(largo))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "private, max-age=3600" if cache else "no-store")
            self.end_headers()
            restante = largo
            while restante > 0:
                trozo = f.read(min(1024 * 512, restante))
                if not trozo:
                    break
                self.wfile.write(trozo)
                restante -= len(trozo)
        except (BrokenPipeError, ConnectionResetError):
            pass  # el navegador cortó la descarga (normal en video)
        finally:
            f.close()

    def _servir_desde(self, base, prefijo):
        rel = unquote(self.path.split("?", 1)[0])[len(prefijo):]
        destino = os.path.normpath(os.path.join(base, rel))
        if not dentro_de(base, destino):
            return self.send_error(403, "Prohibido")
        return self._archivo(destino)

    def _leer_cuerpo_json(self):
        n = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _miniatura(self, rel):
        """Miniatura ligera (~320 px, JPEG) de una imagen del banco, con caché
        por fecha de modificación. Sin Pillow, sirve el original."""
        origen = os.path.normpath(os.path.join(DIR_BANCO, rel))
        if not dentro_de(DIR_BANCO, origen):
            return self.send_error(403, "Prohibido")
        if _PILImage is None or origen.lower().endswith(EXTS_VIDEO + (".svg", ".gif")):
            return self._archivo(origen)
        try:
            mt = int(os.path.getmtime(origen))
        except OSError:
            return self.send_error(404, "No encontrado")
        cache_dir = os.path.join(DIR_EXPORTS, "tmp", "miniaturas")
        clave = re.sub(r"[^\w]", "_", rel) + "-%d.jpg" % mt
        destino = os.path.join(cache_dir, clave)
        if not os.path.exists(destino):
            try:
                os.makedirs(cache_dir, exist_ok=True)
                im = _PILImage.open(origen)
                im = _PILImageOps.exif_transpose(im)
                im.thumbnail((320, 320))
                im.convert("RGB").save(destino, "JPEG", quality=72)
            except Exception:
                return self._archivo(origen)
        return self._archivo(destino)

    # -- control de acceso y prefijo --------------------------------------
    def _preparar(self, metodo):
        """Fija el prefijo público de esta petición y aplica la defensa de Host/Origin.
        Devuelve False (y ya respondió 403) si la petición no viene de un sitio permitido."""
        _LOCAL.prefijo = normalizar_prefijo(self.headers.get("X-Forwarded-Prefix", "")) or BASE_ENTORNO
        red_local = os.environ.get("EDITOR_HOST", _cfg("HOST", "127.0.0.1")) == "0.0.0.0"
        if not peticion_permitida(metodo, self.headers.get("Host", ""),
                                  self.headers.get("Origin", ""), red_local):
            self._json({"ok": False, "error": "Origen no permitido"}, 403)
            return False
        return True

    # -- GET --------------------------------------------------------------
    def do_GET(self):
        if not self._preparar("GET"):
            return
        ruta = unquote(self.path.split("?", 1)[0])
        consulta = parse_qs(self.path.split("?", 1)[1]) \
            if "?" in self.path else {}

        if ruta == "/api/health":
            return self._json({"ok": True, "banco": os.path.basename(DIR_BANCO),
                               "media": True,
                               "ffmpeg": _ffmpeg_disponible()})
        if ruta == "/api/imagenes":
            return self._json(listar_imagenes())
        if ruta == "/api/media":
            return self._json(listar_media())
        if ruta == "/api/design":
            return self._json(api_design())
        if ruta == "/api/video-config":
            return self._json(api_video_config())
        if ruta == "/api/trabajo":
            id_ = (consulta.get("id") or [""])[0]
            with TRABAJOS_LOCK:
                t = dict(TRABAJOS.get(id_, {"estado": "desconocido"}))
            return self._json(t)
        if ruta == "/api/almacen":
            # Todo el estado durable del editor en una sola lectura (arranque).
            return self._json({"ok": True, "claves": almacen_leer_todo()})
        if ruta == "/api/proyectos-media":
            items = []
            if os.path.isdir(DIR_PROYECTOS):
                for n in sorted(os.listdir(DIR_PROYECTOS)):
                    if n.endswith(".json"):
                        p = os.path.join(DIR_PROYECTOS, n)
                        items.append({
                            "nombre": os.path.splitext(n)[0],
                            "fecha": datetime.fromtimestamp(
                                os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M"),
                        })
            return self._json(items)
        if ruta == "/api/proyecto-media":
            nombre = sanear_nombre((consulta.get("nombre") or [""])[0]) + ".json"
            p = os.path.join(DIR_PROYECTOS, nombre)
            if not (dentro_de(DIR_PROYECTOS, p) and os.path.exists(p)):
                return self._json({"ok": False, "error": "No existe"}, 404)
            return self._archivo(p)
        if ruta == "/api/logos":
            # Alias anterior de /api/design → marca.logos (la misma lista; se conserva la forma {name, url}).
            return self._json([{"name": l["name"], "url": l["url"]} for l in listar_logos()])
        if ruta == "/api/fuentes":
            marca = _marca_video()
            return self._json({"ok": True, "fuentes": listar_fuentes(), "textos": textos_perfil(),
                               "familias_marca": {"titular": marca.get("fuente_titular"),
                                                  "texto": marca.get("fuente_texto")}})
        if ruta == "/api/fotograma":
            origen = ruta_de_medio((consulta.get("origen") or [""])[0])
            if not origen:
                return self._json({"ok": False, "error": "medio no válido"}, 404)
            try:
                t = float((consulta.get("t") or ["0"])[0])
                alto = int((consulta.get("alto") or ["72"])[0])
            except ValueError:
                return self._json({"ok": False, "error": "parámetros no válidos"}, 400)
            if origen.lower().endswith(EXTS_VIDEO):
                destino = fotograma(origen, t, alto)
            else:
                destino = origen if origen.lower().endswith(EXTS) else None
            if not destino:
                return self._json({"ok": False, "error": "sin fotograma"}, 404)
            return self._archivo(destino, cache=destino != origen)
        if ruta == "/api/proyectos-foto":
            return self._json(listar_proyectos(DIR_PROYECTOS_FOTO))
        if ruta == "/api/proyecto-foto":
            nombre = sanear_nombre((consulta.get("nombre") or [""])[0]) + ".json"
            p = os.path.join(DIR_PROYECTOS_FOTO, nombre)
            if not (dentro_de(DIR_PROYECTOS_FOTO, p) and os.path.exists(p)):
                return self._json({"ok": False, "error": "No existe"}, 404)
            return self._archivo(p)

        if ruta.startswith("/miniatura/"):
            return self._miniatura(ruta[len("/miniatura/"):])
        if ruta.startswith("/banco/"):
            return self._servir_desde(DIR_BANCO, "/banco/")
        if ruta.startswith("/plantillas/"):
            return self._servir_desde(DIR_PLANTILLAS, "/plantillas/")
        if ruta.startswith("/fuentes/"):
            return self._servir_desde(DIR_FUENTES, "/fuentes/")
        if ruta.startswith("/fuentes-sistema/"):
            # Solo los archivos que /api/fuentes anunció (familias de la marca instaladas): nunca una ruta libre.
            partes = ruta[len("/fuentes-sistema/"):].split("/", 1)
            if not _FUENTES_SISTEMA:
                listar_fuentes()
            destino = _FUENTES_SISTEMA.get(partes[0])
            if not destino:
                return self.send_error(404, "No encontrado")
            return self._archivo(destino, cache=True)
        if ruta.startswith("/logo/"):
            return self._servir_desde(DIR_LOGOS, "/logo/")
        if ruta.startswith("/exports/"):
            return self._servir_desde(DIR_EXPORTS, "/exports/")
        if ruta.startswith("/redes/"):
            return self._servir_desde(DIR_REDES, "/redes/")
        if ruta.startswith("/transmisiones/"):
            return self._servir_desde(DIR_TRANSMISIONES, "/transmisiones/")

        # estático del editor
        if ruta in ("/", ""):
            ruta = "/editor.html"
        destino = os.path.normpath(os.path.join(DIR_EDITOR, ruta.lstrip("/")))
        if not dentro_de(DIR_EDITOR, destino):
            return self.send_error(403, "Prohibido")
        if dentro_de(AQUI, destino):  # no exponer el código del servidor (servidor/)
            return self.send_error(404, "No encontrado")
        return self._archivo(destino)

    # -- POST -------------------------------------------------------------
    # Rutas POST que reciben JSON (el resto: /api/subir, cuerpo binario).
    _POST_JSON = ("/api/imagenes", "/api/exportar-foto", "/api/exportar-video", "/api/proyecto-media",
                  "/api/proyecto-foto", "/api/almacen", "/api/analizar-foto", "/api/mejorar-foto",
                  "/api/exportar-proyecto-video", "/api/plan-video", "/api/subtitular-video")

    def do_POST(self):
        if not self._preparar("POST"):
            return
        ruta = self.path.split("?", 1)[0]
        try:
            largo = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._json({"ok": False, "error": "Content-Length no válido"}, 400)
        if ruta in self._POST_JSON:
            # Solo JSON: un formulario o un text/plain de otra página no llega aquí (CSRF).
            if not es_json(self.headers.get("Content-Type")):
                return self._json({"ok": False, "error": "Se espera application/json"}, 415)
            if largo > MAX_JSON:
                return self._json({"ok": False, "error": "El cuerpo supera %d MB" % (MAX_JSON >> 20)}, 413)
        elif ruta == "/api/subir" and largo > MAX_SUBIDA:
            return self._json({"ok": False, "error": "El archivo supera %d MB" % (MAX_SUBIDA >> 20)}, 413)

        if ruta == "/api/imagenes":       # editor de publicaciones (sin cambios)
            return self._post_imagen_dataurl()
        if ruta == "/api/subir":          # foto o video, cuerpo binario
            return self._post_subir_binario()
        if ruta == "/api/exportar-foto":
            return self._post_exportar_foto()
        if ruta == "/api/exportar-video":
            return self._post_exportar_video()
        if ruta in ("/api/exportar-proyecto-video", "/api/subtitular-video"):
            return self._post_trabajo_video(ruta)
        if ruta == "/api/plan-video":
            return self._post_plan_video()
        if ruta == "/api/proyecto-media":
            return self._post_proyecto()
        if ruta == "/api/proyecto-foto":
            return self._post_proyecto(DIR_PROYECTOS_FOTO)
        if ruta == "/api/almacen":
            return self._post_almacen()
        if ruta == "/api/analizar-foto":
            return self._post_analizar_foto()
        if ruta == "/api/mejorar-foto":
            return self._post_mejorar_foto()
        return self.send_error(404, "No encontrado")

    def _post_imagen_dataurl(self):
        try:
            cuerpo = self._leer_cuerpo_json()
            nombre = sanear_nombre(cuerpo.get("filename", "imagen.png"))
            data_url = cuerpo.get("dataURL", "")
            b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
            datos = base64.b64decode(b64)
        except Exception as e:
            return self._json({"ok": False, "error": "Datos inválidos: %s" % e}, 400)
        os.makedirs(DIR_SUBIDAS, exist_ok=True)
        destino = ruta_libre(os.path.join(DIR_SUBIDAS, nombre))
        try:
            with open(destino, "wb") as f:
                f.write(datos)
        except Exception as e:
            return self._json({"ok": False, "error": "No se pudo guardar: %s" % e}, 500)
        rel = os.path.relpath(destino, DIR_BANCO)
        rel_url = "/".join(quote(seg) for seg in rel.split(os.sep))
        return self._json({"ok": True, "name": rel.replace(os.sep, " / "),
                           "url": pub("/banco/" + rel_url)})

    def _post_subir_binario(self):
        """Sube foto o video al banco (subidas-editor/). El cuerpo es el
        archivo tal cual; el nombre va en la cabecera X-Nombre (URL-encoded)."""
        nombre = sanear_nombre(unquote(self.headers.get("X-Nombre", "") or ""))
        ext = os.path.splitext(nombre)[1].lower()
        if ext not in EXTS + EXTS_VIDEO + EXTS_AUDIO:
            return self._json({"ok": False,
                               "error": "Extensión no permitida: %s" % ext}, 400)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            os.makedirs(DIR_SUBIDAS, exist_ok=True)
            destino = ruta_libre(os.path.join(DIR_SUBIDAS, nombre))
            with open(destino, "wb") as f:
                restante = n
                while restante > 0:
                    trozo = self.rfile.read(min(1024 * 1024, restante))
                    if not trozo:
                        break
                    f.write(trozo)
                    restante -= len(trozo)
        except Exception as e:
            return self._json({"ok": False, "error": "No se pudo guardar: %s" % e}, 500)
        rel = os.path.relpath(destino, DIR_BANCO)
        rel_url = "/".join(quote(seg) for seg in rel.split(os.sep))
        return self._json({"ok": True, "url": pub("/banco/" + rel_url),
                           "esVideo": ext in EXTS_VIDEO, "esAudio": ext in EXTS_AUDIO})

    def _post_trabajo_video(self, ruta):
        """Exportar un proyecto del editor de video o transcribir un clip: trabajo en segundo plano
        en la cola de video (GET /api/trabajo?id=… da estado, etapa y progreso)."""
        if not _ffmpeg_disponible():
            return self._json({"ok": False, "error": "ffmpeg no está instalado"}, 500)
        if ruta == "/api/subtitular-video" and shutil.which("whisper") is None:
            return self._json({"ok": False, "error": "Whisper no está instalado (pip install openai-whisper)"}, 500)
        try:
            cuerpo = self._leer_cuerpo_json()
            if ruta == "/api/exportar-proyecto-video":
                montaje.normalizar(cuerpo.get("proyecto"))      # error claro antes de encolar
        except Exception as e:
            return self._json({"ok": False, "error": "Datos inválidos: %s" % e}, 400)
        limpiar_trabajos()
        id_trabajo = os.urandom(6).hex()
        with TRABAJOS_LOCK:
            TRABAJOS[id_trabajo] = {"estado": "procesando", "cola": True, "etapa": "en cola", "progreso": 0,
                                    "inicio": time.time()}
        destino = exportar_proyecto_en_hilo if ruta == "/api/exportar-proyecto-video" else subtitular_en_hilo
        threading.Thread(target=destino, args=(id_trabajo, cuerpo, prefijo()), daemon=True).start()
        return self._json({"ok": True, "trabajo": id_trabajo})

    def _post_plan_video(self):
        """Plan de render para ffmpeg.wasm (navegador): argumentos, títulos ASS y qué archivos cargar."""
        try:
            cuerpo = self._leer_cuerpo_json()
            return self._json(plan_video_wasm(cuerpo.get("proyecto"), cuerpo.get("normalizar", True) is not False))
        except Exception as e:
            return self._json({"ok": False, "error": "No se pudo preparar: %s" % e}, 400)

    def _post_exportar_foto(self):
        try:
            cuerpo = self._leer_cuerpo_json()
            nombre = sanear_nombre(cuerpo.get("nombre") or "pieza.png")
            canal = cuerpo.get("canal", "")
            data_url = cuerpo.get("dataURL", "")
            b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
            datos = base64.b64decode(b64)
        except Exception as e:
            return self._json({"ok": False, "error": "Datos inválidos: %s" % e}, 400)

        fecha = datetime.now().strftime("%Y-%m-%d")
        # La foto/post FINAL va a la SALIDA por canal (prensa/redes/<canal> o transmisiones).
        dest = dir_canal(canal)
        os.makedirs(dest, exist_ok=True)
        salida = ruta_libre(os.path.join(dest, "%s-%s" % (fecha, nombre)))
        try:
            with open(salida, "wb") as f:
                f.write(datos)
        except Exception as e:
            return self._json({"ok": False, "error": "No se pudo guardar: %s" % e}, 500)

        # Copia al banco compartido para el editor de publicaciones (+ crédito F10)
        banco_url = ""
        try:
            os.makedirs(DIR_EDITADAS, exist_ok=True)
            destino_banco = ruta_libre(
                os.path.join(DIR_EDITADAS, os.path.basename(salida)))
            shutil.copy2(salida, destino_banco)
            rel = os.path.relpath(destino_banco, DIR_BANCO)
            anotar_credito(rel.replace(os.sep, "/"),
                           _cfg("CREDITO_EDITADAS",
                                "Despacho · pieza editada en el Editor"))
            banco_url = pub("/banco/" + "/".join(quote(s) for s in rel.split(os.sep)))
        except Exception:
            pass

        return self._json({
            "ok": True,
            "url": url_canal(salida, canal),
            "banco_url": banco_url,
            "archivo": os.path.basename(salida),
        })

    def _post_exportar_video(self):
        if not _ffmpeg_disponible():
            return self._json({"ok": False,
                               "error": "ffmpeg no está instalado"}, 500)
        try:
            cuerpo = self._leer_cuerpo_json()
        except Exception as e:
            return self._json({"ok": False, "error": "Datos inválidos: %s" % e}, 400)
        limpiar_trabajos()
        id_trabajo = os.urandom(6).hex()
        with TRABAJOS_LOCK:
            TRABAJOS[id_trabajo] = {"estado": "procesando", "cola": True,
                                    "inicio": time.time()}
        hilo = threading.Thread(target=exportar_video_en_hilo,
                                args=(id_trabajo, cuerpo, prefijo()), daemon=True)
        hilo.start()
        return self._json({"ok": True, "trabajo": id_trabajo})

    def _post_proyecto(self, carpeta=None):
        carpeta = carpeta or DIR_PROYECTOS
        try:
            cuerpo = self._leer_cuerpo_json()
            nombre = sanear_nombre(cuerpo.get("nombre") or "proyecto")
            datos = cuerpo.get("datos")
            assert datos is not None
        except Exception as e:
            return self._json({"ok": False, "error": "Datos inválidos: %s" % e}, 400)
        os.makedirs(carpeta, exist_ok=True)
        p = os.path.join(carpeta, nombre + ".json")
        if not dentro_de(carpeta, p):
            return self._json({"ok": False, "error": "Nombre no válido"}, 400)
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"nombre": nombre, "datos": datos,
                           "guardado": datetime.now().isoformat(timespec="seconds")},
                          f, ensure_ascii=False)
        except Exception as e:
            return self._json({"ok": False, "error": "No se pudo guardar: %s" % e}, 500)
        return self._json({"ok": True, "nombre": nombre})

    def _post_almacen(self):
        """Guarda estado durable del editor. Acepta:
          {clave, datos}            -> guarda una clave
          {claves:{clave:datos,..}} -> guarda varias de una vez (flush al cerrar)
          {clave, borrar:true}      -> elimina una clave
        Responde 500 si ALGO no se pudo escribir: el editor nunca da por guardado
        lo que no llegó al disco (así no reemplaza en silencio lo nuevo por lo viejo)."""
        try:
            cuerpo = self._leer_cuerpo_json()
        except Exception as e:
            return self._json({"ok": False, "error": "Datos inválidos: %s" % e}, 400)
        if cuerpo.get("borrar") and "clave" in cuerpo:
            ok = almacen_borrar(cuerpo.get("clave"))
            return self._json({"ok": ok, "borrada": cuerpo.get("clave")},
                              200 if ok else 500)
        if isinstance(cuerpo.get("claves"), dict):
            pares = cuerpo["claves"]
        elif "clave" in cuerpo:
            pares = {cuerpo.get("clave"): cuerpo.get("datos")}
        else:
            return self._json({"ok": False, "error": "Falta 'clave' o 'claves'"}, 400)
        guardadas, fallidas = [], []
        for clave, datos in pares.items():
            (guardadas if almacen_guardar(clave, datos) else fallidas).append(clave)
        if fallidas:
            return self._json({"ok": False, "guardadas": guardadas, "fallidas": fallidas,
                               "error": "No se pudo guardar: %s"
                               % ", ".join(map(str, fallidas))}, 500)
        return self._json({"ok": True, "guardadas": guardadas})

    def _post_analizar_foto(self):
        """Analiza la calidad de una foto ({origen} o {dataURL}) → JSON con el
        veredicto (¿necesita mejora y por qué?). No modifica nada."""
        try:
            cuerpo = self._leer_cuerpo_json()
        except Exception as e:
            return self._json({"ok": False, "error": "Datos inválidos: %s" % e}, 400)
        ruta, _ = _resolver_origen(cuerpo)
        if not ruta:
            return self._json({"ok": False, "error": "origen no válido"}, 400)
        return self._json(analizar_foto(ruta))

    def _post_mejorar_foto(self):
        """Mejora una foto ({origen}|{dataURL} + nivel + sliders) con el motor en
        subproceso. NO destructivo: cachea el resultado y devuelve su URL servida
        (/exports/mejoradas/…). La original nunca se toca."""
        try:
            cuerpo = self._leer_cuerpo_json()
        except Exception as e:
            return self._json({"ok": False, "error": "Datos inválidos: %s" % e}, 400)
        ruta, identidad = _resolver_origen(cuerpo)
        if not ruta:
            return self._json({"ok": False, "error": "origen no válido"}, 400)
        nivel = cuerpo.get("nivel", "auto")
        if nivel not in ("suave", "auto", "intensiva"):
            nivel = "auto"
        params = {k: cuerpo.get(k, -1) for k in
                  ("nitidez", "ruido", "claridad", "contraste", "color", "luz", "resolucion")}
        os.makedirs(DIR_MEJORADAS, exist_ok=True)
        clave = _clave_mejora(identidad, nivel, params)
        salida = os.path.join(DIR_MEJORADAS, "mej_" + clave + ".jpg")
        info = {}
        if not os.path.exists(salida):
            res = mejorar_foto(ruta, salida, nivel, params)
            if not res.get("ok"):
                return self._json({"ok": False, "error": res.get("error", "falló la mejora")}, 500)
            info = res.get("analisis", {}) or {}
        else:  # caché: recuperar el análisis sin re-mejorar
            info = analizar_foto(ruta)
        url = pub("/exports/mejoradas/" + quote(os.path.basename(salida)))
        return self._json({"ok": True, "url": url, "nivel": nivel, "analisis": info})

    def log_message(self, *a):  # servidor silencioso
        pass


def main():
    # Prioridad: EDITOR_PUERTO > PORT (estándar de lanzadores/preview) > config.
    puerto = int(os.environ.get("EDITOR_PUERTO",
                                os.environ.get("PORT", config.PUERTO)))
    host = os.environ.get("EDITOR_HOST", _cfg("HOST", "127.0.0.1"))
    try:
        srv = ThreadingHTTPServer((host, puerto), Handler)
    except OSError as e:
        nucleo.abortar(log, "No se pudo abrir el puerto %d: %s. ¿Ya hay un servidor del editor corriendo? "
                       "Abre: http://127.0.0.1:%d/editor.html" % (puerto, e, puerto))
    base = "http://127.0.0.1:%d" % puerto
    print("Editor de piezas — servidor local")
    print("  Banco de imágenes:      %s" % DIR_BANCO)
    print("  Editor publicaciones:   %s/editor.html" % base)
    print("  Editor fotos y videos:  %s/media.html" % base)
    if host == "0.0.0.0":
        print("  Acceso desde la red local activado (config.HOST) — otras")
        print("  computadoras: http://IP-de-esta-máquina:%d/" % puerto)
    print("  (Ctrl+C para detener)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
