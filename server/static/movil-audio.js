// Conservamos el mismo reproductor al pasar de la arena a la celebración.
// Así, el permiso otorgado por un toque puede servir para ambas pistas.
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

  function mostrarControl() {
    boton.hidden = !escena;
    boton.textContent = pendiente === "error" ? "Reintentar música"
      : activa && !pendiente ? "Silenciar música" : "Activar música";
    boton.setAttribute("aria-pressed", String(activa && !pendiente));
  }

  function pausar() {
    intento++;
    audio.pause();
  }

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

  boton.addEventListener("click", () => {
    activa = !activa || Boolean(pendiente);
    try { localStorage.setItem(clave, activa ? "1" : "0"); } catch { /* Sólo para esta sesión. */ }
    pendiente = "";
    if (activa) reproducir();
    else pausar();
    mostrarControl();
  });

  // En navegadores con reproducción automática bloqueada, el siguiente toque
  // en la partida reintenta dentro del gesto, sin interrumpir la acción elegida.
  boton.closest("#partida").addEventListener("click", evento => {
    if (!boton.contains(evento.target) && pendiente === "gesto") reproducir();
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) pausar();
    else reproducir();
  });
  window.addEventListener("pagehide", () => { paginaActiva = false; pausar(); });
  window.addEventListener("pageshow", () => { paginaActiva = true; reproducir(); });

  mostrarControl();
  return {
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
        // Libera el recurso al volver a la sala, abandonar o cerrar la sesión.
        audio.removeAttribute("src");
        audio.load();
      }
      mostrarControl();
    },
  };
}
