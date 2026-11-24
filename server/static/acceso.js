const erroresFirebase = {
  "auth/popup-closed-by-user": "Acceso con Google cancelado. Puedes volver a intentarlo.",
  "auth/cancelled-popup-request": "Acceso con Google cancelado.",
  "auth/popup-blocked": "Permite las ventanas emergentes y vuelve a pulsar Continuar con Google.",
  "auth/unauthorized-domain": "Este sitio no está autorizado para Google. Usa la dirección habilitada por el equipo.",
  "auth/operation-not-allowed": "Este método de acceso no está habilitado en Firebase.",
  "auth/operation-not-supported-in-this-environment": "Abre el juego en un navegador compatible desde la dirección autorizada.",
  "auth/account-exists-with-different-credential": "Este correo ya tiene una cuenta. Usa su método de acceso original.",
  "auth/email-already-in-use": "Ese correo ya tiene una cuenta. Vuelve a iniciar sesión.",
  "auth/invalid-email": "La dirección de correo no es válida.",
  "auth/invalid-api-key": "La configuración de Firebase del servidor no es válida.",
  "auth/weak-password": "La contraseña es demasiado débil.",
  "auth/user-disabled": "Esta cuenta está deshabilitada.",
  "auth/too-many-requests": "Demasiados intentos. Espera un momento antes de reintentar.",
  "auth/network-request-failed": "No se pudo conectar a Firebase. Revisa tu conexión.",
};
const credencialesInvalidas = new Set(["auth/invalid-credential", "auth/wrong-password", "auth/user-not-found"]);

// El formulario pasa aquí los fallos de acceso. Los códigos de Firebase distinguen una ventana cancelada, un dominio
// sin autorizar o una cuenta bloqueada. Un HTTP 503 del juego tiene su propio aviso para indicar qué servicio falló.
/** @brief US-01–US-05 y US-29–US-30: traduce errores de autenticación en mensajes para la interfaz. */
function mensajeError(error) {
  if (error.estado === 503) return "El servidor del juego todavía no puede verificar la sesión. Contacta al equipo que lo aloja.";
  if (error.code) return erroresFirebase[error.code] || "Firebase no pudo completar la solicitud. Inténtalo de nuevo.";
  if (error instanceof TypeError) return "No se pudo conectar. Revisa tu conexión e inténtalo de nuevo.";
  return error.message || "No se pudo completar la solicitud.";
}

