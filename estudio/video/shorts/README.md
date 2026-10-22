---
tipo: readme
estado: activo
---
# video/shorts/ — cortes verticales para redes (1080×1920) con la identidad del sistema

Convierte un **lote** de cortes (YAML o JSON, que vive fuera de este repo, junto al material
de quien lo usa) en vídeos verticales listos para Reels, TikTok, Shorts, Facebook o estados:
cabecera del programa, titular, rótulo de fuente, retrato con onda de audio (**audiograma**) o
vídeo reencuadrado (**reencuadre**), nombre de quien habla, **subtítulos palabra a palabra**,
barra de progreso y sonoridad normalizada a −14 LUFS.

Colores, tipografías y zonas seguras salen de los tokens de Unancha (`colors.json`,
`typography.json`, `layout.json`); los ajustes por red, de `redes.json`. **Aquí no hay HEX ni
nombres de un cliente**: los textos (programa, emisora, quién habla) y las rutas los pone el lote.

## Uso

```bash
shorts.py plan       <lote.yml>                         # lista los cortes y su estado
shorts.py portadas   <lote.yml> [--incluir-verificar]   # portada 1080×1920 por corte (SVG editable + PNG, Inkscape)
shorts.py kdenlive   <lote.yml> [--incluir-verificar]   # proyecto de Kdenlive prearmado por corte
shorts.py render     <lote.yml> --limpio                # sin subtítulos grabados (base del proyecto de Kdenlive)
shorts.py subtitular <lote.yml> [--id E2-2] [--modelo small]   # palabras con sus tiempos (Whisper)
shorts.py render     <lote.yml> [--id …] [--red reels] [--muestra 8] [--dry-run]
shorts.py render     <lote.yml> --incluir-verificar     # también los no publicables, con «-por-verificar» en el nombre
```

- `subtitular` extrae el audio de cada corte y guarda `<episodio>-<id>.palabras.json` en la
  salida; se ejecuta una vez y se reutiliza. Las `correcciones` del lote arreglan nombres propios.
- `render` solo compone los cortes con `estado: publicable`; el resto se omite, o sale con
  `-por-verificar` en el nombre del archivo si se pide `--incluir-verificar` (la imagen no lleva marca:
  los cortes se revisan en grupo antes de publicar).
- `--muestra N` compone solo los primeros N segundos, para revisar el diseño rápido.
- `portadas` deja el titular y el rostro en la franja central 4:5 (lo que muestra la cuadrícula de
  Instagram); en un reencuadre usa un fotograma del centro del corte con el mismo recuadre.
- `kdenlive` escribe `<episodio>-<id>.kdenlive` en el formato de documento **1.1** (el de las pruebas
  del repositorio de Kdenlive, tests/dataset/clip-ids.kdenlive en KDE/kdenlive): V2 «Títulos de la
  identidad» (vacía), V1 «Corte» (el corte limpio), A1 «Voz» (su audio), A2 «Música» (vacía); en la
  bandeja, el corte, la portada y el directo completo. Los subtítulos van en
  `<episodio>-<id>-subtitulos.ass`, al lado: en Kdenlive, *Subtítulos → Importar*.

## El lote

```yaml
tipo: lote_cortes
episodio: ep02-2026-09-19
audio: audio/directo.m4a          # rutas relativas al lote
video: audio/directo.mp4          # solo para «reencuadre»
imagen: /ruta/al/retrato.png      # para «audiograma» (mejor con fondo transparente)
salida: audio/cortes
marca: {programa: "…", emisora: "…", voz: {nombre: "…", cargo: "…"}}
correcciones: {apeyido: Apellido}      # lo que Whisper escribe mal
recuadre: {x: 240, y: 0, w: 800, h: 450}   # recorte del vídeo de origen (reencuadre)
cortes:
  - {id: E2-2, entra: "11:18", sale: "12:29", formato: audiograma, estado: publicable,
     titulo: "…", rotulo: "…"}
```

## Estructura

```
shorts.py     CLI (librería estándar; ffmpeg con libass; `whisper` para subtitular; PyYAML opcional)
redes.json    duración máxima por red, códec, fps y sonoridad
```

## Consumidores

Este README es el contrato del **lote** (§El lote) y de `redes.json`; quien los usa enlaza aquí y no los copia.

| consumidor | qué usa |
|---|---|
| programa de radio (`radio`, cadena `prompts/08 radio`) | `shorts.py` con el lote de cada emisión; los adaptadores de Kdenlive e Inkscape para retocar un corte |
| `divulgacion` | `redes.json` (duración, códec, fps y sonoridad por red), por lectura |

Un cambio de clave del lote o de `redes.json` se avisa a ambos.

## Límite honesto

- Sale a 1080×1920, 30 fps, H.264 + AAC, a −14 LUFS (medido con `ebur128`). El bloque de video sigue la proporción
  del `recuadre`. `subtitular` es lento en CPU: varios minutos por minuto de corte con Whisper `small`.
- Un directo puede cambiar de composición a mitad (pantalla dividida, cámara completa): el `recuadre` se fija **por
  corte**, midiendo un fotograma del tramo.
- Whisper se equivoca en nombres y en palabras sueltas que cambian el sentido: se revisa el texto
  (`*.palabras.json`) antes de publicar y se corrige con `correcciones` en el lote.
- La pieza es **fija**: sin animaciones de entrada ni transiciones; para eso está el proyecto de Kdenlive que
  escribe `kdenlive` (formato 1.1; abre con sus cuatro pistas y la bandeja, y `melt` lo exporta igual que el corte).
- Los subtítulos **no** se incrustan en el proyecto de Kdenlive (su formato interno no está documentado): se
  importan del `.ass` en un paso.
- Los productores de la línea de tiempo del proyecto llevan `length`: sin ella, MLT los trata como de longitud cero
  y el video sale negro.
- El reencuadre es un recorte **fijo** (sirve para una cámara quieta); no sigue caras.
- No hay diarización: los subtítulos no distinguen quién habla.
- Las zonas seguras son las de `layout.json` más la botonera de TikTok (140 px); cambian con cada versión de las apps.
