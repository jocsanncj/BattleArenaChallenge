// Conservamos el mismo reproductor al pasar de la arena a la celebración.
// Así, el permiso otorgado por un toque puede servir para ambas pistas.
// Al abrir la página, movil.js entrega el botón que contiene las URL de ambas pistas. Esta función
// lee la preferencia de sonido de este navegador y devuelve sincronizar para seguir la escena del juego.
/** @brief US-24 y US-30: configura reproducción accesible para arena y ceremonia móvil. */
export function prepararMusica(boton) {
  const audio = new Audio();
  audio.preload = "none";
  audio.loop = true;
  const clave = "battle-arena.musica";
  let activa = true;
  try { activa = localStorage.getItem(clave) !== "0"; } catch { /* Sólo para esta sesión. */ }
  let escena = null;
  let pendiente = "";
  let intento = 0;
  let paginaActiva = true;
  // Usa la escena, la preferencia y el último intento para elegir el texto del botón. aria-pressed
  // informa a los lectores de pantalla de si está activada la música sin ningún reintento pendiente.
  /** @brief US-24 y US-30: actualiza el botón según escena, preferencia y reproducción. */
  function mostrarControl() {
    boton.hidden = !escena;
    boton.textContent = pendiente === "error" ? "Reintentar música"
      : activa && !pendiente ? "Silenciar música" : "Activar música";
    boton.setAttribute("aria-pressed", String(activa && !pendiente));
  }
  // Pausa el reproductor y avanza el número de intento. Un play() anterior puede fallar más tarde
  // y su número ya no coincidirá, por lo que el error no cambiará el control de la escena actual.
  /** @brief US-24 y US-30: pausa la pista e invalida intentos de reproducción anteriores. */
  function pausar() {
    intento++;
    audio.pause();
  }
  // Pide al navegador que reproduzca la pista si la página está visible, hay escena y el usuario quiere sonido.
  // await espera la respuesta de play(). NotAllowedError deja pendiente un toque del jugador.
  // Los demás errores dejan disponible el botón de reintento.
  /** @brief US-24 y US-30: reproduce la pista activa respetando la preferencia del usuario. */
  async function reproducir() {
    if (!escena || !activa || !paginaActiva || document.hidden) return;
    const actual = ++intento;
    try {
      if (audio.error) audio.load();
      pendiente = "";
      mostrarControl();
      await audio.play();
    } catch (error) {
      if (actual !== intento) return;
      pendiente = error.name === "NotAllowedError" ? "gesto" : "error";
      mostrarControl();
    }
  }
  // Un toque silencia la pista activa o vuelve a intentar la que falló. localStorage conserva
  // la elección para otra visita. Si no está disponible, activa la mantiene durante esta visita.
  boton.addEventListener("click", () => {
    activa = !activa || Boolean(pendiente);
    try { localStorage.setItem(clave, activa ? "1" : "0"); } catch { /* Sólo para esta sesión. */ }
    pendiente = "";
    if (activa) reproducir();
    else pausar();
    mostrarControl();
  });
  // Si el navegador pide un gesto, un toque en otro control del juego también sirve para reintentar.
  // El evento llega al contenedor #partida después de llegar al control pulsado.
  boton.closest("#partida").addEventListener("click", evento => {
    if (!boton.contains(evento.target) && pendiente === "gesto") reproducir();
  });
  // visibilitychange se dispara al ocultar o volver a mostrar la pestaña. Pausa al ocultarse
  // y al volver comprueba otra vez la escena y la preferencia de sonido.
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) pausar();
    else reproducir();
  });
  // pagehide marca la página como inactiva para que una consulta tardía del juego no reinicie el audio.
  window.addEventListener("pagehide", () => { paginaActiva = false; pausar(); });
  // pageshow vuelve a habilitar los intentos, incluso cuando el navegador restaura la página desde el historial.
  window.addEventListener("pageshow", () => { paginaActiva = true; reproducir(); });
  mostrarControl();
  return {
    // El sondeo de la partida pasa «arena», «resultados» o null. Si la escena se repite deja seguir
    // la pista. Si cambia, lee la URL del atributo data-arena o data-resultados del botón.
    sincronizar(nuevaEscena) {
      if (nuevaEscena === escena) return;
      pausar();
      escena = nuevaEscena;
      pendiente = "";
      if (escena) {
        audio.volume = escena === "arena" ? 0.42 : 0.40;
        audio.src = boton.dataset[escena];
        reproducir();
      } else {
        // Con la escena vacía, quitar src y llamar a load() libera la pista anterior al volver a la sala o cerrar sesión.
        audio.removeAttribute("src");
        audio.load();
      }
      mostrarControl();
    },
  };
}
