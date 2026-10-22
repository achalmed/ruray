# -*- coding: utf-8 -*-
"""editor/servidor/montaje.py — del proyecto del editor de video (video.html) a una orden de ffmpeg.

Función pura (sin E/S ni ffmpeg): recibe el proyecto en JSON (lista de decisiones de edición: pistas y
clips), lo que ffprobe dijo de cada medio y cómo se llama cada medio en disco, y devuelve los argumentos
de ffmpeg y el texto ASS de los títulos. La usan el servidor (render en esta computadora) y el navegador
(ffmpeg.wasm pide el plan al servidor y lo ejecuta con sus propios nombres de archivo), así que hay UN solo
constructor y la vista previa del navegador imita sus reglas (video.html, «Compositor»).

Modelo (todo en segundos; posiciones en fracciones del cuadro):
  proyecto = {ancho, alto, fps, pistas:[{id, tipo: video|texto|audio, silencio, solo, oculta, bloqueada}], clips:[…]}
  clip     = {id, pista, tipo: video|imagen|audio|texto, origen, inicio, duracion, entrada, velocidad,
              volumen, silencio, fundido_entrada, fundido_salida, opacidad, ajustes{br,ct,sat},
              recorte{x,y,w,h}, encaje: cubrir|contener, kb{ini{escala,x,y}, fin{…}}, transicion{tipo,dur},
              ducking, texto{…}}
Las pistas van en el orden de la pantalla (arriba → abajo): se compone de abajo hacia arriba y los
títulos (ASS, libass) quedan encima de todo.

Transición de entrada de un clip B (sobre el clip A que termina donde B empieza, en la misma pista):
  fundido   A se prolonga `dur` bajo B (último cuadro congelado si no hay más material) y B aparece
  deslizar  A se prolonga y B entra desde la derecha
  barrido   A se prolonga y B se descubre de izquierda a derecha
  negro     A se funde a negro en dur/2 y B aparece desde negro en dur/2
El audio de A y B se cruza en el mismo tramo.

Los subtítulos palabra a palabra reutilizan video/shorts/shorts.py (grupos y resaltado) para que el
editor y los cortes verticales digan lo mismo de la misma manera.
"""
import importlib.util
import os
import re

TIPOS_CLIP = ("video", "imagen", "audio", "texto")
TIPOS_PISTA = ("video", "texto", "audio")
TRANSICIONES = ("fundido", "negro", "deslizar", "barrido")
ESTILOS_TEXTO = ("titular", "rotulo", "subtitulo", "libre")
ROLES_COLOR = ("texto", "texto_suave", "acento", "marca", "fondo")
MAX_CLIPS = 200
CONTIGUO = 0.05          # dos clips se tocan si el hueco es menor que esto (s)

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

_shorts = None


def shorts():
    """video/shorts/shorts.py como módulo (subtítulos palabra a palabra, ASS, sonoridad)."""
    global _shorts
    if _shorts is None:
        ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "video", "shorts", "shorts.py")
        spec = importlib.util.spec_from_file_location("shorts_identidad", ruta)
        _shorts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_shorts)
    return _shorts


# ------------------------------------------------------------------ normalizar


def _num(v, defecto, lo=None, hi=None):
    try:
        x = float(v)
    except (TypeError, ValueError):
        x = float(defecto)
    if x != x:          # NaN
        x = float(defecto)
    if lo is not None:
        x = max(lo, x)
    if hi is not None:
        x = min(hi, x)
    return x


def _par(n):
    """Entero par (H.264 4:2:0 exige ancho y alto pares)."""
    return int(round(n / 2.0)) * 2


