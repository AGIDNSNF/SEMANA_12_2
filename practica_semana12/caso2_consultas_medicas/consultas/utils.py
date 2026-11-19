"""Utilidades de IP y auditoría médica (sin datos clínicos)."""
import logging

from .models import AuditoriaMedica

logger = logging.getLogger("consultas")


def obtener_ip(request) -> str:
    if request is None:
        return "127.0.0.1"
    return request.META.get("REMOTE_ADDR") or "127.0.0.1"


def registrar_auditoria_medica(
    usuario, accion, paciente=None, paciente_id=None, ip=None, recurso=""
):
    """Registra metadatos de acceso. Nunca incluye diagnósticos ni tratamientos."""
    try:
        datos = {
            "usuario": usuario if getattr(usuario, "is_authenticated", False) else None,
            "accion": accion,
            "ip": ip or "127.0.0.1",
            "recurso": (recurso or "")[:200],
        }
        if paciente is not None:
            datos["paciente"] = paciente
        elif paciente_id is not None:
            datos["paciente_id"] = paciente_id
        return AuditoriaMedica.objects.create(**datos)
    except Exception:  # pragma: no cover
        logger.exception("No se pudo registrar la auditoría médica")
        return None
