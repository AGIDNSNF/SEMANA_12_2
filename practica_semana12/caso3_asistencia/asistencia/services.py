"""Servicios y reglas transaccionales del caso 3."""
import logging
from datetime import time

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    AuditoriaAsistencia,
    CorreccionAsistencia,
    RegistroAsistencia,
    Solicitud,
)
from .permissions import empleado_de, es_rrhh, puede_resolver_solicitud
from .reglas import dias_por_anio
from .utils import registrar_auditoria
from .validators import justificacion_minima, sanitizar_texto

logger = logging.getLogger("asistencia")


class ErrorAsistencia(ValidationError):
    """Error de flujo con mensaje apto para el usuario."""


def _ahora(ahora=None):
    return timezone.localtime(ahora) if ahora is not None else timezone.localtime()


@transaction.atomic
def marcar_entrada(empleado, *, usuario, ahora=None, ip=None):
    if not empleado.activo:
        raise ErrorAsistencia("El empleado no está activo; no puede registrar asistencia.")
    momento = _ahora(ahora)
    registro, _ = RegistroAsistencia.objects.get_or_create(
        empleado=empleado, fecha=momento.date(),
        defaults={"registrado_por": usuario},
    )
    if registro.hora_entrada:
        raise ErrorAsistencia("Ya registró su hora de entrada para hoy.")
    registro.hora_entrada = momento.time().replace(microsecond=0)
    registro.registrado_por = usuario
    registro.save()
    registrar_auditoria(
        usuario=usuario, accion=AuditoriaAsistencia.Accion.MARCACION,
        empleado=empleado, ip=ip, detalle=f"Entrada {registro.fecha} {registro.hora_entrada}",
    )
    logger.info("Entrada empleado=%s fecha=%s", empleado.pk, registro.fecha)
    return registro


@transaction.atomic
def marcar_salida(empleado, *, usuario, ahora=None, ip=None):
    if not empleado.activo:
        raise ErrorAsistencia("El empleado no está activo; no puede registrar asistencia.")
    momento = _ahora(ahora)
    registro = (
        RegistroAsistencia.objects.select_for_update()
        .filter(empleado=empleado, fecha=momento.date())
        .first()
    )
    if registro is None or not registro.hora_entrada:
        raise ErrorAsistencia("Primero debe registrar su hora de entrada.")
    if registro.hora_salida:
        raise ErrorAsistencia("Ya registró su hora de salida para hoy.")
    salida = momento.time().replace(microsecond=0)
    if salida <= registro.hora_entrada:
        raise ErrorAsistencia("La hora de salida debe ser posterior a la entrada.")
    registro.hora_salida = salida
    registro.save()
    registrar_auditoria(
        usuario=usuario, accion=AuditoriaAsistencia.Accion.MARCACION,
        empleado=empleado, ip=ip, detalle=f"Salida {registro.fecha} {registro.hora_salida}",
    )
    logger.info("Salida empleado=%s fecha=%s", empleado.pk, registro.fecha)
    return registro


@transaction.atomic
def corregir_asistencia(
    registro, *, usuario, hora_entrada: time, hora_salida: time,
    justificacion: str, ip=None,
):
    """Solo RRHH. Exige justificación de al menos 50 caracteres."""
    if not es_rrhh(usuario):
        raise ErrorAsistencia("Solo Recursos Humanos puede corregir registros de asistencia.")
    texto = sanitizar_texto(justificacion, 800)
    if len(texto) < justificacion_minima():
        raise ErrorAsistencia(
            f"La justificación debe tener al menos {justificacion_minima()} caracteres."
        )
    if hora_salida <= hora_entrada:
        raise ErrorAsistencia("La hora de salida corregida debe ser posterior a la entrada.")

    registro = RegistroAsistencia.objects.select_for_update().get(pk=registro.pk)
    correccion = CorreccionAsistencia(
        registro=registro,
        hora_entrada_anterior=registro.hora_entrada,
        hora_salida_anterior=registro.hora_salida,
        hora_entrada_nueva=hora_entrada,
        hora_salida_nueva=hora_salida,
        justificacion=texto,
        corregido_por=usuario,
    )
    registro.hora_entrada = hora_entrada
    registro.hora_salida = hora_salida
    registro.save()
    correccion.save()
    registrar_auditoria(
        usuario=usuario, accion=AuditoriaAsistencia.Accion.CORRECCION,
        empleado=registro.empleado, ip=ip,
        detalle=f"Corrección registro #{registro.pk} ({registro.fecha})",
    )
    logger.info(
        "Corrección registro=%s por usuario=%s", registro.pk, getattr(usuario, "pk", None)
    )
    return correccion


