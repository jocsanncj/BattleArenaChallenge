import { iniciarAccesoMovil } from "./acceso.js";

const cuenta = document.querySelector("#cuenta");
const estadoRanking = document.querySelector("#estado-ranking");
const actualizar = document.querySelector("#actualizar-ranking");
const posiciones = document.querySelector("#posiciones");
let jugadorActivo;
let temporizadorPartida;

async function pedir(ruta, opciones) {
  const respuesta = await fetch(ruta, opciones);
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const error = new Error(datos.error || "No se pudo completar la solicitud.");
    error.estado = respuesta.status;
    throw error;
  }
  return datos;
}

async function cargarPerfil(usuario, accesoGoogle = false) {
  // US29 y US30 recuperan el mismo perfil de US04 mediante el UID del token de Firebase.
  const cabeceras = { Authorization: `Bearer ${await usuario.getIdToken()}` };
  try {
    return (await pedir("/api/profile", { headers: cabeceras })).user;
  } catch (error) {
    if (error.estado !== 404) throw error;
    const nombre = (usuario.displayName || usuario.email.split("@")[0]).replaceAll("@", "").trim();
    return (await pedir("/api/profile", {
      method: "POST",
      headers: { ...cabeceras, "Content-Type": "application/json" },
      body: JSON.stringify(accesoGoogle ? {} : { name: nombre.slice(0, 40) || "Jugador" }),
    })).user;
  }
}

function renderPerfil(perfil) {
  document.querySelector("#jugador").textContent = perfil.name;
  const stats = perfil.statistics || {};
  const indicadores = {
    Partidas: stats.matches_played ?? 0,
    Victorias: stats.wins ?? 0,
    Derrotas: stats.losses ?? 0,
    Empates: stats.draws ?? 0,
    Puntos: stats.points_accumulated ?? 0,
    Récord: perfil.record ?? 0,
    Ranking: perfil.ranking ?? "Sin posición",
  };
  const tarjetas = Object.entries(indicadores).map(([nombre, valor]) => {
    const grupo = document.createElement("div");
    const etiqueta = document.createElement("dt");
    const dato = document.createElement("dd");
    etiqueta.textContent = nombre;
    dato.textContent = valor;
    grupo.append(etiqueta, dato);
    return grupo;
  });
  document.querySelector("#estadisticas").replaceChildren(...tarjetas);

  const historial = perfil.match_history || [];
  document.querySelector("#estado-historial").textContent = historial.length ? "" : "Aún no tienes partidas registradas.";
  document.querySelector("#partidas").replaceChildren(...historial.map(partida => fila(
    partida.opponent ? `${partida.result} · ${partida.opponent}` : partida.result,
    `${partida.score} puntos · ${partida.played_at}`,
  )));
}

function fila(titulo, detalle) {
  const item = document.createElement("li");
  const nombre = document.createElement("strong");
  const texto = document.createElement("span");
  nombre.textContent = titulo;
  texto.textContent = detalle;
  item.append(nombre, texto);
  return item;
}

async function cargarRanking() {
  const jugador = jugadorActivo;
  if (!jugador || actualizar.disabled) return false;
  actualizar.disabled = true;
  estadoRanking.textContent = "Cargando ranking…";
  try {
    const { ranking } = await pedir("/api/ranking");
    if (jugadorActivo !== jugador) return;
    posiciones.replaceChildren(...ranking.map(entrada => fila(
      `${entrada.position}. ${entrada.name}`, `${entrada.points} puntos · ${entrada.wins} victorias`,
    )));
    estadoRanking.textContent = ranking.length ? "" : "Todavía no hay jugadores en el ranking.";
    return true;
  } catch {
    if (jugadorActivo === jugador) estadoRanking.textContent = "No se pudo cargar el ranking. Pulsa Actualizar para reintentar.";
    return false;
  } finally {
    if (jugadorActivo === jugador) actualizar.disabled = false;
  }
}

iniciarAccesoMovil({
  pedir,
  async abrirCuenta(user, accesoGoogle) {
    renderPerfil(await cargarPerfil(user, accesoGoogle));
    jugadorActivo = user;
    cuenta.hidden = false;
    cargarRanking();
    cargarEstadoPartida();
    temporizadorPartida = setInterval(cargarEstadoPartida, 2000);
  },
  cerrarCuenta() {
    jugadorActivo = undefined;
    clearInterval(temporizadorPartida);
    limpiarPartidaMovil();
    posiciones.replaceChildren();
    document.querySelector("#jugador").textContent = "";
    document.querySelector("#estadisticas").replaceChildren();
    document.querySelector("#partidas").replaceChildren();
    cuenta.hidden = true;
  },
});

