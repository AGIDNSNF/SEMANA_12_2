"""Pruebas automatizadas del Caso 2 · Plataforma de Consultas Médicas.

Cubren validaciones de negocio, horarios, inmutabilidad de consultas,
autorización sobre historiales, auditoría, sesión y vistas principales.

Ejecutar:  python manage.py test consultas
"""
from datetime import time, timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .horarios import hora_fin, validar_horario_general, validar_horario_medico
from .models import (
    AuditoriaMedica,
    Cita,
    Consulta,
    Especialidad,
    HorarioAtencion,
    Medico,
    NotaClinica,
    Paciente,
)
from .services import ErrorCita, agregar_nota, agendar_cita, registrar_consulta
from .validators import sanitizar_texto

Usuario = get_user_model()


def fecha_habil(dias=1):
    """Fecha futura que no cae en domingo (el centro no atiende domingos)."""
    fecha = timezone.localdate() + timedelta(days=dias)
    while fecha.weekday() == 6:
        fecha += timedelta(days=1)
    return fecha


def proximo_dia(weekday):
    """Próxima fecha futura con el día de semana indicado (0=lunes)."""
    fecha = timezone.localdate() + timedelta(days=1)
    while fecha.weekday() != weekday:
        fecha += timedelta(days=1)
    return fecha


class BaseConsultasTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.especialidad = Especialidad.objects.create(
            nombre="Medicina General", descripcion="Atención primaria."
        )
        cls.otra_especialidad = Especialidad.objects.create(nombre="Cardiología")

        cls.user_medico = Usuario.objects.create_user(
            "medico_test", password="Clave12345!", first_name="Lucía", last_name="Ramírez"
        )
        cls.medico = Medico.objects.create(
            nombres="Lucía", apellidos="Ramírez Ponce", cmp="12345",
            especialidad=cls.especialidad, consultorio="101", usuario=cls.user_medico,
        )
        cls.user_otro_medico = Usuario.objects.create_user(
            "medico_otro", password="Clave12345!", first_name="Jorge", last_name="Salazar"
        )
        cls.otro_medico = Medico.objects.create(
            nombres="Jorge", apellidos="Salazar Vega", cmp="54321",
            especialidad=cls.otra_especialidad, consultorio="102",
            usuario=cls.user_otro_medico,
        )

        for medico in (cls.medico, cls.otro_medico):
            for dia in range(5):
                for inicio, fin in ((time(8, 0), time(12, 0)), (time(14, 0), time(18, 0))):
                    HorarioAtencion.objects.create(
                        medico=medico, dia_semana=dia,
                        hora_inicio=inicio, hora_fin=fin,
                    )
            HorarioAtencion.objects.create(
                medico=medico, dia_semana=5,
                hora_inicio=time(8, 0), hora_fin=time(13, 0),
            )

        cls.user_paciente = Usuario.objects.create_user(
            "paciente_test", password="Clave12345!", first_name="Camila", last_name="Quispe"
        )
        cls.paciente = Paciente.objects.create(
            dni="70000001", nombres="Camila", apellidos="Quispe Rojas",
            fecha_nacimiento=timezone.localdate() - timedelta(days=20 * 365),
            tipo=Paciente.Tipo.ESTUDIANTE, codigo_uncp="20240001",
            email="camila.quispe@uncp.edu.pe", usuario=cls.user_paciente,
        )
        cls.user_paciente2 = Usuario.objects.create_user(
            "paciente_dos", password="Clave12345!", first_name="Mateo", last_name="Paredes"
        )
        cls.paciente2 = Paciente.objects.create(
            dni="70000002", nombres="Mateo", apellidos="Paredes Silva",
            fecha_nacimiento=timezone.localdate() - timedelta(days=19 * 365),
            tipo=Paciente.Tipo.ESTUDIANTE, codigo_uncp="20240002",
            email="mateo.paredes@uncp.edu.pe", usuario=cls.user_paciente2,
        )

        cls.grupo_medicos, _ = Group.objects.get_or_create(name="Médicos")
        cls.grupo_recepcion, _ = Group.objects.get_or_create(name="Recepcionistas")

    # ------------------------------------------------------------------
    def crear_cita(
        self, *, medico=None, paciente=None, fecha=None, hora=None,
        estado=Cita.Estado.CONFIRMADA, motivo=None,
    ):
        cita = Cita(
            medico=medico or self.medico,
            paciente=paciente or self.paciente,
            especialidad=(medico or self.medico).especialidad,
            fecha=fecha or fecha_habil(1),
            hora=hora or time(8, 0),
            motivo=motivo or "Control general por síntomas persistentes.",
            estado=estado,
        )
        cita.full_clean()
        cita.save()
        return cita

    def crear_usuario_recepcion(self, username="recepcion_test", con_permiso=False):
        usuario = Usuario.objects.create_user(username, password="Clave12345!")
        usuario.groups.add(self.grupo_recepcion)
        if con_permiso:
            permisos = Permission.objects.filter(
                content_type__app_label="consultas",
                codename__in=["agendar_cita", "cancelar_cita"],
            )
            usuario.user_permissions.set(permisos)
            usuario = Usuario.objects.get(pk=usuario.pk)
        return usuario


