/* GENERADO por scripts/sitios_modulos.py de Qillqa; no editar. */
/* El sitio de demostración de un proyecto de la plataforma Qillqa: sus pantallas, cómo se conecta (solo o dentro de
   Qillqa), la familia y, en algunos, una pieza que se prueba en el navegador. Uno solo para todos: lo propio de cada
   sitio viene en <script id="datos">. Sin dependencias. */
'use strict'
document.documentElement.classList.add('js')

const $ = (s, r = document) => r.querySelector(s)
const $$ = (s, r = document) => [...r.querySelectorAll(s)]
const calma = matchMedia('(prefers-reduced-motion: reduce)').matches
const guardar = (k, v) => { try { localStorage.setItem(k, v) } catch {} }
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const DATOS = JSON.parse($('#datos').textContent)

/* ---------------------------------------------------------------- íconos (trazo, 24 × 24) */
const ICONOS = {
  inicio: 'M3 11.5 12 4l9 7.5M5.5 9.5V20h4.5v-5.5h4V20h4.5V9.5',
  documentos: 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h4',
  editor: 'M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17zM14.5 7.5l2 2',
  seguimiento: 'M3 12h4l2.5-6 5 12 2.5-6h4',
  recibidos: 'M3 13.5 6 5h12l3 8.5V19H3zM3 13.5h5l1.5 2.5h5l1.5-2.5h5',
  tareas: 'M5 4h4v16H5zM10 4h4v10h-4zM15 4h4v13h-4z',
  matriz: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  agenda: 'M4 6h16v14H4zM4 10.5h16M8.5 3.5v5M15.5 3.5v5',
  chat: 'M4 5h16v11H10l-5 4v-4H4z',
  proyectos: 'M12 3.5 21 8.5l-9 5-9-5zM3 13l9 5 9-5',
  directorio: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3.5 20a5.5 5.5 0 0 1 11 0M16 5.2a3 3 0 0 1 0 5.6M20.5 20a5.5 5.5 0 0 0-3.5-5.1',
  estadisticas: 'M5 20v-7M11 20V5M17 20v-9M3 20h18',
  mapa: 'M6 8.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM18 8.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM12 20.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM8.5 6h7M7.2 8.2l3.6 7.6M16.8 8.2l-3.6 7.6',
  mesa: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.6 3.7 5.6 3.7 9s-1.2 6.4-3.7 9c-2.5-2.6-3.7-5.6-3.7-9s1.2-6.4 3.7-9z',
  firma: 'M3 18c3-6 5-8 6-6s-2 6 1 4 4-7 6-6-1 5 2 4 3-2 3-2M3 21h18',
  pdf: 'M7 3h7l5 5v13H7zM14 3v5h5M9.5 17v-4h1.5a1.3 1.3 0 0 1 0 2.6H9.5',
  nube: 'M7 18a4 4 0 0 1-.5-8 5.5 5.5 0 0 1 10.6 1.5A3.3 3.3 0 0 1 17 18zM12 11v5M10 14l2 2 2-2',
  ajustes: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 0 0-2.1-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2.1 1.2l-2.3-.9-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-.9a7 7 0 0 0 2.1 1.2L10 21h4l.5-2.6a7 7 0 0 0 2.1-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z',
  foto: 'M4 7h3l2-2.5h6L17 7h3v12H4zM12 16.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z',
  dinero: 'M4 7h16v10H4zM12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM7 7v10M17 7v10',
  informe: 'M6 3h12v18H6zM9 8h6M9 12h6M9 16h3',
  enchufe: 'M9 3v5M15 3v5M6 8h12v4a6 6 0 0 1-12 0zM12 18v3',
  puerta: 'M6 21V3h12v18M3 21h18M14.5 12.5v.01',
  video: 'M4 6h12v12H4zM16 10.5l5-3v9l-5-3',
  antena: 'M12 12v9M8.5 8.5a5 5 0 0 1 7 0M5.5 5.5a9 9 0 0 1 13 0M12 12.5v-.5',
  capas: 'M12 3 21 8l-9 5-9-5zM3 12.5l9 5 9-5M3 17l9 5 9-5',
  ojo: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  codigo: 'M8.5 7 3.5 12l5 5M15.5 7l5 5-5 5M13.5 4.5l-3 15',
  pincel: 'M14.5 4.5l5 5L10 19H5v-5zM12.5 6.5l5 5',
  voz: 'M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zM5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3',
  reloj: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  etiqueta: 'M3 12V4h8l10 10-8 8zM7.5 8.5v.01',
  pin: 'M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12zM12 11.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',
  texto: 'M5 6V4h14v2M12 4v16M9 20h6',
  musica: 'M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
  tabla: 'M4 4h16v16H4zM4 10h16M4 15h16M10 4v16',
  rayo: 'M13 3 5 13h6l-1 8 8-10h-6z',
  avion: 'M21 3 3 10.5l7 2.5 2.5 7zM10 13 21 3',
  marco: 'M3 3h18v18H3zM7 7h10v10H7z',
  bus: 'M5 4h14v13H5zM5 11h14M8 17v3M16 17v3M8 14h.01M16 14h.01',
}
const svg = (k) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONOS[k] || ICONOS.documentos}"/></svg>`
function pintarIconos() { $$('[data-icono]').forEach((el) => { el.innerHTML = svg(el.dataset.icono) }) }

