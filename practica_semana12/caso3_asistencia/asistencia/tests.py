"""Pruebas automatizadas del Caso 3 · Asistencia y permisos.

Cubren validaciones, jornada y horas extra, correcciones exclusivas de RRHH,
saldo anual, aprobación por jefe/RRHH sin autoaprobación, alcance por área,
sesión de 45 minutos y vistas principales.

Ejecutar:  python manage.py test asistencia
"""
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import (
    Area,
    AuditoriaAsistencia,
    CorreccionAsistencia,
    Empleado,
    RegistroAsistencia,
    Solicitud,
)
from .reglas import dias_habiles

Usuario = get_user_model()


def fecha_habil(dias=1):
    fecha = timezone.localdate() + timedelta(days=dias)
    while fecha.weekday() >= 5:
        fecha += timedelta(days=1)
    return fecha


def fecha_pasada_habil():
    fecha = timezone.localdate() - timedelta(days=1)
    while fecha.weekday() >= 5:
        fecha -= timedelta(days=1)
    return fecha


def proximo_dia(weekday):
    fecha = timezone.localdate() + timedelta(days=1)
    while fecha.weekday() != weekday:
        fecha += timedelta(days=1)
    return fecha


def crear_empleado(dni, username, nombres, apellidos, area, *, grupos=(), cargo="Analista"):
    usuario = Usuario.objects.create_user(
        username, password="Clave12345!", first_name=nombres, last_name=apellidos
    )
    if grupos:
        usuario.groups.set(Group.objects.filter(name__in=grupos))
    empleado = Empleado.objects.create(
        dni=dni, nombres=nombres, apellidos=apellidos,
        email=f"{username}@tecnoandes.pe", cargo=cargo, area=area,
        usuario=usuario, fecha_ingreso=timezone.localdate() - timedelta(days=365),
        sueldo_basico="2500.00",
    )
    return empleado, usuario


def treinta_dias_habiles():
    """Rango de 30 días hábiles consecutivos dentro de un mismo año futuro."""
    anio = timezone.localdate().year + 1
    cursor = date(anio, 1, 1)
    while cursor.weekday() != 0:
        cursor += timedelta(days=1)
    dias = []
    while len(dias) < 30:
        if cursor.weekday() < 5:
            dias.append(cursor)
        cursor += timedelta(days=1)
    return dias[0], dias[-1], anio


class BaseAsistenciaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grupo_rrhh, _ = Group.objects.get_or_create(name="Recursos Humanos")
        cls.grupo_jefes, _ = Group.objects.get_or_create(name="Jefes de área")
        cls.grupo_empleados, _ = Group.objects.get_or_create(name="Empleados")
        cls.grupo_contadores, _ = Group.objects.get_or_create(name="Contadores")

        cls.area_ti = Area.objects.create(nombre="Tecnología", codigo="TI")
        cls.area_oper = Area.objects.create(nombre="Operaciones", codigo="OPER")
        cls.area_rrhh = Area.objects.create(nombre="Recursos Humanos", codigo="RRHH")
        cls.area_cont = Area.objects.create(nombre="Contabilidad", codigo="CONT")

        cls.jefe_ti, cls.user_jefe_ti = crear_empleado(
            "80100001", "jefe_ti", "Jefe", "Alfa", cls.area_ti,
            grupos=("Jefes de área",), cargo="Jefe de Tecnología",
        )
        cls.empleado1, cls.user_empleado1 = crear_empleado(
            "80100002", "empleado1", "Ana", "Tirado", cls.area_ti,
            grupos=("Empleados",), cargo="Desarrolladora",
        )
        cls.empleado2, cls.user_empleado2 = crear_empleado(
            "80100003", "empleado2", "Bruno", "Ticona", cls.area_ti,
            grupos=("Empleados",), cargo="Soporte",
        )
        cls.jefe_oper, cls.user_jefe_oper = crear_empleado(
            "80100004", "jefe_oper", "Jefe", "Omega", cls.area_oper,
            grupos=("Jefes de área",), cargo="Jefe de Operaciones",
        )
        cls.empleado3, cls.user_empleado3 = crear_empleado(
            "80100005", "empleado3", "Oscar", "Operario", cls.area_oper,
            grupos=("Empleados",), cargo="Operario",
        )
        cls.rrhh1, cls.user_rrhh = crear_empleado(
            "80100006", "rrhh1", "Rosa", "Humanos", cls.area_rrhh,
            grupos=("Recursos Humanos",), cargo="Analista de RRHH",
        )
        cls.contador, cls.user_contador = crear_empleado(
            "80100007", "contador1", "Carla", "Contable", cls.area_cont,
            grupos=("Contadores",), cargo="Contador",
        )

        cls.area_ti.jefe = cls.jefe_ti
        cls.area_ti.save(update_fields=["jefe"])
        cls.area_oper.jefe = cls.jefe_oper
        cls.area_oper.save(update_fields=["jefe"])
        cls.area_rrhh.jefe = cls.rrhh1
        cls.area_rrhh.save(update_fields=["jefe"])
        cls.area_cont.jefe = cls.contador
        cls.area_cont.save(update_fields=["jefe"])

    # ------------------------------------------------------------------
    def crear_registro(
        self, empleado=None, *, fecha=None, entrada=time(8, 0),
        salida=time(17, 0), observacion="Registro de prueba",
    ):
        return RegistroAsistencia.objects.create(
            empleado=empleado or self.empleado1,
            fecha=fecha or fecha_habil(-1),
            hora_entrada=entrada, hora_salida=salida,
            observacion=observacion,
        )

    def crear_solicitud(self, empleado=None, usuario=None, **overrides):
        datos = {
            "empleado": empleado or self.empleado1,
            "tipo": Solicitud.Tipo.PERMISO,
            "fecha_inicio": fecha_habil(3),
            "fecha_fin": fecha_habil(3),
            "motivo": "Permiso solicitado por trámite personal justificado.",
            "usuario": usuario or self.user_empleado1,
        }
        datos.update(overrides)
        return services.crear_solicitud(**datos)


class ModeloAsistenciaTest(BaseAsistenciaTest):
    def test_dni_debe_tener_ocho_digitos(self):
        empleado = Empleado(
            dni="1234567", nombres="Prueba", apellidos="DNI",
            email="prueba.dni@tecnoandes.pe", cargo="Analista",
            area=self.area_ti, fecha_ingreso=timezone.localdate() - timedelta(days=10),
        )
        with self.assertRaises(ValidationError) as ctx:
            empleado.full_clean()
        self.assertIn("dni", ctx.exception.message_dict)

    def test_correo_debe_ser_corporativo(self):
        empleado = Empleado(
            dni="80100099", nombres="Prueba", apellidos="Correo",
            email="prueba@gmail.com", cargo="Analista",
            area=self.area_ti, fecha_ingreso=timezone.localdate() - timedelta(days=10),
        )
        with self.assertRaises(ValidationError) as ctx:
            empleado.full_clean()
        self.assertIn("email", ctx.exception.message_dict)

    def test_fecha_ingreso_no_puede_ser_futura(self):
        empleado = Empleado(
            dni="80100098", nombres="Prueba", apellidos="Futuro",
            email="prueba.futuro@tecnoandes.pe", cargo="Analista",
            area=self.area_ti, fecha_ingreso=timezone.localdate() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError) as ctx:
            empleado.full_clean()
        self.assertIn("fecha_ingreso", ctx.exception.message_dict)

    def test_jornada_de_ocho_horas_sin_extra(self):
        registro = self.crear_registro(entrada=time(8, 0), salida=time(16, 0))
        self.assertEqual(registro.total_horas, 8)
        self.assertEqual(registro.total_extra, 0)
        self.assertTrue(registro.esta_completo)

    def test_horas_extra_cuando_supera_la_jornada(self):
        registro = self.crear_registro(entrada=time(8, 0), salida=time(17, 30))
        self.assertEqual(registro.total_horas, 9.5)
        self.assertEqual(registro.total_extra, 1.5)
        self.assertTrue(registro.tiene_extra)

    def test_salida_debe_ser_posterior_a_la_entrada(self):
        registro = RegistroAsistencia(
            empleado=self.empleado1, fecha=fecha_habil(-1),
            hora_entrada=time(17, 0), hora_salida=time(8, 0),
        )
        with self.assertRaises(ValidationError) as ctx:
            registro.full_clean()
        self.assertIn("hora_salida", ctx.exception.message_dict)

    def test_no_permite_asistencia_futura(self):
        registro = RegistroAsistencia(
            empleado=self.empleado1, fecha=timezone.localdate() + timedelta(days=1),
            hora_entrada=time(8, 0), hora_salida=time(16, 0),
        )
        with self.assertRaises(ValidationError) as ctx:
            registro.full_clean()
        self.assertIn("fecha", ctx.exception.message_dict)

    def test_no_permite_dos_registros_el_mismo_dia(self):
        fecha = fecha_habil(-1)
        self.crear_registro(fecha=fecha)
        with self.assertRaises(ValidationError):
            RegistroAsistencia.objects.create(
                empleado=self.empleado1, fecha=fecha,
                hora_entrada=time(8, 0), hora_salida=time(16, 0),
            )


