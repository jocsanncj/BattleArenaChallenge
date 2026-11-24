// Las rutas y los nombres del catálogo vienen del servidor que también usa Pygame.
const radios = [...document.querySelectorAll('input[name="avatar"]')];
// filter selecciona los botones con imagen de personaje. map forma pares de ID y datos para
// construir el catálogo. El mismo ID permite buscar el retrato del perfil y la figura de la arena.
export const catalogo = new Map(radios.filter(radio => radio.dataset.personaje).map(radio => [
  radio.value, { nombre: radio.dataset.nombre, retrato: radio.parentElement.querySelector("img").src, personaje: radio.dataset.personaje },
]));

// Recibe el texto base64 de una imagen personal. Comprueba el prefijo habitual de un PNG y el límite
// de caracteres. Devuelve una dirección que img.src puede mostrar directamente, o una cadena vacía.
/** @brief US-06 y US-30: convierte una imagen PNG válida en una URL de retrato. */
export function retratoPersonalizado(valor) {
  return typeof valor === "string" && valor.startsWith("iVBORw0KGgo") && valor.length <= 2_000_000
    ? "data:image/png;base64," + valor : "";
}

// El selector de archivos entrega un File local. Se aceptan PNG, JPEG y WebP de hasta 10 MB.
// decode() espera a que el navegador pueda leer sus píxeles. El resultado es un PNG en base64
// preparado para enviar a la API cuando el jugador confirme su elección.
/** @brief US-06 y US-30: valida, recorta y codifica la imagen de avatar elegida. */
async function convertirImagen(archivo) {
  if (archivo.size > 10 * 1024 * 1024 || !["image/png", "image/jpeg", "image/webp"].includes(archivo.type)) {
    throw new Error("Elige una imagen PNG, JPG o WebP de hasta 10 MB.");
  }
  const url = URL.createObjectURL(archivo);
  try {
    const imagen = new Image();
    imagen.src = url;
    await imagen.decode();
    // Recorta un cuadrado centrado y lo escala a 128 × 128, el formato compartido con el escritorio.
    // toDataURL incluye una cabecera. La parte que sigue a la coma contiene los datos que guarda la API.
    const lado = Math.min(imagen.naturalWidth, imagen.naturalHeight);
    const lienzo = document.createElement("canvas");
    lienzo.width = lienzo.height = 128;
    lienzo.getContext("2d").drawImage(imagen, (imagen.naturalWidth - lado) / 2,
      (imagen.naturalHeight - lado) / 2, lado, lado, 0, 0, 128, 128);
    return lienzo.toDataURL("image/png").split(",")[1];
  } finally {
    URL.revokeObjectURL(url);
  }
}