/* ---------------------------------------------------------------- pantallas */
function iniciarPantallas() {
  const P = DATOS.pantallas
  const dock = $('#dock'), img = $('#modulo-imagen'), titulo = $('#modulo-titulo')
  const caja = $('.explicacion'), nombre = $('#modulo-nombre'), grupo = $('#modulo-grupo')
  const texto = $('#modulo-texto'), puntos = $('#modulo-puntos')
  let actual = 0
  dock.innerHTML = P.map((m, i) => `<button type="button" role="tab" aria-selected="${i === 0}">
    ${svg(m.icono)}<span>${esc(m.nombre)}</span></button>`).join('')
  const botones = $$('button', dock)
  if (P.length < 2) $('.ventana-pasos').hidden = true

  function mostrar(i, enfocar = false) {
    actual = (i + P.length) % P.length
    const m = P[actual]
    botones.forEach((b, j) => { b.setAttribute('aria-selected', j === actual); b.tabIndex = j === actual ? 0 : -1 })
    if (enfocar) botones[actual].focus()
    img.classList.add('cambiando')
    const nueva = new Image()
    nueva.onload = nueva.onerror = () => {
      img.src = nueva.src; img.alt = `${m.nombre}: ${m.titulo}`
      requestAnimationFrame(() => img.classList.remove('cambiando'))
    }
    nueva.src = `img/${m.img}.webp`
    titulo.textContent = `${DATOS.nombre} · ${m.nombre}`
    grupo.textContent = m.nombre; nombre.textContent = m.titulo; texto.textContent = m.texto
    puntos.innerHTML = m.puntos.map((p) => `<li>${esc(p)}</li>`).join('')
    caja.classList.remove('entra'); void caja.offsetWidth; caja.classList.add('entra')
    if (P.length > 1) new Image().src = `img/${P[(actual + 1) % P.length].img}.webp`
  }
  botones.forEach((b, i) => b.addEventListener('click', () => { parar(); mostrar(i) }))
  dock.addEventListener('keydown', (e) => {
    const paso = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 1, ArrowUp: -1 }[e.key]
    if (paso) { e.preventDefault(); parar(); mostrar(actual + paso, true) }
  })
  $('#modulo-ant').addEventListener('click', () => { parar(); mostrar(actual - 1) })
  $('#modulo-sig').addEventListener('click', () => { parar(); mostrar(actual + 1) })

  // Avance solo mientras la ventana se ve y nadie la ha tocado.
  let reloj = null
  function parar() { clearInterval(reloj); reloj = null }
  if (!calma && P.length > 1) {
    new IntersectionObserver(([e]) => {
      if (e.isIntersecting && reloj === null && !dock.dataset.tocado) reloj = setInterval(() => mostrar(actual + 1), 6000)
      else if (!e.isIntersecting) parar()
    }, { threshold: .4 }).observe($('#ventana-modulo'))
    const tocar = () => { dock.dataset.tocado = '1'; parar() }
    dock.addEventListener('pointerdown', tocar); dock.addEventListener('focusin', tocar)
  }
  mostrar(0)
}

