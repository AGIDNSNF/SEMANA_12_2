"""Validadores y sanitización del caso 2."""
import re
import unicodedata

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

PATRON_DNI = re.compile(r"^\d{8}$")
PATRON_CMP = re.compile(r"^\d{5}$")
ETIQUETAS_HTML = re.compile(r"<[^>]*>")
CARACTERES_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

validar_dni = RegexValidator(
    regex=PATRON_DNI,
    message="El DNI debe tener exactamente 8 dígitos numéricos.",
    code="dni_invalido",
)
validar_cmp = RegexValidator(
    regex=PATRON_CMP,
    message="El CMP debe tener exactamente 5 dígitos numéricos (ejemplo: 50123).",
    code="cmp_invalido",
)

DOMINIO_INSTITUCIONAL = "@uncp.edu.pe"


def validar_correo_institucional(valor: str) -> None:
    if not valor or not valor.lower().endswith(DOMINIO_INSTITUCIONAL):
        raise ValidationError(
            "Los estudiantes deben registrar un correo institucional @uncp.edu.pe.",
            code="correo_no_institucional",
        )


def validar_sin_html(valor: str) -> None:
    if valor and ETIQUETAS_HTML.search(valor):
        raise ValidationError(
            "El texto no puede contener etiquetas HTML.", code="html_no_permitido"
        )


def sanitizar_texto(valor: str, longitud_maxima: int = 2000) -> str:
    """Normaliza y limpia texto clínico antes de almacenarlo.

    No sustituye al escape de plantillas: evita guardar marcado y caracteres de
    control. En logs nunca se vuelca el contenido clínico.
    """
    if not valor:
        return ""
    texto = unicodedata.normalize("NFKC", str(valor))
    texto = ETIQUETAS_HTML.sub("", texto)
    texto = CARACTERES_CONTROL.sub("", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()[:longitud_maxima]
