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

// Punto común para las llamadas HTTP del móvil. ruta identifica el recurso y opciones puede incluir método, token y cuerpo.
// Devuelve el JSON o lanza un Error con el estado HTTP para que el llamador distinga, por ejemplo, un perfil ausente de una sesión rechazada.
async function pedir(ruta, opciones) {
  const respuesta = await fetch(ruta, opciones);
  // Si la respuesta no contiene JSON válido, usa un objeto vacío para poder informar del error HTTP.
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const error = new Error(datos.error || "No se pudo completar la solicitud.");
    error.estado = respuesta.status;
    throw error;
  }
  return datos;
}

// Se llama al entrar con contraseña o Google. Busca el perfil de juego asociado a la identidad que Firebase acaba de comprobar.
// Devuelve el objeto user de la API tanto si el perfil ya existía como si se acaba de crear.
async function cargarPerfil(usuario, accesoGoogle = false) {
  // US29 y US30 recuperan el mismo perfil de US04 mediante el UID del token de Firebase.
  const cabeceras = { Authorization: `Bearer ${await usuario.getIdToken()}` };
  try {
    return (await pedir("/api/profile", { headers: cabeceras })).user;
  } catch (error) {
    // Solo el 404 abre el alta. Un error de permisos o de conexión se devuelve al formulario.
    // Con Google el servidor deduce el nombre del token. Para contraseña se propone el nombre visible o la parte del correo anterior a @.
    if (error.estado !== 404) throw error;
    const nombre = (usuario.displayName || usuario.email.split("@")[0]).replaceAll("@", "").trim();
    return (await pedir("/api/profile", {
      method: "POST",
      headers: { ...cabeceras, "Content-Type": "application/json" },
      body: JSON.stringify(accesoGoogle ? {} : { name: nombre.slice(0, 40) || "Jugador" }),
    })).user;
  }
}

// Al entrar o actualizar el perfil, lee el nombre, avatar, estadísticas, logros e historial del perfil que envía el servidor.
// avatar_selection trae una imagen personal o el identificador del catálogo. Un perfil sin selección usa el primer avatar.
function renderPerfil(perfil) {
  document.querySelector("#jugador").textContent = perfil.name;
  const imagenAvatar = document.querySelector("#avatar-perfil");
  const avatar = perfil.avatar_selection
    || { tipo: "predeterminado", valor: "avatar_1" };
  // Para un PNG personal se prepara una URL de imagen. Para un ID del catálogo se busca su retrato o el avatar predeterminado.
  // Si no se obtiene una URL, se quita la foto anterior para no mostrar la de otro jugador.
  const retrato = avatar.tipo === "personalizado"
    ? retratoPersonalizado(avatar.valor)
    : catalogo.get(avatar.valor)?.retrato || catalogo.get("avatar_1")?.retrato;
  if (retrato) {
    imagenAvatar.src = retrato;
    imagenAvatar.alt = `Avatar de ${perfil.name}`;
    imagenAvatar.hidden = false;
  } else {
    imagenAvatar.removeAttribute("src");
    imagenAvatar.hidden = true;
  }
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
  // Object.entries convierte los indicadores en pares de etiqueta y valor. map crea una tarjeta por par
  // y replaceChildren sustituye las tarjetas anteriores para que una actualización no las duplique.
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
  const logros = perfil.achievements; //Logros en movil
  document.querySelector("#estado-logros").textContent =
    logros.length ? "" : "Aún no hay logros.";
  const elementosLogros = logros.map(logro => {
    const elemento = document.createElement("li");
    elemento.textContent = logro;
    return elemento;
  });
  document.querySelector("#logros").replaceChildren(...elementosLogros);

  const historial = perfil.match_history || [];
  document.querySelector("#estado-historial").textContent = historial.length ? "" : "Aún no tienes partidas registradas.";
  // Reutiliza fila para convertir cada partida en una entrada del historial. Si el servidor omite el rival, muestra solo el resultado.
  document.querySelector("#partidas").replaceChildren(...historial.map(partida => fila(
    partida.opponent ? `${partida.result} · ${partida.opponent}` : partida.result,
    `${partida.score} puntos · ${partida.played_at}`,
  )));
}