class MarcacionServiceTest(BaseAsistenciaTest):
    def test_marcar_entrada_y_salida(self):
        momento = timezone.localtime() - timedelta(days=1)
        momento = momento.replace(hour=8, minute=0, second=0, microsecond=0)
        registro = services.marcar_entrada(
            self.empleado1, usuario=self.user_empleado1, ahora=momento
        )
        self.assertEqual(registro.hora_entrada, time(8, 0))
        salida = momento.replace(hour=17, minute=15)
        registro = services.marcar_salida(
            self.empleado1, usuario=self.user_empleado1, ahora=salida
        )
        self.assertEqual(registro.hora_salida, time(17, 15))
        self.assertEqual(registro.total_horas, 9.25)
        self.assertTrue(
            AuditoriaAsistencia.objects.filter(
                accion=AuditoriaAsistencia.Accion.MARCACION, empleado=self.empleado1
            ).count() >= 2
        )

    def test_no_permite_doble_entrada(self):
        momento = timezone.localtime() - timedelta(days=1)
        momento = momento.replace(hour=8, minute=0, second=0, microsecond=0)
        services.marcar_entrada(self.empleado1, usuario=self.user_empleado1, ahora=momento)
        with self.assertRaises(services.ErrorAsistencia):
            services.marcar_entrada(
                self.empleado1, usuario=self.user_empleado1, ahora=momento
            )

    def test_salida_sin_entrada_es_rechazada(self):
        momento = timezone.localtime() - timedelta(days=1)
        momento = momento.replace(hour=17, minute=0, second=0, microsecond=0)
        RegistroAsistencia.objects.create(
            empleado=self.empleado2, fecha=momento.date(),
            observacion="Sin entrada",
        )
        with self.assertRaises(services.ErrorAsistencia):
            services.marcar_salida(
                self.empleado2, usuario=self.user_empleado2, ahora=momento
            )