class ValidacionesModeloTest(BaseConsultasTest):
    def test_dni_debe_tener_ocho_digitos(self):
        paciente = Paciente(
            dni="1234567", nombres="Ana", apellidos="Prueba",
            fecha_nacimiento=timezone.localdate() - timedelta(days=365 * 20),
            tipo=Paciente.Tipo.ESTUDIANTE, email="ana@uncp.edu.pe",
        )
        with self.assertRaises(ValidationError) as ctx:
            paciente.full_clean()
        self.assertIn("dni", ctx.exception.message_dict)

    def test_dni_no_admite_letras(self):
        paciente = Paciente(
            dni="1234ABCD", nombres="Ana", apellidos="Prueba",
            fecha_nacimiento=timezone.localdate() - timedelta(days=365 * 20),
            tipo=Paciente.Tipo.ESTUDIANTE, email="ana@uncp.edu.pe",
        )
        with self.assertRaises(ValidationError) as ctx:
            paciente.full_clean()
        self.assertIn("dni", ctx.exception.message_dict)

    def test_cmp_debe_tener_cinco_digitos(self):
        medico = Medico(
            nombres="Carlos", apellidos="Prueba", cmp="1234",
            especialidad=self.especialidad, consultorio="201",
        )
        with self.assertRaises(ValidationError) as ctx:
            medico.full_clean()
        self.assertIn("cmp", ctx.exception.message_dict)

    def test_fecha_nacimiento_no_puede_ser_futura(self):
        paciente = Paciente(
            dni="70000099", nombres="Futuro", apellidos="Prueba",
            fecha_nacimiento=timezone.localdate() + timedelta(days=5),
            tipo=Paciente.Tipo.ESTUDIANTE, email="futuro@uncp.edu.pe",
        )
        with self.assertRaises(ValidationError) as ctx:
            paciente.full_clean()
        self.assertIn("fecha_nacimiento", ctx.exception.message_dict)

    def test_estudiante_requiere_correo_institucional(self):
        paciente = Paciente(
            dni="70000098", nombres="Estudiante", apellidos="Prueba",
            fecha_nacimiento=timezone.localdate() - timedelta(days=365 * 18),
            tipo=Paciente.Tipo.ESTUDIANTE, email="estudiante@gmail.com",
        )
        with self.assertRaises(ValidationError) as ctx:
            paciente.full_clean()
        self.assertIn("email", ctx.exception.message_dict)

    def test_docente_puede_usar_otro_dominio(self):
        paciente = Paciente(
            dni="70000097", nombres="Docente", apellidos="Prueba",
            fecha_nacimiento=timezone.localdate() - timedelta(days=365 * 40),
            tipo=Paciente.Tipo.DOCENTE, email="docente@gmail.com",
        )
        paciente.full_clean()

    def test_dni_duplicado_es_rechazado(self):
        paciente = Paciente(
            dni=self.paciente.dni, nombres="Duplicado", apellidos="Prueba",
            fecha_nacimiento=timezone.localdate() - timedelta(days=365 * 20),
            tipo=Paciente.Tipo.ESTUDIANTE, email="duplicado@uncp.edu.pe",
        )
        with self.assertRaises(ValidationError) as ctx:
            paciente.full_clean()
        self.assertIn("dni", ctx.exception.message_dict)

    def test_cmp_duplicado_es_rechazado(self):
        medico = Medico(
            nombres="Duplicado", apellidos="Prueba", cmp=self.medico.cmp,
            especialidad=self.especialidad, consultorio="202",
        )
        with self.assertRaises(ValidationError) as ctx:
            medico.full_clean()
        self.assertIn("cmp", ctx.exception.message_dict)

    def test_motivo_minimo_veinte_caracteres(self):
        cita = Cita(
            medico=self.medico, paciente=self.paciente,
            especialidad=self.especialidad, fecha=fecha_habil(1),
            hora=time(8, 0), motivo="Dolor", estado=Cita.Estado.PENDIENTE,
        )
        with self.assertRaises(ValidationError) as ctx:
            cita.full_clean()
        self.assertIn("motivo", ctx.exception.message_dict)

    def test_motivo_se_sanitiza_y_elimina_html(self):
        cita = Cita(
            medico=self.medico, paciente=self.paciente,
            especialidad=self.especialidad, fecha=fecha_habil(1),
            hora=time(8, 0),
            motivo="<b>Dolor</b> de cabeza persistente durante la semana.",
            estado=Cita.Estado.PENDIENTE,
        )
        cita.full_clean()
        cita.save()
        self.assertNotIn("<b>", cita.motivo)
        self.assertIn("Dolor de cabeza", cita.motivo)

    def test_sanitizar_texto_elimina_etiquetas_y_controles(self):
        limpio = sanitizar_texto("<script>alert(1)</script>Texto clínico\x00 válido")
        self.assertNotIn("<script>", limpio)
        self.assertNotIn("\x00", limpio)
        self.assertIn("Texto clínico válido", limpio)


