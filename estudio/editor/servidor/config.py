# -*- coding: utf-8 -*-
"""editor/servidor/config.py — configuración del servidor local del editor: rutas del perfil (IDENTIDAD_PERFIL), banco y opciones."""
# =====================================================================
#  Configuración del servidor local del Editor de piezas.
#  Edita SOLO este archivo para ajustar rutas y opciones.
#  La lógica vive en servidor.py (no necesitas tocarla).
# =====================================================================

# Puerto local. El servidor escucha únicamente en 127.0.0.1 (tu equipo);
# no se expone a la red. Cámbialo solo si el 8099 ya está ocupado.
PUERTO = 8099

# Carpeta que es la FUENTE de imágenes del banco, relativa a esta carpeta
# (editor/servidor/). Se suben dos niveles: servidor/ -> editor/ ->
# identidad-visual/, y de ahí a recursos.
# Cambia esta línea si quieres apuntar a otra carpeta del proyecto.
CARPETA_BANCO = "../../recursos"

# Subcarpeta (dentro de CARPETA_BANCO) donde se GUARDAN las imágenes que subes
# desde el editor. Se crea sola la primera vez. Así las subidas no se mezclan
# con las carpetas temáticas que ya organizas a mano.
SUBCARPETA_SUBIDAS = "subidas-editor"

# Listar también las imágenes de las subcarpetas (educacion/, congreso/, ...).
RECURSIVO = True

# Carpetas a NO mostrar en el banco (material interno / ruido).
# Añade aquí cualquier subcarpeta de recursos que no quieras ver en el editor.
EXCLUIR = ["_recursos"]

