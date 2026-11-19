"""Validadores y sanitización del caso 3."""
import re
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

PATRON_DNI = re.compile(r"^\d{8}$")
ETIQUETAS_HTML = re.compile(r"<[^>]*>")
CARACTERES_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

validar_dni = RegexValidator(
    regex=PATRON_DNI,
    message="El DNI debe tener exactamente 8 dígitos numéricos.",
    code="dni_invalido",
)

DOMINIO_CORPORATIVO = "@tecnoandes.pe"


def validar_correo_corporativo(valor: str) -> None:
    if not valor or not valor.lower().endswith(DOMINIO_CORPORATIVO):
        raise ValidationError(
            "El correo debe pertenecer al dominio corporativo @tecnoandes.pe.",
            code="correo_no_corporativo",
        )


def validar_sin_html(valor: str) -> None:
    if valor and ETIQUETAS_HTML.search(valor):
        raise ValidationError(
            "El texto no puede contener etiquetas HTML.", code="html_no_permitido"
        )


def sanitizar_texto(valor: str, longitud_maxima: int = 2000) -> str:
    if not valor:
        return ""
    texto = unicodedata.normalize("NFKC", str(valor))
    texto = ETIQUETAS_HTML.sub("", texto)
    texto = CARACTERES_CONTROL.sub("", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()[:longitud_maxima]


def justificacion_minima() -> int:
    return int(getattr(settings, "JUSTIFICACION_MINIMA", 50))