class HorarioTest(BaseConsultasTest):
    def test_domingo_cerrado(self):
        domingo = proximo_dia(6)
        valido, mensaje = validar_horario_general(domingo, time(10, 0))
        self.assertFalse(valido)
        self.assertIn("domingo", mensaje.lower())

    def test_sabado_solo_hasta_trece(self):
        sabado = proximo_dia(5)
        valido, _ = validar_horario_general(sabado, time(13, 30))
        self.assertFalse(valido)
        valido, _ = validar_horario_general(sabado, time(12, 30))
        self.assertTrue(valido)

    def test_semana_antes_de_apertura_y_despues_de_cierre(self):
        lunes = proximo_dia(0)
        self.assertFalse(validar_horario_general(lunes, time(7, 30))[0])
        self.assertFalse(validar_horario_general(lunes, time(18, 0))[0])
        self.assertTrue(validar_horario_general(lunes, time(17, 30))[0])

    def test_cita_de_treinta_minutos_no_puede_pasar_del_cierre(self):
        lunes = proximo_dia(0)
        valido, mensaje = validar_horario_general(lunes, time(17, 45))
        self.assertFalse(valido)
        self.assertIn("cierre", mensaje.lower())
        self.assertEqual(hora_fin(time(17, 30)), time(18, 0))

    def test_horario_declarado_del_medico(self):
        lunes = proximo_dia(0)
        self.assertTrue(validar_horario_medico(self.medico, lunes, time(11, 30))[0])
        # 13:00 está dentro del horario general pero el médico no atiende 12-14.
        valido, mensaje = validar_horario_medico(self.medico, lunes, time(13, 0))
        self.assertFalse(valido)
        self.assertIn("horario de atención del médico", mensaje)

    def test_horarios_superpuestos_del_mismo_medico(self):
        lunes = proximo_dia(0)
        horario = HorarioAtencion(
            medico=self.medico, dia_semana=lunes.weekday(),
            hora_inicio=time(10, 0), hora_fin=time(15, 0),
        )
        with self.assertRaises(ValidationError) as ctx:
            horario.full_clean()
        self.assertIn("hora_inicio", ctx.exception.message_dict)

    def test_cita_en_domingo_rechazada_por_modelo(self):
        cita = Cita(
            medico=self.medico, paciente=self.paciente,
            especialidad=self.especialidad, fecha=proximo_dia(6),
            hora=time(10, 0),
            motivo="Evaluación general solicitada por el paciente.",
            estado=Cita.Estado.PENDIENTE,
        )
        with self.assertRaises(ValidationError) as ctx:
            cita.full_clean()
        self.assertIn("hora", ctx.exception.message_dict)