/* ---------------------------------------------------------------- cómo se conecta */
// Lo que da cada anfitrión: el mínimo de Tiqsi solo la identidad; Qillqa, su núcleo y lo que ofrecen sus módulos.
function ofrecidoPor(anfitrion, montados) {
  const PL = DATOS.plataforma, da = new Map()
  if (anfitrion === 'minimo') PL.minimo.forEach((c) => da.set(c, 'Tiqsi mínimo'))
  if (anfitrion === 'qillqa') PL.nucleo.forEach((c) => da.set(c, 'Qillqa'))
  montados.forEach((m) => m.ofrece.forEach((c) => { if (!da.has(c)) da.set(c, PL.proveedor[c] || m.nombre) }))
  return da
}
const cap = (c, clase, quien) =>
  `<li class="cap ${clase}"><b>${esc(c)}</b><small>${esc(DATOS.plataforma.capacidades[c] || '')}</small>${quien ? `<i>${esc(quien)}</i>` : ''}</li>`

function iniciarConexion() {
  const grupos = $('#conexion-grupos'); if (!grupos) return
  const PL = DATOS.plataforma, propios = DATOS.conexion.manifiestos
  const texto = $('#conexion-texto'), botones = $$('#anfitrion button')

  function pintar(anfitrion) {
    botones.forEach((b) => b.setAttribute('aria-checked', b.dataset.anfitrion === anfitrion))
    const montados = anfitrion === 'qillqa' ? PL.manifiestos : propios
    const da = ofrecidoPor(anfitrion, montados)
    let usados = 0, posibles = 0
    grupos.innerHTML = propios.map((m) => {
      const nec = m.necesita.map((c) => cap(c, da.has(c) ? 'si' : 'no', da.has(c) ? `lo da ${da.get(c)}` : 'falta'))
      const apr = m.aprovecha.map((c) => {
        posibles++
        const quien = da.get(c)
        if (quien) { usados++; return cap(c, 'si', `lo da ${quien}`) }
        return cap(c, 'apagada', 'no está: esa parte no se ofrece')
      })
      const ofr = m.ofrece.map((c) => {
        const quienes = anfitrion === 'qillqa'
          ? [...new Set(PL.manifiestos.filter((x) => x !== m && (x.aprovecha.includes(c) || x.necesita.includes(c))).map((x) => x.nombre))]
          : []
        return cap(c, 'ofrece', quienes.length ? `lo usan: ${quienes.join(', ')}` : (anfitrion === 'qillqa' ? 'queda a disposición' : 'listo para quien lo pida'))
      })
      const fila = (t, lista, vacio) => `<div class="cap-fila"><h4>${t}</h4>${lista.length ? `<ul>${lista.join('')}</ul>` : `<p class="cap-vacio">${vacio}</p>`}</div>`
      return `<article class="conexion-modulo vidrio"><h3>${esc(m.nombre)}</h3>
        ${fila('Necesita', nec, 'Nada: no pide ni la identidad al anfitrión.')}
        ${fila('Aprovecha', apr, 'Nada: funciona igual en cualquier anfitrión.')}
        ${fila('Ofrece', ofr, 'Nada a los demás: es una herramienta que se usa por sí misma.')}</article>`
    }).join('')
    texto.innerHTML = anfitrion === 'minimo'
      ? `Con el <b>anfitrión mínimo de Tiqsi</b>: cuentas locales, inicio de sesión y la identidad. ${posibles ? `Se enciende <b>${usados} de ${posibles}</b> de lo que aprovecha; lo demás no se ofrece y nada se rompe.` : 'No le hace falta nada más.'}`
      : `<b>Dentro de Qillqa</b>: el núcleo y los otros módulos dan lo que aprovecha. ${posibles ? `Se enciende <b>${usados} de ${posibles}</b>.` : 'Aparece en el menú de la plataforma, con su cuenta y su tema.'}`
  }
  botones.forEach((b) => b.addEventListener('click', () => pintar(b.dataset.anfitrion)))
  pintar('minimo')
}