// US30 conecta los formularios de registro y verificación (US01–02), contraseña (US03), recuperación (US05) y Google (US29).
// movil.js entrega pedir para consultar la API y tres funciones para abrir la ficha, liberar la plaza y limpiar la cuenta.
/** @brief US-01–US-05 y US-29–US-30: configura registro, acceso y recuperación en móvil. */
export function iniciarAccesoMovil({ pedir, abrirCuenta, salirDePartida, cerrarCuenta }) {
  // Busca los controles de acceso por el identificador que tienen en el HTML.
  const elemento = id => document.getElementById(id);
  const panel = elemento("autenticacion");
  const estado = elemento("estado-acceso");
  const salir = elemento("salir");
  const reintentar = elemento("reintentar-conexion");
  const config = JSON.parse(elemento("firebase-config").textContent);
  let sdk, auth, carga;
  let vista = "bienvenida";
  let ocupado = false;
  let intentos = 0;
  let nombrePendiente = "";
  // Se ejecuta al empezar o terminar una acción. Mientras ocupado sea true bloquea todos los botones de acceso y el de salir.
  // Cuando queda libre el panel, los botones data-remoto siguen esperando a que auth esté listo.
  /** @brief US-01–US-05 y US-29–US-30: habilita controles según la conexión y acción pendiente. */
  function controles() {
    for (const boton of panel.querySelectorAll("button")) {
      boton.disabled = ocupado || (boton.hasAttribute("data-remoto") && !auth);
    }
    salir.disabled = ocupado;
  }
  // Al abrir un formulario o reintentar, descarga los módulos de Firebase. carga guarda la promesa compartida
  // para evitar otra descarga si se cambia de pantalla mientras llega la primera. Al terminar vuelve a evaluar los controles.
  /** @brief US-01–US-05 y US-29–US-30: carga Firebase Auth de forma diferida. */
  async function conectar() {
    if (!config.apiKey) {
      estado.textContent = "El servidor todavía no tiene configurado el acceso de Firebase.";
      return;
    }
    if (auth || carga) return;
    estado.textContent = "Conectando con Firebase…";
    reintentar.hidden = true;
    try {
      carga = Promise.all([
        import("https://www.gstatic.com/firebasejs/13.3.0/firebase-app.js"),
        import("https://www.gstatic.com/firebasejs/13.3.0/firebase-auth.js"),
      ]);
      const [appSdk, authSdk] = await carga;
      sdk = authSdk;
      auth = sdk.initializeAuth(appSdk.initializeApp(config), {
        // La sesión dura mientras la página siga abierta. Al recargar, el jugador vuelve a identificarse.
        persistence: sdk.inMemoryPersistence,
        popupRedirectResolver: sdk.browserPopupRedirectResolver,
      });
      if (estado.textContent === "Conectando con Firebase…") estado.textContent = "";
    } catch {
      if (vista !== "bienvenida") {
        estado.textContent = "No se pudo cargar Firebase. Revisa tu conexión y vuelve a intentarlo.";
        reintentar.hidden = false;
      }
    } finally {
      carga = undefined;
      controles();
    }
  }
  // Recibe el id de la sección de destino y un mensaje opcional. Oculta las demás secciones y mueve el foco al título
  // para que el teclado y el lector de pantalla sigan la navegación. Solo los formularios que usan Firebase inician la conexión.
  /** @brief US-01–US-05 y US-29–US-30: muestra una pantalla de acceso y gestiona su foco. */
  function mostrar(destino, mensaje = "") {
    vista = destino;
    for (const seccion of panel.querySelectorAll("section")) seccion.hidden = seccion.id !== destino;
    estado.textContent = mensaje;
    reintentar.hidden = true;
    elemento(destino).querySelector("h2").focus();
    if (["acceso", "registro", "recuperacion"].includes(destino) && !auth) conectar();
  }
  // Recibe una función, la ejecuta una sola vez mientras los botones están bloqueados y espera su resultado con await.
  // Si falla, escribe en el panel visible. finally vuelve a habilitar los controles tanto en caso de éxito como de error.
  /** @brief US-01–US-05 y US-29–US-30: ejecuta una acción de formulario sin duplicar envíos. */
  async function ejecutar(accion) {
    if (ocupado) return;
    ocupado = true;
    controles();
    const aviso = panel.hidden ? elemento("estado-cuenta") : estado;
    aviso.textContent = "";
    try {
      await accion();
    } catch (error) {
      aviso.textContent = mensajeError(error);
    } finally {
      ocupado = false;
      controles();
    }
  }
  for (const boton of panel.querySelectorAll("[data-vista]")) {
    // Cada botón lee el destino de su atributo data-vista. Al abrir recuperación copia el identificador que ya se escribió.
    // Abandonar la verificación cierra la sesión provisional y borra el nombre pendiente antes de mostrar otro formulario.
    boton.addEventListener("click", () => ejecutar(async () => {
      if (vista === "verificacion") {
        if (auth.currentUser) await sdk.signOut(auth);
        nombrePendiente = "";
        elemento("elegir-nombre").hidden = true;
      }
      if (boton.dataset.vista === "recuperacion") elemento("cuenta-recuperacion").value = elemento("identificador").value;
      elemento("contrasena").value = "";
      elemento("form-registro").reset();
      mostrar(boton.dataset.vista);
    }));
  }
  // El botón de reintento vuelve a cargar la conexión con Firebase tras un fallo.
  reintentar.addEventListener("click", conectar);
  // Al preparar la página, asocia cada id de formulario con la función que procesa sus datos. La misma conexión sirve
  // tanto al botón de enviar como a la tecla Intro, ya que ambos generan el evento submit.
  /** @brief US-01–US-05 y US-29–US-30: conecta el envío de un formulario con su caso de uso. */
  function alEnviar(id, accion) {
    // Intercepta el envío para procesarlo en esta página sin recargar el navegador.
    elemento(id).addEventListener("submit", evento => {
      evento.preventDefault();
      if (auth) ejecutar(accion);
    });
  }
  // Login y recuperación aceptan usuario o correo. Para un nombre consulta /api/correo y URLSearchParams lo codifica para la URL.
  // El formulario que llamó a la función decide qué mostrar si la búsqueda no trae correo.
  /** @brief US-03 y US-30: convierte nombre de usuario o correo en la dirección para autenticación. */
  async function resolverCorreo(identificador) {
    const valor = identificador.trim();
    if (!valor) throw new Error("Escribe tu usuario o correo electrónico.");
    if (valor.includes("@")) return valor;
    return (await pedir("/api/correo?" + new URLSearchParams({ nombre: valor }))).correo;
  }
  // El formulario de contraseña llama a esta función tras un identificador desconocido o credenciales rechazadas.
  // Al tercer fallo reinicia el contador y pasa el identificador a recuperación para que el jugador no tenga que repetirlo.
  /** @brief US-03 y US-30: cuenta fallos de acceso y ofrece recuperación tras tres intentos. */
  function credencialesRechazadas() {
    intentos++;
    if (intentos < 3) {
      estado.textContent = `Usuario/correo o contraseña incorrectos. Intento ${intentos}/3.`;
      return;
    }
    intentos = 0;
    elemento("cuenta-recuperacion").value = elemento("identificador").value;
    mostrar("recuperacion", "Fallaste tres veces. Puedes solicitar un enlace para recuperar tu contraseña.");
  }
  // Recibe el usuario devuelto por Firebase y, para Google, la señal que permite crear un perfil en el primer ingreso.
  /** @brief US-04, US-29 y US-30: abre el perfil del jugador tras autenticarlo. */
  async function entrarAlJuego(usuario, google = false) {
    // abrirCuenta en movil.js recupera o crea el perfil del juego (US04). Solo al completar ese paso
    // se oculta el formulario, se reinicia el contador de fallos y se muestra la opción de cerrar sesión.
    try {
      await abrirCuenta(usuario, google);
    } catch (error) {
      // Si la API del juego rechaza el perfil, cerramos también la sesión que Firebase acaba de abrir.
      await sdk.signOut(auth);
      throw error;
    }
    intentos = 0;
    elemento("formulario").reset();
    panel.hidden = true;
    estado.textContent = "";
    salir.hidden = false;
    salir.focus();
  }
  // Al enviar usuario o correo, Firebase comprueba la contraseña. Un correo pendiente lleva a verificación para poder reenviar el enlace.
  // Un usuario verificado pasa a su perfil. La contraseña se borra en todos los casos al terminar.
  alEnviar("formulario", async () => {
    estado.textContent = "Iniciando sesión…";
    try {
      const correo = await resolverCorreo(elemento("identificador").value);
      if (!correo) return credencialesRechazadas();
      const { user } = await sdk.signInWithEmailAndPassword(auth, correo, elemento("contrasena").value);
      if (!user.emailVerified) {
        mostrar("verificacion", "Tu correo todavía no está verificado. Abre el enlace de verificación o solicita otro.");
        return;
      }
      await entrarAlJuego(user);
    } catch (error) {
      if (credencialesInvalidas.has(error.code)) credencialesRechazadas();
      else throw error;
    } finally {
      elemento("contrasena").value = "";
    }
  });
  // El clic abre el selector de cuentas de Google desde el navegador. Con correo verificado, user pasa a entrarAlJuego junto con true
  // para que el servidor pueda dar de alta el perfil en el primer acceso. Si falta verificación se cierra la sesión provisional.
  elemento("google").addEventListener("click", () => ejecutar(async () => {
    const proveedor = new sdk.GoogleAuthProvider();
    proveedor.setCustomParameters({ prompt: "select_account" });
    estado.textContent = "Continúa con Google en la ventana de acceso.";
    const { user } = await sdk.signInWithPopup(auth, proveedor);
    if (!user.emailVerified) {
      await sdk.signOut(auth);
      throw new Error("Google no confirmó un correo verificado.");
    }
    await entrarAlJuego(user, true);
  }));
  // Registro y reintentos de alta validan el nombre antes de enviarlo. Array.from cuenta puntos de código de Unicode
  // y el signo @ se reserva para distinguir los correos de los nombres de jugador en el formulario de acceso.
  /** @brief US-01 y US-30: valida el nombre de usuario antes de crear el perfil. */
  function validarNombre(nombre) {
    if (!nombre || nombre.includes("@") || Array.from(nombre).length > 40) {
      throw new Error("Elige un nombre de 1 a 40 caracteres sin @.");
    }
  }
  // Sirve al primer registro y al reenvío. Con un nombre pendiente, actualiza el nombre visible en Firebase y guarda el perfil
  // en el juego con el token del mismo usuario. Solo tras un guardado correcto pide enviar el enlace de verificación.
  /** @brief US-02 y US-30: guarda el perfil pendiente y solicita el correo de verificación. */
  async function enviarVerificacion() {
    const usuario = auth.currentUser;
    if (!usuario) throw new Error("Vuelve a iniciar sesión para reenviar el enlace.");
    if (nombrePendiente) {
      // Firebase ya creó la cuenta. Si falló el alta del perfil en el servidor,
      // el reintento conserva esa identidad y permite corregir un nombre ocupado.
      const nombre = elemento("elegir-nombre").hidden ? nombrePendiente : elemento("nombre-pendiente").value.trim();
      validarNombre(nombre);
      nombrePendiente = nombre;
      try {
        await sdk.updateProfile(usuario, { displayName: nombrePendiente });
        await pedir("/api/profile", {
          method: "POST",
          headers: { Authorization: `Bearer ${await usuario.getIdToken()}`, "Content-Type": "application/json" },
          body: JSON.stringify({ name: nombrePendiente }),
        });
      } catch (error) {
        if (error.estado === 409) {
          elemento("elegir-nombre").hidden = false;
          elemento("nombre-pendiente").value = nombrePendiente;
        }
        throw error;
      }
      nombrePendiente = "";
      elemento("elegir-nombre").hidden = true;
    }
    await sdk.sendEmailVerification(usuario);
    estado.textContent = "Enlace enviado. Revisa tu correo y la carpeta de spam. Una vez verificado, vuelve a iniciar sesión.";
  }
  // Antes de crear la cuenta, comprueba el nombre, las reglas de contraseña, su confirmación y la disponibilidad del nombre en la API.
  // Una vez que Firebase acepta el correo, conserva el nombre propuesto para guardar el perfil y enviar la verificación.
  alEnviar("form-registro", async () => {
    const nombre = elemento("nombre-registro").value.trim();
    const correo = elemento("correo-registro").value.trim();
    const clave = elemento("clave-registro").value;
    validarNombre(nombre);
    if (Array.from(clave).length < 8 || !/\p{L}/u.test(clave) || !/\p{Nd}/u.test(clave)) {
      throw new Error("La contraseña debe tener al menos 8 caracteres, con letras y números.");
    }
    if (clave !== elemento("confirmacion").value) throw new Error("Las contraseñas no coinciden.");
    const disponibilidad = await pedir("/api/disponible?" + new URLSearchParams({ nombre }));
    if (!disponibilidad.disponible) throw new Error("Ese nombre de usuario ya está en uso.");
    await sdk.createUserWithEmailAndPassword(auth, correo, clave);
    elemento("form-registro").reset();
    elemento("identificador").value = correo;
    nombrePendiente = nombre;
    mostrar("verificacion", "Cuenta creada. Preparando el enlace de verificación…");
    await enviarVerificacion();
  });
  // Permite reenviar la verificación o completar el nombre pendiente desde la misma cuenta.
  alEnviar("form-verificacion", enviarVerificacion);
  // Busca el correo y pide a Firebase el enlace de restablecimiento si lo encuentra. Una cuenta ausente recibe la misma pantalla
  // de confirmación para que el formulario no revele qué cuentas existen. Los demás fallos vuelven al panel de errores.
  alEnviar("form-recuperacion", async () => {
    const correo = await resolverCorreo(elemento("cuenta-recuperacion").value);
    if (correo) {
      try {
        await sdk.sendPasswordResetEmail(auth, correo);
      } catch (error) {
        if (error.code !== "auth/user-not-found") throw error;
      }
    }
    mostrar("recuperacion-enviada");
  });
  // Primero intenta liberar la plaza mientras la cuenta aún tiene un token válido. Luego cierra Firebase, borra los datos locales
  // y regresa a la bienvenida. Si no pudo confirmar la salida de la sala, la despedida lo indica al jugador.
  salir.addEventListener("click", () => ejecutar(async () => {
    const salaLiberada = await salirDePartida();
    await sdk.signOut(auth);
    cerrarCuenta();
    intentos = 0;
    elemento("formulario").reset();
    elemento("form-recuperacion").reset();
    elemento("estado-cuenta").textContent = "";
    panel.hidden = false;
    salir.hidden = true;
    mostrar("bienvenida", salaLiberada ? "Sesión cerrada." : "Sesión cerrada. No se pudo confirmar la salida de la sala.");
  }));
  controles();
}
