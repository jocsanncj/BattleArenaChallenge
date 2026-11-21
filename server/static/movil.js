import { iniciarAccesoMovil } from "./acceso.js";
import { catalogo, prepararSeleccion, retratoPersonalizado } from "./movil-avatares.js";
import { prepararConfiguracion } from "./movil-configuracion.js";
import { crearRenderArena } from "./movil-arena.js";
import { prepararMusica } from "./movil-audio.js";
import { mostrarResultados } from "./movil-resultados.js";

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
    // El 404 indica el primer ingreso. Con Google enviamos {} para que el servidor nombre el perfil a partir del token.
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
    seleccion.cargar(user, pedir, () => user === jugadorActivo);
    cargarEstadoPartida();
    temporizadorPartida = setInterval(cargarEstadoPartida, 2000);
  },
  async salirDePartida() {
    const jugador = jugadorActivo;
    cerrandoSesion = true;
    actualizarBotones();
    try {
      // Si se pulsó Continuar justo antes de salir, esperamos a que el servidor confirme la plaza.
      await cambioEnCurso;
      if (!jugador) return true;
      const headers = { Authorization: `Bearer ${await jugador.getIdToken()}` };
      const actual = await pedir("/api/game/state", { headers, signal: AbortSignal.timeout(5000) });
      const pertenece = actual.game
        ? actual.game.players.some(j => j.user_id === actual.jugador_actual_id && j.connected)
        : actual.partida.jugadores.some(j => j.id_usuario === actual.jugador_actual_id);
      if (pertenece) await pedir("/api/game/leave", { method: "POST", headers, signal: AbortSignal.timeout(5000) });
      return true;
    } catch {
      return false;
    } finally {
      cerrandoSesion = false;
      actualizarBotones();
    }
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

let consultaActual, datosPartida;
let operacionSala = false, cerrandoSesion = false, cambioEnCurso;
let partidaSeguida, resultadoVisible;
const retratosPersonales = new Map();
const arena = crearRenderArena(document.querySelector("#arena-movil"), jugador =>
  catalogo.get(jugador.avatar_id)?.personaje || retratosPersonales.get(jugador.user_id));
const musica = prepararMusica(document.querySelector("#musica-movil"));
const nombresEscenarios = JSON.parse(document.querySelector("#nombres-escenarios").textContent);
const seleccion = prepararSeleccion(actualizarBotones);
const editorConfiguracion = prepararConfiguracion({
  pedir, jugadorActual: () => jugadorActivo, actualizar: () => cargarEstadoPartida(true),
});

async function cargarEstadoPartida(forzar = false) {
  const jugador = jugadorActivo;
  const estado = document.querySelector("#estado-partida");

  const boton = document.querySelector("#actualizar-partida");
  if (!jugador || operacionSala || (consultaActual && !forzar)) return;
  const consulta = Symbol();
  consultaActual = consulta;
  boton.disabled = true;

  try {
    const token = await jugador.getIdToken();
    // US30 consulta el estado compartido de US13. «partida» incluye la sala
    // de espera y «game» contiene la arena cuando hay una partida en curso o finalizada.
    const ruta = partidaSeguida ? "/api/game/state?resultado_de=" + encodeURIComponent(partidaSeguida) : "/api/game/state";
    const datos = await pedir(ruta, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (jugador !== jugadorActivo || consultaActual !== consulta) return;
    datosPartida = datos;
    const { game, mapa, partida, jugador_actual_id, avatares_sala } = datos;
    const { dentro, sala, jugando } = participacion();
    // Una nueva sala puede abrirse entre dos consultas. El participante conserva su podio hasta pulsar Volver.
    const final = datos.resultado_anterior || (dentro && game?.status === "finished" ? game : null);
    resultadoVisible = mostrarResultados(final, retratoJugador) ? final : null;
    partidaSeguida = resultadoVisible?.match_id || (dentro ? game?.match_id : null);
    mostrarSala(partida, game, jugador_actual_id, avatares_sala);
    const juegoVisible = document.querySelector("#juego-activo").hidden ? null : game;
    const mensajes = juegoVisible ? [juegoVisible.message, ...(juegoVisible.eventos || []).map(e => e.mensaje)] : [];
    if (sala && !resultadoVisible) {
      mensajes.push(partida.jugadores.length < 2 ? "Esperando a otro jugador…" : "La sala está lista para iniciar.");
    }
    estado.textContent = mensajes.join(" ");
    if (resultadoVisible) avisoSala.textContent = "";
    musica.sincronizar(resultadoVisible ? "resultados" : jugando ? "arena" : null);
    const tema = arena.dibujar(mapa, juegoVisible, partida.configuracion, jugador_actual_id);
    if (juegoVisible) mostrarIndicadores(juegoVisible, tema || mapa.nombre, jugador_actual_id);
    mostrarEstadoReactor(juegoVisible);
    if (resultadoVisible && resultadoVisible.match_id !== ultimoResultadoVisto) {
      ultimoResultadoVisto = resultadoVisible.match_id;
      resultadoPendiente = true;
    }
    if (resultadoPendiente) {
      // Tras el cierre de la partida, la API ya dispone del resultado guardado
      // para actualizar el ranking global (US27) y el historial personal (US28).
      const [perfilListo, rankingListo] = await Promise.all([actualizarPerfilMovil(), cargarRanking()]);
      if (jugador === jugadorActivo) resultadoPendiente = !(perfilListo && rankingListo);
    }
  } catch {
    if (jugador === jugadorActivo && consultaActual === consulta) {
      estado.textContent = "No se pudo consultar la partida.";
    }
  } finally {
    if (consultaActual === consulta) { consultaActual = null; boton.disabled = false; }
  }
}
document.querySelector("#actualizar-partida").addEventListener("click", () => cargarEstadoPartida());

function retratoJugador(jugador) {
  return catalogo.get(jugador.avatar_id)?.retrato || retratosPersonales.get(jugador.user_id);
}

function mostrarIndicadores(juego, tema, idPropio) {
  document.querySelector("#titulo-arena").textContent = tema || "Arena";
  const restante = juego.remaining_seconds != null;
  const segundos = Math.floor(Math.max(0, (restante ? juego.remaining_seconds : juego.elapsed_seconds) || 0));
  const reloj = [Math.floor(segundos / 60), segundos % 60].map(n => String(n).padStart(2, "0")).join(":");
  const etiqueta = juego.status === "overtime" ? "Prórroga" : restante ? "Tiempo restante" : "Tiempo transcurrido";
  document.querySelector("#reloj-arena").textContent = etiqueta + " · " + reloj;
  const marcador = document.querySelector("#marcador-partida");
  marcador.replaceChildren(...juego.players.map(j => {
    const item = fila(j.username + (j.user_id === idPropio ? " (tú)" : ""), j.score === 1 ? "1 punto" : j.score + " puntos");
    const url = retratoJugador(j);
    if (url) {
      const img = document.createElement("img");
      img.src = url;
      img.alt = "";
      item.prepend(img);
    }
    return item;
  }));
}

function cargarRetratoPersonal(id, usuario) {
  if (retratosPersonales.has(id)) return;
  retratosPersonales.set(id, "");
  (async () => {
    const token = await usuario.getIdToken();
    const { avatar } = await pedir("/api/game/avatar?id=" + encodeURIComponent(id), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (usuario !== jugadorActivo || avatar?.tipo !== "personalizado") return;
    const url = retratoPersonalizado(avatar.valor);
    if (!url) return;
    retratosPersonales.set(id, url);
    for (const img of document.querySelectorAll("#jugadores-sala img[data-personal]")) {
      if (img.dataset.personal === String(id)) { img.src = url; img.hidden = false; }
    }
    arena.repintar();
    if (resultadoVisible) mostrarResultados(resultadoVisible, retratoJugador);
  })().catch(() => { /* El nombre o el número identifica la ficha si falta su retrato. */ });
}

function participacion() {
  if (!datosPartida) return {};
  const { partida, game, jugador_actual_id } = datosPartida;
  const enSala = partida.jugadores.some(j => j.id_usuario === jugador_actual_id);
  const participante = game?.players.find(j => j.user_id === jugador_actual_id);
  const dentro = game ? Boolean(participante?.connected) : enSala;
  const enCurso = Boolean(game && game.status !== "finished");
  return { dentro, sala: dentro && !game, jugando: dentro && enCurso,
    reconectar: enCurso && participante?.connected === false, enCurso };
}

function actualizarBotones() {
  const { dentro, sala, reconectar, enCurso } = participacion();
  const bloqueo = !datosPartida || operacionSala || cerrandoSesion;
  unirseSala.disabled = bloqueo || dentro || (enCurso ? !reconectar : !seleccion.eleccion());
  unirseSala.textContent = reconectar ? "Volver a la partida" : "Continuar";
  document.querySelector("#opciones-avatar").disabled = operacionSala || Boolean(enCurso);
  document.querySelector("#archivo-avatar").disabled = operacionSala || Boolean(enCurso);
  abandonarSala.disabled = bloqueo;
  iniciarPartida.disabled = bloqueo || !sala || datosPartida.partida.jugadores.length < 2;
}

function mostrarSala(partida, game, idPropio, avatares) {
  const { dentro, sala, jugando } = participacion();
  document.querySelector("#seleccion-personaje").hidden = Boolean(dentro || resultadoVisible);
  document.querySelector("#sala-espera").hidden = !sala || Boolean(resultadoVisible);
  document.querySelector("#juego-activo").hidden = !game || game.status === "finished" || Boolean(resultadoVisible);
  document.querySelector("#acciones-jugador").hidden = !jugando || Boolean(resultadoVisible);
  abandonarSala.hidden = !dentro && !resultadoVisible;
  editorConfiguracion.sincronizar(sala && !resultadoVisible ? partida : null, idPropio);
  actualizarBotones();
  const idsPersonales = new Set();
  for (const j of partida.jugadores) {
    if ((avatares?.[j.id_usuario] || "").startsWith("personalizado-")) {
      idsPersonales.add(j.id_usuario);
      cargarRetratoPersonal(j.id_usuario, jugadorActivo);
    }
  }
  for (const j of (resultadoVisible || game)?.players ?? []) {
    if (j.avatar_id?.startsWith("personalizado-")) {
      idsPersonales.add(j.user_id);
      cargarRetratoPersonal(j.user_id, jugadorActivo);
    }
  }
  for (const [id, url] of retratosPersonales) {
    if (!idsPersonales.has(id)) { retratosPersonales.delete(id); arena.olvidarImagen(url); }
  }
  if (!sala) return;
  document.querySelector("#numero-jugadores").textContent = `Jugadores (${partida.jugadores.length}/3)`;
  const filas = partida.jugadores.map(j => {
    const retrato = document.createElement("img");
    retrato.alt = "";
    const id = avatares?.[j.id_usuario];
    const url = catalogo.get(id)?.retrato || retratosPersonales.get(j.id_usuario);
    if (url) retrato.src = url;
    else retrato.hidden = true;
    if (id?.startsWith("personalizado-")) retrato.dataset.personal = String(j.id_usuario);
    const item = document.createElement("li");
    item.append(retrato, j.nombre_usuario + (j.id_usuario === idPropio ? " (tú)" : ""));
    return item;
  });
  document.querySelector("#jugadores-sala").replaceChildren(...filas);
  const cfg = partida.configuracion;
  const reglas = [
    ["Fin de partida", cfg.modo_fin === "puntos" ? `${cfg.puntos_fin} puntos` : `${cfg.minutos_fin} minutos`],
    ["Congelación", `${cfg.segundos_congelacion} s`],
    ["Mapa", cfg.rotacion ? "Rotación de escenarios" : nombresEscenarios[cfg.escenario ?? 0]],
  ];
  document.querySelector("#configuracion-sala").replaceChildren(...reglas.map(([nombre, valor]) => {
    const g = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = nombre; dd.textContent = valor;
    g.append(dt, dd);
    return g;
  }));
}

const unirseSala = document.querySelector("#unirse-sala");
const abandonarSala = document.querySelector("#abandonar-sala");
const iniciarPartida = document.querySelector("#iniciar-partida");
const avisoSala = document.querySelector("#aviso-sala");

async function cambiarSala(accion) {
  const jugador = jugadorActivo;
  const boton = {join: unirseSala, leave: abandonarSala, start: iniciarPartida}[accion];
  if (!jugador || operacionSala || boton.disabled) return;
  operacionSala = true;
  consultaActual = null;
  actualizarBotones();
  avisoSala.textContent = "";

  try {
    const token = await jugador.getIdToken();
    if (jugador !== jugadorActivo) return;
    const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
    if (accion === "join" && !participacion().reconectar) {
      // Continuar guarda la misma elección que Pygame antes de ocupar una plaza en la sala.
      const avatar = seleccion.eleccion();
      if (!avatar) throw new Error("Selecciona un avatar para continuar.");
      await seleccion.guardar(avatar, headers, pedir, () => jugador === jugadorActivo);
      if (jugador !== jugadorActivo) return;
    }
    // La API de sala (US09) valida quién puede iniciar la partida y US30 consulta el resultado.
    const partidaAlSalir = accion === "leave" ? partidaSeguida : null;
    const ruta = "/api/game/" + accion + (partidaAlSalir ? "?partida=" + encodeURIComponent(partidaAlSalir) : "");
    await pedir(ruta, {
      method: "POST",
      headers,
    });

    if (jugador !== jugadorActivo) return;
    if (accion === "leave") partidaSeguida = null;
    const mensajes = {
      join: "Ya estás en la sala.",
      leave: "Saliste de la sala.",
      start: "Partida iniciada.",
    };

    avisoSala.textContent = mensajes[accion];
  } catch (error) {
    if (jugador === jugadorActivo) {
      avisoSala.textContent = error.message || "No se pudo actualizar la sala.";
    }
  } finally {
    if (jugador === jugadorActivo) {
      operacionSala = false;
      await cargarEstadoPartida(true);
      actualizarBotones();
    }
  }
}

for (const [boton, accion] of [[unirseSala, "join"], [abandonarSala, "leave"], [iniciarPartida, "start"]]) {
  boton.addEventListener("click", () => { cambioEnCurso = cambiarSala(accion); });
}

const controlesArena = document.querySelector("#controles-arena");
const avisoMovimiento = document.querySelector("#aviso-movimiento");

async function moverJugador(direccion) {
  const jugador = jugadorActivo;
  if (!jugador || controlesArena.disabled) return;
  controlesArena.disabled = true;

  try {
    const token = await jugador.getIdToken();
    if (jugador !== jugadorActivo) return;
    // El móvil envía la dirección. El servidor comprueba las colisiones y el mapa se redibuja con la posición confirmada.
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

  // US18 usa el mismo event_id para reconocer un inicio repetido y para cancelar esa extracción concreta.
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

function limpiarPartidaMovil() {
  ultimoResultadoVisto = undefined;
  resultadoPendiente = false;
  extraccion = undefined;
  consultaActual = datosPartida = null;
  operacionSala = false;
  partidaSeguida = resultadoVisible = null;
  mostrarResultados(null);
  musica.sincronizar(null);
  arena.dibujar(null);
  editorConfiguracion.sincronizar(null, null);
  for (const url of retratosPersonales.values()) arena.olvidarImagen(url);
  retratosPersonales.clear();
  document.querySelector("#seleccion-personaje").hidden = false;
  document.querySelector("#sala-espera").hidden = true;
  document.querySelector("#juego-activo").hidden = true;
  abandonarSala.hidden = true;
  document.querySelector("#jugadores-sala").replaceChildren();
  document.querySelector("#marcador-partida").replaceChildren();
  document.querySelectorAll("#partida [role=status], #estado-ranking, #estado-historial").forEach(elemento => {
    elemento.textContent = "";
  });
  document.querySelectorAll("#partida button, #partida fieldset, #actualizar-perfil, #actualizar-ranking").forEach(control => {
    control.disabled = false;
  });
  cancelarExtraccion.disabled = true;
  seleccion.limpiar();
}
