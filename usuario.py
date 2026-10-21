## @brief Representa una cuenta de usuario del modelo legado en memoria.
class Usuario:
    ## @brief Inicializa una cuenta en el modelo legado de usuario.
    ## @param name Nombre público de la cuenta.
    ## @param salt Sal utilizada para derivar el hash de contraseña.
    ## @param hash_password Hash guardado de la contraseña.
    ## @param email Dirección de correo asociada.
    def __init__(self, name, salt, hash_password, email):
        # Conserva el nombre de usuario recibido.
        self.name = name
        # Guarda el hash, nunca la contraseña original.
        self.hash_password = hash_password
        # Guarda el correo para el registro legado.
        self.email = email
        # Inicializa el récord en cero porque todavía no hay partidas.
        self.record = 0
        # Las cuentas nuevas requieren verificación de correo.
        self.verificado = False
        # Conserva la sal necesaria para comprobar la contraseña.
        self.salt = salt
        # No asigna avatar hasta que exista esa funcionalidad.
        self.avatar = None
    ## @brief Marca el correo de la cuenta como verificado.
    ## @return None.
    def verificacion(self):
        # Actualiza el indicador que se usa al serializar la cuenta.
        self.verificado = True
    ## @brief Serializa los campos persistidos por el formato legado.
    ## @return Diccionario compatible con el almacenamiento antiguo en JSON.
    def como_diccionario(self):
        # Devuelve campos de cuenta sin incluir el avatar todavía no soportado.
        return {
            "name": self.name,
            "email": self.email,
            "salt": self.salt,
            "hash_password": self.hash_password,
            "record": self.record,
            "verificado": self.verificado,
        }
    ## @brief Asigna una imagen de avatar al objeto legado.
    ## @param imagen Valor que representa la imagen seleccionada.
    ## @return None.
    def setAvatar(self, imagen):
        # Conserva la imagen recibida en el atributo del objeto.
        self.avatar = imagen
        return