# Qué extensiones se consideran imagen.
EXTENSIONES = [".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".svg"]

# Carpeta del editor (donde está editor.html), relativa a esta carpeta (servidor/).
CARPETA_EDITOR = ".."

# Archivo OPCIONAL de créditos, dentro de CARPETA_BANCO. Formato JSON:
#   { "estudiantes-andinos.jpg": "Foto: MINEDU (CC BY)", "educacion/aula.jpg": "..." }
# La clave puede ser el nombre del archivo o su ruta relativa dentro del banco.
# Si una foto no tiene crédito aquí, se muestra sin él (recuerda la regla F10:
# toda foto con licencia CC debe llevar su crédito al publicar).
ARCHIVO_CREDITOS = "creditos.json"

# ================== Editor de fotos y videos (media.html) ==================

# Dirección de escucha. "127.0.0.1" = solo esta computadora (recomendado).
# Para permitir el acceso desde otras computadoras del despacho (red local),
# cambia a "0.0.0.0" y entra desde ellas con http://IP-de-esta-máquina:8099/
HOST = "127.0.0.1"

# Extensiones de video aceptadas en el banco y en subidas.
VIDEO_EXTENSIONES = [".mp4", ".mov", ".webm", ".m4v"]

# Carpeta de las plantillas de marcos/overlays (relativa a servidor/).
CARPETA_PLANTILLAS_MEDIA = "../../plantillas/marco_foto_video"

# Tokens del design system (colores, layout) y tipografías (sin perfil: las del repo).
CARPETA_TOKENS = "../../tokens"
CARPETA_FUENTES = "../../logos-y-tipografias"

# Logos oficiales que los marcos nativos del editor de medios cargan en el lienzo
# (los del cliente llegan por el perfil, `rutas.logos`; sin perfil, la carpeta del repo).
CARPETA_LOGOS = "../../logos-y-tipografias"

# Carpeta de TRABAJO del editor (temporales, miniaturas). NO es un resultado: vive junto al
# editor (editor/_trabajo), FUERA de prensa. Se crea sola.
CARPETA_EXPORTS = "../_trabajo"

# SALIDA por CANAL: las piezas finales (foto o video) caen en prensa/redes/<canal> según el
# canal elegido en el editor; las transmisiones (EN VIVO/OBS) en prensa/transmisiones. Se crean solas.
CARPETA_REDES = "../../prensa/redes"
CARPETA_TRANSMISIONES = "../../prensa/transmisiones"

# Canales válidos (subcarpetas de prensa/redes) que el editor ofrece en el diálogo Exportar.
CANALES = ["facebook", "instagram", "tiktok", "estados", "x", "youtube", "linkedin"]

# Subcarpeta del banco donde se copian las FOTOS exportadas, para que
# aparezcan en el banco del editor de publicaciones (carpeta compartida).
SUBCARPETA_EDITADAS = "editadas-editor"

# Crédito que se anota automáticamente en creditos.json para esas fotos.
CREDITO_EDITADAS = "Despacho · pieza editada en el Editor"

# Carpeta (dentro de editor/) para los proyectos guardados del editor de medios.
CARPETA_PROYECTOS_MEDIA = "proyectos-media"

# Carpeta (dentro de editor/) para los proyectos con capas del editor de fotos (foto.html).
CARPETA_PROYECTOS_FOTO = "proyectos-foto"

# ================== Almacén durable de estado de los editores ==================
# Carpeta (dentro de editor/) donde se guardan de forma PERMANENTE, como archivos
# en disco, los datos que antes vivían solo en el navegador (localStorage):
# ediciones, «mis plantillas», la predeterminada, la variante actual, etc. Esto
# es la FUENTE DE VERDAD: sobrevive a cerrar el navegador, limpiar su caché e
# incluso a otra computadora del despacho (basta copiar esta carpeta). El
# navegador solo mantiene un espejo local para poder trabajar sin conexión.
# Cada "clave" del editor es un archivo <clave>.json aquí dentro.
CARPETA_ALMACEN = "estado-editor"

# ================== Mejora automática de fotos ==================
# Subcarpeta (dentro de CARPETA_EXPORTS = editor/_trabajo) donde se cachean las
# fotos MEJORADAS. Es NO destructiva: la foto original nunca se modifica; aquí
# solo viven las versiones realzadas (upscale + limpieza de compresión + nitidez).
# Se sirven en /exports/mejoradas/. Se puede borrar sin miedo: se regenera sola.
SUBCARPETA_MEJORADAS = "mejoradas"

# ================== Perfil del despacho (IDENTIDAD_PERFIL) ==================
# El repo identidad-visual es reutilizable: las rutas de ESTE despliegue (banco de
# fotos, tipografías, logos, marcos, salidas de prensa, estado del editor) las da un
# perfil.json (clave "rutas") cuya ruta llega por la variable de entorno
# IDENTIDAD_PERFIL. Si no hay perfil, valen los valores relativos de arriba.
import json as _json
import os as _os

# ================== El kit común: Unancha (UNANCHA_DIR) ==================
# Desde que el estudio vive en qillqa (los cuatro editores, fase 10.2b E0, 2026-10-20), lo común de la identidad —tokens,
# fuentes y logos, plantillas de marcos y el banco de ejemplo— sigue en Unancha y llega por UNANCHA_DIR. El perfil
# (abajo) manda sobre esto, como antes.
_KIT = _os.environ.get("UNANCHA_DIR", "")
if _KIT:
    CARPETA_BANCO = _os.path.join(_KIT, "recursos")
    CARPETA_PLANTILLAS_MEDIA = _os.path.join(_KIT, "plantillas", "marco_foto_video")
    CARPETA_TOKENS = _os.path.join(_KIT, "tokens")
    CARPETA_FUENTES = CARPETA_LOGOS = _os.path.join(_KIT, "logos-y-tipografias")

_PERFIL = _os.environ.get("IDENTIDAD_PERFIL", "")
PERFIL = {}
if _PERFIL and _os.path.isfile(_PERFIL):
    with open(_PERFIL, encoding="utf-8") as _fh:
        PERFIL = _json.load(_fh)
    _r = PERFIL.get("rutas", {})
    _m = {"banco": "CARPETA_BANCO", "fuentes": "CARPETA_FUENTES", "logos": "CARPETA_LOGOS",
          "plantillas_media": "CARPETA_PLANTILLAS_MEDIA", "redes": "CARPETA_REDES",
          "transmisiones": "CARPETA_TRANSMISIONES", "exports": "CARPETA_EXPORTS",
          "almacen": "CARPETA_ALMACEN", "proyectos_media": "CARPETA_PROYECTOS_MEDIA",
          "proyectos_foto": "CARPETA_PROYECTOS_FOTO"}
    for _k, _var in _m.items():
        if _r.get(_k):
            globals()[_var] = _r[_k]          # absolutas: os.path.join las respeta
    if _r.get("imgbank"):
        ARCHIVO_IMGBANK = _r["imgbank"]