def normalizar(proyecto):
    """Copia saneada del proyecto: tipos válidos, números acotados, nada que llegue a ffmpeg sin pasar
    por float() o por las listas cerradas de arriba. Lanza ValueError si no hay nada que exportar."""
    if not isinstance(proyecto, dict):
        raise ValueError("el proyecto no es un objeto")
    W = _par(_num(proyecto.get("ancho"), 1080, 64, 3840))
    H = _par(_num(proyecto.get("alto"), 1920, 64, 3840))
    fps = int(_num(proyecto.get("fps"), 30, 12, 60))
    pistas = []
    for i, p in enumerate(proyecto.get("pistas") or []):
        if not isinstance(p, dict) or p.get("tipo") not in TIPOS_PISTA:
            continue
        pistas.append({"id": str(p.get("id") or "p%d" % i), "tipo": p["tipo"],
                       "silencio": bool(p.get("silencio")), "oculta": bool(p.get("oculta")),
                       "solo": bool(p.get("solo")) and p["tipo"] != "texto"})
    # «Solo» (como en una mesa de mezcla): si alguna pista con sonido lo tiene, solo suenan las que lo tienen.
    # El bloqueo de una pista («bloqueada») es de la edición: no cambia el render.
    if any(p["solo"] for p in pistas):
        for p in pistas:
            if p["tipo"] != "texto" and not p["solo"]:
                p["silencio"] = True
    ids = {p["id"]: p for p in pistas}
    clips = []
    for c in (proyecto.get("clips") or [])[:MAX_CLIPS]:
        if not isinstance(c, dict) or c.get("tipo") not in TIPOS_CLIP or str(c.get("pista")) not in ids:
            continue
        pista = ids[str(c["pista"])]
        dur = _num(c.get("duracion"), 0, 0, 6 * 3600)
        if dur < 0.04:
            continue
        aj = c.get("ajustes") or {}
        rc = c.get("recorte") or {}
        kb = c.get("kb") or {}
        tr = c.get("transicion") or {}

        def punto(d):
            d = d if isinstance(d, dict) else {}
            return {"escala": _num(d.get("escala"), 1, 0.1, 8), "x": _num(d.get("x"), 0, -2, 2),
                    "y": _num(d.get("y"), 0, -2, 2)}

        rx, ry = _num(rc.get("x"), 0, 0, 0.95), _num(rc.get("y"), 0, 0, 0.95)
        n = {
            "id": str(c.get("id") or len(clips)), "pista": pista["id"], "tipo": c["tipo"],
            "origen": str(c.get("origen") or ""),
            "inicio": _num(c.get("inicio"), 0, 0, 6 * 3600), "duracion": dur,
            "entrada": _num(c.get("entrada"), 0, 0, 24 * 3600),
            "velocidad": _num(c.get("velocidad"), 1, 0.25, 4),
            "volumen": _num(c.get("volumen"), 1, 0, 4),
            "silencio": bool(c.get("silencio")) or pista["silencio"],
            "fundido_entrada": _num(c.get("fundido_entrada"), 0, 0, dur),
            "fundido_salida": _num(c.get("fundido_salida"), 0, 0, dur),
            "opacidad": _num(c.get("opacidad"), 1, 0, 1),
            "ajustes": {"br": _num(aj.get("br"), 100, 0, 200), "ct": _num(aj.get("ct"), 100, 0, 200),
                        "sat": _num(aj.get("sat"), 100, 0, 300)},
            "recorte": {"x": rx, "y": ry, "w": _num(rc.get("w"), 1, 0.05, 1 - rx),
                        "h": _num(rc.get("h"), 1, 0.05, 1 - ry)},
            "kb": {"ini": punto(kb.get("ini")), "fin": punto(kb.get("fin") or kb.get("ini"))},
            "encaje": "contener" if c.get("encaje") == "contener" else "cubrir",
            "transicion": None, "ducking": bool(c.get("ducking")),
            "oculto": pista["oculta"], "pista_tipo": pista["tipo"],
        }
        if tr.get("tipo") in TRANSICIONES and _num(tr.get("dur"), 0) > 0.04:
            n["transicion"] = {"tipo": tr["tipo"], "dur": _num(tr.get("dur"), 0.5, 0.04, dur * 0.9)}
        if c["tipo"] == "texto":
            n["texto"] = _texto(c.get("texto") or {})
        clips.append(n)
    total = max([c["inicio"] + c["duracion"] for c in clips if not c["oculto"]] or [0])
    if total <= 0.04:
        raise ValueError("la línea de tiempo está vacía")
    return {"ancho": W, "alto": H, "fps": fps, "pistas": pistas, "clips": clips, "duracion": round(total, 3)}