/* ---------------------------------------------------------------- la familia */
function iniciarFamilia() {
  const lista = $('#familia-lista'); if (!lista) return
  lista.innerHTML = DATOS.familia.map((f) => {
    const aqui = f.id === DATOS.id
    return `<a class="pariente vidrio${aqui ? ' aqui' : ''}" href="${aqui ? '#inicio' : `${DATOS.pages}/${f.id}/`}"${aqui ? ' aria-current="page"' : ''}>
      <span class="icono">${svg(f.icono)}</span><b>${esc(f.nombre)}</b><small>${esc(f.que)}${aqui ? ' · aquí' : ''}</small></a>`
  }).join('')
}

/* ---------------------------------------------------------------- piezas que se prueban */
// Tiqsi: arma un anfitrión, elige módulos y arráncalo.
function piezaTiqsi(caja) {
  const PL = DATOS.plataforma
  const repos = [...new Set(PL.manifiestos.map((m) => m.repo))]
  const nombreRepo = Object.fromEntries(DATOS.familia.map((f) => [f.id, f.nombre]))
  caja.classList.add('anfitrion')
  caja.innerHTML = `<div class="anfitrion-panel vidrio">
      <h3>Anfitrión</h3>
      <div class="segmentos" role="radiogroup" aria-label="Anfitrión" id="pz-anf">
        <button type="button" role="radio" aria-checked="true" data-a="minimo">Tiqsi mínimo</button>
        <button type="button" role="radio" aria-checked="false" data-a="qillqa">Qillqa</button>
        <button type="button" role="radio" aria-checked="false" data-a="vacio">Sin cuentas</button>
      </div>
      <h3>Módulos</h3>
      <div class="anfitrion-modulos">${repos.map((r) => `<label><input type="checkbox" value="${r}"${['rikchay', 'minka', 'punku'].includes(r) ? ' checked' : ''}> ${esc(nombreRepo[r] || r)}</label>`).join('')}</div>
      <button class="boton primario" type="button" id="pz-arrancar">Arrancar</button>
    </div>
    <div class="anfitrion-salida vidrio"><ol id="pz-log" aria-live="polite"></ol><p class="anfitrion-resumen" id="pz-resumen" role="status"></p></div>`
  let anf = 'minimo'
  $$('#pz-anf button', caja).forEach((b) => b.addEventListener('click', () => {
    anf = b.dataset.a; $$('#pz-anf button', caja).forEach((x) => x.setAttribute('aria-checked', x === b)); arrancar()
  }))
  $$('input', caja).forEach((i) => i.addEventListener('change', arrancar))
  $('#pz-arrancar', caja).addEventListener('click', arrancar)
  let turno = 0
  function arrancar() {
    const mio = ++turno
    const elegidos = $$('input:checked', caja).map((i) => i.value)
    const montados = PL.manifiestos.filter((m) => elegidos.includes(m.repo))
    const da = ofrecidoPor(anf === 'vacio' ? 'ninguno' : anf, montados)
    const lineas = [], faltas = []
    lineas.push(['', `Anfitrión: ${anf === 'minimo' ? 'Tiqsi mínimo (cuentas locales e identidad)' : anf === 'qillqa' ? 'Qillqa (su núcleo: identidad, directorio, calendario, avisos…)' : 'uno sin cuentas: no da la identidad'}`])
    if (!montados.length) lineas.push(['aviso', 'No elegiste módulos: el anfitrión arranca vacío.'])
    montados.forEach((m) => {
      const falta = m.necesita.filter((c) => !da.has(c))
      if (falta.length) { faltas.push([m, falta]); lineas.push(['error', `«${m.id}» necesita ${falta.join(', ')} y nadie lo ofrece`]); return }
      const si = m.aprovecha.filter((c) => da.has(c))
      lineas.push(['ok', `Valida «${m.id}» (${m.nombre}): ${m.necesita.length ? 'lo que necesita está' : 'no necesita nada'}`])
      if (m.aprovecha.length) lineas.push([si.length ? 'ok' : 'aviso', `Conecta lo que aprovecha: ${si.length} de ${m.aprovecha.length}${si.length ? ` (${si.join(', ')})` : ''}`])
      if (m.ofrece.length) lineas.push(['', `Registra lo que ofrece: ${m.ofrece.join(', ')}`])
    })
    if (faltas.length) lineas.push(['error', 'No arranca ninguno: Tiqsi nunca arranca a medias.'])
    else if (montados.length) lineas.push(['ok', `Monta las rutas en orden y arranca ${montados.length} ${montados.length === 1 ? 'módulo' : 'módulos'}.`])
    const log = $('#pz-log', caja), resumen = $('#pz-resumen', caja)
    log.innerHTML = ''; resumen.textContent = ''
    lineas.forEach(([clase, t], i) => setTimeout(() => {
      if (mio !== turno) return
      const li = document.createElement('li'); li.className = clase; li.textContent = t; log.append(li)
      if (i === lineas.length - 1) resumen.textContent = faltas.length ? 'Elige «Tiqsi mínimo» o «Qillqa»: los dos dan la identidad.' : (montados.length ? 'Cambia el anfitrión y mira cuánto de lo que aprovechan se enciende.' : '')
    }, calma ? 0 : i * 140))
  }
  arrancar()
}

