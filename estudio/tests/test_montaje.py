"""estudio/tests/test_montaje.py — (vino de Unancha con el estudio, fase 10.2b E0) del proyecto del editor de video (video.html) a la orden de ffmpeg (editor/servidor/montaje.py).

Las pruebas del constructor son puras (no hace falta ffmpeg); la última compone de verdad un video corto si
ffmpeg está instalado: dos clips de un testsrc con fundido cruzado y un título, y comprueba la duración."""
import importlib.util
import json
import shutil
import subprocess

import pytest

from conftest import RAIZ

RUTA = RAIZ / "editor" / "servidor" / "montaje.py"


@pytest.fixture(scope="module")
def m():
    spec = importlib.util.spec_from_file_location("montaje_editor", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def proyecto(**extra):
    p = {"ancho": 1080, "alto": 1920, "fps": 30,
         "pistas": [{"id": "t1", "tipo": "texto"}, {"id": "v1", "tipo": "video"}, {"id": "a1", "tipo": "audio"}],
         "clips": [
             {"id": "a", "pista": "v1", "tipo": "video", "origen": "/banco/x.mp4", "inicio": 0, "duracion": 2, "entrada": 1},
             {"id": "b", "pista": "v1", "tipo": "video", "origen": "/banco/x.mp4", "inicio": 2, "duracion": 2, "entrada": 5,
              "transicion": {"tipo": "fundido", "dur": 0.5}},
         ]}
    p.update(extra)
    return p


SONDEO = {"/banco/x.mp4": {"w": 1920, "h": 1080, "dur": 30, "audio": True},
          "/banco/m.mp3": {"dur": 60, "audio": True}, "/banco/f.png": {"w": 800, "h": 800}}


def plan(m, p, **kw):
    return m.construir(p, SONDEO, lambda u: "/medios" + u, "/salida/x.mp4", ass_ruta="/tmp/t.ass", **kw)


def grafo(r):
    return r["args"][r["args"].index("-filter_complex") + 1]


def test_normaliza_y_acota(m):
    n = m.normalizar({"ancho": 1081, "alto": 99999, "fps": 500, "pistas": [{"id": "v", "tipo": "video"}, {"id": "x", "tipo": "raro"}],
                      "clips": [{"id": "1", "pista": "v", "tipo": "video", "inicio": -5, "duracion": 3, "velocidad": 9, "volumen": -1},
                                {"id": "2", "pista": "x", "tipo": "video", "duracion": 3},
                                {"id": "3", "pista": "v", "tipo": "malo", "duracion": 3}]})
    assert (n["ancho"], n["alto"], n["fps"]) == (1080, 3840, 60)
    assert [c["id"] for c in n["clips"]] == ["1"]
    c = n["clips"][0]
    assert c["inicio"] == 0 and c["velocidad"] == 4 and c["volumen"] == 0
    with pytest.raises(ValueError):
        m.normalizar({"pistas": [], "clips": []})


def test_fundido_prolonga_el_clip_anterior(m):
    n = m.normalizar(proyecto())
    pl = m.planificar_transiciones(n["clips"])
    assert pl["a"]["ext"] == pytest.approx(0.5) and pl["a"]["aext"] == pytest.approx(0.5)
    assert pl["b"]["fi"] == pytest.approx(0.5) and pl["b"]["afi"] == pytest.approx(0.5)


def test_negro_funde_los_dos_lados(m):
    p = proyecto()
    p["clips"][1]["transicion"] = {"tipo": "negro", "dur": 1}
    pl = m.planificar_transiciones(m.normalizar(p)["clips"])
    assert pl["a"]["ext"] == 0 and pl["a"]["fo"] == pytest.approx(0.5) and pl["b"]["fi"] == pytest.approx(0.5)


def test_orden_basica(m):
    r = plan(m, proyecto())
    a, g = r["args"], grafo(r)
    assert r["duracion"] == pytest.approx(4)
    # Entradas con búsqueda exacta (-ss antes de -i) y el tramo con la prolongación de la transición.
    assert a[a.index("-i") - 4:a.index("-i") + 2] == ["-ss", "1.0000", "-t", "2.6000", "-i", "/medios/banco/x.mp4"]
    assert "fade=t=in:st=0:d=0.5000:alpha=1" in g
    assert "tpad=stop_mode=clone:stop_duration=2.5000" in g
    assert "overlay=" in g and "eof_action=pass" in g
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in g            # −14 LUFS como shorts.py
    assert a[-1] == "/salida/x.mp4" and "+faststart" in a
    assert a[a.index("-c:v") + 1] == "libx264" and a[a.index("-c:a") + 1] == "aac"


def test_velocidad_y_atempo(m):
    p = proyecto()
    p["clips"][0]["velocidad"] = 0.25
    p["clips"][1]["velocidad"] = 4
    g = grafo(plan(m, p))
    assert "setpts=(PTS-STARTPTS)/0.25000" in g and "atempo=0.50000,atempo=0.50000" in g
    assert "atempo=2.00000,atempo=2.00000" in g
    assert m._atempo(1) == "" and m._atempo(1.5) == "atempo=1.50000"


def test_ken_burns_y_recorte(m):
    p = proyecto()
    p["clips"][0].update(kb={"ini": {"escala": 1, "x": 0, "y": 0}, "fin": {"escala": 1.3, "x": 0.1, "y": -0.1}},
                         recorte={"x": 0.25, "y": 0, "w": 0.5, "h": 1})
    g = grafo(plan(m, p))
    assert "crop=960:1080:480:0" in g
    assert "eval=frame" in g and "min(t/2.0000,1)" in g
    assert "(0.0000+0.1000*min(max((t-0.0000)/2.0000,0),1))*1080" in g


def test_encaje_contener(m):
    p = proyecto()
    p["clips"][0]["encaje"] = "contener"
    assert "scale=1080:608" in grafo(plan(m, p))       # 1920×1080 dentro de 1080×1920
    assert "scale=3414:1920" in grafo(plan(m, proyecto()))


def test_deslizar_barrido_y_opacidad(m):
    p = proyecto()
    p["clips"][1]["transicion"] = {"tipo": "deslizar", "dur": 0.4}
    p["clips"][0]["opacidad"] = 0.5
    g = grafo(plan(m, p))
    assert "+W*(1-min(max((t-2.0000)/0.4000,0),1))" in g and "lut=a='val*0.500'" in g
    p["clips"][1]["transicion"] = {"tipo": "barrido", "dur": 0.4}
    assert "geq=" in grafo(plan(m, p))


def test_musica_con_ducking_y_silencio(m):
    p = proyecto()
    p["clips"].append({"id": "m", "pista": "a1", "tipo": "audio", "origen": "/banco/m.mp3", "inicio": 0, "duracion": 4,
                       "ducking": True, "volumen": 0.6})
    g = grafo(plan(m, p))
    assert "sidechaincompress" in g and "volume=0.600" in g
    p["pistas"][1]["silencio"] = True
    g = grafo(plan(m, p, normalizar_audio=False))
    assert "[0:a]" not in g and "sidechaincompress" not in g and "loudnorm" not in g


def test_pista_solo_silencia_las_demas(m):
    p = proyecto()
    p["clips"].append({"id": "m", "pista": "a1", "tipo": "audio", "origen": "/banco/m.mp3", "inicio": 0, "duracion": 4})
    p["pistas"][2]["solo"] = True
    n = m.normalizar(p)
    assert [c["silencio"] for c in n["clips"] if c["tipo"] == "video"] == [True, True]
    assert [c["silencio"] for c in n["clips"] if c["tipo"] == "audio"] == [False]
    assert "[0:a]" not in grafo(plan(m, p, normalizar_audio=False))


def test_sin_audio_genera_silencio(m):
    p = proyecto()
    p["clips"] = [{"id": "f", "pista": "v1", "tipo": "imagen", "origen": "/banco/f.png", "inicio": 0, "duracion": 3}]
    r = plan(m, p)
    assert "anullsrc" in grafo(r)
    assert r["args"][r["args"].index("-i") - 6:r["args"].index("-i")] == ["-loop", "1", "-framerate", "30", "-t", "3.1000"]


def test_titulos_ass(m):
    p = proyecto()
    p["clips"] += [
        {"id": "t", "pista": "t1", "tipo": "texto", "inicio": 0.5, "duracion": 1, "fundido_entrada": 0.2,
         "texto": {"estilo": "titular", "contenido": "Hola {mundo}", "x": 0.5, "y": 0.2, "caja": True}},
        {"id": "r", "pista": "t1", "tipo": "texto", "inicio": 1, "duracion": 1,
         "texto": {"estilo": "rotulo", "contenido": "Nombre Apellido", "cargo": "Cargo", "x": 0.1, "y": 0.8}},
        {"id": "s", "pista": "t1", "tipo": "texto", "inicio": 2, "duracion": 1,
         "texto": {"estilo": "subtitulo", "resaltado": "palabra",
                   "palabras": [{"p": "uno", "i": 0, "f": 0.4}, {"p": "dos", "i": 0.5, "f": 0.9}]}},
    ]
    r = plan(m, p, marca={"colores": {"acento": "#112233"}, "fuente_titular": "Archivo Black"})
    ass = r["ass"]
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Hola (mundo)" in ass                               # llaves escapadas (shorts._esc)
    assert "\\fad(200,0)" in ass and "TituloCaja" in ass
    assert "Nombre Apellido" in ass and "Cargo" in ass
    assert "{\\c&H00332211}uno{\\c&H00ECF1F5} dos" in ass    # palabra a palabra (color ASS en BGR)
    assert "ass=filename='/tmp/t.ass'" in grafo(r)
    # Sin títulos no hay filtro ass.
    assert "ass=" not in grafo(plan(m, proyecto()))


def test_pista_oculta_no_se_compone(m):
    p = proyecto()
    p["pistas"][1]["oculta"] = True
    p["clips"].append({"id": "m", "pista": "a1", "tipo": "audio", "origen": "/banco/m.mp3", "inicio": 0, "duracion": 1})
    g = grafo(plan(m, p))
    assert "overlay" not in g


def test_medio_desconocido_falla(m):
    with pytest.raises(ValueError):
        m.construir(proyecto(), SONDEO, lambda u: None, "/x.mp4")


def test_wasm_usa_preset_rapido(m):
    a = plan(m, proyecto(), wasm=True)["args"]
    assert a[a.index("-preset") + 1] == "ultrafast"


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="sin ffmpeg")
def test_render_real(m, tmp_path):
    """Dos clips de 1 s de un testsrc de 2 s (con tono), fundido cruzado de 0,4 s y un título: dura 2 s."""
    fuente = tmp_path / "fuente.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(fuente)], check=True)
    p = {"ancho": 360, "alto": 640, "fps": 25,
         "pistas": [{"id": "t1", "tipo": "texto"}, {"id": "v1", "tipo": "video"}],
         "clips": [
             {"id": "a", "pista": "v1", "tipo": "video", "origen": "/banco/fuente.mp4", "inicio": 0, "duracion": 1, "entrada": 0},
             {"id": "b", "pista": "v1", "tipo": "video", "origen": "/banco/fuente.mp4", "inicio": 1, "duracion": 1, "entrada": 0.5,
              "transicion": {"tipo": "fundido", "dur": 0.4}},
             {"id": "t", "pista": "t1", "tipo": "texto", "inicio": 0, "duracion": 2,
              "texto": {"estilo": "titular", "contenido": "Título", "x": 0.5, "y": 0.2}},
         ]}
    salida, ass = tmp_path / "salida.mp4", tmp_path / "titulos.ass"
    r = m.construir(p, {"/banco/fuente.mp4": {"w": 320, "h": 240, "dur": 2, "audio": True}},
                    lambda u: str(tmp_path / u.rsplit("/", 1)[-1]), str(salida), ass_ruta=str(ass))
    ass.write_text(r["ass"], encoding="utf-8")
    hecho = subprocess.run(["ffmpeg"] + r["args"], capture_output=True, text=True, timeout=120)
    assert hecho.returncode == 0, hecho.stderr[-800:]
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height",
                                      "-of", "json", str(salida)], capture_output=True, text=True).stdout)
    assert float(info["format"]["duration"]) == pytest.approx(2.0, abs=0.1)
    codecs = {s["codec_name"] for s in info["streams"]}
    assert codecs == {"h264", "aac"}
    assert any(s.get("width") == 360 and s.get("height") == 640 for s in info["streams"])
