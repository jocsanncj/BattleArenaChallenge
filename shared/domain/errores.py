"""Excepciones de dominio que pueden mostrarse en la interfaz."""


class ErrorApp(Exception):
    """
    Descripción:
        Excepción propia del programa para errores que el usuario debe conocer (sala
        llena, archivo inválido, configuración bloqueada, etc.). Su mensaje está escrito
        para personas, no para programadores. La interfaz la captura y muestra ese
        mensaje en pantalla en lugar de cerrar el programa.
    Atributos:
        Sin atributos propios: el mensaje es el texto con el que se crea la excepción.
    """