// Wayra: un rótulo con sus textos y la URL para OBS.
function piezaWayra(caja) {
  const PIEZAS = [
    { ruta: 'rotulos/entrevistado.html', nombre: 'Rótulo de entrevistado', clase: 'rotulo',
      campos: [['kicker', 'Antetítulo', 'PARTICIPA'], ['nombre', 'Nombre', 'María Quispe'], ['rol', 'Cargo', 'Presidenta · Junta vecinal de ejemplo']] },
    { ruta: 'rotulos/tema.html', nombre: 'Rótulo de tema', clase: 'rotulo tema',
      campos: [['kicker', 'Antetítulo', 'TEMA'], ['tema', 'Tema', 'PRESUPUESTO PARTICIPATIVO'], ['bajada', 'Bajada', 'Lo que se votó en la asamblea']] },
    { ruta: 'tarjetas/dato.html', nombre: 'Tarjeta de dato', clase: 'dato',
      campos: [['kicker', 'Antetítulo', 'EL DATO'], ['cifra', 'Cifra', '63%'], ['label', 'Qué mide', 'de los hogares de ejemplo tiene agua potable'], ['fuente', 'Fuente', 'Fuente: encuesta ficticia']] },
  ]
  caja.classList.add('constructor')
  caja.innerHTML = `<form class="formulario vidrio" id="pz-form" novalidate>
      <label>Pieza<select id="pz-pieza">${PIEZAS.map((p, i) => `<option value="${i}">${esc(p.nombre)}</option>`).join('')}</select></label>
      <div id="pz-campos" class="constructor-campos"></div>
    </form>
    <div class="constructor-escena">
      <div class="pantalla-obs" aria-label="Vista previa"><div id="pz-vista"></div></div>
      <figure class="ventana terminal url"><div class="ventana-barra"><span class="ventana-titulo">Fuente de navegador · URL</span>
        <button class="copiar" type="button" data-copiar="pz-url">Copiar</button></div><pre id="pz-url"></pre></figure>
    </div>`
  const sel = $('#pz-pieza', caja), campos = $('#pz-campos', caja), vista = $('#pz-vista', caja), url = $('#pz-url', caja)
  function elegir() {
    const p = PIEZAS[sel.value]
    campos.innerHTML = p.campos.map(([k, et, v]) => `<label>${esc(et)}<input name="${k}" autocomplete="off" value="${esc(v)}"></label>`).join('')
    $$('input', campos).forEach((i) => i.addEventListener('input', pintar)); pintar()
  }
  function pintar() {
    const p = PIEZAS[sel.value], v = Object.fromEntries($$('input', campos).map((i) => [i.name, i.value]))
    const q = new URLSearchParams(Object.entries(v).filter(([, x]) => x.trim())).toString()
    url.textContent = `http://localhost:8036/api/obs/video/obs-studio/${p.ruta}${q ? '?' + q : ''}`
    vista.className = `obs ${p.clase}`
    vista.innerHTML = p.clase === 'dato'
      ? `<span class="obs-kicker">${esc(v.kicker)}</span><b class="obs-cifra">${esc(v.cifra)}</b><p>${esc(v.label)}</p><small>${esc(v.fuente)}</small>`
      : `<span class="obs-kicker">${esc(v.kicker)}</span><div class="obs-cuerpo"><b>${esc(v.nombre ?? v.tema)}</b><p>${esc(v.rol ?? v.bajada)}</p></div>`
  }
  sel.addEventListener('change', elegir); elegir()
}

