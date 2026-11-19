"""Capa de servicios: reglas de negocio y transacciones del caso 1.

Las vistas y los formularios delegan aquí para que las validaciones no puedan
saltarse desde la interfaz ni desde el admin.
"""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    ESTADOS_QUE_OCUPAN,
    MAX_PRESTAMOS_ACTIVOS,
    Auditoria,
    Devolucion,
    Equipo,
    Prestamo,
)
from .utils import registrar_auditoria

logger = logging.getLogger("prestamos")


class ErrorPrestamo(ValidationError):
    """Error de negocio con mensaje apto para mostrar al usuario."""


def _validar_docente_y_cupo(docente, prestamo=None):
    consulta = Prestamo.objects.filter(
        docente=docente, estado__in=ESTADOS_QUE_OCUPAN
    )
    if prestamo and prestamo.pk:
        consulta = consulta.exclude(pk=prestamo.pk)
    if consulta.count() >= MAX_PRESTAMOS_ACTIVOS:
        raise ErrorPrestamo(
            f"El docente ya tiene {MAX_PRESTAMOS_ACTIVOS} préstamos activos. "
            "Debe devolver uno antes de solicitar otro."
        )


@transaction.atomic
def crear_prestamo(
    *,
    docente,
    equipo,
    cantidad,
    fecha_prestamo,
    fecha_prevista_devolucion,
    observaciones="",
    estado=Prestamo.Estado.PENDIENTE,
    asistente=None,
    usuario_accion=None,
    ip=None,
):
    """Crea una solicitud (pendiente) o un préstamo directo (activo).

    Bloquea la fila del equipo para evitar sobreasignaciones concurrentes.
    """
    equipo = Equipo.objects.select_for_update().get(pk=equipo.pk)

    if estado not in (Prestamo.Estado.PENDIENTE, Prestamo.Estado.ACTIVO):
        raise ErrorPrestamo("Estado inicial de préstamo no permitido.")

    _validar_docente_y_cupo(docente)
    if equipo.estado != Equipo.Estado.OPERATIVO:
        raise ErrorPrestamo("Solo se pueden prestar equipos en estado Operativo.")
    if cantidad is None or cantidad <= 0:
        raise ErrorPrestamo("La cantidad debe ser un número mayor que cero.")
    disponible = equipo.cantidad_disponible
    if cantidad > disponible:
        raise ErrorPrestamo(
            f"Stock insuficiente: se solicitan {cantidad} y solo hay "
            f"{disponible} disponible(s)."
        )

    prestamo = Prestamo(
        docente=docente,
        equipo=equipo,
        cantidad=cantidad,
        fecha_prestamo=fecha_prestamo,
        fecha_prevista_devolucion=fecha_prevista_devolucion,
        observaciones=observaciones,
        estado=estado,
        asistente_responsable=asistente,
    )
    prestamo.full_clean()
    prestamo.save()
    registrar_auditoria(
        usuario=usuario_accion or asistente or docente,
        accion=Auditoria.Accion.SOLICITUD if estado == Prestamo.Estado.PENDIENTE
        else Auditoria.Accion.APROBACION,
        entidad="Prestamo",
        entidad_id=prestamo.pk,
        descripcion=(
            f"{prestamo.get_estado_display()} de {cantidad} unidad(es) de "
            f"{equipo.codigo_patrimonial} para {docente.get_username()}"
        ),
        ip=ip,
    )
    logger.info(
        "Préstamo %s creado estado=%s equipo=%s docente=%s",
        prestamo.pk, estado, equipo.pk, docente.pk,
    )
    return prestamo


@transaction.atomic
def aprobar_prestamo(prestamo, *, asistente, ip=None):
    """Activa una solicitud pendiente. Revalida stock y cupo bajo bloqueo."""
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.Estado.PENDIENTE:
        raise ErrorPrestamo("Solo se pueden aprobar préstamos pendientes.")

    equipo = Equipo.objects.select_for_update().get(pk=prestamo.equipo_id)
    if equipo.estado != Equipo.Estado.OPERATIVO:
        raise ErrorPrestamo("El equipo ya no está operativo.")
    _validar_docente_y_cupo(prestamo.docente, prestamo)
    # El propio préstamo pendiente ya reserva stock, por eso se excluye.
    disponible = equipo.cantidad_disponible + prestamo.cantidad
    if prestamo.cantidad > disponible:
        raise ErrorPrestamo("No hay stock suficiente para aprobar la solicitud.")

    prestamo.estado = Prestamo.Estado.ACTIVO
    prestamo.asistente_responsable = asistente
    prestamo.save(update_fields=["estado", "asistente_responsable", "fecha_actualizacion"])
    registrar_auditoria(
        usuario=asistente,
        accion=Auditoria.Accion.APROBACION,
        entidad="Prestamo",
        entidad_id=prestamo.pk,
        descripcion=f"Préstamo aprobado por {asistente.get_username()}",
        ip=ip,
    )
    return prestamo