class CitaReglasTest(BaseConsultasTest):
    def test_agendar_cita_valida(self):
        cita = agendar_cita(
            paciente=self.paciente, medico=self.medico,
            especialidad=self.especialidad, fecha=fecha_habil(1),
            hora=time(8, 0),
            motivo="Control general por síntomas persistentes.",
            usuario=self.user_paciente,
        )
        self.assertEqual(cita.estado, Cita.Estado.PENDIENTE)
        self.assertTrue(
            AuditoriaMedica.objects.filter(
                accion=AuditoriaMedica.Accion.AGENDAR, paciente=self.paciente
            ).exists()
        )

    def test_paciente_no_puede_tener_dos_citas_activas_el_mismo_dia(self):
        dia = fecha_habil(1)
        self.crear_cita(fecha=dia, hora=time(8, 0))
        with self.assertRaises((ValidationError, ErrorCita)) as ctx:
            agendar_cita(
                paciente=self.paciente, medico=self.medico,
                especialidad=self.especialidad, fecha=dia, hora=time(9, 0),
                motivo="Segunda consulta del mismo día no permitida.",
                usuario=self.user_paciente,
            )
        self.assertIn("ya tiene una cita activa", str(ctx.exception))

    def test_medico_no_puede_tener_citas_superpuestas(self):
        dia = fecha_habil(1)
        self.crear_cita(paciente=self.paciente, fecha=dia, hora=time(8, 0))
        with self.assertRaises((ValidationError, ErrorCita)) as ctx:
            agendar_cita(
                paciente=self.paciente2, medico=self.medico,
                especialidad=self.especialidad, fecha=dia, hora=time(8, 15),
                motivo="Cita que se superpone con otra atención.",
                usuario=self.user_paciente2,
            )
        self.assertIn("ya tiene una cita", str(ctx.exception))

    def test_cita_cancelada_libera_la_franja(self):
        dia = fecha_habil(1)
        self.crear_cita(
            paciente=self.paciente, fecha=dia, hora=time(8, 0),
            estado=Cita.Estado.CANCELADA,
        )
        nueva = agendar_cita(
            paciente=self.paciente2, medico=self.medico,
            especialidad=self.especialidad, fecha=dia, hora=time(8, 0),
            motivo="Reprogramación en la misma franja horaria.",
            usuario=self.user_paciente2,
        )
        self.assertEqual(nueva.estado, Cita.Estado.PENDIENTE)

    def test_especialidad_debe_coincidir_con_el_medico(self):
        with self.assertRaises((ValidationError, ErrorCita)) as ctx:
            agendar_cita(
                paciente=self.paciente, medico=self.medico,
                especialidad=self.otra_especialidad, fecha=fecha_habil(1),
                hora=time(8, 0),
                motivo="Consulta con especialidad incorrecta.",
                usuario=self.user_paciente,
            )
        self.assertIn("especialidad", str(ctx.exception).lower())

    def test_no_permite_citas_en_fechas_pasadas(self):
        ayer = timezone.localdate() - timedelta(days=1)
        with self.assertRaises((ValidationError, ErrorCita)) as ctx:
            agendar_cita(
                paciente=self.paciente, medico=self.medico,
                especialidad=self.especialidad, fecha=ayer, hora=time(9, 0),
                motivo="Intento de agendar en una fecha pasada.",
                usuario=self.user_paciente,
            )
        self.assertIn("pasadas", str(ctx.exception).lower())

    def test_servicio_rechaza_medico_inactivo(self):
        self.medico.activo = False
        self.medico.save(update_fields=["activo"])
        with self.assertRaises(ErrorCita):
            agendar_cita(
                paciente=self.paciente, medico=self.medico,
                especialidad=self.especialidad, fecha=fecha_habil(1),
                hora=time(8, 0),
                motivo="Intento de agendar con médico inactivo.",
                usuario=self.user_paciente,
            )

    def test_servicio_rechaza_estado_inicial_no_permitido(self):
        with self.assertRaises(ErrorCita):
            agendar_cita(
                paciente=self.paciente, medico=self.medico,
                especialidad=self.especialidad, fecha=fecha_habil(1),
                hora=time(8, 0),
                motivo="Estado inicial inválido para una cita nueva.",
                estado=Cita.Estado.COMPLETADA,
                usuario=self.user_paciente,
            )


