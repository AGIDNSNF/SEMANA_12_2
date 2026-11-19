"""Validadores reutilizables y funciones de sanitización del caso 1."""
import re
import unicodedata

from django.core.exceptions import ValidationError

PATRON_CODIGO_PATRIMONIAL = re.compile(r"^[A-Z0-9][A-Z0-9\-]{3,29}$")
PATRON_CODIGO_LABORATORIO = re.compile(r"^LAB-[A-Z0-9]{2,6}$")
ETIQUETAS_HTML = re.compile(r"<[^>]*>")
CARACTERES_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validar_codigo_patrimonial(valor: str) -> None:
    """Formato institucional: mayúsculas, dígitos y guiones (p. ej. SIS-PC-001)."""
    if not PATRON_CODIGO_PATRIMONIAL.match(valor or ""):
        raise ValidationError(
            "El código patrimonial debe usar mayúsculas, números y guiones "
            "(ejemplo: SIS-PC-001), entre 4 y 30 caracteres.",
            code="codigo_invalido",
        )


def validar_codigo_laboratorio(valor: str) -> None:
    if not PATRON_CODIGO_LABORATORIO.match(valor or ""):
        raise ValidationError(
            "El código de laboratorio debe tener el formato LAB-XXX (ejemplo: LAB-SIS).",
            code="codigo_laboratorio_invalido",
        )


def validar_sin_html(valor: str) -> None:
    """Rechaza etiquetas HTML en campos de texto libre."""
    if valor and ETIQUETAS_HTML.search(valor):
        raise ValidationError(
            "El texto no puede contener etiquetas HTML.", code="html_no_permitido"
        )


def sanitizar_texto(valor: str, longitud_maxima: int = 1000) -> str:
    """Normaliza texto libre: quita etiquetas/controles y limita la longitud.

    El escape HTML final lo realiza la plantilla (autoescape); esta función evita
    almacenar marcado y caracteres de control.
    """
    if not valor:
        return ""
    texto = unicodedata.normalize("NFKC", str(valor))
    texto = ETIQUETAS_HTML.sub("", texto)
    texto = CARACTERES_CONTROL.sub("", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()[:longitud_maxima]