@transaction.atomic
def rechazar_prestamo(prestamo, *, asistente, motivo="", ip=None):
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.Estado.PENDIENTE:
        raise ErrorPrestamo("Solo se pueden rechazar solicitudes pendientes.")
    prestamo.estado = Prestamo.Estado.RECHAZADO
    prestamo.asistente_responsable = asistente
    if motivo:
        prestamo.observaciones = (prestamo.observaciones + "\n" + motivo).strip()[:500]
    prestamo.save(
        update_fields=["estado", "asistente_responsable", "observaciones", "fecha_actualizacion"]
    )
    registrar_auditoria(
        usuario=asistente,
        accion=Auditoria.Accion.RECHAZO,
        entidad="Prestamo",
        entidad_id=prestamo.pk,
        descripcion=f"Solicitud rechazada. Motivo: {motivo or 'no indicado'}",
        ip=ip,
    )
    return prestamo


@transaction.atomic
def registrar_devolucion(
    prestamo, *, asistente, estado_equipo=Devolucion.EstadoEquipo.OPERATIVO,
    observaciones="", ip=None,
):
    """Registra una única devolución y actualiza el equipo de forma atómica."""
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if Devolucion.objects.filter(prestamo=prestamo).exists() or prestamo.fecha_real_devolucion:
        raise ErrorPrestamo("Este préstamo ya tiene una devolución registrada.")
    if prestamo.estado not in (Prestamo.Estado.ACTIVO, Prestamo.Estado.VENCIDO):
        raise ErrorPrestamo("Solo se pueden devolver préstamos activos o vencidos.")

    devolucion = Devolucion(
        prestamo=prestamo,
        fecha=timezone.localdate(),
        estado_equipo_al_retornar=estado_equipo,
        observaciones=observaciones,
        asistente_responsable=asistente,
    )
    devolucion.full_clean()
    devolucion.save()

    prestamo.estado = Prestamo.Estado.DEVUELTO
    prestamo.fecha_real_devolucion = devolucion.fecha
    prestamo.save(
        update_fields=["estado", "fecha_real_devolucion", "fecha_actualizacion"]
    )

    equipo = Equipo.objects.select_for_update().get(pk=prestamo.equipo_id)
    if estado_equipo != equipo.estado and estado_equipo in (
        Equipo.Estado.OPERATIVO, Equipo.Estado.MANTENIMIENTO, Equipo.Estado.BAJA
    ):
        equipo.estado = estado_equipo
        equipo.save(update_fields=["estado"])

    registrar_auditoria(
        usuario=asistente,
        accion=Auditoria.Accion.DEVOLUCION,
        entidad="Prestamo",
        entidad_id=prestamo.pk,
        descripcion=(
            f"Devolución registrada. Equipo {equipo.codigo_patrimonial} "
            f"retornó en estado {estado_equipo}."
        ),
        ip=ip,
    )
    logger.info("Devolución registrada préstamo=%s por=%s", prestamo.pk, asistente.pk)
    return devolucion


def marcar_vencidos(usuario=None, ip=None) -> int:
    """Marca como vencidos los préstamos activos cuya fecha ya pasó."""
    hoy = timezone.localdate()
    vencidos = list(
        Prestamo.objects.filter(estado=Prestamo.Estado.ACTIVO, fecha_prevista_devolucion__lt=hoy)
    )
    for prestamo in vencidos:
        prestamo.estado = Prestamo.Estado.VENCIDO
        prestamo.save(update_fields=["estado", "fecha_actualizacion"])
        registrar_auditoria(
            usuario=usuario,
            accion=Auditoria.Accion.OTRO,
            entidad="Prestamo",
            entidad_id=prestamo.pk,
            descripcion="Préstamo marcado automáticamente como vencido.",
            ip=ip,
        )
    return len(vencidos)


def eliminar_equipo(equipo, *, usuario, ip=None):
    """Elimina un equipo solo si no tiene préstamos que ocupen stock."""
    if equipo.tiene_prestamos_activos():
        raise ErrorPrestamo(
            "No se puede eliminar un equipo con préstamos pendientes, activos o vencidos."
        )
    codigo = equipo.codigo_patrimonial
    equipo.delete()
    registrar_auditoria(
        usuario=usuario,
        accion=Auditoria.Accion.EQUIPO,
        entidad="Equipo",
        entidad_id=codigo,
        descripcion=f"Equipo {codigo} eliminado del catálogo.",
        ip=ip,
    )
