#!/usr/bin/env python3
"""video/shorts/shorts.py — cortes verticales (1080×1920) con la identidad del sistema.

Convierte un LOTE de cortes (YAML o JSON, fuera de este repo) en vídeos para redes:

  subtitular  extrae el audio de cada corte y obtiene las palabras con sus tiempos
              (Whisper, marcas por palabra); se guardan junto a la salida y se reutilizan
  render      compone cada corte: cabecera del programa, titular, rótulo de fuente,
              imagen (audiograma: retrato + onda) o vídeo reencuadrado, nombre de quien
              habla, subtítulos palabra a palabra y barra de progreso; sonoridad a −14 LUFS

Todo color sale de tokens/colors.json, toda tipografía de tokens/typography.json y las
zonas seguras de tokens/layout.json: aquí no hay ningún HEX ni ningún nombre de un cliente.
Los textos (programa, emisora, quién habla) los pone el lote.

Uso:
  shorts.py subtitular <lote.yml> [--id E1-1 ...] [--modelo small]
  shorts.py render     <lote.yml> [--id ...] [--red reels] [--muestra 8] [--incluir-verificar] [--dry-run]
  shorts.py portadas   <lote.yml> [--id ...] [--incluir-verificar]   # portada 1080×1920 (SVG + PNG, Inkscape)
  shorts.py kdenlive   <lote.yml> [--id ...] [--incluir-verificar]   # proyecto de Kdenlive prearmado por corte
  shorts.py plan       <lote.yml>          # qué haría, sin escribir nada

Depende de: ffmpeg (con libass) y, para `subtitular`, el CLI `whisper` (openai-whisper).
PyYAML es opcional: sin él, el lote va en JSON.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # raíz del repo: lib/nucleo
from lib import nucleo  # noqa: E402  raíz y logger de core/ (RQ-COD-06)

log = nucleo.registro("identidad-visual.shorts")

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = str(nucleo.RAIZ)
# Los tokens son del kit común (Unancha, UNANCHA_DIR) desde que el estudio vive en qillqa (fase 10.2b E0).
TOKENS = os.path.join(os.environ.get("UNANCHA_DIR") or RAIZ, "tokens")

W, H = 1080, 1920


# ------------------------------------------------------------------ tokens


def _json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


class Marca:
    """Colores, tipografías y zonas seguras leídos de los tokens del sistema."""

    def __init__(self):
        c = _json(os.path.join(TOKENS, "colors.json"))
        t = _json(os.path.join(TOKENS, "typography.json"))
        l = _json(os.path.join(TOKENS, "layout.json"))
        self.escalas = c["escalas"]
        fam = t["familias"]
        # Archivo Black (o la primera del stack) para titulares; Source Sans 3 para texto.
        pila = fam["display"]["stack"]
        self.fuente_titular = next((f for f in pila if "Black" in f), pila[0])
        self.fuente_display = fam["display"]["nombre"]
        self.fuente_texto = fam["body"]["nombre"]
        story = l.get("formatos", {}).get("story_1080x1920", {})
        self.sup = int(story.get("zona_segura_superior_px", 250))
        self.inf = int(story.get("zona_segura_inferior_px", 340))
        self.lat = int(story.get("margen_lateral_px", 96))
        self.der_tiktok = 140      # botonera de TikTok: dato de la app (igual que servidor.py)

    def hex(self, ref):
        """'puka.600' → su HEX (solo desde las escalas de colors.json)."""
        escala, tono = ref.split(".")
        return self.escalas[escala][tono]

    def ass(self, ref, alfa=0):
        """Color en formato ASS (&HAABBGGRR)."""
        h = self.hex(ref).lstrip("#")
        r, g, b = h[0:2], h[2:4], h[4:6]
        return "&H%02X%s%s%s" % (alfa, b, g, r)

    def ffmpeg(self, ref):
        return "0x" + self.hex(ref).lstrip("#")


# Papel de cada color en la pieza: referencias a las escalas, nunca HEX.
PALETA = {
    "fondo": "neutral.900",          # tinta
    "texto": "neutral.100",          # papel sobre oscuro
    "texto_suave": "neutral.400",
    "acento": "qillu.400",           # ancla secundaria
    "marca": "puka.600",             # ancla primaria
    "onda": "qillu.400",
}


# ------------------------------------------------------------------ lote


def tc_a_s(tc):
    """'19:39' · '1:02:03' · '95.5' → segundos."""
    if isinstance(tc, (int, float)):
        return float(tc)
    partes = [float(p) for p in str(tc).strip().split(":")]
    s = 0.0
    for p in partes:
        s = s * 60 + p
    return s


def s_a_tc(s):
    m, s = divmod(max(0.0, s), 60)
    return "%d:%05.2f" % (m, s)


def leer_lote(ruta):
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    if ruta.endswith(".json"):
        lote = json.loads(texto)
    else:
        try:
            import yaml
        except ImportError:
            nucleo.abortar(log, "PyYAML no está instalado: use el lote en JSON")
        lote = yaml.safe_load(texto)
    base = os.path.dirname(os.path.abspath(ruta))

    def ruta_de(v):
        if not v:
            return None
        return os.path.normpath(os.path.join(base, os.path.expanduser(str(v))))

    lote["_base"] = base
    lote["_salida"] = ruta_de(lote.get("salida") or "cortes")
    for clave in ("audio", "video", "imagen"):
        lote["_" + clave] = ruta_de(lote.get(clave))
    for c in lote.get("cortes", []):
        c["_entra"] = tc_a_s(c["entra"])
        c["_sale"] = tc_a_s(c["sale"])
        c["_dur"] = round(c["_sale"] - c["_entra"], 3)
        if c["_dur"] <= 0:
            nucleo.abortar(log, "corte %s: la salida es anterior a la entrada" % c.get("id"))
        c["_imagen"] = ruta_de(c.get("imagen")) or lote["_imagen"]
    return lote


def elegir(lote, ids, incluir_verificar=False):
    cortes = lote.get("cortes", [])
    if ids:
        cortes = [c for c in cortes if c.get("id") in ids]
        faltan = set(ids) - {c.get("id") for c in cortes}
        if faltan:
            nucleo.abortar(log, "no están en el lote: %s" % ", ".join(sorted(faltan)))
    elif not incluir_verificar:
        cortes = [c for c in cortes if c.get("estado") == "publicable"]
    return cortes


def nombre_base(lote, corte):
    ep = re.sub(r"[^a-z0-9]+", "-", str(lote.get("episodio", "ep")).lower()).strip("-")
    return "%s-%s" % (ep, str(corte["id"]).lower())


# ------------------------------------------------------------------ subtitular


def _requiere(binario):
    if shutil.which(binario) is None:
        nucleo.abortar(log, "falta «%s» en el PATH" % binario)


def transcribir(fuente, entra, dur, modelo="small", idioma="es", tiempo_max=None, prioridad_baja=False):
    """Palabras con sus tiempos ([{p, i, f}], segundos desde `entra`) del tramo `entra`…`entra+dur` de
    `fuente` (audio o vídeo), con el CLI de Whisper y marcas por palabra. Lo usan `subtitular` y los
    subtítulos automáticos del editor de video (editor/servidor/servidor.py)."""
    pre = ["nice", "-n", "10"] if prioridad_baja and shutil.which("nice") else []
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "corte.wav")
        subprocess.run(pre + ["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.3f" % entra,
                              "-t", "%.3f" % dur, "-i", fuente, "-ac", "1", "-ar", "16000", wav],
                       check=True, timeout=tiempo_max)
        # idioma None: Whisper detecta el idioma (sin --language).
        lengua = ["--language", idioma] if idioma else []
        subprocess.run(pre + ["whisper", wav, "--model", modelo] + lengua + [
                              "--word_timestamps", "True", "--output_format", "json",
                              "--output_dir", tmp, "--verbose", "False", "--fp16", "False"],
                       check=True, capture_output=True, timeout=tiempo_max)
        datos = _json(os.path.join(tmp, "corte.json"))
    palabras = []
    for seg in datos.get("segments", []):
        for p in seg.get("words", []):
            t = p["word"].strip()
            if t:
                palabras.append({"p": t, "i": round(p["start"], 3), "f": round(p["end"], 3)})
    return palabras


def subtitular(lote, cortes, modelo, dry):
    _requiere("ffmpeg")
    _requiere("whisper")
    fuente = lote["_audio"] or lote["_video"]
    if not fuente or not os.path.exists(fuente):
        nucleo.abortar(log, "el lote no tiene «audio» (o «video») que exista")
    os.makedirs(lote["_salida"], exist_ok=True) if not dry else None
    for c in cortes:
        destino = os.path.join(lote["_salida"], nombre_base(lote, c) + ".palabras.json")
        print("· %s  %s–%s  → %s" % (c["id"], c["entra"], c["sale"], os.path.basename(destino)))
        if dry:
            continue
        palabras = transcribir(fuente, c["_entra"], c["_dur"], modelo)
        with open(destino, "w", encoding="utf-8") as f:
            json.dump({"_": "%s — palabras con sus tiempos del corte %s (GENERADO por video/shorts/shorts.py subtitular; no editar)"
                            % (os.path.basename(destino), c["id"]),
                       "corte": c["id"], "entra": c["entra"], "sale": c["sale"],
                       "entra_s": c["_entra"], "sale_s": c["_sale"],
                       "modelo": modelo, "palabras": palabras}, f, ensure_ascii=False, indent=1)


def cargar_palabras(lote, corte):
    ruta = os.path.join(lote["_salida"], nombre_base(lote, corte) + ".palabras.json")
    if not os.path.exists(ruta):
        return None
    datos = _json(ruta)
    # Si el corte se ajustó después de subtitular, se reutilizan las palabras desplazadas
    # (solo si el nuevo tramo cae dentro del transcrito; si no, hay que volver a subtitular).
    ini = datos.get("entra_s", tc_a_s(datos["entra"]))
    fin = datos.get("sale_s", tc_a_s(datos["sale"]))
    if corte["_entra"] < ini - 0.05 or corte["_sale"] > fin + 0.05:
        print("  ⚠ %s: el tramo cambió fuera de lo transcrito; ejecute «subtitular» otra vez" % corte["id"])
        return None
    off = ini - corte["_entra"]
    palabras = []
    for p in datos["palabras"]:
        i, f = p["i"] + off, p["f"] + off
        if i >= -0.05 and f <= corte["_dur"] + 0.3:
            palabras.append({"p": p["p"], "i": max(0.0, i), "f": f})
    # Correcciones del lote: nombres propios y siglas que Whisper escribe mal.
    corr = {k.lower(): v for k, v in (lote.get("correcciones") or {}).items()}
    for p in palabras:
        limpio = re.sub(r"[^\wáéíóúüñ]", "", p["p"].lower())
        if limpio in corr:
            p["p"] = re.sub(re.escape(limpio), corr[limpio] or "", p["p"], flags=re.I)
    # Una corrección vacía une dos palabras en una («juzguin morismo» → «fujimorismo», «»).
    palabras = [p for p in palabras if re.sub(r"[^\wáéíóúüñ]", "", p["p"].lower())]
    # Whisper parte las cifras con separador de miles («1» «.200»): se vuelven a unir.
    unidas = []
    for p in palabras:
        if unidas and re.match(r"^[.,]\d", p["p"]) and re.search(r"\d$", unidas[-1]["p"]):
            unidas[-1] = dict(unidas[-1], p=unidas[-1]["p"] + p["p"], f=p["f"])
        else:
            unidas.append(p)
    return unidas


# ------------------------------------------------------------------ ASS


def _t(s):
    s = max(0.0, s)
    h, r = divmod(s, 3600)
    m, r = divmod(r, 60)
    return "%d:%02d:%05.2f" % (h, m, r)


def _esc(texto):
    return str(texto).replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def grupos_de_palabras(palabras, max_car=26, max_pausa=0.7):
    """Agrupa palabras en frases cortas de subtítulo (una o dos líneas)."""
    grupos, actual = [], []
    for p in palabras:
        largo = sum(len(x["p"]) + 1 for x in actual) + len(p["p"])
        pausa = actual and p["i"] - actual[-1]["f"] > max_pausa
        if actual and (largo > max_car or pausa):
            grupos.append(actual)
            actual = []
        actual.append(p)
        if re.search(r"[.?!]$", p["p"]):
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return grupos


def eventos_resaltados(grupo, acento, dur):
    """Subtítulo palabra a palabra de un grupo: [(inicio, fin, texto ASS)], la frase entera y la palabra
    que suena en `acento` (color ASS). Lo reutiliza el editor de video (editor/servidor/montaje.py)."""
    eventos = []
    for k, p in enumerate(grupo):
        i = p["i"]
        f = grupo[k + 1]["i"] if k + 1 < len(grupo) else p["f"]
        if f <= i or i >= dur:
            continue
        partes = []
        for j, q in enumerate(grupo):
            t = _esc(q["p"])
            partes.append("{\\c%s}%s{\\r}" % (acento, t) if j == k else t)
        eventos.append((i, min(f, dur), " ".join(partes)))
    return eventos


def geometria(m, formato, alto_medio=None):
    """Cajas de la pieza, dentro de las zonas seguras de layout.json."""
    # Cabecera y titular arriba; el medio (retrato u vídeo) en el tercio central; nombre sobre
    # el pie del medio; onda y subtítulos justo encima de la zona segura inferior.
    g = {"cab": m.sup - 110, "titular": m.sup + 30}
    g["rotulo"] = g["titular"] + 215          # titular de hasta dos líneas
    g["medio_y"] = g["rotulo"] + 75
    g["medio_h"] = alto_medio or (700 if formato == "audiograma" else 608)
    g["nombre"] = g["medio_y"] + g["medio_h"] - 110
    g["ondas"] = g["medio_y"] + g["medio_h"] + 10
    # Subtítulos: bajo la onda (audiograma) o pegados al vídeo (reencuadre, que no lleva onda).
    g["subs"] = g["ondas"] + 130 if formato == "audiograma" else g["medio_y"] + g["medio_h"] + 50
    g["pie"] = H - m.inf + 40
    return g


def escribir_ass(ruta, m, lote, corte, palabras, formato, dur, fijos=True):
    g = geometria(m, formato, alto_del_medio(lote, corte, formato))
    marca = lote.get("marca", {})
    der = m.lat + m.der_tiktok // 2
    c = {k: m.ass(v) for k, v in PALETA.items()}
    estilos = [
        # nombre, fuente, tamaño, color, contorno, negrita, alineación, margenV, bordestyle, fondo
        ("Programa", m.fuente_titular, 44, c["acento"], c["fondo"], 0, 7, g["cab"], 1, c["fondo"]),
        ("Emisora", m.fuente_texto, 32, c["texto_suave"], c["fondo"], -1, 7, g["cab"] + 58, 1, c["fondo"]),
        ("Titular", m.fuente_titular, 78, c["texto"], c["fondo"], 0, 7, g["titular"], 1, c["fondo"]),
        ("Rotulo", m.fuente_texto, 30, c["texto_suave"], c["fondo"], -1, 7, g["rotulo"], 1, c["fondo"]),
        ("Nombre", m.fuente_titular, 38, c["texto"], c["marca"], 0, 7, g["nombre"], 3, c["marca"]),
        ("Cargo", m.fuente_texto, 30, c["fondo"], c["acento"], -1, 7, g["nombre"] + 60, 3, c["acento"]),
        ("Subtitulo", m.fuente_texto, 70, c["texto"], c["fondo"], -1, 8, g["subs"], 1, c["fondo"]),
        ("Pie", m.fuente_texto, 28, c["texto_suave"], c["fondo"], -1, 7, g["pie"], 1, c["fondo"]),
    ]
    lin = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: %d" % W, "PlayResY: %d" % H,
           "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
           "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
           "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"]
    for (n, f, t, col, cont, neg, al, mv, bs, fondo) in estilos:
        contorno = 10 if bs == 3 else (3 if n == "Subtitulo" else 0)
        lin.append("Style: %s,%s,%d,%s,%s,%s,%s,%d,0,0,0,100,100,0,0,%d,%d,0,%d,%d,%d,%d,1"
                   % (n, f, t, col, col, cont, fondo, neg, bs, contorno, al, m.lat, der, mv))
    lin += ["", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    fin = _t(dur)

    def ev(estilo, texto, i=0.0, f=None, capa=1):
        lin.append("Dialogue: %d,%s,%s,%s,,0,0,0,,%s" % (capa, _t(i), f or fin, estilo, texto))

    if fijos and marca.get("programa"):
        ev("Programa", _esc(marca["programa"]).upper())
    voz = corte.get("voz") or marca.get("voz") or {}
    if fijos:
        if marca.get("emisora"):
            ev("Emisora", _esc(marca["emisora"]))
        if corte.get("titulo"):
            ev("Titular", _esc(corte["titulo"]))
        if corte.get("rotulo"):
            ev("Rotulo", _esc(corte["rotulo"]))
        if voz.get("nombre"):
            ev("Nombre", " " + _esc(voz["nombre"]) + " ")
        if voz.get("cargo"):
            ev("Cargo", " " + _esc(voz["cargo"]) + " ")
        if lote.get("pie") or marca.get("pie"):
            ev("Pie", _esc(lote.get("pie") or marca.get("pie")))

    # Subtítulos palabra a palabra: la frase entera en papel, la palabra que suena en acento.
    if palabras:
        for grupo in grupos_de_palabras(palabras):
            for i, f, texto in eventos_resaltados(grupo, c["acento"], dur):
                ev("Subtitulo", texto, i, _t(f), capa=2)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lin) + "\n")


# ------------------------------------------------------------------ render


def _esc_filtro(ruta):
    return ruta.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def alto_del_medio(lote, corte, formato):
    """En el reencuadre, el bloque de vídeo sigue la proporción del recuadre (ancho = 1080)."""
    r = corte.get("recuadre") or lote.get("recuadre")
    if formato == "reencuadre" and r:
        return int(round(W * r["h"] / r["w"] / 2.0)) * 2
    return None


def comando_render(m, lote, corte, red, ajustes, ass, salida, muestra):
    comun = ajustes["comun"]
    son = comun["sonoridad"]
    formato = corte.get("formato", "audiograma")
    g = geometria(m, formato, alto_del_medio(lote, corte, formato))
    dur = min(corte["_dur"], muestra) if muestra else corte["_dur"]
    fps = comun["fps"]
    fondo = m.ffmpeg(PALETA["fondo"])
    fuente = lote["_video"] if formato == "reencuadre" else (lote["_audio"] or lote["_video"])
    if not fuente or not os.path.exists(fuente):
        raise SystemExit("corte %s: no existe la fuente de %s" % (corte["id"], formato))

    ent = ["-ss", "%.3f" % corte["_entra"], "-t", "%.3f" % dur, "-i", fuente]
    filtros = ["color=c=%s:s=%dx%d:r=%d:d=%.3f[bg]" % (fondo, W, H, fps, dur)]
    audio = ("[0:a]loudnorm=I=%s:TP=%s:LRA=%s,aresample=%d,asplit=2[aout][aw]"
             % (son["lufs"], son["pico_verdadero_db"], son["rango_lra"], comun["audio"]["muestreo"]))
    filtros.append(audio)
    if formato == "reencuadre":
        r = corte.get("recuadre") or lote.get("recuadre") or {}
        if r:
            crop = "crop=%d:%d:%d:%d," % (r["w"], r["h"], r["x"], r["y"])
        else:
            crop = ""
        filtros.append("[0:v]%sscale=%d:-2,setsar=1,fps=%d[vid]" % (crop, W, fps))
        filtros.append("[bg][vid]overlay=0:%d:shortest=1[b1]" % g["medio_y"])
        filtros.append("[aw]anullsink")
        ultimo = "b1"
    else:
        img = corte["_imagen"]
        if not img or not os.path.exists(img):
            raise SystemExit("corte %s: el audiograma necesita «imagen»" % corte["id"])
        ent += ["-loop", "1", "-t", "%.3f" % dur, "-i", img]
        alto_img = g["medio_h"]
        filtros.append("[1:v]scale=-2:%d,format=rgba[foto]" % alto_img)
        filtros.append("[bg][foto]overlay=(W-w)/2:%d:shortest=1[b0]" % g["medio_y"])
        filtros.append("[aw]showwaves=s=%dx110:mode=cline:scale=sqrt:draw=full:rate=%d:colors=%s,"
                       "format=rgba[ondas]" % (W - 2 * m.lat, fps, m.ffmpeg(PALETA["onda"])))
        filtros.append("[b0][ondas]overlay=%d:%d[b1]" % (m.lat, g["ondas"]))
        ultimo = "b1"
    # Barra de progreso arriba (ancla primaria).
    filtros.append("color=c=%s:s=%dx12:r=%d:d=%.3f[barra]" % (m.ffmpeg(PALETA["marca"]), W, fps, dur))
    filtros.append("[%s][barra]overlay=x='-W+W*t/%.3f':y=0[b2]" % (ultimo, dur))
    filtros.append("[b2]ass='%s'[v]" % _esc_filtro(ass))

    v = comun["video"]
    a = comun["audio"]
    return (["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + ent +
            ["-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "[aout]",
             "-c:v", v["codec"], "-crf", str(v["crf"]), "-preset", v["preset"],
             "-profile:v", v["perfil"], "-pix_fmt", v["pix_fmt"], "-r", str(fps),
             "-c:a", a["codec"], "-b:a", a["bitrate"], "-ar", str(a["muestreo"]),
             "-t", "%.3f" % dur, "-movflags", "+faststart", salida])


def render(lote, cortes, red, muestra, incluir_verificar, dry, limpio=False):
    _requiere("ffmpeg")
    m = Marca()
    ajustes = _json(os.path.join(AQUI, "redes.json"))
    if red not in ajustes["redes"]:
        nucleo.abortar(log, "red desconocida: %s (hay: %s)" % (red, ", ".join(ajustes["redes"])))
    limite = ajustes["redes"][red]["max_s"]
    if not dry:
        os.makedirs(lote["_salida"], exist_ok=True)
    for c in cortes:
        borrador = c.get("estado") != "publicable"
        if borrador and not incluir_verificar:
            print("· %s  omitido: estado «%s» (use --incluir-verificar: sale con «-por-verificar» en el nombre)"
                  % (c["id"], c.get("estado")))
            continue
        aviso = "  ⚠ %ds supera el máximo de %s (%ds)" % (c["_dur"], red, limite) if c["_dur"] > limite else ""
        # Un corte no publicable no lleva marca en la imagen (se revisa en grupo): lo delata el nombre.
        base = (nombre_base(lote, c) + "-" + red + ("-muestra" if muestra else "") + ("-limpio" if limpio else "")
                + ("-por-verificar" if borrador else ""))
        salida = os.path.join(lote["_salida"], base + ".mp4")
        palabras = None if limpio else cargar_palabras(lote, c)
        print("· %s  %s  %s–%s (%s)%s%s  → %s" % (
            c["id"], c.get("formato", "audiograma"), c["entra"], c["sale"], s_a_tc(c["_dur"]),
            "  sin subtítulos (versión limpia)" if limpio else ("" if palabras else "  sin subtítulos (falta «subtitular»)"),
            aviso, os.path.basename(salida)))
        ass = os.path.join(lote["_salida"], base + ".ass")
        dur = min(c["_dur"], muestra) if muestra else c["_dur"]
        cmd = comando_render(m, lote, c, red, ajustes, ass, salida, muestra)
        if dry:
            print("  " + " ".join("'%s'" % x if (" " in x or ";" in x) else x for x in cmd))
            continue
        escribir_ass(ass, m, lote, c, palabras, c.get("formato", "audiograma"), dur)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            nucleo.abortar(log, "ffmpeg falló en %s:\n%s" % (c["id"], (r.stderr or "").strip()[-800:]))


# ------------------------------------------------------------------ portadas (Inkscape)


def _inkscape():
    """El CLI de Inkscape: el nativo (APT) si existe; si no, el Flatpak. La decisión vive en un solo
    sitio del estudio, lib/herramientas.py (herramienta)."""
    from lib.herramientas import herramienta   # la raíz del estudio ya está en sys.path (lib/nucleo)
    cmd, _via = herramienta("inkscape")
    if not cmd:
        nucleo.abortar(log, "no hay Inkscape (ni APT ni Flatpak)")
    return cmd


def _lineas(texto, ancho_px, tam_max, tam_min=56, factor=0.66):
    """Parte el titular en líneas sin cortar palabras y elige el mayor tamaño que cabe en el ancho
    (factor: ancho medio de un carácter de Archivo Black respecto del cuerpo)."""
    import textwrap
    for tam in range(tam_max, tam_min - 1, -4):
        por_linea = max(8, int(ancho_px / (tam * factor)))
        lineas = textwrap.wrap(texto, por_linea, break_long_words=False)
        if len(lineas) <= 4 and max(len(l) for l in lineas) * tam * factor <= ancho_px:
            return lineas, tam
    return textwrap.wrap(texto, int(ancho_px / (tam_min * factor)), break_long_words=False), tam_min


def svg_portada(m, lote, corte, imagen, alto_img):
    """Portada vertical: el titular y el rostro caen en la franja 4:5 central (1080×1350, y 285–1635)
    que Instagram muestra en la cuadrícula; cabecera y rótulo de fuente, fuera de ella."""
    from urllib.parse import quote
    from xml.sax.saxutils import escape as x
    marca = lote.get("marca", {})
    voz = corte.get("voz") or marca.get("voz") or {}
    ancho = W - 2 * m.lat
    lineas, tam = _lineas(corte.get("titulo", ""), ancho, 104)
    y_tit = 470
    tspans = "".join('<tspan x="%d" dy="%s">%s</tspan>' % (m.lat, "0" if i == 0 else "1.08em", x(l))
                     for i, l in enumerate(lineas))
    y_img = y_tit + int(len(lineas) * tam * 1.08) + 20
    y_img = max(y_img, 760)
    if corte.get("formato") == "reencuadre":
        img = '<image x="0" y="%d" width="%d" height="%d" preserveAspectRatio="xMidYMid slice" href="file://%s"/>' % (
            y_img, W, alto_img, quote(imagen))
        y_nom = y_img + alto_img - 120
    else:
        alto = 1635 - y_img
        img = '<image x="0" y="%d" width="%d" height="%d" preserveAspectRatio="xMidYMax meet" href="file://%s"/>' % (
            y_img, W, alto, quote(imagen))
        y_nom = 1635 - 130
    def t(xx, yy, tamano, color, fuente, texto, peso="normal"):
        return ('<text x="%d" y="%d" style="font-family:\'%s\';font-size:%dpx;font-weight:%s;fill:%s">%s</text>'
                % (xx, yy, fuente, tamano, peso, m.hex(color), x(texto)))
    nombre, cargo = voz.get("nombre", ""), voz.get("cargo", "")
    wn = int(40 * 0.62 * len(nombre)) + 44
    wc = int(32 * 0.56 * len(cargo)) + 44
    rotulo = ""
    if nombre:
        rotulo += '<rect x="%d" y="%d" width="%d" height="64" fill="%s"/>' % (m.lat - 10, y_nom, wn, m.hex(PALETA["marca"]))
        rotulo += t(m.lat + 12, y_nom + 46, 40, PALETA["texto"], m.fuente_titular, nombre)
    if cargo:
        rotulo += '<rect x="%d" y="%d" width="%d" height="54" fill="%s"/>' % (m.lat - 10, y_nom + 64, wc, m.hex(PALETA["acento"]))
        rotulo += t(m.lat + 12, y_nom + 104, 32, PALETA["fondo"], m.fuente_texto, cargo, "bold")
    return """<?xml version="1.0" encoding="UTF-8"?>