def _texto(t):
    estilo = t.get("estilo") if t.get("estilo") in ESTILOS_TEXTO else "libre"
    palabras = []
    for p in (t.get("palabras") or [])[:2000]:
        if isinstance(p, dict) and str(p.get("p", "")).strip():
            palabras.append({"p": str(p["p"]).strip()[:80], "i": _num(p.get("i"), 0, 0), "f": _num(p.get("f"), 0, 0)})
    color = t.get("color") if t.get("color") in ROLES_COLOR else None
    return {"estilo": estilo, "contenido": str(t.get("contenido") or "")[:2000],
            "cargo": str(t.get("cargo") or "")[:300],
            "x": _num(t.get("x"), 0.5, 0, 1), "y": _num(t.get("y"), 0.5, 0, 1),
            "tam": _num(t.get("tam"), 0, 0, 400), "color": color,
            "caja": bool(t.get("caja")), "alinear": t.get("alinear") if t.get("alinear") in ("izq", "centro", "der") else None,
            "resaltado": t.get("resaltado") == "palabra", "palabras": palabras}


# ------------------------------------------------------------------ transiciones


def planificar_transiciones(clips):
    """Por clip: cuánto se prolonga bajo el siguiente (ext), su fundido de entrada y salida efectivo y
    el tipo de entrada (deslizar/barrido). Reglas compartidas con la vista previa."""
    plan = {c["id"]: {"ext": 0.0, "fi": c["fundido_entrada"], "fo": c["fundido_salida"],
                      "afi": c["fundido_entrada"], "afo": c["fundido_salida"], "aext": 0.0,
                      "entra": None, "dur_entra": 0.0} for c in clips}
    por_pista = {}
    for c in clips:
        por_pista.setdefault(c["pista"], []).append(c)
    for lista in por_pista.values():
        lista.sort(key=lambda c: c["inicio"])
        for k, b in enumerate(lista):
            tr = b.get("transicion")
            if not tr:
                continue
            d = tr["dur"]
            a = next((x for x in reversed(lista[:k]) if abs(x["inicio"] + x["duracion"] - b["inicio"]) < CONTIGUO), None)
            pb = plan[b["id"]]
            if tr["tipo"] == "negro":
                pb["fi"] = max(pb["fi"], d / 2)
                pb["afi"] = max(pb["afi"], d / 2)
                if a:
                    pa = plan[a["id"]]
                    pa["fo"] = max(pa["fo"], min(d / 2, a["duracion"]))
                    pa["afo"] = max(pa["afo"], min(d / 2, a["duracion"]))
                continue
            pb["afi"] = max(pb["afi"], d)
            if tr["tipo"] == "fundido":
                pb["fi"] = max(pb["fi"], d)
            else:
                pb["entra"], pb["dur_entra"] = tr["tipo"], d
            if a:
                pa = plan[a["id"]]
                pa["ext"] = max(pa["ext"], d)
                pa["aext"] = max(pa["aext"], d)
            elif tr["tipo"] != "fundido":
                pb["fi"] = max(pb["fi"], 0)   # sin clip previo: entra sobre el fondo
    return plan


# ------------------------------------------------------------------ video


def _f(x):
    return "%.4f" % x


def _atempo(v):
    """atempo admite 0.5–2 por eslabón: 0.25 → 0.5,0.5; 4 → 2,2."""
    eslabones = []
    while v < 0.5 - 1e-9:
        eslabones.append(0.5)
        v /= 0.5
    while v > 2 + 1e-9:
        eslabones.append(2.0)
        v /= 2.0
    if abs(v - 1) > 1e-6:
        eslabones.append(v)
    return ",".join("atempo=%.5f" % e for e in eslabones)


