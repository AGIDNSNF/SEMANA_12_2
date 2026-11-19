"""Utilidades transversales: IP del cliente, auditoría y detección de roles."""
import logging

from django.utils import timezone

logger = logging.getLogger("prestamos")


def obtener_ip(request) -> str:
    """Obtiene la IP del cliente sin confiar ciegamente en cabeceras externas.

    En desarrollo se usa REMOTE_ADDR. X-Forwarded-For se considera solo como
    respaldo (útil detrás de un proxy propio) y se toma el primer valor.
    """
    if request is None:
        return "127.0.0.1"
    ip = request.META.get("REMOTE_ADDR")
    if not ip:
        reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = reenviada.split(",")[0].strip()
    return ip or "127.0.0.1"


def registrar_auditoria(usuario, accion, entidad, entidad_id="", descripcion="", ip=None):
    """Crea un registro de auditoría de forma tolerante a fallos.

    La auditoría nunca debe romper la operación de negocio: si falla el registro
    se escribe en el log y se continúa.
    """
    from .models import Auditoria

    try:
        return Auditoria.objects.create(
            usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
            accion=accion,
            entidad=entidad,
            entidad_id=str(entidad_id or ""),
            descripcion=descripcion[:500],
            ip=ip or "127.0.0.1",
        )
    except Exception:  # pragma: no cover - protección defensiva
        logger.exception("No se pudo registrar la auditoría")
        return None


def dias_desde(fecha) -> int | None:
    if not fecha:
        return None
    return (timezone.localdate() - fecha).days
