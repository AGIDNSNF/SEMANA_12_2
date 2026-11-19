"""Reglas laborales centralizadas del caso 3."""
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings


def jornada_horas() -> Decimal:
    return Decimal(str(getattr(settings, "JORNADA_HORAS", 8)))


def saldo_anual_dias() -> int:
    return int(getattr(settings, "SALDO_ANUAL_DIAS", 30))


def es_dia_habil(fecha: date) -> bool:
    return fecha.weekday() < 5


def dias_habiles(inicio: date, fin: date) -> int:
    """Días de lunes a viernes entre dos fechas inclusive."""
    if not inicio or not fin or fin < inicio:
        return 0
    total = 0
    cursor = inicio
    while cursor <= fin:
        if es_dia_habil(cursor):
            total += 1
        cursor += timedelta(days=1)
    return total


def dias_por_anio(inicio: date, fin: date) -> dict[int, int]:
    """Días hábiles solicitados desglosados por año calendario."""
    resultado: dict[int, int] = {}
    if not inicio or not fin or fin < inicio:
        return resultado
    for anio in range(inicio.year, fin.year + 1):
        desde = max(inicio, date(anio, 1, 1))
        hasta = min(fin, date(anio, 12, 31))
        dias = dias_habiles(desde, hasta)
        if dias:
            resultado[anio] = dias
    return resultado


def solapan(inicio_a: date, fin_a: date, inicio_b: date, fin_b: date) -> bool:
    return inicio_a <= fin_b and inicio_b <= fin_a


def combinar(fecha: date, hora: time) -> datetime:
    return datetime.combine(fecha, hora)


def horas_trabajadas(entrada: time | None, salida: time | None) -> Decimal:
    if not entrada or not salida:
        return Decimal("0")
    referencia = date(2000, 1, 1)
    delta = combinar(referencia, salida) - combinar(referencia, entrada)
    horas = Decimal(str(delta.total_seconds() / 3600))
    return horas.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def horas_extra(entrada: time | None, salida: time | None) -> Decimal:
    total = horas_trabajadas(entrada, salida)
    extra = total - jornada_horas()
    return extra.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if extra > 0 else Decimal("0.00")