def validar_saldo(solicitud: Solicitud):
    for anio, dias in dias_por_anio(solicitud.fecha_inicio, solicitud.fecha_fin).items():
        disponible = solicitud.empleado.saldo_disponible(anio, excluir_pk=solicitud.pk)
        if dias > disponible:
            raise ErrorAsistencia(
                f"Saldo insuficiente para {anio}: solicita {dias} día(s) y dispone de {disponible}."
            )


@transaction.atomic
def crear_solicitud(
    *, empleado, tipo, fecha_inicio, fecha_fin, motivo, usuario, ip=None
):
    solicitud = Solicitud(
        empleado=empleado, tipo=tipo, fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin, motivo=motivo,
    )
    solicitud.full_clean()
    solicitud.save()
    registrar_auditoria(
        usuario=usuario, accion=AuditoriaAsistencia.Accion.SOLICITUD,
        empleado=empleado, ip=ip, detalle=f"Solicitud #{solicitud.pk} {solicitud.get_tipo_display()}",
    )
    return solicitud


@transaction.atomic
def resolver_solicitud(solicitud, *, usuario, aprobar: bool, comentario="", ip=None):
    solicitud = Solicitud.objects.select_for_update().get(pk=solicitud.pk)
    if not solicitud.es_pendiente:
        raise ErrorAsistencia("La solicitud ya fue resuelta.")
    if not puede_resolver_solicitud(usuario, solicitud):
        raise ErrorAsistencia(
            "Solo el jefe del área o Recursos Humanos puede resolver esta solicitud, "
            "y nunca el propio solicitante."
        )
    if aprobar:
        validar_saldo(solicitud)
        solicitud.estado = Solicitud.Estado.APROBADA
    else:
        solicitud.estado = Solicitud.Estado.RECHAZADA
    solicitud.revisado_por = usuario
    solicitud.fecha_revision = timezone.now()
    solicitud.comentario_revision = sanitizar_texto(comentario, 300)
    solicitud.save(update_fields=[
        "estado", "revisado_por", "fecha_revision", "comentario_revision", "actualizado_en",
    ])
    registrar_auditoria(
        usuario=usuario,
        accion=(
            AuditoriaAsistencia.Accion.APROBACION if aprobar
            else AuditoriaAsistencia.Accion.RECHAZO
        ),
        empleado=solicitud.empleado, ip=ip,
        detalle=f"Solicitud #{solicitud.pk}",
    )
    logger.info(
        "Solicitud %s %s por usuario=%s",
        solicitud.pk, "aprobada" if aprobar else "rechazada", getattr(usuario, "pk", None),
    )
    return solicitud


@transaction.atomic
def cancelar_solicitud(solicitud, *, usuario, ip=None):
    solicitud = Solicitud.objects.select_for_update().get(pk=solicitud.pk)
    if not solicitud.es_pendiente:
        raise ErrorAsistencia("Solo se pueden cancelar solicitudes pendientes.")
    propio = empleado_de(usuario)
    if not (es_rrhh(usuario) or (propio is not None and propio.pk == solicitud.empleado_id)):
        raise ErrorAsistencia("No puede cancelar esta solicitud.")
    solicitud.estado = Solicitud.Estado.CANCELADA
    solicitud.save(update_fields=["estado", "actualizado_en"])
    registrar_auditoria(
        usuario=usuario, accion=AuditoriaAsistencia.Accion.CANCELACION,
        empleado=solicitud.empleado, ip=ip, detalle=f"Solicitud #{solicitud.pk}",
    )
    return solicitud