actualizar.addEventListener("click", cargarRanking);

let ultimoResultadoVisto;
let resultadoPendiente = false;
const actualizarPerfil = document.querySelector("#actualizar-perfil");

async function actualizarPerfilMovil() {
  const jugador = jugadorActivo;
  if (!jugador || actualizarPerfil.disabled) return false;
  actualizarPerfil.disabled = true;
  try {
    const token = await jugador.getIdToken();
    const { user } = await pedir("/api/profile", { headers: { Authorization: `Bearer ${token}` } });
    if (jugador !== jugadorActivo) return false;
    renderPerfil(user);
    return true;
  } catch {
    if (jugador === jugadorActivo) {
      document.querySelector("#estado-historial").textContent = "No se pudo actualizar el historial. Inténtalo de nuevo.";
    }
    return false;
  } finally {
    if (jugador === jugadorActivo) actualizarPerfil.disabled = false;
  }
}
actualizarPerfil.addEventListener("click", actualizarPerfilMovil);

async function cargarEstadoPartida() {
  const jugador = jugadorActivo;
  const estado = document.querySelector("#estado-partida");

  const boton = document.querySelector("#actualizar-partida");
  if (!jugador || !estado || boton.disabled) return;
  boton.disabled = true;

  try {
    const token = await jugador.getIdToken();
    // US30 consulta el estado compartido de US13. «partida» incluye la sala
    // de espera y «game» contiene la arena cuando hay una partida en curso o finalizada.
    const { game, mapa, partida } = await pedir("/api/game/state", {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (jugador !== jugadorActivo) return;

    const jugadores = game?.players ?? [];
    // US25 publica el ganador en winner_id. Al conectar el podio de US26, usar
    // sus posiciones finales también aquí para que ambos clientes coincidan en los empates.
    const ganador = game?.status === "finished"
      ? jugadores.find(jugador => jugador.player_id === game.winner_id)
      : undefined;

    const enSala = partida?.jugadores ?? [];
    const mensajes = [game?.message ?? `Sala de espera: ${enSala.length} de 3 jugadores.`];
    if (ganador) mensajes[0] = `Partida finalizada. Ganador: ${ganador.username}.`;
    for (const evento of game?.eventos ?? []) mensajes.push(evento.mensaje);
    estado.textContent = mensajes.join(" ");
    const marcador = document.querySelector("#marcador-partida");
    const fichas = jugadores.map((jugador, indice) => ({ jugador, numero: indice + 1 }));
    if (ganador) fichas.sort((a, b) => b.jugador.score - a.jugador.score);
    const filas = game
      ? fichas.map(({ jugador, numero }) => fila(`Ficha ${numero} · ${jugador.username}`, `${jugador.score} puntos`))
      : enSala.map(jugador => fila(jugador.nombre_usuario, "En la sala"));
    marcador.replaceChildren(...filas);
    dibujarArena(mapa, jugadores, game);
    mostrarEstadoReactor(game);
    if (game?.status === "finished" && game.match_id !== ultimoResultadoVisto) {
      ultimoResultadoVisto = game.match_id;
      resultadoPendiente = true;
    }
    if (resultadoPendiente) {
      // Tras el cierre de la partida, la API ya dispone del resultado guardado
      // para actualizar el ranking global (US27) y el historial personal (US28).
      const [perfilListo, rankingListo] = await Promise.all([actualizarPerfilMovil(), cargarRanking()]);
      if (jugador === jugadorActivo) resultadoPendiente = !(perfilListo && rankingListo);
    }
  } catch {
    if (jugador === jugadorActivo) {
      estado.textContent = "No se pudo consultar la partida.";
    }
  } finally {
    if (jugador === jugadorActivo) boton.disabled = false;
  }
}
document.querySelector("#actualizar-partida").addEventListener("click", cargarEstadoPartida);

function dibujarArena(mapa, jugadores, juego) {
  const canvas = document.querySelector("#arena-movil");
  if (!mapa || !juego) {
    canvas.hidden = true;
    return;
  }

  const lado = 24;
  const ancho = mapa.columnas * lado;
  const alto = mapa.filas * lado;
  if (canvas.width !== ancho) canvas.width = ancho;
  if (canvas.height !== alto) canvas.height = alto;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, ancho, alto);

  const colores = {
    "#": "#64748b",
    X: "#7c3aed",
    R: "#f59e0b",
  };

  // Si US23 incorpora un símbolo de casilla nuevo, añadir aquí su color.
  // Las posiciones de obstáculos (US20), guardianes (US21) y energía extra (US22) llegan en «game».
  mapa.plano.forEach((fila, y) => {
    Array.from(fila).forEach((casilla, x) => {
      ctx.fillStyle = colores[casilla] ?? "#243247";
      ctx.fillRect(x * lado, y * lado, lado - 1, lado - 1);
    });
  });

  ctx.font = "bold 12px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  function dibujarMarca(objeto, texto, color) {
    const centroX = (objeto.x + 0.5) * lado;
    const centroY = (objeto.y + 0.5) * lado;

    ctx.beginPath();
    ctx.arc(centroX, centroY, 9, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.fillStyle = "#0f172a";
    ctx.fillText(texto, centroX, centroY);
  }

  const obstaculos = juego?.obstaculos;
  for (const puerta of obstaculos?.puertas ?? []) {
    dibujarMarca(puerta, "P", puerta.abierta ? "#4ade80" : "#f87171");
  }

  const marcasTrampas = { jaula: "J", arenas_movedizas: "A", campo_electrico: "E" };
  for (const trampa of obstaculos?.trampas ?? []) {
    if (trampa.activa === false) continue;
    dibujarMarca(trampa, marcasTrampas[trampa.tipo] ?? "!", "#fbbf24");
  }

  for (const guardian of juego?.guardianes ?? []) {
    dibujarMarca(guardian, "G", "#fb7185");
  }
  if (juego.energia_adicional) dibujarMarca(juego.energia_adicional, "+", "#a3e635");

  jugadores.forEach((jugador, indice) => {
    if (jugador.connected === false) return;
    dibujarMarca(jugador, String(indice + 1), "#38bdf8");
  });

  canvas.hidden = false;
}

const unirseSala = document.querySelector("#unirse-sala");
const abandonarSala = document.querySelector("#abandonar-sala");
const iniciarPartida = document.querySelector("#iniciar-partida");
const avisoSala = document.querySelector("#aviso-sala");

async function cambiarSala(accion) {
  const jugador = jugadorActivo;
  if (!jugador || unirseSala.disabled) return;

  unirseSala.disabled = true;
  abandonarSala.disabled = true;
  iniciarPartida.disabled = true;

  try {
    const token = await jugador.getIdToken();
    if (jugador !== jugadorActivo) return;
    // La API de sala (US09) valida quién puede iniciar la partida y US30 consulta el resultado.
    await pedir(`/api/game/${accion}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });

    if (jugador !== jugadorActivo) return;
    const mensajes = {
      join: "Ya estás en la sala.",
      leave: "Saliste de la sala.",
      start: "Partida iniciada.",
    };

    avisoSala.textContent = mensajes[accion];
    cargarEstadoPartida();

  } catch (error) {
    if (jugador === jugadorActivo) {
      avisoSala.textContent = error.message || "No se pudo actualizar la sala.";
    }
  } finally {
    if (jugador === jugadorActivo) {
      unirseSala.disabled = false;
      abandonarSala.disabled = false;
      iniciarPartida.disabled = false;
    }
  }
}

unirseSala.addEventListener("click", () => cambiarSala("join"));
abandonarSala.addEventListener("click", () => cambiarSala("leave"));
iniciarPartida.addEventListener("click", () => cambiarSala("start"));

const controlesArena = document.querySelector("#controles-arena");
const avisoMovimiento = document.querySelector("#aviso-movimiento");

async function moverJugador(direccion) {
  const jugador = jugadorActivo;
  if (!jugador || controlesArena.disabled) return;
  controlesArena.disabled = true;

  try {
    const token = await jugador.getIdToken();
    if (jugador !== jugadorActivo) return;
    const resultado = await pedir("/api/game/move", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ direction: direccion }),
    });

    if (jugador !== jugadorActivo) return;
    avisoMovimiento.textContent = resultado.ok
      ? ""
      : (resultado.error || "No se pudo mover al jugador.");
    cargarEstadoPartida();
  } catch (error) {
    if (jugador === jugadorActivo) {
      avisoMovimiento.textContent = error.message || "No se pudo mover al jugador.";
    }
  } finally {
    if (jugador === jugadorActivo) controlesArena.disabled = false;
  }
}

controlesArena.querySelectorAll("[data-direction]").forEach(boton => {
  boton.addEventListener("click", () => moverJugador(boton.dataset.direction));
});

const extraerEnergia = document.querySelector("#extraer-energia");
const cancelarExtraccion = document.querySelector("#cancelar-extraccion");
const avisoReactor = document.querySelector("#aviso-reactor");
let extraccion;

async function cambiarExtraccion(accion) {
  // US30 envía la acción del reactor (US18). El servidor valida la extracción
  // y publica los puntos de US19 en el siguiente estado del marcador.
  const jugador = jugadorActivo;
  if (!jugador || extraerEnergia.disabled) return;

  const intento = accion === "start"
    ? { jugador, id: crypto.getRandomValues(new Uint32Array(4)).join("-") }
    : extraccion;

  if (intento?.jugador !== jugador) return;
  extraerEnergia.disabled = true;
  cancelarExtraccion.disabled = true;

  try {
    const token = await jugador.getIdToken();
    if (jugador !== jugadorActivo) return;
    await pedir("/api/game/reactor", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ action: accion, event_id: intento.id }),
    });

    if (jugador !== jugadorActivo) return;
    extraccion = accion === "start" ? intento : undefined;
    avisoReactor.textContent = accion === "start"
      ? "Extracción iniciada. Mantente junto al reactor."
      : "Solicitud de cancelación enviada.";
    cargarEstadoPartida();
  } catch (error) {
    if (jugador === jugadorActivo) {
      avisoReactor.textContent = error.message || "No se pudo usar el reactor.";
    }
  } finally {
    if (jugador === jugadorActivo) {
      extraerEnergia.disabled = false;
      cancelarExtraccion.disabled = extraccion?.jugador !== jugador;
    }
  }
}

extraerEnergia.addEventListener("click", () => cambiarExtraccion("start"));
cancelarExtraccion.addEventListener("click", () => cambiarExtraccion("stop"));

function mostrarEstadoReactor(juego) {
  const estado = document.querySelector("#estado-reactor");
  const reactor = juego?.reactor;
  let mensaje = "Reactor: sin partida activa.";

  if (juego?.active && !juego.paused && reactor) {
    const segundos = Math.ceil(reactor.remaining_seconds);
    const mensajes = {
      disponible: "Reactor: disponible.",
      ocupado: `Reactor: extracción en curso (${segundos} s).`,
      recargando: `Reactor: recargando (${segundos} s).`,
      sobrecargado: "Reactor: desactivado por una sobrecarga.",
    };
    mensaje = mensajes[reactor.status] ?? mensaje;
  }

  if (estado.textContent !== mensaje) estado.textContent = mensaje;
}

const selectorAvatar = document.querySelector("#avatar-partida");
const guardarAvatar = document.querySelector("#guardar-avatar");
const avisoAvatar = document.querySelector("#aviso-avatar");

guardarAvatar.addEventListener("click", async () => {
  const jugador = jugadorActivo;
  const valor = selectorAvatar.value;
  if (!jugador) return;
  if (!valor) {
    avisoAvatar.textContent = "Elige un avatar primero.";
    return;
  }

  guardarAvatar.disabled = true;
  avisoAvatar.textContent = "Guardando avatar...";
  try {
    const token = await jugador.getIdToken();
    if (jugador !== jugadorActivo) return;
    await pedir("/api/game/avatar", {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ tipo: "predeterminado", valor }),
    });
    if (jugador === jugadorActivo) avisoAvatar.textContent = "Avatar guardado.";
  } catch (error) {
    if (jugador === jugadorActivo) avisoAvatar.textContent = error.message;
  } finally {
    if (jugador === jugadorActivo) guardarAvatar.disabled = false;
  }
});

function limpiarPartidaMovil() {
  ultimoResultadoVisto = undefined;
  resultadoPendiente = false;
  extraccion = undefined;
  selectorAvatar.value = "";
  document.querySelector("#marcador-partida").replaceChildren();
  const canvas = document.querySelector("#arena-movil");
  canvas.hidden = true;
  canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
  document.querySelectorAll("#partida [role=status], #estado-ranking, #estado-historial").forEach(elemento => {
    elemento.textContent = "";
  });
  document.querySelectorAll("#partida button, #partida fieldset, #actualizar-perfil, #actualizar-ranking").forEach(control => {
    control.disabled = false;
  });
  cancelarExtraccion.disabled = true;
}