<!-- portada de {id} · GENERADO por video/shorts/shorts.py portadas; se puede retocar en Inkscape -->
<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <rect width="{W}" height="{H}" fill="{fondo}"/>
  <rect width="{W}" height="14" fill="{marca_c}"/>
  <g inkscape:label="Imagen">{img}</g>
  {prog}
  {emis}
  <text x="{lat}" y="{y_tit}" style="font-family:'{ft}';font-size:{tam}px;fill:{texto}" inkscape:label="Titular">{tspans}</text>
  <g inkscape:label="Rótulo nombre y cargo">{rotulo}</g>
  {fuente}
</svg>
""".format(id=x(str(corte["id"])), W=W, H=H, fondo=m.hex(PALETA["fondo"]), marca_c=m.hex(PALETA["marca"]), img=img,
           prog=t(m.lat, 330, 46, PALETA["acento"], m.fuente_titular, marca.get("programa", "").upper()),
           emis=t(m.lat, 388, 32, PALETA["texto_suave"], m.fuente_texto, marca.get("emisora", ""), "bold"),
           lat=m.lat, y_tit=y_tit + tam, ft=m.fuente_titular, tam=tam, texto=m.hex(PALETA["texto"]), tspans=tspans,
           rotulo=rotulo, fuente=t(m.lat, 1700, 30, PALETA["texto_suave"], m.fuente_texto, corte.get("rotulo", ""), "bold"))


def portadas(lote, cortes, incluir_verificar, dry):
    m = Marca()
    if not dry:
        os.makedirs(lote["_salida"], exist_ok=True)
    for c in cortes:
        borrador = c.get("estado") != "publicable"
        if borrador and not incluir_verificar:
            print("· %s  omitido: estado «%s»" % (c["id"], c.get("estado")))
            continue
        base = nombre_base(lote, c) + "-portada" + ("-por-verificar" if borrador else "")
        svg = os.path.join(lote["_salida"], base + ".svg")
        png = os.path.join(lote["_salida"], base + ".png")
        alto_img = 810
        if c.get("formato") == "reencuadre":
            # Fotograma del centro del corte, con el mismo recuadre que el vídeo.
            imagen = os.path.join(lote["_salida"], base + "-fotograma.png")
            r = c.get("recuadre") or lote.get("recuadre") or {}
            crop = "crop=%d:%d:%d:%d," % (r["w"], r["h"], r["x"], r["y"]) if r else ""
            alto_img = alto_del_medio(lote, c, "reencuadre") or 608
            cmd_f = ["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.2f" % (c["_entra"] + c["_dur"] / 2),
                     "-i", lote["_video"], "-frames:v", "1", "-vf", crop + "scale=%d:-2" % W, imagen]
        else:
            imagen, cmd_f = c["_imagen"], None
        print("· %s  %s  → %s" % (c["id"], c.get("formato", "audiograma"), os.path.basename(png)))
        if dry:
            continue
        if cmd_f:
            subprocess.run(cmd_f, check=True)
        with open(svg, "w", encoding="utf-8") as f:
            f.write(svg_portada(m, lote, c, imagen, alto_img))
        r = subprocess.run(_inkscape() + ["--export-type=png", "--export-filename=" + png, svg],
                           capture_output=True, text=True)
        if not os.path.exists(png):
            nucleo.abortar(log, "Inkscape no exportó %s:\n%s" % (c["id"], r.stderr[-600:]))


# ------------------------------------------------------------------ proyecto de Kdenlive


def _xml(t):
    from xml.sax.saxutils import escape
    return escape(str(t), {'"': "&quot;"})


def _k_prop(nombre, valor):
    return '<property name="%s">%s</property>' % (nombre, _xml(valor))


def _k_chain(cid, kid, recurso, frames, extra=""):
    """Clip de vídeo o audio (Kdenlive ≥ 23.04 usa <chain>). `length` es obligatoria: sin ella MLT
    toma el clip como de longitud cero y la imagen sale negra (comprobado el 2026-09-30)."""
    return ('<chain id="%s" out="%d">%s%s%s%s%s%s%s%s%s</chain>' % (
        cid, frames - 1, _k_prop("length", frames), _k_prop("eof", "pause"), _k_prop("resource", recurso),
        _k_prop("mlt_service", "avformat-novalidate"), _k_prop("seekable", 1), _k_prop("audio_index", 1),
        _k_prop("video_index", 0), _k_prop("kdenlive:clip_type", 0),
        _k_prop("kdenlive:folderid", -1) + _k_prop("kdenlive:id", kid) + extra))


def _k_imagen(pid, kid, recurso, frames):
    return ('<producer id="%s" in="0" out="%d">%s%s%s%s%s%s%s</producer>' % (
        pid, frames - 1, _k_prop("length", frames), _k_prop("eof", "pause"), _k_prop("resource", recurso),
        _k_prop("mlt_service", "qimage"), _k_prop("ttl", 25), _k_prop("kdenlive:clip_type", 2),
        _k_prop("kdenlive:folderid", -1) + _k_prop("kdenlive:id", kid)))


def _k_pista(tid, entradas, audio, nombre):
    """Pista de Kdenlive: un tractor con dos playlists (la segunda, vacía, es la de mezclas)."""
    marca = _k_prop("kdenlive:audio_track", 1) if audio else ""
    oculta = "video" if audio else "audio"
    return ('<playlist id="%s_a">%s%s</playlist><playlist id="%s_b">%s</playlist>'
            '<tractor id="%s" in="0">%s%s%s<track hide="%s" producer="%s_a"/><track hide="%s" producer="%s_b"/></tractor>'
            % (tid, marca, entradas, tid, marca, tid, marca, _k_prop("kdenlive:trackheight", 67),
               _k_prop("kdenlive:track_name", nombre), oculta, tid, oculta, tid))


def proyecto_kdenlive(lote, corte, limpio, portada, fps=30):
    """Proyecto de Kdenlive en el formato de documento 1.1, copiado de sus propias pruebas
    (tests/dataset/clip-ids.kdenlive en KDE/kdenlive): secuencia con uuid, dos pistas de audio y dos
    de vídeo, el corte limpio en A1 y V1, y en la bandeja el corte, la portada y el directo completo.
    Los subtítulos no se incrustan: van en el .ass de al lado (Subtítulos → Importar)."""
    import uuid
    n = int(round(corte["_dur"] * fps))
    u = "{%s}" % uuid.uuid5(uuid.NAMESPACE_URL, "identidad-shorts/" + limpio)
    fuente = lote["_video"] or lote["_audio"]
    # Clips de la línea de tiempo: el mismo archivo, uno solo con audio y otro solo con imagen.
    audio = _k_chain("clip_a1", 4, limpio, n, _k_prop("set.test_audio", 0) + _k_prop("set.test_image", 1))
    video = _k_chain("clip_v1", 4, limpio, n, _k_prop("set.test_audio", 1) + _k_prop("set.test_image", 0))
    ent = lambda cid: '<entry producer="%s" in="0" out="%d">%s</entry>' % (cid, n - 1, _k_prop("kdenlive:id", 4))
    pistas = (_k_pista("pista_a1", ent("clip_a1"), True, "Voz") + _k_pista("pista_a2", "", True, "Música") +
              _k_pista("pista_v1", ent("clip_v1"), False, "Corte") +
              _k_pista("pista_v2", "", False, "Títulos de la identidad"))
    mezclas = "".join(
        '<transition id="mezcla%d">%s%s%s%s%s</transition>' % (b, _k_prop("a_track", 0), _k_prop("b_track", b),
                                                           _k_prop("mlt_service", "mix"), _k_prop("kdenlive_id", "mix"),
                                                           _k_prop("internal_added", 237) + _k_prop("always_active", 1) + _k_prop("sum", 1))
        for b in (1, 2)) + "".join(
        '<transition id="mezcla%d">%s%s%s%s%s</transition>' % (b, _k_prop("a_track", 0), _k_prop("b_track", b),
                                                           _k_prop("compositing", 0), _k_prop("mlt_service", "qtblend"),
                                                         _k_prop("internal_added", 237) + _k_prop("always_active", 1))
        for b in (3, 4))
    # Kdenlive numera el audio desde la pista más cercana al vídeo: la voz va la última de las de
    # audio para quedar en A1 (comprobado al abrir el proyecto en Kdenlive 25.12).
    secuencia = ('<tractor id="%s" in="0" out="%d">%s<track producer="negro"/><track producer="pista_a2"/>'
                 '<track producer="pista_a1"/><track producer="pista_v1"/><track producer="pista_v2"/>%s</tractor>' % (
                     u, n - 1, "".join(_k_prop(k, v) for k, v in [
                         ("kdenlive:uuid", u), ("kdenlive:clipname", str(corte["id"])),
                         ("kdenlive:sequenceproperties.hasAudio", 1), ("kdenlive:sequenceproperties.hasVideo", 1),
                         ("kdenlive:sequenceproperties.activeTrack", 3), ("kdenlive:sequenceproperties.tracksCount", 4),
                         ("kdenlive:sequenceproperties.documentuuid", u), ("kdenlive:sequenceproperties.audioTarget", 2),
                         ("kdenlive:sequenceproperties.videoTarget", 3), ("kdenlive:producer_type", 17),
                         ("kdenlive:id", 3), ("kdenlive:clip_type", 0), ("kdenlive:folderid", 2)]), mezclas))
    bandeja = [_k_chain("bin_corte", 4, limpio, n)]
    entradas = ['<entry producer="%s" in="0" out="0"/>' % u, '<entry producer="bin_corte" in="0" out="%d"/>' % (n - 1)]
    if portada and os.path.exists(portada):
        bandeja.append(_k_imagen("bin_portada", 5, portada, 5 * fps))
        entradas.append('<entry producer="bin_portada" in="0" out="%d"/>' % (5 * fps - 1))
    if fuente and os.path.exists(fuente):
        bandeja.append(_k_chain("bin_directo", 6, fuente, n))
        entradas.append('<entry producer="bin_directo" in="0" out="%d"/>' % (n - 1))
    docprops = "".join(_k_prop(k, v) for k, v in [
        ("kdenlive:folder.-1.2", "Sequences"), ("kdenlive:sequenceFolder", 2),
        ("kdenlive:docproperties.version", "1.1"), ("kdenlive:docproperties.uuid", u),
        ("kdenlive:docproperties.opensequences", u), ("kdenlive:docproperties.activetimeline", u),
        ("kdenlive:docproperties.profile", "vertical_1080p_30"), ("kdenlive:docproperties.audioChannels", 2),
        ("kdenlive:docproperties.compositing", 1), ("xml_retain", 1)])
    return """<?xml version='1.0' encoding='utf-8'?>
