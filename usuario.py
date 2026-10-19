class Usuario:
    def __init__(self, name, salt, hash_password, email):
        self.name = name
        self.hash_password = hash_password
        self.email = email
        self.record = 0
        self.verificado = False
        self.salt = salt
        self.avatar = None
    def verificacion(self):
        self.verificado = True
    def como_diccionario(self):
        return {
            "name": self.name,
            "email": self.email,
            "salt": self.salt,
            "hash_password": self.hash_password,
            "record": self.record,
            "verificado": self.verificado,
        }
    def setAvatar(self, imagen):
        self.avatar = imagen
        return
    