def _cadena_visual(c, p, sondeo, W, H, fps):
    """Filtros de un clip visual en su tiempo propio (0…largo) hasta un cuadro RGBA listo para superponer."""
    dur, ext = c["duracion"], p["ext"]
    largo = dur + ext
    f = []
    if c["tipo"] == "video":
        if abs(c["velocidad"] - 1) > 1e-6:
            f.append("setpts=(PTS-STARTPTS)/%.5f" % c["velocidad"])
        else:
            f.append("setpts=PTS-STARTPTS")
        f.append("fps=%d" % fps)
    else:
        f.append("setpts=PTS-STARTPTS")
    sw, sh = max(2, int(sondeo.get("w") or W)), max(2, int(sondeo.get("h") or H))
    rc = c["recorte"]
    if rc["x"] > 0 or rc["y"] > 0 or rc["w"] < 1 or rc["h"] < 1:
        cw, ch = max(2, int(sw * rc["w"])), max(2, int(sh * rc["h"]))
        f.append("crop=%d:%d:%d:%d" % (cw, ch, int(sw * rc["x"]), int(sh * rc["y"])))
    else:
        cw, ch = sw, sh
    # Rellena con el último cuadro si el material no alcanza (o para quedarse bajo la transición).
    f.append("tpad=stop_mode=clone:stop_duration=%s" % _f(largo))
    f.append("trim=duration=%s" % _f(largo))
    aj = c["ajustes"]
    br, ct, sat = (aj["br"] - 100) / 100.0, aj["ct"] / 100.0, aj["sat"] / 100.0
    if abs(br) > 0.005 or abs(ct - 1) > 0.005 or abs(sat - 1) > 0.005:
        f.append("eq=brightness=%.3f:contrast=%.3f:saturation=%.3f" % (br, ct, sat))
    # Escala «cubrir» (o «contener»: logos, marcos) × escala del Ken Burns (de ini a fin en la duración visible).
    s0 = (max if c["encaje"] == "cubrir" else min)(W / float(cw), H / float(ch))
    bw, bh = cw * s0, ch * s0
    e0, e1 = c["kb"]["ini"]["escala"], c["kb"]["fin"]["escala"]
    if abs(e1 - e0) > 1e-4:
        k = "(%s+%s*min(t/%s,1))" % (_f(e0), _f(e1 - e0), _f(dur))
        f.append("scale=w='trunc(%s*%s/2)*2':h='trunc(%s*%s/2)*2':eval=frame" % (_f(bw), k, _f(bh), k))
    else:
        f.append("scale=%d:%d" % (_par(bw * e0), _par(bh * e0)))
    f.append("format=yuva420p")
    if c["opacidad"] < 0.999:
        f.append("lut=a='val*%.3f'" % c["opacidad"])
    if p["fi"] > 0.01:
        f.append("fade=t=in:st=0:d=%s:alpha=1" % _f(p["fi"]))
    if p["fo"] > 0.01:
        f.append("fade=t=out:st=%s:d=%s:alpha=1" % (_f(max(0, dur - p["fo"])), _f(p["fo"])))
    if p["entra"] == "barrido":
        d = p["dur_entra"]
        f.append("geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='if(lt(X,W*T/%s),alpha(X,Y),0)':enable='lt(t,%s)'"
                 % (_f(d), _f(d)))
    f.append("setpts=PTS+%s/TB" % _f(c["inicio"]))
    return ",".join(f)


def _posicion(c, p, W, H):
    """Expresiones x, y del overlay (tiempo de la línea de tiempo): centro + desplazamiento del Ken Burns
    (+ la entrada deslizada)."""
    ini, dur = c["inicio"], c["duracion"]
    a, b = c["kb"]["ini"], c["kb"]["fin"]
    k = "min(max((t-%s)/%s,0),1)" % (_f(ini), _f(dur))

    def eje(v0, v1, tam):
        if abs(v1 - v0) > 1e-4:
            return "(%s+%s*%s)*%d" % (_f(v0), _f(v1 - v0), k, tam)
        return "%s" % _f(v0 * tam)

    x = "(W-w)/2+%s" % eje(a["x"], b["x"], W)
    y = "(H-h)/2+%s" % eje(a["y"], b["y"], H)
    if p["entra"] == "deslizar":
        d = p["dur_entra"]
        x += "+W*(1-min(max((t-%s)/%s,0),1))" % (_f(ini), _f(d))
    return x, y


