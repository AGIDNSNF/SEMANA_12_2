"""Utilidades de auditoría del caso 3."""
import logging

from .models import AuditoriaAsistencia

logger = logging.getLogger("asistencia")


def obtener_ip(request) -> str:
    if request is None:
        return "127.0.0.1"
    return request.META.get("REMOTE_ADDR") or "127.0.0.1"


def registrar_auditoria(
    usuario, accion, empleado=None, empleado_id=None, ip=None, detalle=""
):
    """Registra metadatos; nunca incluye justificaciones ni motivos completos."""
    try:
        datos = {
            "usuario": usuario if getattr(usuario, "is_authenticated", False) else None,
            "accion": accion,
            "ip": ip or "127.0.0.1",
            "detalle": (detalle or "")[:200],
        }
        if empleado is not None:
            datos["empleado"] = empleado
        elif empleado_id is not None:
            datos["empleado_id"] = empleado_id
        return AuditoriaAsistencia.objects.create(**datos)
    except Exception:  # pragma: no cover
        logger.exception("No se pudo registrar la auditoría de asistencia")
        return None