class ConsultaTest(BaseConsultasTest):
    def setUp(self):
        self.cita = self.crear_cita(fecha=fecha_habil(2), hora=time(9, 0))

    def datos_consulta(self):
        return {
            "diagnostico": "Cuadro leve compatible con proceso transitorio.",
            "tratamiento": "Reposo relativo e hidratación durante 48 horas.",
            "medicamentos": "Paracetamol 500 mg cada 8 horas (ficticio).",
        }

    def test_registrar_consulta_completa_la_cita(self):
        consulta = registrar_consulta(
            self.cita, medico=self.medico, usuario=self.user_medico,
            **self.datos_consulta(),
        )
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, Cita.Estado.COMPLETADA)
        self.assertEqual(Consulta.objects.filter(cita=self.cita).count(), 1)
        self.assertEqual(consulta.medico, self.medico)
        self.assertTrue(
            AuditoriaMedica.objects.filter(
                accion=AuditoriaMedica.Accion.CREAR_CONSULTA
            ).exists()
        )

    def test_consulta_registrada_es_inmutable(self):
        consulta = registrar_consulta(
            self.cita, medico=self.medico, usuario=self.user_medico,
            **self.datos_consulta(),
        )
        consulta = Consulta.objects.get(pk=consulta.pk)
        consulta.diagnostico = "Diagnóstico modificado posteriormente."
        with self.assertRaises(ValidationError):
            consulta.save()

    def test_no_se_puede_registrar_dos_consultas_para_la_misma_cita(self):
        registrar_consulta(
            self.cita, medico=self.medico, usuario=self.user_medico,
            **self.datos_consulta(),
        )
        with self.assertRaises(ErrorCita):
            registrar_consulta(
                self.cita, medico=self.medico, usuario=self.user_medico,
                **self.datos_consulta(),
            )

    def test_solo_el_medico_de_la_cita_registra_la_consulta(self):
        with self.assertRaises(ErrorCita):
            registrar_consulta(
                self.cita, medico=self.otro_medico, usuario=self.user_otro_medico,
                **self.datos_consulta(),
            )

    def test_no_se_registra_consulta_de_cita_pendiente(self):
        cita = self.crear_cita(
            paciente=self.paciente2, fecha=fecha_habil(3), hora=time(9, 0),
            estado=Cita.Estado.PENDIENTE,
        )
        with self.assertRaises(ErrorCita):
            registrar_consulta(
                cita, medico=self.medico, usuario=self.user_medico,
                **self.datos_consulta(),
            )

    def test_nota_clinica_amplia_sin_modificar_la_consulta(self):
        consulta = registrar_consulta(
            self.cita, medico=self.medico, usuario=self.user_medico,
            **self.datos_consulta(),
        )
        diagnostico_original = consulta.diagnostico
        nota = agregar_nota(
            consulta, autor=self.user_medico,
            contenido="Paciente refiere mejoría parcial tras el tratamiento.",
        )
        consulta.refresh_from_db()
        self.assertEqual(consulta.diagnostico, diagnostico_original)
        self.assertEqual(NotaClinica.objects.filter(consulta=consulta).count(), 1)
        self.assertEqual(nota.autor, self.user_medico)

    def test_solo_el_medico_responsable_agrega_notas(self):
        consulta = registrar_consulta(
            self.cita, medico=self.medico, usuario=self.user_medico,
            **self.datos_consulta(),
        )
        with self.assertRaises(ErrorCita):
            agregar_nota(
                consulta, autor=self.user_otro_medico,
                contenido="Nota de un médico ajeno a la atención.",
            )

    def test_proxima_cita_no_puede_estar_en_el_pasado(self):
        datos = self.datos_consulta()
        datos["proxima_cita"] = timezone.localdate() - timedelta(days=1)
        with self.assertRaises(ValidationError):
            registrar_consulta(
                self.cita, medico=self.medico, usuario=self.user_medico, **datos
            )


