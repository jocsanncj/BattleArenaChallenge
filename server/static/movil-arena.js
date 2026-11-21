// El servidor genera el fondo con el mismo dibujo de Pygame que usa el escritorio.
// Sobre él, US30 coloca únicamente las entidades confirmadas por /api/game/state.
const trampas = {
  jaula: ["J", "#e6b437"],
  arenas_movedizas: ["A", "#a57341"],
  campo_electrico: ["E", "#a05ae6"],
};
const estadosReactor = {
  disponible: ["#3cdce6", "REACTOR DISPONIBLE"],
  ocupado: ["#ffaa3c", "REACTOR OCUPADO"],
  recargando: ["#788296", "RECARGA"],
  sobrecargado: ["#e64141", "REACTOR SOBRECARGADO"],
};

export function crearRenderArena(canvas, urlJugador) {
  const arte = JSON.parse(document.getElementById("arte-arena").textContent);
  const lado = arte.lado;
  const ctx = canvas.getContext("2d");
  const imagenes = new Map();
  let escena;

  function imagen(url) {
    if (!url) return;
    if (!imagenes.has(url)) {
      const sprite = new Image();
      imagenes.set(url, sprite);
      // Puede haber llegado otro estado mientras se descargaba la imagen.
      sprite.onload = repintar;
      sprite.src = url;
    }
    const sprite = imagenes.get(url);
    return sprite.complete && sprite.naturalWidth ? sprite : undefined;
  }

  function aro(x, y, radio, color, grosor) {
    ctx.beginPath();
    ctx.arc(x, y, radio, 0, 2 * Math.PI);
    ctx.strokeStyle = color;
    ctx.lineWidth = grosor;
    ctx.stroke();
  }

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

  function dibujarGuardian(guardian) {
    const sprite = imagen(arte.guardianes[guardian.tipo]);
    if (!sprite) { marca(guardian, "G", "#a74751"); return; }
    const x = guardian.x * lado, y = guardian.y * lado;
    ctx.drawImage(sprite, x + 1, y, lado - 3, lado - 3);
    const ancho = lado - 6;
    ctx.fillStyle = "#474f5d";
    ctx.fillRect(x + 3, y + lado - 5, ancho, 3);
    if (Number.isFinite(guardian.salud) && guardian.salud_maxima > 0) {
      ctx.fillStyle = "#66e29f";
      ctx.fillRect(x + 3, y + lado - 5, ancho * Math.max(0, Math.min(1, guardian.salud / guardian.salud_maxima)), 3);
    } else {
      ctx.fillStyle = "#7e8692";
      for (let i = 1; i < ancho - 1; i += 7) ctx.fillRect(x + 3 + i, y + lado - 4, 2, 2);
    }
  }

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

  function dibujarJugadores(jugadores, idPropio) {
    const etiquetas = [];
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
      if (etiquetas.some(e => Math.abs(e.x - centro) < e.mitad + mitad && Math.abs(e.y - base) < 18)) {
        base = Math.min(canvas.height - 10, y + lado + 10);
      }
      etiquetas.push({ texto, x: centro, y: base, mitad });
    });
    ctx.strokeStyle = "#142333";
    ctx.fillStyle = "#f0f5f7";
    ctx.lineWidth = 3;
    etiquetas.forEach(e => { ctx.strokeText(e.texto, e.x, e.y); ctx.fillText(e.texto, e.x, e.y); });
  }

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
      marca(puerta, "P", puerta.abierta ? "#37cd73" : "#dc4141", true);
    }
    for (const trampa of juego.obstaculos?.trampas || []) {
      if (trampa.activa !== false) marca(trampa, ...(trampas[trampa.tipo] || ["!", "#e65a5a"]));
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
    repintar,
    olvidarImagen(url) { imagenes.delete(url); },
  };
}