class CorreccionTest(BaseAsistenciaTest):
    def setUp(self):
        self.registro = self.crear_registro(
            empleado=self.empleado1,
            fecha=fecha_pasada_habil(),
            entrada=time(8, 15), salida=time(16, 45),
        )
        self.justificacion = (
            "El colaborador registró su ingreso con retraso por una incidencia "
            "del sistema biométrico y Recursos Humanos regulariza la marcación."
        )

    def test_solo_rrhh_puede_corregir(self):
        with self.assertRaises(services.ErrorAsistencia):
            services.corregir_asistencia(
                self.registro, usuario=self.user_jefe_ti,
                hora_entrada=time(8, 0), hora_salida=time(17, 0),
                justificacion=self.justificacion,
            )

    def test_justificacion_menor_a_cincuenta_caracteres_es_rechazada(self):
        with self.assertRaises(services.ErrorAsistencia):
            services.corregir_asistencia(
                self.registro, usuario=self.user_rrhh,
                hora_entrada=time(8, 0), hora_salida=time(17, 0),
                justificacion="Justificación demasiado corta para el registro.",
            )
        self.registro.refresh_from_db()
        self.assertEqual(self.registro.hora_entrada, time(8, 15))

    def test_rrhh_corrige_y_registra_auditoria(self):
        correccion = services.corregir_asistencia(
            self.registro, usuario=self.user_rrhh,
            hora_entrada=time(8, 0), hora_salida=time(17, 0),
            justificacion=self.justificacion,
        )
        self.registro.refresh_from_db()
        self.assertEqual(self.registro.hora_entrada, time(8, 0))
        self.assertEqual(self.registro.hora_salida, time(17, 0))
        self.assertEqual(correccion.hora_entrada_anterior, time(8, 15))
        self.assertEqual(correccion.hora_salida_anterior, time(16, 45))
        self.assertTrue(
            AuditoriaAsistencia.objects.filter(
                accion=AuditoriaAsistencia.Accion.CORRECCION
            ).exists()
        )

    def test_correccion_es_inmutable(self):
        correccion = services.corregir_asistencia(
            self.registro, usuario=self.user_rrhh,
            hora_entrada=time(8, 0), hora_salida=time(17, 0),
            justificacion=self.justificacion,
        )
        correccion = CorreccionAsistencia.objects.get(pk=correccion.pk)
        correccion.justificacion = "Intento de modificación posterior no permitido."
        with self.assertRaises(ValidationError):
            correccion.save()

    def test_horas_corregidas_recalculan_extra(self):
        services.corregir_asistencia(
            self.registro, usuario=self.user_rrhh,
            hora_entrada=time(8, 0), hora_salida=time(18, 0),
            justificacion=self.justificacion,
        )
        self.registro.refresh_from_db()
        self.assertEqual(self.registro.total_horas, 10)
        self.assertEqual(self.registro.total_extra, 2)


class SolicitudReglasTest(BaseAsistenciaTest):
    def test_crear_solicitud_valida(self):
        solicitud = self.crear_solicitud()
        self.assertEqual(solicitud.estado, Solicitud.Estado.PENDIENTE)
        self.assertEqual(solicitud.dias_solicitados, 1)
        self.assertTrue(
            AuditoriaAsistencia.objects.filter(
                accion=AuditoriaAsistencia.Accion.SOLICITUD
            ).exists()
        )

    def test_motivo_minimo_veinte_caracteres(self):
        with self.assertRaises(ValidationError):
            self.crear_solicitud(motivo="Corto")

    def test_fecha_fin_no_anterior_al_inicio(self):
        inicio = fecha_habil(4)
        with self.assertRaises(ValidationError) as ctx:
            self.crear_solicitud(fecha_inicio=inicio, fecha_fin=inicio - timedelta(days=2))
        self.assertIn("fecha_fin", ctx.exception.message_dict)

    def test_solicitud_debe_iniciar_en_dia_habil(self):
        sabado = proximo_dia(5)
        with self.assertRaises(ValidationError) as ctx:
            self.crear_solicitud(fecha_inicio=sabado, fecha_fin=sabado)
        self.assertIn("fecha_inicio", ctx.exception.message_dict)

    def test_no_permite_fechas_pasadas(self):
        ayer = timezone.localdate() - timedelta(days=1)
        while ayer.weekday() >= 5:
            ayer -= timedelta(days=1)
        with self.assertRaises(ValidationError) as ctx:
            self.crear_solicitud(fecha_inicio=ayer, fecha_fin=ayer)
        self.assertIn("fecha_inicio", ctx.exception.message_dict)

    def test_no_permite_solicitudes_superpuestas(self):
        primer_dia = fecha_habil(3)
        self.crear_solicitud(fecha_inicio=primer_dia, fecha_fin=primer_dia)
        with self.assertRaises(ValidationError) as ctx:
            self.crear_solicitud(
                fecha_inicio=primer_dia, fecha_fin=primer_dia,
                motivo="Segunda solicitud que se superpone con la anterior.",
            )
        self.assertIn("fecha_inicio", ctx.exception.message_dict)

    def test_dias_habiles_excluyen_fin_de_semana(self):
        viernes = proximo_dia(4)
        lunes = viernes + timedelta(days=3)
        self.assertEqual(dias_habiles(viernes, lunes), 2)

    def test_saldo_anual_de_treinta_dias(self):
        inicio, fin, anio = treinta_dias_habiles()
        Solicitud.objects.create(
            empleado=self.empleado2, tipo=Solicitud.Tipo.VACACIONES,
            fecha_inicio=inicio, fecha_fin=fin,
            motivo="Vacaciones anuales completas del colaborador.",
            estado=Solicitud.Estado.APROBADA,
        )
        self.assertEqual(self.empleado2.saldo_disponible(anio), 0)
        siguiente = fin + timedelta(days=1)
        while siguiente.weekday() >= 5:
            siguiente += timedelta(days=1)
        with self.assertRaises(ValidationError) as ctx:
            self.crear_solicitud(
                empleado=self.empleado2, usuario=self.user_empleado2,
                fecha_inicio=siguiente, fecha_fin=siguiente,
                motivo="Solicitud adicional sin saldo anual disponible.",
            )
        self.assertIn("Saldo insuficiente", str(ctx.exception))

    def test_saldo_disminuye_con_solicitud_aprobada(self):
        solicitud = self.crear_solicitud()
        services.resolver_solicitud(
            solicitud, usuario=self.user_jefe_ti, aprobar=True
        )
        self.assertEqual(self.empleado1.saldo_disponible(), 29)

    def test_solicitud_pendiente_no_afecta_saldo(self):
        self.crear_solicitud()
        self.assertEqual(self.empleado1.saldo_disponible(), 30)