class PermisosHistorialTest(BaseConsultasTest):
    def setUp(self):
        self.url = reverse("consultas:historial", args=[self.paciente.pk])
        self.permiso_historial = Permission.objects.get(
            codename="ver_historial_clinico"
        )

    def test_anonimo_es_redirigido_al_login(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("consultas:login"), respuesta["Location"])

    def test_paciente_ve_su_propio_historial(self):
        self.client.force_login(self.user_paciente)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.paciente.nombres)

    def test_paciente_no_ve_historial_de_otro_paciente(self):
        self.client.force_login(self.user_paciente)
        respuesta = self.client.get(
            reverse("consultas:historial", args=[self.paciente2.pk])
        )
        self.assertEqual(respuesta.status_code, 403)
        self.assertTrue(
            AuditoriaMedica.objects.filter(
                accion=AuditoriaMedica.Accion.ACCESO_DENEGADO,
                paciente=self.paciente2,
            ).exists()
        )

    def test_recepcionista_no_accede_a_historiales_clinicos(self):
        usuario = self.crear_usuario_recepcion()
        self.client.force_login(usuario)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 403)

    def test_medico_con_relacion_asistencial_ve_el_historial(self):
        self.crear_cita(fecha=fecha_habil(2), hora=time(10, 0))
        self.user_medico.user_permissions.add(self.permiso_historial)
        self.client.force_login(self.user_medico)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(
            AuditoriaMedica.objects.filter(
                accion=AuditoriaMedica.Accion.VER_HISTORIAL,
                paciente=self.paciente,
            ).exists()
        )

    def test_medico_sin_relacion_asistencial_no_ve_el_historial(self):
        self.user_medico.user_permissions.add(self.permiso_historial)
        self.client.force_login(self.user_medico)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 403)

    def test_medico_sin_permiso_especifico_no_ve_el_historial(self):
        self.crear_cita(fecha=fecha_habil(2), hora=time(10, 0))
        self.client.force_login(self.user_medico)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 403)

    def test_administrador_ve_cualquier_historial(self):
        admin = Usuario.objects.create_superuser(
            "admin_test", "admin@uncp.edu.pe", "Clave12345!"
        )
        self.client.force_login(admin)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)

    def test_auditoria_no_guarda_contenido_clinico(self):
        self.client.force_login(self.user_paciente)
        self.client.get(self.url)
        evento = AuditoriaMedica.objects.filter(
            accion=AuditoriaMedica.Accion.VER_HISTORIAL
        ).first()
        self.assertIsNotNone(evento)
        self.assertNotIn("diagnóstico", (evento.recurso or "").lower())
        self.assertEqual(evento.paciente, self.paciente)


