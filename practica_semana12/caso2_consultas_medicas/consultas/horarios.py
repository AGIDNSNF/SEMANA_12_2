"""Reglas centralizadas de horario del Centro Médico.

Se usan desde el modelo Cita, el formulario, el servicio de agendamiento y el
middleware de validación de horario.
"""
from datetime import datetime, time, timedelta

from django.conf import settings

# Lunes a viernes 08:00-18:00; sábados 08:00-13:00; domingos cerrado.
HORARIO_GENERAL = {
    0: (time(8, 0), time(18, 0)),
    1: (time(8, 0), time(18, 0)),
    2: (time(8, 0), time(18, 0)),
    3: (time(8, 0), time(18, 0)),
    4: (time(8, 0), time(18, 0)),
    5: (time(8, 0), time(13, 0)),
    6: None,
}

DIAS_SEMANA = {
    0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
    4: "Viernes", 5: "Sábado", 6: "Domingo",
}

ESTADOS_CITA_ACTIVOS = ("pendiente", "confirmada")


def duracion_cita() -> int:
    return int(getattr(settings, "CITA_DURACION_MINUTOS", 30))


def hora_fin(hora: time, duracion: int | None = None) -> time:
    base = datetime(2000, 1, 1, hora.hour, hora.minute)
    return (base + timedelta(minutes=duracion or duracion_cita())).time()


def validar_horario_general(fecha, hora, duracion: int | None = None):
    """Devuelve (es_valido, mensaje). Valida día, apertura y cierre."""
    if fecha is None or hora is None:
        return False, "Debe indicar fecha y hora."
    rango = HORARIO_GENERAL.get(fecha.weekday())
    if rango is None:
        return False, "El Centro Médico no atiende los domingos."
    apertura, cierre = rango
    if hora < apertura or hora >= cierre:
        return False, (
            f"El horario de atención del {DIAS_SEMANA[fecha.weekday()]} es "
            f"{apertura:%H:%M} a {cierre:%H:%M}."
        )
    if hora_fin(hora, duracion) > cierre:
        return False, (
            f"La cita terminaría después del cierre ({cierre:%H:%M}). "
            "Seleccione una hora más temprana."
        )
    return True, ""


def validar_horario_medico(medico, fecha, hora, duracion: int | None = None):
    """Valida el horario general y la disponibilidad declarada del médico."""
    valido, mensaje = validar_horario_general(fecha, hora, duracion)
    if not valido:
        return False, mensaje
    fin = hora_fin(hora, duracion)
    horarios = medico.horarios.filter(dia_semana=fecha.weekday())
    if not horarios.exists():
        return False, f"El médico no atiende el {DIAS_SEMANA[fecha.weekday()].lower()}."
    for horario in horarios:
        if horario.hora_inicio <= hora and fin <= horario.hora_fin:
            return True, ""
    return False, (
        "La hora solicitada está fuera del horario de atención del médico "
        f"({DIAS_SEMANA[fecha.weekday()].lower()})."
    )


def se_solapan(inicio_a: time, fin_a: time, inicio_b: time, fin_b: time) -> bool:
    return inicio_a < fin_b and inicio_b < fin_a