// Yupay: un día de comisión contra su tope.
function piezaYupay(caja) {
  const TOPE = 320
  const GASTOS = [
    ['Desayuno', 'Boleta EB01-1203 · Restaurante El Ejemplo', 18, true],
    ['Almuerzo', 'Boleta EB01-1218 · Restaurante El Ejemplo', 32, true],
    ['Hospedaje', 'Factura F001-880 · Hospedaje La Muestra', 120, true],
    ['Cena', 'Ticket T01-93 · Pollería Don Ejemplo', 26, true],
    ['Movilidad local', 'Taxi del terminal al local (sin comprobante)', 15, false],
  ]
  const sol = (n) => `S/ ${n.toFixed(2)}`
  caja.classList.add('calculo')
  caja.innerHTML = `<div class="calculo-lista vidrio"><h3>lun 12/10 <small>tope del día: ${sol(TOPE)}</small></h3>
      <ul>${GASTOS.map(([t, d, m, c], i) => `<li><label><input type="checkbox" data-i="${i}"${c ? ' checked' : ''}>
        <span><b>${esc(t)}</b><small>${esc(d)}</small></span><em>${sol(m)}</em></label></li>`).join('')}</ul>
      <p class="calculo-ayuda">Desmarca un gasto si no tienes su comprobante: pasa a la declaración jurada.</p></div>
    <div class="calculo-total vidrio">
      <div class="calculo-barra" aria-hidden="true"><i id="pz-con"></i><i id="pz-dj"></i></div>
      <dl><dt>Con comprobante</dt><dd id="pz-v-con"></dd><dt>Declaración jurada</dt><dd id="pz-v-dj"></dd>
        <dt>Gastado del día</dt><dd id="pz-v-tot"></dd><dt>Queda del tope</dt><dd id="pz-v-saldo"></dd></dl>
      <p class="calculo-nota" id="pz-nota" role="status"></p></div>`
  function pintar() {
    let con = 0, dj = 0
    $$('input', caja).forEach((i) => { const m = GASTOS[i.dataset.i][2]; if (i.checked) con += m; else dj += m })
    const tot = con + dj
    $('#pz-v-con', caja).textContent = sol(con); $('#pz-v-dj', caja).textContent = sol(dj)
    $('#pz-v-tot', caja).textContent = `${sol(tot)} de ${sol(TOPE)}`; $('#pz-v-saldo', caja).textContent = sol(Math.max(0, TOPE - tot))
    $('#pz-con', caja).style.width = `${Math.min(100, con / TOPE * 100)}%`
    $('#pz-dj', caja).style.width = `${Math.min(100 - Math.min(100, con / TOPE * 100), dj / TOPE * 100)}%`
    $('#pz-nota', caja).textContent = dj ? `${sol(dj)} sin comprobante: Yupay lo lleva a la declaración jurada.` : 'Todo con comprobante: la declaración jurada queda vacía.'
  }
  $$('input', caja).forEach((i) => i.addEventListener('change', pintar)); pintar()
}

