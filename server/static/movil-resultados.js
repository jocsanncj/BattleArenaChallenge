const panel = document.querySelector("#resultados-partida");
const podio = document.querySelector("#podio-partida");
const campeon = document.querySelector("#retrato-ganador");
let partidaMostrada;

// Recibe el score numérico de un jugador y devuelve el texto que usan tanto el anuncio del ganador
// como las tarjetas. Uno se muestra en singular, por ejemplo «1 punto».
function puntos(cantidad) {
  return cantidad === 1 ? "1 punto" : `${cantidad} puntos`;
}

// Construye el elemento que pide la tarjeta y le asigna la clase CSS. textContent trata el nombre
// o el puntaje como texto visible. Quien llama recibe el nodo y decide dónde insertarlo.
function texto(etiqueta, clase, valor) {
  const nodo = document.createElement(etiqueta);
  nodo.className = clase;
  nodo.textContent = valor;
  return nodo;
}

// Recibe un participante del resultado confirmado y devuelve un elemento de lista para su puesto.
// score es el puntaje de esta partida y personal_record es su mejor marca. new_record indica
// si esta partida la mejoró. La imagen queda preparada para completarse cuando haya retrato.
function tarjeta(jugador) {
  const puesto = document.createElement("li");
  const retrato = document.createElement("span");
  retrato.className = "retrato-podio";
  retrato.setAttribute("aria-hidden", "true");
  const img = document.createElement("img");
  img.alt = "";
  img.hidden = true;
  retrato.append(texto("span", "inicial-avatar", ""), img);
  puesto.append(
    retrato,
    texto("span", "puesto-podio", `${jugador.position}. lugar`),
    texto("strong", "nombre-podio", jugador.username),
    texto("span", "puntos-podio", puntos(jugador.score)),
    texto("span", jugador.new_record ? "record-podio nuevo-record" : "record-podio",
      jugador.new_record ? `¡Nuevo récord! ${jugador.personal_record}` : `Récord personal: ${jugador.personal_record}`),
  );
  return puesto;
}

// Recibe el elemento img, el jugador y la URL disponible en este momento. Si falta la URL,
// muestra la inicial. Si después llega el retrato personal, cambia ese elemento sin rehacer el podio.
function actualizarRetrato(img, jugador, url) {
  const inicial = img.previousElementSibling;
  inicial.textContent = Array.from(jugador.username)[0] || "·";
  inicial.hidden = Boolean(url);
  img.hidden = !url;
  if (!url) img.removeAttribute("src");
  else if (img.getAttribute("src") !== url) img.setAttribute("src", url);
}

// movil.js entrega el resultado de esta partida o el resultado anterior recuperado en un sondeo.
// retratoDe busca la imagen de cada jugador. Se devuelve true al mostrar el podio y false al ocultarlo.
// US17 y US30 toman el ganador y los puestos del servidor. Una prórroga mantiene oculto el podio.
export function mostrarResultados(juego, retratoDe) {
  // Exige un resultado guardado y terminado. find devuelve el jugador cuyo ID coincide con winner_id
  // y cuyo puesto es 1. Si falta alguna condición se oculta el resultado que pudiera quedar en pantalla.
  const ganador = juego?.results_persisted === true && juego.status === "finished"
    && juego.players.find(j => j.player_id === juego.winner_id && j.position === 1);
  if (!ganador) {
    if (!panel.hidden) {
      panel.hidden = true;
      podio.replaceChildren();
      campeon.removeAttribute("src");
      partidaMostrada = undefined;
    }
    return false;
  }
  // Los tres puntos copian los participantes en otro arreglo antes de ordenar. El comparador usa
  // position del servidor, de menor a mayor, para conservar el orden original en juego.players.
  const jugadores = [...juego.players].sort((a, b) => a.position - b.position);
  if (partidaMostrada !== juego.match_id || panel.hidden) {
    document.querySelector("#ganador-partida").textContent = ganador.username;
    document.querySelector("#puntaje-final").textContent = `Puntaje final: ${puntos(ganador.score)}`;
    // El servidor da la duración en segundos. La división entera obtiene los minutos y % 60 da el resto.
    // padStart añade el cero que falta y la plantilla une ambas partes. Por ejemplo, 65 segundos se muestran como 01:05.
    const duracion = juego.duration_seconds;
    const minutos = String(Math.floor(duracion / 60)).padStart(2, "0");
    const segundos = String(duracion % 60).padStart(2, "0");
    document.querySelector("#duracion-partida").textContent = `Duración de la partida: ${minutos}:${segundos}`;
    // map(tarjeta) crea una tarjeta por jugador. Los tres puntos pasan esos nodos como argumentos
    // a replaceChildren para sustituir todas las tarjetas del podio anterior en una sola llamada.
    podio.replaceChildren(...jugadores.map(tarjeta));
    partidaMostrada = juego.match_id;
    panel.hidden = false;
    if (document.querySelector("#juego-activo")?.contains(document.activeElement)) {
      document.querySelector("#titulo-resultados").focus();
    }
  }
  actualizarRetrato(campeon, ganador, retratoDe(ganador));
  // Los sondeos de una misma partida conservan las tarjetas. forEach usa el índice de la lista ordenada
  // para completar la imagen del puesto correspondiente con el retrato más reciente.
  jugadores.forEach((jugador, indice) => {
    actualizarRetrato(podio.children[indice].querySelector("img"), jugador, retratoDe(jugador));
  });
  return true;
}