// Prepara la vista previa y devuelve los métodos que movil.js usa para leer, guardar o limpiar la selección.
// cambio es la función que actualiza los botones de la sala cuando el jugador elige otro avatar.
/** @brief US-06 y US-30: configura selección, carga, guardado y limpieza del avatar móvil. */
export function prepararSeleccion(cambio) {
  const personalizado = document.querySelector("#opcion-personalizada");
  const archivo = document.querySelector("#archivo-avatar");
  const aviso = document.querySelector("#aviso-avatar");
  const vista = document.querySelector("#retrato-seleccionado");
  let imagenPersonal, guardado, revision = 0, leyendo = false;
  // find devuelve la opción marcada. Para una figura del catálogo se muestra su retrato. Para una foto
  // personal se usa la copia preparada en memoria. Después se notifica el cambio a los botones de la sala.
  /** @brief US-06 y US-30: sincroniza la vista previa con la opción seleccionada. */
  function actualizarVista() {
    const opcion = radios.find(radio => radio.checked);
    const retrato = catalogo.get(opcion?.value)?.retrato || retratoPersonalizado(imagenPersonal);
    if (retrato) vista.src = retrato;
    else vista.removeAttribute("src");
    vista.hidden = !retrato;
    document.querySelector("#nombre-seleccionado").textContent = opcion?.dataset.nombre || "—";
    cambio();
  }
  // Recibe el base64 guardado en la cuenta o generado por el selector. Conserva el valor en memoria
  // y solo muestra la opción «Personalizado» cuando se puede construir su dirección de imagen.
  /** @brief US-06 y US-30: guarda y presenta el avatar personalizado en memoria. */
  function mostrarPersonal(valor) {
    imagenPersonal = valor;
    const retrato = retratoPersonalizado(valor);
    personalizado.hidden = !retrato;
    const img = personalizado.querySelector("img");
    if (retrato) img.src = retrato;
    else img.removeAttribute("src");
  }
  // Al marcar una opción, revision avanza. Una conversión de archivo que empezó antes podrá terminar,
  // pero su resultado ya no sustituirá a la elección que el jugador acaba de hacer.
  for (const radio of radios) radio.addEventListener("change", () => {
    revision++;
    leyendo = false;
    aviso.textContent = "";
    actualizarVista();
  });
  // Al elegir un archivo se guarda el número de esta revisión y se avisa de que la imagen se está preparando.
  // Solo la revisión vigente puede marcar el avatar, mostrar el error o habilitar de nuevo la selección.
  archivo.addEventListener("change", async () => {
    const elegido = archivo.files[0];
    archivo.value = "";
    if (!elegido) return;
    const intento = ++revision;
    leyendo = true;
    aviso.textContent = "Preparando la imagen…";
    cambio();
    try {
      const valor = await convertirImagen(elegido);
      if (revision !== intento) return;
      mostrarPersonal(valor);
      personalizado.querySelector("input").checked = true;
      aviso.textContent = "";
    } catch (error) {
      if (revision === intento) aviso.textContent = error.message || "No se pudo abrir la imagen.";
    } finally {
      if (revision === intento) { leyendo = false; actualizarVista(); }
    }
  });
  return {
    // Al abrir la selección, pide GET /api/game/avatar con el token de Firebase y lee el campo avatar.
    // Antes de marcar la opción comprueba que sigue abierta la misma sesión y que el usuario no eligió
    // otro avatar durante la consulta. guardado conserva la elección recibida para comparar al continuar.
    async cargar(usuario, pedir, sigueActivo) {
      const intento = revision;
      try {
        const { avatar } = await pedir("/api/game/avatar", { headers: { Authorization: `Bearer ${await usuario.getIdToken()}` } });
        if (!sigueActivo()) return;
        if (intento !== revision) return;
        guardado = avatar;
        if (avatar?.tipo === "personalizado") mostrarPersonal(avatar.valor);
        // Para un avatar del catálogo, busca su identificador entre los botones y usa el primero si falta.
        const radio = avatar?.tipo === "personalizado" && !personalizado.hidden ? personalizado.querySelector("input")
          : radios.find(item => item.value === avatar?.valor) || radios[0];
        radio.checked = true;
        actualizarVista();
      } catch {
        if (sigueActivo() && revision === intento) aviso.textContent = "No se pudo consultar tu avatar. Elige uno para continuar.";
      }
    },
    // Continuar consulta este método para construir el objeto que espera la API. valor contiene el ID
    // de catálogo o el PNG en base64 según el tipo. Devuelve null cuando falta la opción o aún se lee el archivo.
    eleccion() {
      const opcion = radios.find(radio => radio.checked);
      if (!opcion || leyendo) return null;
      if (opcion.value === "personalizado") return { tipo: "personalizado", valor: imagenPersonal };
      return { tipo: "predeterminado", valor: opcion.value };
    },
    // Antes de entrar a la sala se comparan tipo y valor con la última elección conocida. Si cambiaron,
    // PUT /api/game/avatar los envía en JSON con las cabeceras de la sesión. Solo se actualiza la copia
    // local después de recibir la respuesta y comprobar que el jugador sigue activo.
    async guardar(eleccion, cabeceras, pedir, sigueActivo) {
      if (guardado?.tipo === eleccion.tipo && guardado.valor === eleccion.valor) return;
      await pedir("/api/game/avatar", { method: "PUT", headers: cabeceras, body: JSON.stringify(eleccion) });
      if (sigueActivo()) guardado = eleccion;
    },
    // Al cerrar o cambiar de cuenta elimina la elección y la vista previa. Incrementar revision evita
    // que una lectura pendiente vuelva a mostrar el avatar de la cuenta anterior.
    limpiar() {
      revision++;
      leyendo = false;
      guardado = undefined;
      mostrarPersonal(null);
      // Desmarca cada opción antes de volver a calcular la vista previa.
      radios.forEach(radio => { radio.checked = false; });
      archivo.value = "";
      actualizarVista();
    },
  };
}