// Construye y devuelve un elemento <li> con título y detalle. El historial, el ranking y el marcador deciden dónde insertarlo.
// textContent muestra los nombres como texto incluso cuando contienen caracteres como < o >.
function fila(titulo, detalle) {
  const item = document.createElement("li");
  const nombre = document.createElement("strong");
  const texto = document.createElement("span");
  nombre.textContent = titulo;
  texto.textContent = detalle;
  item.append(nombre, texto);
  return item;
}

// Se usa al abrir la cuenta, al refrescar el ranking y tras una partida. Conserva al jugador que inició la consulta
// para que una respuesta tardía no cambie la pantalla de otra cuenta. Un ranking válido devuelve true aunque esté vacío.
async function cargarRanking() {
  const jugador = jugadorActivo;
  if (!jugador || actualizar.disabled) return false;
  actualizar.disabled = true;
  estadoRanking.textContent = "Cargando ranking…";
  try {
    const { ranking } = await pedir("/api/ranking");
    if (jugadorActivo !== jugador) return;
    // Presenta cada puesto con el nombre del jugador, sus puntos y sus victorias.
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
  // acceso.js llama a este método una vez autenticado el usuario. Espera su perfil antes de mostrar la cuenta
  // y después inicia el ranking, la selección de avatar y la consulta de la sala cada dos segundos.
  async abrirCuenta(user, accesoGoogle) {
    renderPerfil(await cargarPerfil(user, accesoGoogle));
    jugadorActivo = user;
    cuenta.hidden = false;
    cargarRanking();
    // La función que se entrega a cargar comprueba la identidad al recibir el avatar. Así una descarga tardía pertenece a la sesión correcta.
    seleccion.cargar(user, pedir, () => user === jugadorActivo);
    cargarEstadoPartida();
    temporizadorPartida = setInterval(cargarEstadoPartida, 2000);
  },
  // El botón de salir llama a este método antes de cerrar Firebase, mientras el token aún permite liberar la plaza.
  // Devuelve false si la red o el servidor impiden confirmarlo. El formulario usa ese resultado en el mensaje de despedida.
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
      // Busca al usuario por su identificador entre los jugadores conectados o en la lista de espera.
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
  // Después de cerrar Firebase, invalida la referencia al jugador y detiene el temporizador de dos segundos.
  // Las consultas ya enviadas comprueban esa referencia antes de volver a escribir en el perfil o la sala.
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

// Permite recargar el ranking bajo demanda desde la pantalla de la cuenta.
actualizar.addEventListener("click", cargarRanking);

let ultimoResultadoVisto;
let resultadoPendiente = false;
const actualizarPerfil = document.querySelector("#actualizar-perfil");

// El botón del perfil y el cierre de partida vuelven a pedir /api/profile. El token identifica la cuenta y renderPerfil
// intenta actualizar la ficha completa, incluidos los logros. El sondeo del podio usa el resultado booleano para saber si debe reintentar.
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
// Permite pedir la ficha actual desde el móvil, por ejemplo para ver un avatar guardado desde otro dispositivo.
actualizarPerfil.addEventListener("click", actualizarPerfilMovil);

let consultaActual, datosPartida;
let operacionSala = false, cerrandoSesion = false, cambioEnCurso;
let partidaSeguida, resultadoVisible;
const retratosPersonales = new Map();
// El lienzo llama a esta función para elegir qué imagen dibujar. Un avatar del catálogo usa el personaje de cuerpo entero.
// Para uno personalizado se busca en memoria la imagen del participante usando su user_id.
const arena = crearRenderArena(document.querySelector("#arena-movil"), jugador =>
  catalogo.get(jugador.avatar_id)?.personaje || retratosPersonales.get(jugador.user_id));
const musica = prepararMusica(document.querySelector("#musica-movil"));
const nombresEscenarios = JSON.parse(document.querySelector("#nombres-escenarios").textContent);
const seleccion = prepararSeleccion(actualizarBotones);
const editorConfiguracion = prepararConfiguracion({
  // El editor pide el jugador al enviar el formulario para usar la sesión vigente. Tras guardar llama a cargarEstadoPartida(true)
  // para traer la configuración confirmada aunque haya un sondeo anterior pendiente.
  pedir, jugadorActual: () => jugadorActivo, actualizar: () => cargarEstadoPartida(true),
});

// La cuenta, el temporizador y varias acciones vuelven a pedir el estado compartido. Cada petición guarda una marca única (Symbol).
// Una consulta forzada reemplaza esa marca. Solo la respuesta que aún la conserva y corresponde al mismo usuario puede redibujar la partida.
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
    // Si otra sala se abrió entre dos sondeos, resultado_anterior recupera el último podio de ese participante.
    // Se recuerda el match_id mostrado para seguir pidiéndolo hasta que el jugador pulse Volver.
    const final = datos.resultado_anterior || (dentro && game?.status === "finished" ? game : null);
    resultadoVisible = mostrarResultados(final, retratoJugador) ? final : null;
    partidaSeguida = resultadoVisible?.match_id || (dentro ? game?.match_id : null);
    mostrarSala(partida, game, jugador_actual_id, avatares_sala);
    const juegoVisible = document.querySelector("#juego-activo").hidden ? null : game;
    // Extrae el mensaje de cada evento para mostrarlo junto al aviso principal de la partida.
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
      // Se consultan en paralelo el perfil (US28) y el ranking (US27) una vez guardado el resultado.
      // Si una de las dos consultas queda pendiente o falla, el siguiente sondeo permite volver a intentarlo.
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
// El botón permite volver a consultar la partida entre dos actualizaciones automáticas.
document.querySelector("#actualizar-partida").addEventListener("click", () => cargarEstadoPartida());

// El marcador y el podio piden un retrato con el registro de un participante. Primero se busca su avatar_id en el catálogo
// y luego su user_id en las imágenes personales que ya llegaron. Durante la descarga puede no haber imagen.
function retratoJugador(jugador) {
  return catalogo.get(jugador.avatar_id)?.retrato || retratosPersonales.get(jugador.user_id);
}

// En cada actualización de la arena usa el reloj y los puntos recibidos del servidor. Si existe remaining_seconds muestra
// la cuenta atrás. En su ausencia muestra el tiempo transcurrido, y cambia la etiqueta si la partida entra en prórroga.
function mostrarIndicadores(juego, tema, idPropio) {
  document.querySelector("#titulo-arena").textContent = tema || "Arena";
  const restante = juego.remaining_seconds != null;
  const segundos = Math.floor(Math.max(0, (restante ? juego.remaining_seconds : juego.elapsed_seconds) || 0));
  // Da dos dígitos tanto a los minutos como a los segundos para mostrar el reloj como 05:09.
  const reloj = [Math.floor(segundos / 60), segundos % 60].map(n => String(n).padStart(2, "0")).join(":");
  const etiqueta = juego.status === "overtime" ? "Prórroga" : restante ? "Tiempo restante" : "Tiempo transcurrido";
  document.querySelector("#reloj-arena").textContent = etiqueta + " · " + reloj;
  const marcador = document.querySelector("#marcador-partida");
  // Genera una fila por jugador y marca cuál corresponde al usuario de este móvil.
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

// La sala y el podio pueden pedir la misma foto en cada sondeo. La entrada vacía reserva el id antes de descargarla.
// Cuando llega la imagen, reemplaza esa marca. Si la descarga falla se conserva la marca mientras ese jugador siga en la caché.
function cargarRetratoPersonal(id, usuario) {
  if (retratosPersonales.has(id)) return;
  retratosPersonales.set(id, "");
  // Descarga el retrato en segundo plano y actualiza sala, arena y podio si sigue abierta la misma cuenta.
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

// Interpreta el último estado sin enviar peticiones. En la sala busca id_usuario y, durante una partida, user_id y connected.
// Devuelve las señales que la interfaz usa para entrar, jugar o volver a conectar a un participante desconectado.
function participacion() {
  if (!datosPartida) return {};
  const { partida, game, jugador_actual_id } = datosPartida;
  // Busca el mismo identificador en la lista de espera y en la lista de participantes de la partida.
  const enSala = partida.jugadores.some(j => j.id_usuario === jugador_actual_id);
  const participante = game?.players.find(j => j.user_id === jugador_actual_id);
  const dentro = game ? Boolean(participante?.connected) : enSala;
  const enCurso = Boolean(game && game.status !== "finished");
  return { dentro, sala: dentro && !game, jugando: dentro && enCurso,
    reconectar: enCurso && participante?.connected === false, enCurso };
}

// Recalcula los botones al cambiar el estado o la selección. Para entrar en la sala se necesita una elección de avatar o una reconexión disponible.
// El móvil habilita Iniciar con al menos dos jugadores en la sala. El servidor decide finalmente si puede comenzar.
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

// Con una sola respuesta de la API alterna las vistas de selección, espera, juego y resultados, y sincroniza el editor de la sala.
// Descarga los retratos de participantes actuales y libera los que ya salieron. Solo reconstruye la lista de espera si el usuario está en ella.
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
  // Crea una fila por participante y añade «(tú)» al comparar su id con el de esta cuenta.
  // En un retrato personalizado deja el id en el HTML para poder actualizar esa fila cuando termine la descarga.
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
  // Crea una etiqueta y un valor visibles para cada regla de la sala.
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

// Los botones envían join, leave o start. Mientras se tramita una acción se impide otra y se invalida cualquier sondeo anterior.
// Al terminar, incluso ante un error, pide el estado vigente para que los botones reflejen la decisión del servidor.
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
      // Comprueba durante el guardado que el avatar sigue siendo del jugador activo.
      await seleccion.guardar(avatar, headers, pedir, () => jugador === jugadorActivo);
      if (jugador !== jugadorActivo) return;
    }
    // US09 valida la operación. Al salir se incluye la partida que el móvil seguía para que una salida tardía del podio
    // no desconecte al usuario de una partida posterior.
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
  // Guarda la promesa devuelta por el clic. El cierre de sesión la espera para evitar que una entrada termine después de intentar salir.
  boton.addEventListener("click", () => { cambioEnCurso = cambiarSala(accion); });
}

const controlesArena = document.querySelector("#controles-arena");
const avisoMovimiento = document.querySelector("#aviso-movimiento");

// Recibe la dirección de la flecha pulsada y envía una petición autenticada por movimiento aceptado por el control.
// Mientras espera la respuesta ignora otras pulsaciones. Una respuesta de otra sesión tampoco cambia los controles.
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

// Cada botón declara su dirección en data-direction. Al hacer clic, dataset.direction entrega ese texto a moverJugador.
controlesArena.querySelectorAll("[data-direction]").forEach(boton => {
  boton.addEventListener("click", () => moverJugador(boton.dataset.direction));
});

const extraerEnergia = document.querySelector("#extraer-energia");
const cancelarExtraccion = document.querySelector("#cancelar-extraccion");
const avisoReactor = document.querySelector("#aviso-reactor");
let extraccion;

// Extraer y Cancelar llaman a esta función con start o stop. Cada inicio crea un identificador aleatorio que se conserva
// al recibir confirmación para asociar una posible cancelación al mismo jugador y al mismo intento.
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

// Al pulsar Extraer energía, pide iniciar un intento de extracción.
extraerEnergia.addEventListener("click", () => cambiarExtraccion("start"));
// Al pulsar Cancelar, pide detener el intento de extracción guardado.
cancelarExtraccion.addEventListener("click", () => cambiarExtraccion("stop"));

// En cada sondeo convierte el estado del reactor en texto para el jugador. Redondea hacia arriba los segundos pendientes
// y mantiene el aviso de partida inactiva si falta el reactor, el juego terminó o está en pausa.
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

// Al cerrar la cuenta, descarta la consulta pendiente, el intento de extracción, el podio y las imágenes personales.
// Vacía el marcador y devuelve los controles a selección de personaje, listos para el siguiente jugador de este móvil.
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
  // Borra el texto de cada aviso para que el siguiente jugador empiece con los mensajes vacíos.
  document.querySelectorAll("#partida [role=status], #estado-ranking, #estado-historial").forEach(elemento => {
    elemento.textContent = "";
  });
  // Vuelve a habilitar los controles antes de preparar la siguiente sesión.
  document.querySelectorAll("#partida button, #partida fieldset, #actualizar-perfil, #actualizar-ranking").forEach(control => {
    control.disabled = false;
  });
  cancelarExtraccion.disabled = true;
  seleccion.limpiar();
}