class AprobacionSolicitudTest(BaseAsistenciaTest):
    def test_jefe_del_area_puede_aprobar(self):
        solicitud = self.crear_solicitud()
        services.resolver_solicitud(
            solicitud, usuario=self.user_jefe_ti, aprobar=True,
            comentario="Aprobado por el jefe inmediato.",
        )
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, Solicitud.Estado.APROBADA)
        self.assertEqual(solicitud.revisado_por, self.user_jefe_ti)
        self.assertIsNotNone(solicitud.fecha_revision)

    def test_rrhh_puede_aprobar_cualquier_area(self):
        solicitud = self.crear_solicitud(
            empleado=self.empleado3, usuario=self.user_empleado3,
            fecha_inicio=fecha_habil(4), fecha_fin=fecha_habil(4),
        )
        services.resolver_solicitud(
            solicitud, usuario=self.user_rrhh, aprobar=True
        )
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, Solicitud.Estado.APROBADA)

    def test_jefe_de_otra_area_no_puede_aprobar(self):
        solicitud = self.crear_solicitud(
            empleado=self.empleado3, usuario=self.user_empleado3,
            fecha_inicio=fecha_habil(4), fecha_fin=fecha_habil(4),
        )
        with self.assertRaises(services.ErrorAsistencia):
            services.resolver_solicitud(
                solicitud, usuario=self.user_jefe_ti, aprobar=True
            )
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, Solicitud.Estado.PENDIENTE)

    def test_nadie_puede_aprobar_su_propia_solicitud(self):
        solicitud = self.crear_solicitud(
            empleado=self.jefe_ti, usuario=self.user_jefe_ti,
            fecha_inicio=fecha_habil(5), fecha_fin=fecha_habil(5),
        )
        with self.assertRaises(services.ErrorAsistencia):
            services.resolver_solicitud(
                solicitud, usuario=self.user_jefe_ti, aprobar=True
            )
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, Solicitud.Estado.PENDIENTE)

    def test_rrhh_tampoco_puede_aprobar_su_propia_solicitud(self):
        solicitud = self.crear_solicitud(
            empleado=self.rrhh1, usuario=self.user_rrhh,
            fecha_inicio=fecha_habil(6), fecha_fin=fecha_habil(6),
        )
        with self.assertRaises(services.ErrorAsistencia):
            services.resolver_solicitud(
                solicitud, usuario=self.user_rrhh, aprobar=True
            )

    def test_empleado_no_puede_aprobar(self):
        solicitud = self.crear_solicitud()
        with self.assertRaises(services.ErrorAsistencia):
            services.resolver_solicitud(
                solicitud, usuario=self.user_empleado1, aprobar=True
            )

    def test_rechazo_registra_estado_y_comentario(self):
        solicitud = self.crear_solicitud()
        services.resolver_solicitud(
            solicitud, usuario=self.user_jefe_ti, aprobar=False,
            comentario="No procede por carga operativa del área.",
        )
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, Solicitud.Estado.RECHAZADA)
        self.assertIn("carga operativa", solicitud.comentario_revision)

    def test_no_se_resuelve_dos_veces(self):
        solicitud = self.crear_solicitud()
        services.resolver_solicitud(solicitud, usuario=self.user_jefe_ti, aprobar=True)
        with self.assertRaises(services.ErrorAsistencia):
            services.resolver_solicitud(
                solicitud, usuario=self.user_jefe_ti, aprobar=False
            )


