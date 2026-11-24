// El servidor genera el fondo con el mismo dibujo de Pygame que usa el escritorio.
// Sobre él, US30 coloca únicamente las entidades confirmadas por /api/game/state.
const estadosReactor = {
  disponible: ["#3cdce6", "REACTOR DISPONIBLE"],
  ocupado: ["#ffaa3c", "REACTOR OCUPADO"],
  recargando: ["#788296", "RECARGA"],
  sobrecargado: ["#e64141", "REACTOR SOBRECARGADO"],
};

// movil.js llama a esta función al abrir la página. canvas es la superficie de dibujo y urlJugador
// es la función que busca la imagen de cada personaje. El catálogo de Flask indica cuántos píxeles
// ocupa cada casilla. El objeto devuelto permite dibujar un estado nuevo o repintar el último.
/** @brief US-07, US-20–US-23 y US-30: crea el renderizador móvil del estado de arena. */
export function crearRenderArena(canvas, urlJugador) {
  const arte = JSON.parse(document.getElementById("arte-arena").textContent);
  const lado = arte.lado;
  const ctx = canvas.getContext("2d");
  const imagenes = new Map();
  let escena;

  // Busca la URL en imagenes, un Map que conserva un objeto Image por dirección. La primera llamada
  // inicia la descarga. Devuelve la imagen solo cuando tiene anchura y ha terminado de cargar.
  /** @brief US-06 y US-30: carga y reutiliza imágenes de arena y jugadores. */
  function imagen(url) {
    if (!url) return;
    if (!imagenes.has(url)) {
      const sprite = new Image();
      imagenes.set(url, sprite);
      // onload llama a repintar con la escena más reciente, aunque el jugador se haya movido durante la descarga.
      sprite.onload = repintar;
      sprite.src = url;
    }
    const sprite = imagenes.get(url);
    return sprite.complete && sprite.naturalWidth ? sprite : undefined;
  }
  // Dibuja un borde circular en coordenadas de píxeles. El color y el grosor distinguen al jugador
  // local, los estados temporales y el reactor sin tapar la figura que está debajo.
  /** @brief US-07 y US-30: dibuja un indicador circular sobre una casilla. */
  function aro(x, y, radio, color, grosor) {
    ctx.beginPath();
    ctx.arc(x, y, radio, 0, 2 * Math.PI);
    ctx.strokeStyle = color;
    ctx.lineWidth = grosor;
    ctx.stroke();
  }
  // Toma la fila y la columna de la entidad. Sumar media casilla sitúa el texto en el centro.
  // Las puertas usan un cuadrado y la energía usa un círculo con su símbolo.
  /** @brief US-18–US-22 y US-30: dibuja un marcador temporal en una entidad del tablero. */
  function marca(entidad, texto, color, cuadrada = false) {
    const x = (entidad.x + .5) * lado, y = (entidad.y + .5) * lado;
    const radio = lado / 2 - 3;
    ctx.beginPath();
    if (cuadrada) ctx.rect(x - radio, y - radio, radio * 2, radio * 2);
    else ctx.arc(x, y, radio, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    if (cuadrada || texto === "+") {
      ctx.strokeStyle = "#fff6dc";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    ctx.fillStyle = texto === "+" ? "#6e4b0f" : "white";
    ctx.fillText(texto, x, y);
  }
  // Lee el tipo y la posición del guardián recibidos del servidor para elegir la figura y su casilla.
  /** @brief US-21 y US-30: dibuja un guardián usando el recurso del servidor. */
  function dibujarGuardian(guardian) {
    const sprite = imagen(arte.guardianes[guardian.tipo]);
    if (!sprite) { marca(guardian, "G", "#a74751"); return; }
    const x = guardian.x * lado, y = guardian.y * lado;
    ctx.drawImage(sprite, x + 1, y, lado - 3, lado - 3);
  }
  // El catálogo del mapa fija el centro del reactor. juego.reactor determina el color y la etiqueta,
  // y remaining_seconds da el tiempo de recarga. El tiempo de partida solo orienta los arcos
  // de luz en el dibujo. La disponibilidad para extraer energía la decide el servidor.
  /** @brief US-18–US-19 y US-30: dibuja el reactor y su disponibilidad actual. */
  function dibujarReactor(mapaArte, tema, juego) {
    const [columna, fila] = mapaArte.centro;
    const x = (columna + .5) * lado, y = (fila + .5) * lado;
    const reactor = juego.reactor || {};
    const [color, nombre] = estadosReactor[reactor.status] || estadosReactor.disponible;
    aro(x, y, lado * 1.4, color, 3);
    const giro = (juego.elapsed_seconds || 0) * .7;
    for (let i = 0; i < 8; i++) {
      const angulo = giro + i * Math.PI / 4;
      ctx.beginPath();
      ctx.arc(x, y, Math.floor(lado * 1.34) - 5, -angulo - .48, -angulo);
      ctx.strokeStyle = arte.coloresLuz[tema];
      ctx.lineWidth = 3;
      ctx.stroke();
    }
    const etiqueta = reactor.status === "recargando"
      ? nombre + " " + (reactor.remaining_seconds ?? 0).toFixed(1) + " s" : nombre;
    ctx.font = "bold 15px system-ui, sans-serif";
    const base = y + lado * 1.5 + 10;
    ctx.strokeStyle = "#132333";
    ctx.lineWidth = 3;
    ctx.strokeText(etiqueta, x, base);
    ctx.fillStyle = "#f0f5f7";
    ctx.fillText(etiqueta, x, base);
  }
  // Recibe la lista de jugadores que envía la API e idPropio, el identificador de quien usa el móvil.
  // Primero pinta las figuras y guarda la posición de los nombres. Dibuja el texto al final
  // para que los personajes vecinos no lo tapen.
  /** @brief US-06, US-10–US-11 y US-30: dibuja participantes y estados confirmados. */
  function dibujarJugadores(jugadores, idPropio) {
    const etiquetas = [];
    // forEach pasa cada jugador y su índice. El índice permite mostrar un número mientras carga
    // su imagen. Los aros indican si está inmovilizado o congelado y cuál es el jugador local.
    jugadores.forEach((jugador, i) => {
      if (jugador.connected === false) return;
      const x = jugador.x * lado, y = jugador.y * lado;
      const sprite = imagen(urlJugador(jugador));
      if (sprite) ctx.drawImage(sprite, x + 1, y + 1, lado - 2, lado - 2);
      else marca(jugador, String(i + 1), "#328db2");
      const cx = x + lado / 2, cy = y + lado / 2;
      if (jugador.estado_temporal === "congelado" || jugador.estado_temporal === "inmovilizado") {
        aro(cx, cy, lado / 2 - 2, jugador.estado_temporal === "congelado" ? "#5abeff" : "#ff914b", 3);
      }
      if (jugador.user_id === idPropio) aro(cx, cy, lado / 2, "#5aa0ff", 2);
      // La lista inferior conserva el nombre completo. En casillas contiguas separamos las etiquetas.
      const nombre = jugador.username || "";
      const texto = nombre.length > 12 ? nombre.slice(0, 11) + "…" : nombre;
      const mitad = ctx.measureText(texto).width / 2 + 2;
      const centro = Math.max(mitad, Math.min(canvas.width - mitad, cx));
      let base = Math.max(10, y - 10);
      // some devuelve true con la primera etiqueta que ocuparía el mismo espacio. En ese caso
      // se intenta colocar el nombre debajo del personaje.
      if (etiquetas.some(e => Math.abs(e.x - centro) < e.mitad + mitad && Math.abs(e.y - base) < 18)) {
        base = Math.min(canvas.height - 10, y + lado + 10);
      }
      etiquetas.push({ texto, x: centro, y: base, mitad });
    });
    ctx.strokeStyle = "#142333";
    ctx.fillStyle = "#f0f5f7";
    ctx.lineWidth = 3;
    // Dibuja el contorno y luego el texto de cada nombre en la posición reservada.
    etiquetas.forEach(e => { ctx.strokeText(e.texto, e.x, e.y); ctx.fillText(e.texto, e.x, e.y); });
  }
  // Redibuja el último estado recibido, tanto al cambiar el juego como al terminar de cargar una imagen.
  // Coloca el fondo y luego los objetos, guardianes, reactor y jugadores en ese orden.
  /** @brief US-07, US-20–US-23 y US-30: vuelve a dibujar todos los elementos de la arena. */
  function repintar() {
    if (!ctx || !escena) return;
    const { mapa, juego, mapaArte, tema, idPropio } = escena;
    const fondo = imagen(mapaArte.tableros[tema]);
    if (fondo) {
      ctx.drawImage(fondo, 0, 0, canvas.width, canvas.height);
    } else {
      const colores = { "#": "#25536f", X: "#5499b1", R: "#294f60" };
      ctx.fillStyle = "#13283a";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      // El primer forEach recorre las filas del plano. El segundo recorre los símbolos de una fila
      // y colorea las casillas reconocidas hasta que el PNG esté listo.
      mapa.plano.forEach((fila, y) => Array.from(fila).forEach((tipo, x) => {
        if (colores[tipo]) {
          ctx.fillStyle = colores[tipo];
          ctx.fillRect(x * lado, y * lado, lado - 1, lado - 1);
        }
      }));
    }
    ctx.font = "bold 17px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const puerta of juego.obstaculos?.puertas || []) {
      const sprite = imagen(arte.puertas[puerta.abierta ? "abierta" : "cerrada"]);
      if (sprite) ctx.drawImage(sprite, puerta.x * lado + 1, puerta.y * lado + 1, lado - 2, lado - 2);
      else marca(puerta, "", puerta.abierta ? "#37cd73" : "#dc4141", true);
    }
    for (const trampa of juego.obstaculos?.trampas || []) {
      if (trampa.activa === false) continue;
      const sprite = imagen(arte.trampas[trampa.tipo] || arte.trampas.jaula);
      if (sprite) ctx.drawImage(sprite, trampa.x * lado + 1, trampa.y * lado + 1, lado - 2, lado - 2);
      else marca(trampa, "", "#c7873d");
    }
    if (juego.energia_adicional) marca(juego.energia_adicional, "+", "#ffdc46");
    for (const guardian of juego.guardianes || []) dibujarGuardian(guardian);
    dibujarReactor(mapaArte, tema, juego);
    ctx.strokeStyle = "#ffdc50";
    ctx.lineWidth = 3;
    ctx.strokeRect(lado + 1.5, lado + 1.5, canvas.width - 2 * lado - 3, canvas.height - 2 * lado - 3);
    ctx.font = "bold 16px system-ui, sans-serif";
    dibujarJugadores(juego.players || [], idPropio);
  }
  return {
    // Cada actualización entrega el plano, el estado del juego, las reglas de la sala y el ID local.
    // Sin juego o sin mapa oculta el lienzo. Con rotación cambia la paleta según los periodos
    // transcurridos, conserva el plano elegido y devuelve el nombre del tema para el indicador.
    /** @brief US-07, US-23 y US-30: guarda y dibuja el mapa y estado actual de la partida. */
    dibujar(mapa, juego, configuracion = {}, idPropio) {
      if (!mapa || !juego) {
        escena = null;
        canvas.hidden = true;
        return;
      }
      const indice = arte.escenarios[configuracion.escenario] ? configuracion.escenario : 0;
      const periodo = configuracion.rotacion ? Math.floor(Math.max(0, juego.elapsed_seconds || 0) / arte.periodo) : 0;
      const tema = (indice + periodo) % arte.coloresLuz.length;
      escena = { mapa, juego, mapaArte: arte.escenarios[indice], tema, idPropio };
      if (canvas.width !== mapa.columnas * lado) canvas.width = mapa.columnas * lado;
      if (canvas.height !== mapa.filas * lado) canvas.height = mapa.filas * lado;
      canvas.hidden = false;
      repintar();
      return arte.escenarios[tema].nombre;
    },
    /** @brief US-30: redibuja el último estado al terminar de cargar un recurso gráfico. */
    repintar,
    // Al retirar el retrato de un participante o salir de la cuenta, elimina esa URL de la caché
    // de este lienzo. Una petición posterior de la misma imagen podrá cargarla de nuevo.
    /** @brief US-06 y US-30: elimina de la caché una imagen que ya no se usa. */
    olvidarImagen(url) { imagenes.delete(url); },
  };
}