# ------------------------------------------------------------------ títulos (ASS)


def _ass_color(hexa, alfa=0):
    h = hexa.lstrip("#")
    return "&H%02X%s%s%s" % (alfa, h[4:6], h[2:4], h[0:2])


def _alfa(opacidad):
    return int(round((1 - opacidad) * 255))


TAM_DEFECTO = {"titular": 0.062, "rotulo": 0.036, "subtitulo": 0.05, "libre": 0.045}   # × alto


def tamano_texto(t, W, H):
    """Tamaño ASS (px de línea) del texto; la vista previa usa la misma regla."""
    return int(t["tam"] or round(TAM_DEFECTO[t["estilo"]] * (H if H >= W else H * 1.4)))


def escribir_ass(n, marca):
    """Texto ASS con todos los clips de texto (una capa por pista: la de más arriba encima)."""
    s = shorts()
    W, H = n["ancho"], n["alto"]
    col = {k: v for k, v in (marca.get("colores") or {}).items() if _HEX.match(str(v))}
    if any(k not in col for k in ROLES_COLOR) or not marca.get("fuente_titular") or not marca.get("fuente_texto"):
        # Lo que no trae la marca sale de los tokens (tokens/colors.json, typography.json), vía shorts.Marca.
        m = s.Marca()
        for k in ROLES_COLOR:
            col.setdefault(k, m.hex(s.PALETA[k]))
        marca = dict(marca, fuente_titular=marca.get("fuente_titular") or m.fuente_titular,
                     fuente_texto=marca.get("fuente_texto") or m.fuente_texto)
    ft, fx = marca["fuente_titular"], marca["fuente_texto"]
    lin = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: %d" % W, "PlayResY: %d" % H,
           "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
           "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
           "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           "Style: Titulo,%s,60,%s,%s,%s,%s,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1"
           % (ft, _ass_color(col["texto"]), _ass_color(col["texto"]), _ass_color(col["fondo"]), _ass_color(col["fondo"])),
           "Style: Texto,%s,48,%s,%s,%s,%s,-1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1"
           % (fx, _ass_color(col["texto"]), _ass_color(col["texto"]), _ass_color(col["fondo"]), _ass_color(col["fondo"])),
           "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    capas = {p["id"]: len(n["pistas"]) - i for i, p in enumerate(n["pistas"])}
    plan = planificar_transiciones(n["clips"])
    hay = False
    for c in n["clips"]:
        if c["tipo"] != "texto" or c["oculto"]:
            continue
        t = c["texto"]
        if not (t["contenido"].strip() or t["palabras"]):
            continue
        hay = True
        capa = capas.get(c["pista"], 1) * 4
        tam = tamano_texto(t, W, H)
        fi, fo = int(plan[c["id"]]["fi"] * 1000), int(plan[c["id"]]["fo"] * 1000)
        fad = "\\fad(%d,%d)" % (fi, fo) if (fi or fo) else ""
        al = "\\alpha&H%02X&" % _alfa(c["opacidad"]) if c["opacidad"] < 0.999 else ""
        x, y = int(t["x"] * W), int(t["y"] * H)
        i0, i1 = c["inicio"], c["inicio"] + c["duracion"]

        def ev(texto, a=i0, b=i1, k=0):
            lin.append("Dialogue: %d,%s,%s,%s,,0,0,0,,%s" % (capa + k, s._t(a), s._t(b),
                                                         "Titulo" if t["estilo"] in ("titular", "rotulo") else "Texto", texto))

        color = col[t["color"]] if t["color"] else None
        if t["estilo"] == "rotulo":
            # Rótulo «nombre / cargo»: dos franjas (marca y acento) alineadas a la izquierda, como shorts.py.
            an = {"izq": 1, "centro": 2, "der": 3}[t["alinear"] or "izq"]
            caja1 = "\\bord%d\\3c%s\\4c%s" % (max(6, tam // 4), _ass_color(col["marca"]), _ass_color(col["marca"]))
            ev("{\\an%d\\pos(%d,%d)\\fn%s\\fs%d\\c%s%s%s%s}%s" % (an, x, y, ft, tam, _ass_color(color or col["texto"]), caja1,
                                                              fad, al, s._esc(" " + t["contenido"] + " ")), k=1)
            if t["cargo"].strip():
                tc = max(12, int(tam * 0.72))
                caja2 = "\\bord%d\\3c%s\\4c%s" % (max(5, tc // 4), _ass_color(col["acento"]), _ass_color(col["acento"]))
                ev("{\\an%d\\pos(%d,%d)\\fn%s\\b1\\fs%d\\c%s%s%s%s}%s" % (
                    an, x, y + int(tam * 0.55) + int(tc * 1.0), fx, tc, _ass_color(col["fondo"]), caja2, fad, al,
                    s._esc(" " + t["cargo"] + " ")), k=2)
            continue
        an = {"izq": 4, "centro": 5, "der": 6}[t["alinear"] or "centro"]
        fuente = ft if t["estilo"] == "titular" else fx
        if t["caja"]:      # caja semitransparente del color de fondo (\4c marca el evento como «con caja»)
            borde = "\\3c%s\\4c%s\\bord%d" % (_ass_color(col["fondo"], 40), _ass_color(col["fondo"], 40), max(6, tam // 4))
        else:              # subtítulo: contorno fino; titular y libre: sin contorno
            borde = "\\3c%s\\bord%d\\shad0" % (_ass_color(col["fondo"]), max(2, tam // 18) if t["estilo"] == "subtitulo" else 0)
        base = "{\\an%d\\pos(%d,%d)\\fn%s\\fs%d\\c%s%s%s%s%s}" % (
            an, x, y, fuente, tam, _ass_color(color or col["texto"]), borde, "\\b1" if t["estilo"] != "libre" else "",
            fad, al)
        if t["palabras"] and t["resaltado"]:
            # Palabra a palabra (shorts.py): la frase en papel y la palabra que suena en acento.
            pals = [{"p": p["p"], "i": i0 + p["i"], "f": i0 + p["f"]} for p in t["palabras"]]
            sin_fad = base.replace(fad, "") if fad else base
            for grupo in s.grupos_de_palabras(pals):
                for a, b, texto in s.eventos_resaltados(grupo, _ass_color(col["acento"]), i1):
                    # {\r} volvería al estilo base (otro tamaño y fuente): se vuelve al color del texto.
                    ev(sin_fad + texto.replace("{\\r}", "{\\c%s}" % _ass_color(color or col["texto"])), a, b)
        elif t["palabras"] and not t["contenido"].strip():
            ev(base + s._esc(" ".join(p["p"] for p in t["palabras"])))
        else:
            ev(base + s._esc(t["contenido"]))
    if not hay:
        return None
    # libass necesita BorderStyle 3 para la caja opaca: se fija por estilo (las etiquetas no lo cambian).
    return _con_cajas("\n".join(lin) + "\n")


def _con_cajas(texto):
    """Las cajas de fondo (rótulo, títulos con caja) necesitan BorderStyle 3, que en ASS es del estilo:
    se añaden estilos «…Caja» y los eventos con \\4c (la marca de caja) pasan a usarlos."""
    lineas = texto.split("\n")
    out = []
    for l in lineas:
        if l.startswith("Style: Titulo,") or l.startswith("Style: Texto,"):
            out.append(l)
            partes = l.split(",")
            partes[0] = partes[0] + "Caja"
            partes[15] = "3"
            out.append(",".join(partes))
            continue
        if l.startswith("Dialogue:") and "\\4c" in l:
            l = l.replace(",Titulo,,", ",TituloCaja,,", 1).replace(",Texto,,", ",TextoCaja,,", 1)
        out.append(l)
    return "\n".join(out)


# ------------------------------------------------------------------ orden completa


def construir(proyecto, sondeos, resolver, salida, ajustes=None, marca=None, ass_ruta=None, fuentes_dir=None,
              normalizar_audio=True, calidad="alta", wasm=False):
    """Plan de render: {args (sin «ffmpeg»), ass (texto o None), duracion, entradas [(url, ruta)]}.

    sondeos  {origen: {w, h, dur, audio}} (ffprobe; imagen: w, h)
    resolver origen → ruta del archivo de entrada (en disco o en el FS de ffmpeg.wasm)
    ajustes  redes.json de shorts.py (codec, sonoridad); marca: colores por rol y fuentes."""
    n = normalizar(proyecto)
    W, H, fps, total = n["ancho"], n["alto"], n["fps"], n["duracion"]
    ajustes = ajustes or {"comun": {"video": {"codec": "libx264", "crf": 20, "preset": "medium", "pix_fmt": "yuv420p",
                                              "perfil": "high"},
                                    "audio": {"codec": "aac", "bitrate": "160k", "muestreo": 48000},
                                    "sonoridad": {"lufs": -14, "pico_verdadero_db": -1.5, "rango_lra": 11}}}
    comun = ajustes["comun"]
    plan = planificar_transiciones(n["clips"])
    # En el navegador, ffmpeg.wasm calcula el progreso leyendo las líneas «time=» del registro.
    args = ["-y", "-hide_banner"] + (["-loglevel", "info"] if wasm else ["-loglevel", "error", "-nostats"])
    entradas = []
    filtros = ["color=c=black:s=%dx%d:r=%d:d=%s,format=yuv420p[base]" % (W, H, fps, _f(total))]
    actual = "base"
    voces, musica = [], []

    def entrada(c, extra):
        ruta = resolver(c["origen"])
        if not ruta:
            raise ValueError("medio no disponible: %s" % (c["origen"] or c["id"]))
        entradas.append((c["origen"], ruta))
        args.extend(extra + ["-i", ruta])
        return len(entradas) - 1

    orden_visual = [p["id"] for p in reversed(n["pistas"]) if p["tipo"] == "video"]
    visuales = [c for pid in orden_visual for c in sorted((c for c in n["clips"] if c["pista"] == pid),
                                                         key=lambda c: c["inicio"])
                if c["tipo"] in ("video", "imagen") and not c["oculto"]]
    audibles = [c for c in n["clips"] if c["tipo"] in ("video", "audio") and not c["oculto"] and not c["silencio"]
                and c["volumen"] > 0.001]
    indice = {}
    for k, c in enumerate(visuales):
        p = plan[c["id"]]
        so = sondeos.get(c["origen"]) or {}
        largo = c["duracion"] + p["ext"]
        if c["tipo"] == "imagen":
            i = entrada(c, ["-loop", "1", "-framerate", str(fps), "-t", _f(largo + 0.1)])
        else:
            i = entrada(c, ["-ss", _f(c["entrada"]), "-t", _f(largo * c["velocidad"] + 0.1)])
        indice[c["id"]] = i
        filtros.append("[%d:v]%s[c%d]" % (i, _cadena_visual(c, p, so, W, H, fps), k))
        x, y = _posicion(c, p, W, H)
        filtros.append("[%s][c%d]overlay=x='%s':y='%s':eof_action=pass:enable='between(t,%s,%s)'[o%d]"
                       % (actual, k, x, y, _f(c["inicio"]), _f(c["inicio"] + largo), k))
        actual = "o%d" % k
    # Audio: cada clip audible se recorta, cambia de tempo, se funde y se coloca en su sitio.
    ak = 0
    for c in sorted(audibles, key=lambda c: c["inicio"]):
        so = sondeos.get(c["origen"]) or {}
        if c["tipo"] == "video" and not so.get("audio"):
            continue
        p = plan[c["id"]]
        largo = c["duracion"] + p["aext"]
        if c["id"] in indice:
            i = indice[c["id"]]
        else:
            i = entrada(c, ["-ss", _f(c["entrada"]), "-t", _f(largo * c["velocidad"] + 0.1)])
        a = ["asetpts=PTS-STARTPTS"]
        tempo = _atempo(c["velocidad"])
        if tempo:
            a.append(tempo)
        a += ["aresample=48000", "aformat=channel_layouts=stereo", "apad", "atrim=duration=%s" % _f(largo)]
        if abs(c["volumen"] - 1) > 0.001:
            a.append("volume=%.3f" % c["volumen"])
        if p["afi"] > 0.01:
            a.append("afade=t=in:st=0:d=%s" % _f(p["afi"]))
        if p["aext"] > 0.01:
            a.append("afade=t=out:st=%s:d=%s" % (_f(c["duracion"]), _f(p["aext"])))
        elif p["afo"] > 0.01:
            a.append("afade=t=out:st=%s:d=%s" % (_f(max(0, c["duracion"] - p["afo"])), _f(p["afo"])))
        ms = int(round(c["inicio"] * 1000))
        if ms > 0:
            a.append("adelay=%d:all=1" % ms)
        filtros.append("[%d:a]%s[a%d]" % (i, ",".join(a), ak))
        (musica if c["ducking"] else voces).append("[a%d]" % ak)
        ak += 1

    def mezclar(lista, nombre):
        if len(lista) == 1:
            filtros.append("%sanull[%s]" % (lista[0], nombre))
        else:
            filtros.append("%samix=inputs=%d:normalize=0:dropout_transition=0[%s]" % ("".join(lista), len(lista), nombre))

    son = comun["sonoridad"]
    final_a = None
    if voces and musica:
        mezclar(voces, "voz")
        mezclar(musica, "mus")
        # Ducking: la música baja cuando hay voz (compresor con la voz como cadena lateral).
        filtros.append("[voz]asplit=2[voz1][vozsc]")
        filtros.append("[mus][vozsc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[musd]")
        filtros.append("[voz1][musd]amix=inputs=2:normalize=0:dropout_transition=0[mez]")
        final_a = "mez"
    elif voces or musica:
        mezclar(voces or musica, "mez")
        final_a = "mez"
    if final_a:
        cola = ["apad", "atrim=duration=%s" % _f(total)]
        if normalizar_audio:
            cola.insert(0, "loudnorm=I=%s:TP=%s:LRA=%s" % (son["lufs"], son["pico_verdadero_db"], son["rango_lra"]))
        cola.append("aresample=%d" % comun["audio"]["muestreo"])
        filtros.append("[%s]%s[aout]" % (final_a, ",".join(cola)))
    else:
        filtros.append("anullsrc=r=%d:cl=stereo,atrim=duration=%s[aout]" % (comun["audio"]["muestreo"], _f(total)))
    ass = escribir_ass(n, marca or {})
    if ass:
        if not ass_ruta:
            raise ValueError("falta la ruta del archivo de títulos")
        esc = shorts()._esc_filtro
        opc = "filename='%s'" % esc(ass_ruta)
        if fuentes_dir:
            opc += ":fontsdir='%s'" % esc(fuentes_dir)
        filtros.append("[%s]ass=%s,format=yuv420p[vout]" % (actual, opc))
    else:
        filtros.append("[%s]format=yuv420p[vout]" % actual)
    v, a = comun["video"], comun["audio"]
    preset = v["preset"] if calidad == "alta" else "veryfast"
    if wasm:
        preset = "ultrafast"
    crf = v["crf"] if calidad == "alta" else v["crf"] + 3
    args += ["-filter_complex", ";".join(filtros), "-map", "[vout]", "-map", "[aout]",
             "-c:v", v["codec"], "-crf", str(crf), "-preset", preset, "-profile:v", v["perfil"],
             "-pix_fmt", v["pix_fmt"], "-r", str(fps),
             "-c:a", a["codec"], "-b:a", a["bitrate"], "-ar", str(a["muestreo"]),
             "-t", _f(total), "-movflags", "+faststart", salida]
    return {"args": args, "ass": ass, "duracion": total, "entradas": entradas, "normalizado": n}