class SesionTest(BaseConsultasTest):
    def test_sesion_expira_tras_veinte_minutos_de_inactividad(self):
        self.client.force_login(self.user_paciente)
        sesion = self.client.session
        sesion["ultima_actividad"] = (
            timezone.now() - timedelta(minutes=21)
        ).isoformat()
        sesion.save()

        respuesta = self.client.get(reverse("consultas:dashboard"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("expirada=1", respuesta["Location"])
        self.assertIsNone(self.client.session.get("_auth_user_id"))

    def test_sesion_activa_no_expira_a_los_diez_minutos(self):
        self.client.force_login(self.user_paciente)
        sesion = self.client.session
        sesion["ultima_actividad"] = (
            timezone.now() - timedelta(minutes=10)
        ).isoformat()
        sesion.save()

        respuesta = self.client.get(reverse("consultas:dashboard"))
        self.assertEqual(respuesta.status_code, 200)

    def test_login_registra_auditoria_y_marca_actividad(self):
        respuesta = self.client.post(
            reverse("consultas:login"),
            {"username": "paciente_test", "password": "Clave12345!"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            AuditoriaMedica.objects.filter(
                accion=AuditoriaMedica.Accion.LOGIN, usuario=self.user_paciente
            ).exists()
        )
        self.assertIn("ultima_actividad", self.client.session)

    def test_logout_requiere_post(self):
        self.client.force_login(self.user_paciente)
        respuesta = self.client.get(reverse("consultas:logout"))
        self.assertEqual(respuesta.status_code, 405)


class VistasAgendamientoTest(BaseConsultasTest):
    def datos_cita(self, **overrides):
        datos = {
            "especialidad": self.especialidad.pk,
            "medico": self.medico.pk,
            "fecha": fecha_habil(1).isoformat(),
            "hora": "08:00",
            "motivo": "Control general por síntomas persistentes.",
        }
        datos.update(overrides)
        return datos

    def test_paciente_agenda_una_cita(self):
        self.client.force_login(self.user_paciente)
        respuesta = self.client.post(
            reverse("consultas:agendar_cita"), self.datos_cita()
        )
        self.assertEqual(respuesta.status_code, 302)
        cita = Cita.objects.get(paciente=self.paciente)
        self.assertEqual(cita.estado, Cita.Estado.PENDIENTE)

    def test_motivo_corto_muestra_error_de_validacion(self):
        self.client.force_login(self.user_paciente)
        respuesta = self.client.post(
            reverse("consultas:agendar_cita"),
            self.datos_cita(motivo="Dolor"),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "al menos 20 caracteres")
        self.assertFalse(Cita.objects.filter(paciente=self.paciente).exists())

    def test_middleware_rechaza_horario_no_permitido(self):
        self.client.force_login(self.user_paciente)
        lunes = proximo_dia(0)
        respuesta = self.client.post(
            reverse("consultas:agendar_cita"),
            self.datos_cita(fecha=lunes.isoformat(), hora="19:00"),
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertContains(respuesta, "Horario no permitido", status_code=400)

    def test_medico_no_puede_agendar_citas(self):
        self.client.force_login(self.user_medico)
        respuesta = self.client.get(reverse("consultas:agendar_cita"))
        self.assertEqual(respuesta.status_code, 403)

    def test_recepcionista_sin_permiso_no_agenda(self):
        usuario = self.crear_usuario_recepcion()
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("consultas:agendar_cita"))
        self.assertEqual(respuesta.status_code, 403)

    def test_recepcionista_con_permiso_agenda_para_un_paciente(self):
        usuario = self.crear_usuario_recepcion(con_permiso=True)
        self.client.force_login(usuario)
        datos = self.datos_cita()
        datos["paciente"] = self.paciente2.pk
        respuesta = self.client.post(reverse("consultas:agendar_cita"), datos)
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Cita.objects.filter(paciente=self.paciente2).exists())

    def test_paciente_no_accede_al_detalle_de_otra_cita(self):
        cita = self.crear_cita(
            paciente=self.paciente2, fecha=fecha_habil(1), hora=time(10, 0)
        )
        self.client.force_login(self.user_paciente)
        respuesta = self.client.get(
            reverse("consultas:cita_detalle", args=[cita.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_paciente_puede_cancelar_su_cita(self):
        cita = self.crear_cita(fecha=fecha_habil(2), hora=time(11, 0))
        self.client.force_login(self.user_paciente)
        respuesta = self.client.post(
            reverse("consultas:cancelar_cita", args=[cita.pk]),
            {"motivo": "No podré asistir por motivos académicos."},
        )
        self.assertEqual(respuesta.status_code, 302)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CANCELADA)


class FormulariosTest(BaseConsultasTest):
    def test_formulario_paciente_rechaza_dni_duplicado(self):
        from .forms import PacienteForm

        formulario = PacienteForm(
            data={
                "dni": self.paciente.dni, "nombres": "Otro", "apellidos": "Paciente",
                "fecha_nacimiento": "2000-01-01", "tipo": "estudiante",
                "codigo_uncp": "20249999", "email": "otro@uncp.edu.pe", "alergias": "",
            }
        )
        self.assertFalse(formulario.is_valid())
        self.assertIn("dni", formulario.errors)

    def test_formulario_paciente_rechaza_correo_no_institucional(self):
        from .forms import PacienteForm

        formulario = PacienteForm(
            data={
                "dni": "70000123", "nombres": "Nuevo", "apellidos": "Estudiante",
                "fecha_nacimiento": "2002-05-10", "tipo": "estudiante",
                "codigo_uncp": "20240123", "email": "nuevo@gmail.com", "alergias": "",
            }
        )
        self.assertFalse(formulario.is_valid())
        self.assertIn("email", formulario.errors)

    def test_formulario_medico_rechaza_cmp_invalido(self):
        from .forms import MedicoForm

        formulario = MedicoForm(
            data={
                "nombres": "Nuevo", "apellidos": "Médico", "cmp": "123456",
                "especialidad": self.especialidad.pk, "consultorio": "301", "activo": True,
            }
        )
        self.assertFalse(formulario.is_valid())
        self.assertIn("cmp", formulario.errors)

    def test_formulario_cita_oculta_paciente_para_paciente(self):
        from .forms import CitaForm

        formulario = CitaForm(usuario=self.user_paciente)
        self.assertNotIn("paciente", formulario.fields)

    def test_formulario_cita_muestra_paciente_para_recepcion(self):
        from .forms import CitaForm

        usuario = self.crear_usuario_recepcion()
        formulario = CitaForm(usuario=usuario)
        self.assertIn("paciente", formulario.fields)


class AdminTest(BaseConsultasTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin_user = Usuario.objects.create_superuser(
            "admin_consultas", "admin.consultas@uncp.edu.pe", "Clave12345!"
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_changelist_de_citas_carga(self):
        respuesta = self.client.get(reverse("admin:consultas_cita_changelist"))
        self.assertEqual(respuesta.status_code, 200)

    def test_agenda_diaria_del_admin_carga(self):
        self.crear_cita(fecha=fecha_habil(1), hora=time(9, 0))
        respuesta = self.client.get(
            reverse("admin:consultas_cita_agenda"),
            {"fecha": fecha_habil(1).isoformat()},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.paciente.apellidos)

    def test_reportes_del_admin_cargan(self):
        respuesta = self.client.get(reverse("admin:consultas_cita_reportes"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Estadísticas")

    def test_accion_masiva_confirma_citas_pendientes(self):
        cita = self.crear_cita(
            fecha=fecha_habil(1), hora=time(14, 0), estado=Cita.Estado.PENDIENTE
        )
        respuesta = self.client.post(
            reverse("admin:consultas_cita_changelist"),
            {
                "action": "confirmar_citas",
                "_selected_action": [str(cita.pk)],
                "index": "0",
            },
            follow=True,
        )
        self.assertEqual(respuesta.status_code, 200)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CONFIRMADA)

    def test_consulta_es_solo_lectura_en_el_admin(self):
        from .admin import ConsultaAdmin

        modelo_admin = ConsultaAdmin(Consulta, admin.site)
        request = RequestFactory().get("/admin/consultas/consulta/")
        request.user = self.admin_user
        self.assertFalse(modelo_admin.has_add_permission(request))
        self.assertFalse(modelo_admin.has_change_permission(request))
        self.assertFalse(modelo_admin.has_delete_permission(request))
