"""Servicios y reglas transaccionales del caso 2."""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AuditoriaMedica, Cita, Consulta, Especialidad, Medico, NotaClinica, Paciente
from .permissions import es_administrador, medico_de
from .utils import registrar_auditoria_medica

logger = logging.getLogger("consultas")


class ErrorCita(ValidationError):
    """Error de flujo con mensaje apto para el usuario."""


@transaction.atomic
def agendar_cita(
    *, paciente, medico, especialidad, fecha, hora, motivo,
    estado=Cita.Estado.PENDIENTE, usuario, ip=None,
):
    """Agenda una cita con bloqueo del médico para evitar superposiciones."""
    if estado not in (Cita.Estado.PENDIENTE, Cita.Estado.CONFIRMADA):
        raise ErrorCita("Estado inicial de cita no permitido.")
    medico = Medico.objects.select_for_update().get(pk=medico.pk)
    if not medico.activo:
        raise ErrorCita("El médico seleccionado no está activo.")
    cita = Cita(
        paciente=paciente, medico=medico, especialidad=especialidad,
        fecha=fecha, hora=hora, motivo=motivo, estado=estado,
    )
    cita.full_clean()
    cita.save()
    registrar_auditoria_medica(
        usuario=usuario, accion=AuditoriaMedica.Accion.AGENDAR, paciente=paciente,
        ip=ip, recurso=f"Cita #{cita.pk} {fecha:%Y-%m-%d} {hora:%H:%M}",
    )
    logger.info("Cita %s agendada paciente=%s medico=%s", cita.pk, paciente.pk, medico.pk)
    return cita


@transaction.atomic
def cancelar_cita(cita, *, usuario, motivo="", ip=None):
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    if not cita.es_activa:
        raise ErrorCita("Solo se pueden cancelar citas pendientes o confirmadas.")
    cita.estado = Cita.Estado.CANCELADA
    if motivo:
        cita.motivo = (cita.motivo + f"\nCancelación: {motivo}")[:500]
    cita.save(update_fields=["estado", "motivo", "actualizado_en"])
    registrar_auditoria_medica(
        usuario=usuario, accion=AuditoriaMedica.Accion.CANCELAR, paciente=cita.paciente,
        ip=ip, recurso=f"Cita #{cita.pk}",
    )
    return cita


@transaction.atomic
def confirmar_cita(cita, *, usuario, ip=None):
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    if cita.estado != Cita.Estado.PENDIENTE:
        raise ErrorCita("Solo se pueden confirmar citas pendientes.")
    cita.estado = Cita.Estado.CONFIRMADA
    cita.save(update_fields=["estado", "actualizado_en"])
    registrar_auditoria_medica(
        usuario=usuario, accion=AuditoriaMedica.Accion.CONFIRMAR, paciente=cita.paciente,
        ip=ip, recurso=f"Cita #{cita.pk}",
    )
    return cita


@transaction.atomic
def marcar_completada(cita, *, usuario, ip=None):
    """Completa una cita únicamente si ya existe una consulta registrada."""
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    if cita.estado not in (Cita.Estado.CONFIRMADA, Cita.Estado.PENDIENTE):
        raise ErrorCita("La cita no está en un estado que permita completarla.")
    if not Consulta.objects.filter(cita=cita).exists():
        raise ErrorCita(
            "No se puede marcar como completada una cita sin consulta registrada. "
            "El médico debe registrar la atención."
        )
    cita.estado = Cita.Estado.COMPLETADA
    cita.save(update_fields=["estado", "actualizado_en"])
    return cita


@transaction.atomic
def registrar_consulta(cita, *, medico, diagnostico, tratamiento, medicamentos="",
                       proxima_cita=None, archivos_referencia="", usuario, ip=None):
    """Registra la consulta inmutable y completa la cita en una sola transacción."""
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    if cita.estado != Cita.Estado.CONFIRMADA:
        raise ErrorCita("Solo se registra consulta de una cita confirmada.")
    if Consulta.objects.filter(cita=cita).exists():
        raise ErrorCita("Esta cita ya tiene una consulta registrada.")
    if cita.medico_id != medico.pk and not es_administrador(usuario):
        raise ErrorCita("Solo el médico de la cita puede registrar la consulta.")

    consulta = Consulta(
        cita=cita, medico=medico, diagnostico=diagnostico, tratamiento=tratamiento,
        medicamentos=medicamentos, proxima_cita=proxima_cita,
        archivos_referencia=archivos_referencia,
    )
    consulta.full_clean()
    consulta.save()
    cita.estado = Cita.Estado.COMPLETADA
    cita.save(update_fields=["estado", "actualizado_en"])
    registrar_auditoria_medica(
        usuario=usuario, accion=AuditoriaMedica.Accion.CREAR_CONSULTA,
        paciente=cita.paciente, ip=ip, recurso=f"Consulta #{consulta.pk} · Cita #{cita.pk}",
    )
    return consulta


def agregar_nota(consulta, *, autor, contenido, ip=None):
    """Las consultas no se editan: solo se amplían con notas posteriores."""
    medico = medico_de(autor)
    if medico is None or (consulta.medico_id != medico.pk and not es_administrador(autor)):
        raise ErrorCita("Solo el médico responsable puede agregar notas a esta consulta.")
    nota = NotaClinica(consulta=consulta, autor=autor, contenido=contenido)
    nota.full_clean()
    nota.save()
    registrar_auditoria_medica(
        usuario=autor, accion=AuditoriaMedica.Accion.CREAR_NOTA,
        paciente=consulta.cita.paciente, ip=ip, recurso=f"Consulta #{consulta.pk}",
    )
    return nota


def paciente_de_usuario(usuario):
    try:
        return usuario.paciente
    except Exception:
        return None


def citas_para(usuario):
    """Queryset de citas visibles según el rol (sin filtrar por fecha)."""
    consulta = Cita.objects.select_related("paciente", "medico", "especialidad")
    if usuario.is_superuser or es_administrador(usuario) or usuario.groups.filter(
        name="Recepcionistas"
    ).exists():
        return consulta
    paciente = paciente_de_usuario(usuario)
    if paciente is not None:
        return consulta.filter(paciente=paciente)
    medico = medico_de(usuario)
    if medico is not None:
        return consulta.filter(medico=medico)
    return consulta.none()


def citas_pendientes_medico(usuario):
    medico = medico_de(usuario)
    if medico is None:
        return 0
    return Cita.objects.filter(
        medico=medico,
        estado__in=(Cita.Estado.PENDIENTE, Cita.Estado.CONFIRMADA),
        fecha__gte=timezone.localdate(),
    ).count()
