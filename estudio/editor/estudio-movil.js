/* estudio-movil.js — comportamiento mínimo de los editores del estudio en un teléfono (≤ 760 px de ancho).

   Cada página declara sus paneles en <body data-movil-izq="#id" data-movil-der="#id">. En pantalla angosta:
   los paneles dejan la rejilla y pasan a cajones que se abren y cierran (botones en la cabecera, el riel o las
   pestañas los abren; la ✕ del cajón o un toque fuera los cierran), la cabecera se desliza de lado y los
   controles crecen a 40 px para el dedo (estudio-tema.css, «Teléfono»). Se puede ver, elegir y exportar; la
   edición fina sigue pensada para una pantalla grande. Sin dependencias; los íconos, de estudio-iconos.js. */
(function(){
  "use strict";
  var mq = window.matchMedia("(max-width: 760px)");
  var ico = function(n){ return (window.icono && window.icono(n, "")) || ""; };
  function paneles(){
    var b = document.body, out = [];
    [["izq", b.dataset.movilIzq], ["der", b.dataset.movilDer]].forEach(function(p){
      var el = p[1] && document.querySelector(p[1]); if(el) out.push([p[0], el]);
    });
    return out;
  }
  function cerrarTodo(){ paneles().forEach(function(p){ p[1].classList.remove("abierto"); }); }
  function abrir(lado){
    paneles().forEach(function(p){ p[1].classList.toggle("abierto", p[0] === lado && !p[1].classList.contains("abierto")); });
  }
  function preparar(){
    var cab = document.querySelector(".est-cabecera"), ps = paneles();
    if(!cab || !ps.length || cab.querySelector(".est-movil-boton")) return;
    ps.forEach(function(p){
      var lado = p[0], el = p[1];
      el.setAttribute("data-movil-panel", lado);
      var cerrar = document.createElement("button");
      cerrar.type = "button"; cerrar.className = "est-boton est-boton--icono est-movil-boton est-movil-cerrar";
      cerrar.title = "Cerrar el panel"; cerrar.setAttribute("aria-label", "Cerrar el panel"); cerrar.innerHTML = ico("cerrar");
      cerrar.onclick = function(ev){ ev.stopPropagation(); el.classList.remove("abierto"); };
      el.insertBefore(cerrar, el.firstChild);
      var b = document.createElement("button");
      b.type = "button"; b.className = "est-boton est-boton--icono est-movil-boton";
      b.title = lado === "izq" ? "Paneles (banco, texto, marca…)" : "Propiedades";
      b.setAttribute("aria-label", b.title); b.innerHTML = ico(lado === "izq" ? "capas" : "propiedades");
      b.onclick = function(ev){ ev.stopPropagation(); abrir(lado); };
      if(lado === "izq") cab.insertBefore(b, cab.firstChild); else cab.appendChild(b);
    });
    // el riel y las pestañas abren el panel izquierdo; un toque fuera de los cajones los cierra
    document.addEventListener("click", function(ev){
      if(!mq.matches) return;
      var t = ev.target;
      if(t.closest && t.closest(".est-riel__boton,[data-vista],#rail button")){
        var izq = paneles().filter(function(p){ return p[0] === "izq"; })[0];
        if(izq) setTimeout(function(){ izq[1].classList.add("abierto"); }, 0);
        return;
      }
      if(t.closest && !t.closest("[data-movil-panel],.est-movil-boton,.est-modal,#modal,#modal-fondo,#modal-bg,.av-dialogo")) cerrarTodo();
    }, true);
  }
  function aplicar(){
    document.documentElement.classList.toggle("est-movil", mq.matches);
    if(!mq.matches) cerrarTodo();
    window.dispatchEvent(new Event("resize"));
  }
  function iniciar(){ preparar(); aplicar(); }
  if(mq.addEventListener) mq.addEventListener("change", aplicar); else mq.addListener(aplicar);
  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar); else iniciar();
})();
