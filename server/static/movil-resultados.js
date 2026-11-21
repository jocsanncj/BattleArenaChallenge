const panel = document.querySelector("#resultados-partida");
const podio = document.querySelector("#podio-partida");
const campeon = document.querySelector("#retrato-ganador");
let partidaMostrada;

function puntos(cantidad) {
  return cantidad === 1 ? "1 punto" : `${cantidad} puntos`;
}

function texto(etiqueta, clase, valor) {
  const nodo = document.createElement(etiqueta);
  nodo.className = clase;
  nodo.textContent = valor;
  return nodo;
}

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

function actualizarRetrato(img, jugador, url) {
  const inicial = img.previousElementSibling;
  inicial.textContent = Array.from(jugador.username)[0] || "·";
  inicial.hidden = Boolean(url);
  img.hidden = !url;
  if (!url) img.removeAttribute("src");
  else if (img.getAttribute("src") !== url) img.setAttribute("src", url);
}

// US17 y US30 muestran el mismo ganador y los mismos puestos confirmados por el servidor.
// Durante una prórroga no hay podio. Los sondeos posteriores solo completan retratos pendientes.
export function mostrarResultados(juego, retratoDe) {
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
  const jugadores = [...juego.players].sort((a, b) => a.position - b.position);
  if (partidaMostrada !== juego.match_id || panel.hidden) {
    document.querySelector("#ganador-partida").textContent = ganador.username;
    document.querySelector("#puntaje-final").textContent = `Puntaje final: ${puntos(ganador.score)}`;
    const duracion = juego.duration_seconds;
    const minutos = String(Math.floor(duracion / 60)).padStart(2, "0");
    const segundos = String(duracion % 60).padStart(2, "0");
    document.querySelector("#duracion-partida").textContent = `Duración de la partida: ${minutos}:${segundos}`;
    podio.replaceChildren(...jugadores.map(tarjeta));
    partidaMostrada = juego.match_id;
    panel.hidden = false;
    if (document.querySelector("#juego-activo")?.contains(document.activeElement)) {
      document.querySelector("#titulo-resultados").focus();
    }
  }
  actualizarRetrato(campeon, ganador, retratoDe(ganador));
  jugadores.forEach((jugador, indice) => {
    actualizarRetrato(podio.children[indice].querySelector("img"), jugador, retratoDe(jugador));
  });
  return true;
}