<!-- proyecto de {id} · GENERADO por video/shorts/shorts.py kdenlive; ábralo en Kdenlive y guárdelo con otro nombre para editarlo -->
<mlt LC_NUMERIC="C" producer="main_bin" version="7.36.0" root="{raiz}">
 <profile description="Vertical 1080x1920 30 fps (identidad visual)" width="1080" height="1920" progressive="1" sample_aspect_num="1" sample_aspect_den="1" display_aspect_num="9" display_aspect_den="16" frame_rate_num="{fps}" frame_rate_den="1" colorspace="709"/>
 <producer id="negro" in="0" out="{fin}"><property name="length">2147483647</property><property name="eof">continue</property><property name="resource">black</property><property name="mlt_service">color</property><property name="kdenlive:playlistid">black_track</property><property name="mlt_image_format">rgba</property><property name="set.test_audio">0</property></producer>
 {audio}
 {video}
 {pistas}
 {secuencia}
 {bandeja}
 <playlist id="main_bin">{docprops}{entradas}</playlist>
 <tractor id="proyecto" in="0" out="{fin}"><property name="kdenlive:projectTractor">1</property><track producer="{u}" in="0" out="{fin}"/></tractor>
</mlt>
""".format(id=_xml(corte["id"]), raiz=_xml(os.path.dirname(limpio)), fps=fps, fin=n - 1, audio=audio, video=video,
           pistas=pistas, secuencia=secuencia, bandeja="\n ".join(bandeja), docprops=docprops,
           entradas="".join(entradas), u=u)


def kdenlive(lote, cortes, red, incluir_verificar, dry):
    """Por corte: versión limpia (sin subtítulos grabados), .ass solo con los subtítulos y proyecto."""
    m = Marca()
    for c in cortes:
        borrador = c.get("estado") != "publicable"
        if borrador and not incluir_verificar:
            print("· %s  omitido: estado «%s»" % (c["id"], c.get("estado")))
            continue
        suf = "-por-verificar" if borrador else ""
        base = nombre_base(lote, c)
        limpio = os.path.join(lote["_salida"], "%s-%s-limpio%s.mp4" % (base, red, suf))
        subs = os.path.join(lote["_salida"], "%s-subtitulos%s.ass" % (base, suf))
        portada = os.path.join(lote["_salida"], "%s-portada%s.png" % (base, suf))
        proyecto = os.path.join(lote["_salida"], "%s%s.kdenlive" % (base, suf))
        print("· %s  → %s" % (c["id"], os.path.basename(proyecto)))
        if dry:
            continue
        if not os.path.exists(limpio):
            render(lote, [c], red, 0, True, False, limpio=True)
        palabras = cargar_palabras(lote, c)
        if palabras:
            escribir_ass(subs, m, lote, c, palabras, c.get("formato", "audiograma"), c["_dur"], fijos=False)
        contenido = proyecto_kdenlive(lote, c, limpio, portada)
        with open(proyecto, "w", encoding="utf-8") as f:
            f.write(contenido)


def plan(lote, cortes_todos):
    print("lote: %s · salida: %s" % (lote.get("episodio"), lote["_salida"]))
    for c in cortes_todos:
        print("  %-6s %-11s %-12s %s–%s (%s)  %s" % (
            c["id"], c.get("formato", "audiograma"), c.get("estado", "?"), c["entra"], c["sale"],
            s_a_tc(c["_dur"]), c.get("titulo", "")))


def main():
    ap = argparse.ArgumentParser(description="Cortes verticales con la identidad del sistema.")
    sub = ap.add_subparsers(dest="orden", required=True)
    for n in ("subtitular", "render", "portadas", "kdenlive", "plan"):
        p = sub.add_parser(n)
        p.add_argument("lote")
        p.add_argument("--id", nargs="*", default=[])
        p.add_argument("--dry-run", action="store_true", help="muestra lo que haría, sin escribir")
        if n == "subtitular":
            p.add_argument("--modelo", default="small")
        if n in ("portadas", "kdenlive"):
            p.add_argument("--incluir-verificar", action="store_true")
        if n == "kdenlive":
            p.add_argument("--red", default="reels")
        if n == "render":
            p.add_argument("--red", default="reels")
            p.add_argument("--muestra", type=float, default=0, help="solo los primeros N segundos")
            p.add_argument("--incluir-verificar", action="store_true",
                           help="compone también los cortes no publicables («-por-verificar» en el nombre)")
            p.add_argument("--limpio", action="store_true",
                           help="sin subtítulos grabados (para editar en Kdenlive con el .ass aparte)")
    a = ap.parse_args()
    lote = leer_lote(a.lote)
    if a.orden == "plan":
        return plan(lote, lote.get("cortes", []))
    incluir = getattr(a, "incluir_verificar", False) or a.orden == "subtitular"
    cortes = elegir(lote, a.id, incluir)
    if a.orden == "subtitular":
        subtitular(lote, cortes, a.modelo, a.dry_run)
    elif a.orden == "portadas":
        portadas(lote, cortes, a.incluir_verificar, a.dry_run)
    elif a.orden == "kdenlive":
        kdenlive(lote, cortes, a.red, a.incluir_verificar, a.dry_run)
    else:
        render(lote, cortes, a.red, a.muestra, a.incluir_verificar, a.dry_run, a.limpio)


if __name__ == "__main__":
    main()