function iniciarPieza() {
  const caja = $('.pieza'); if (!caja) return
  ;({ tiqsi: piezaTiqsi, wayra: piezaWayra, yupay: piezaYupay })[DATOS.id]?.(caja)
}

/* ---------------------------------------------------------------- utilidades de página */
function iniciarTema() {
  const raiz = document.documentElement
  $('#tema').addEventListener('click', () => {
    const oscuro = raiz.dataset.theme ? raiz.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches
    raiz.dataset.theme = oscuro ? 'light' : 'dark'
    guardar('qillqa-tema', raiz.dataset.theme)
  })
}
function iniciarCabecera() {
  const menu = $('#menu')
  const marcar = () => menu.classList.toggle('con-borde', scrollY > 8)
  addEventListener('scroll', marcar, { passive: true }); marcar()
}
function iniciarRevelar() {
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return
    e.target.classList.add('visible'); io.unobserve(e.target)
    $$('[data-contar]', e.target).forEach(contarHasta)
  }), { threshold: .12, rootMargin: '0px 0px -40px 0px' })
  $$('.revelar').forEach((el) => io.observe(el))
}
function contarHasta(el) {
  const fin = Number(el.dataset.contar), suf = el.dataset.sufijo || ''
  if (calma || fin === 0) { el.textContent = fin + suf; return }
  el.textContent = 0 + suf
  const t0 = performance.now(), dur = 1100
  const paso = (t) => {
    const k = Math.min(1, (t - t0) / dur), v = Math.round(fin * (1 - Math.pow(1 - k, 3)))
    el.textContent = v + suf; if (k < 1) requestAnimationFrame(paso)
  }
  requestAnimationFrame(paso)
}
function iniciarMenuActivo() {
  const enlaces = $$('.menu-nav a'), mapa = new Map(enlaces.map((a) => [a.getAttribute('href').slice(1), a]))
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) enlaces.forEach((a) => a.classList.toggle('activo', a === mapa.get(e.target.id)))
  }), { rootMargin: '-45% 0px -50% 0px' })
  mapa.forEach((_, id) => { const s = document.getElementById(id); if (s) io.observe(s) })
}
function iniciarVisor() {
  const visor = $('#visor'), img = $('#visor-imagen')
  if (typeof visor.showModal !== 'function') return
  document.addEventListener('click', (e) => {
    const fuente = e.target.closest('img[data-ampliar]'); if (!fuente) return
    img.src = fuente.currentSrc || fuente.src; img.alt = fuente.alt
    visor.showModal()
  })
  visor.addEventListener('click', (e) => { if (e.target !== img) visor.close() })
  $('#visor-cerrar').addEventListener('click', () => visor.close())
}
function iniciarCopiar() {
  // Delegado: la pieza de Wayra añade su propio botón después de arrancar.
  document.addEventListener('click', async (ev) => {
    const b = ev.target.closest('[data-copiar]'); if (!b) return
    const texto = $(`#${b.dataset.copiar}`).innerText.split('\n').filter((l) => l.trim() && !l.trim().startsWith('#'))
      .map((l) => l.replace(/\s+#.*$/, '')).join('\n')
    try { await navigator.clipboard.writeText(texto); b.textContent = 'Copiado' }
    catch {
      const t = document.createElement('textarea'); t.value = texto; document.body.append(t); t.select()
      try { document.execCommand('copy'); b.textContent = 'Copiado' } catch { b.textContent = 'Selecciona y copia' }
      t.remove()
    }
    setTimeout(() => { b.textContent = 'Copiar' }, 1800)
  })
}

for (const f of [pintarIconos, iniciarTema, iniciarCabecera, iniciarPantallas, iniciarPieza, iniciarConexion, iniciarFamilia,
  iniciarVisor, iniciarCopiar, iniciarRevelar, iniciarMenuActivo]) {
  try { f() } catch (err) { console.error(`[${DATOS.id}] ${f.name}:`, err) }
}