class VistasAsistenciaTest(BaseAsistenciaTest):
    def test_anonimo_es_redirigido_al_login(self):
        respuesta = self.client.get(reverse("asistencia:dashboard"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("asistencia:login"), respuesta["Location"])

    def test_empleado_marca_entrada_y_salida(self):
        self.client.force_login(self.user_empleado1)
        respuesta = self.client.post(reverse("asistencia:marcar_asistencia"))
        self.assertEqual(respuesta.status_code, 302)
        registro = RegistroAsistencia.objects.get(
            empleado=self.empleado1, fecha=timezone.localdate()
        )
        self.assertIsNotNone(registro.hora_entrada)
        registro.hora_entrada = time(0, 0)
        registro.save()
        self.client.post(reverse("asistencia:marcar_asistencia"))
        registro.refresh_from_db()
        self.assertIsNotNone(registro.hora_salida)

    def test_empleado_no_accede_a_registros_generales(self):
        self.client.force_login(self.user_empleado1)
        respuesta = self.client.get(reverse("asistencia:registros"))
        self.assertEqual(respuesta.status_code, 403)
        self.assertTrue(
            AuditoriaAsistencia.objects.filter(
                accion=AuditoriaAsistencia.Accion.ACCESO_DENEGADO
            ).exists()
        )

    def test_jefe_solo_ve_registros_de_su_area(self):
        self.crear_registro(empleado=self.empleado1, fecha=timezone.localdate())
        self.crear_registro(empleado=self.empleado3, fecha=timezone.localdate())
        self.client.force_login(self.user_jefe_ti)
        respuesta = self.client.get(reverse("asistencia:registros"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Tirado")
        self.assertNotContains(respuesta, "Operario")

    def test_rrhh_ve_registros_de_todas_las_areas(self):
        self.crear_registro(empleado=self.empleado1, fecha=timezone.localdate())
        self.crear_registro(empleado=self.empleado3, fecha=timezone.localdate())
        self.client.force_login(self.user_rrhh)
        respuesta = self.client.get(reverse("asistencia:registros"))
        self.assertContains(respuesta, "Tirado")
        self.assertContains(respuesta, "Operario")

    def test_contador_tiene_acceso_solo_lectura(self):
        registro = self.crear_registro(fecha=timezone.localdate())
        self.client.force_login(self.user_contador)
        self.assertEqual(
            self.client.get(reverse("asistencia:registros")).status_code, 200
        )
        self.assertEqual(
            self.client.get(
                reverse("asistencia:corregir_registro", args=[registro.pk])
            ).status_code,
            403,
        )
        respuesta = self.client.post(
            reverse("asistencia:corregir_registro", args=[registro.pk]),
            {
                "hora_entrada": "08:00", "hora_salida": "17:00",
                "justificacion": (
                    "Intento de corrección por un usuario contador que no tiene "
                    "permiso para modificar asistencias."
                ),
            },
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_rrhh_corrige_desde_la_vista(self):
        registro = self.crear_registro(
            fecha=fecha_pasada_habil(), entrada=time(8, 30), salida=time(16, 30)
        )
        self.client.force_login(self.user_rrhh)
        respuesta = self.client.post(
            reverse("asistencia:corregir_registro", args=[registro.pk]),
            {
                "hora_entrada": "08:00", "hora_salida": "17:00",
                "justificacion": (
                    "El colaborador olvidó marcar su salida y Recursos Humanos "
                    "regulariza la jornada con sustento verificable."
                ),
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        registro.refresh_from_db()
        self.assertEqual(registro.hora_salida, time(17, 0))

    def test_justificacion_corta_no_corrige(self):
        registro = self.crear_registro(fecha=fecha_pasada_habil())
        self.client.force_login(self.user_rrhh)
        respuesta = self.client.post(
            reverse("asistencia:corregir_registro", args=[registro.pk]),
            {
                "hora_entrada": "08:00", "hora_salida": "17:00",
                "justificacion": "Texto insuficiente.",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "al menos 50 caracteres")
        self.assertFalse(
            CorreccionAsistencia.objects.filter(registro=registro).exists()
        )

    def test_empleado_crea_solicitud_propia(self):
        self.client.force_login(self.user_empleado1)
        dia = fecha_habil(3)
        respuesta = self.client.post(
            reverse("asistencia:solicitud_crear"),
            {
                "tipo": "permiso", "fecha_inicio": dia.isoformat(),
                "fecha_fin": dia.isoformat(),
                "motivo": "Permiso por trámite personal debidamente justificado.",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        solicitud = Solicitud.objects.get(empleado=self.empleado1)
        self.assertEqual(solicitud.estado, Solicitud.Estado.PENDIENTE)

    def test_empleado_no_puede_crear_solicitud_para_otro(self):
        self.client.force_login(self.user_empleado1)
        dia = fecha_habil(5)
        self.client.post(
            reverse("asistencia:solicitud_crear"),
            {
                "empleado": self.empleado3.pk,
                "tipo": "permiso", "fecha_inicio": dia.isoformat(),
                "fecha_fin": dia.isoformat(),
                "motivo": "Intento de crear una solicitud a nombre de otro.",
            },
        )
        self.assertTrue(Solicitud.objects.filter(empleado=self.empleado1).exists())
        self.assertFalse(Solicitud.objects.filter(empleado=self.empleado3).exists())

    def test_jefe_aprueba_solicitud_desde_la_vista(self):
        solicitud = self.crear_solicitud()
        self.client.force_login(self.user_jefe_ti)
        respuesta = self.client.post(
            reverse("asistencia:resolver_solicitud", args=[solicitud.pk]),
            {"accion": "aprobar", "comentario": "Conforme."},
        )
        self.assertEqual(respuesta.status_code, 302)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, Solicitud.Estado.APROBADA)

    def test_jefe_no_aprueba_solicitud_de_otra_area(self):
        solicitud = self.crear_solicitud(
            empleado=self.empleado3, usuario=self.user_empleado3,
            fecha_inicio=fecha_habil(5), fecha_fin=fecha_habil(5),
        )
        self.client.force_login(self.user_jefe_ti)
        respuesta = self.client.post(
            reverse("asistencia:resolver_solicitud", args=[solicitud.pk]),
            {"accion": "aprobar"},
        )
        self.assertEqual(respuesta.status_code, 403)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, Solicitud.Estado.PENDIENTE)

    def test_autoaprobacion_desde_la_vista_es_403(self):
        solicitud = self.crear_solicitud(
            empleado=self.jefe_ti, usuario=self.user_jefe_ti,
            fecha_inicio=fecha_habil(6), fecha_fin=fecha_habil(6),
        )
        self.client.force_login(self.user_jefe_ti)
        respuesta = self.client.post(
            reverse("asistencia:resolver_solicitud", args=[solicitud.pk]),
            {"accion": "aprobar"},
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_empleado_no_ve_solicitud_de_otra_area(self):
        solicitud = self.crear_solicitud(
            empleado=self.empleado3, usuario=self.user_empleado3,
            fecha_inicio=fecha_habil(7), fecha_fin=fecha_habil(7),
        )
        self.client.force_login(self.user_empleado1)
        respuesta = self.client.get(
            reverse("asistencia:solicitud_detalle", args=[solicitud.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_empleado_cancela_su_solicitud_pendiente(self):
        solicitud = self.crear_solicitud()
        self.client.force_login(self.user_empleado1)
        respuesta = self.client.post(
            reverse("asistencia:cancelar_solicitud", args=[solicitud.pk])
        )
        self.assertEqual(respuesta.status_code, 302)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, Solicitud.Estado.CANCELADA)

    def test_empleado_no_accede_al_listado_de_empleados(self):
        self.client.force_login(self.user_empleado1)
        self.assertEqual(
            self.client.get(reverse("asistencia:empleados")).status_code, 403
        )

    def test_jefe_ve_solo_empleados_de_su_area(self):
        self.client.force_login(self.user_jefe_ti)
        respuesta = self.client.get(reverse("asistencia:empleados"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Tirado")
        self.assertNotContains(respuesta, "Operario")

    def test_empleado_ve_su_ficha_pero_no_la_de_otro(self):
        self.client.force_login(self.user_empleado1)
        self.assertEqual(
            self.client.get(
                reverse("asistencia:empleado_detalle", args=[self.empleado1.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("asistencia:empleado_detalle", args=[self.empleado3.pk])
            ).status_code,
            403,
        )

    def test_rrhh_crea_empleado_con_correo_corporativo(self):
        self.client.force_login(self.user_rrhh)
        respuesta = self.client.post(
            reverse("asistencia:empleado_crear"),
            {
                "dni": "80100050", "nombres": "Nuevo", "apellidos": "Ingreso",
                "email": "nuevo.ingreso@tecnoandes.pe", "cargo": "Analista",
                "area": self.area_ti.pk,
                "fecha_ingreso": fecha_pasada_habil().isoformat(),
                "activo": "on", "sueldo_basico": "2600.00",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Empleado.objects.filter(dni="80100050").exists())

    def test_rrhh_rechaza_correo_externo(self):
        self.client.force_login(self.user_rrhh)
        respuesta = self.client.post(
            reverse("asistencia:empleado_crear"),
            {
                "dni": "80100051", "nombres": "Nuevo", "apellidos": "Externo",
                "email": "nuevo@gmail.com", "cargo": "Analista",
                "area": self.area_ti.pk,
                "fecha_ingreso": fecha_pasada_habil().isoformat(),
                "activo": "on", "sueldo_basico": "2600.00",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "@tecnoandes.pe")
        self.assertFalse(Empleado.objects.filter(dni="80100051").exists())


class SesionTest(BaseAsistenciaTest):
    def test_sesion_expira_tras_cuarenta_y_cinco_minutos(self):
        self.client.force_login(self.user_empleado1)
        sesion = self.client.session
        sesion["ultima_actividad"] = (
            timezone.now() - timedelta(minutes=46)
        ).isoformat()
        sesion.save()
        respuesta = self.client.get(reverse("asistencia:dashboard"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("expirada=1", respuesta["Location"])
        self.assertIsNone(self.client.session.get("_auth_user_id"))

    def test_sesion_activa_a_los_treinta_minutos(self):
        self.client.force_login(self.user_empleado1)
        sesion = self.client.session
        sesion["ultima_actividad"] = (
            timezone.now() - timedelta(minutes=30)
        ).isoformat()
        sesion.save()
        self.assertEqual(
            self.client.get(reverse("asistencia:dashboard")).status_code, 200
        )

    def test_login_registra_auditoria(self):
        respuesta = self.client.post(
            reverse("asistencia:login"),
            {"username": "empleado1", "password": "Clave12345!"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            AuditoriaAsistencia.objects.filter(
                accion=AuditoriaAsistencia.Accion.LOGIN, usuario=self.user_empleado1
            ).exists()
        )

    def test_logout_requiere_post(self):
        self.client.force_login(self.user_empleado1)
        self.assertEqual(
            self.client.get(reverse("asistencia:logout")).status_code, 405
        )


class AdminTest(BaseAsistenciaTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = Usuario.objects.create_superuser(
            "admin_asistencia_test", "admin.test@tecnoandes.pe", "Clave12345!"
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_changelist_de_solicitudes_carga(self):
        self.assertEqual(
            self.client.get(
                reverse("admin:asistencia_solicitud_changelist")
            ).status_code,
            200,
        )

    def test_accion_admin_aprueba_solicitud(self):
        solicitud = self.crear_solicitud()
        respuesta = self.client.post(
            reverse("admin:asistencia_solicitud_changelist"),
            {
                "action": "aprobar_solicitudes",
                "_selected_action": [str(solicitud.pk)],
                "index": "0",
            },
            follow=True,
        )
        self.assertEqual(respuesta.status_code, 200)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, Solicitud.Estado.APROBADA)

    def test_registro_de_asistencia_es_solo_lectura_en_admin(self):
        self.assertEqual(
            self.client.get(
                reverse("admin:asistencia_registroasistencia_add")
            ).status_code,
            403,
        )
