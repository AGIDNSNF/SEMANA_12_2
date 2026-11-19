"""Pruebas automatizadas del Caso 1: préstamos de equipos de laboratorio."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import services
from .forms import BusquedaEquipoForm, EquipoForm, PrestamoSolicitudForm
from .models import Auditoria, Devolucion, Equipo, Laboratorio, Prestamo
from .validators import sanitizar_texto

Usuario = get_user_model()


def crear_grupos():
    definiciones = {
        "Docente": ["add_prestamo", "view_prestamo", "view_equipo", "view_laboratorio"],
        "Asistente": [
            "add_prestamo", "change_prestamo", "view_prestamo",
            "add_devolucion", "view_devolucion", "view_equipo",
            "view_laboratorio", "registrar_prestamo",
        ],
        "Invitado": ["view_equipo", "view_laboratorio"],
        "Administrador": ["ver_reportes", "gestionar_equipos", "registrar_prestamo"],
    }
    for nombre, codenames in definiciones.items():
        grupo, _ = Group.objects.get_or_create(name=nombre)
        grupo.permissions.set(
            Permission.objects.filter(
                content_type__app_label="prestamos", codename__in=codenames
            )
        )


class BasePrestamosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        crear_grupos()
        cls.admin = Usuario.objects.create_superuser(
            "admin_test", "admin@uncp.edu.pe", "ClaveSegura123!"
        )
        cls.docente = Usuario.objects.create_user(
            "docente_test", password="ClaveSegura123!", first_name="Ana", last_name="Rojas"
        )
        cls.docente.groups.add(Group.objects.get(name="Docente"))
        cls.docente2 = Usuario.objects.create_user("docente2_test", password="ClaveSegura123!")
        cls.docente2.groups.add(Group.objects.get(name="Docente"))
        cls.asistente = Usuario.objects.create_user("asistente_test", password="ClaveSegura123!")
        cls.asistente.groups.add(Group.objects.get(name="Asistente"))
        cls.invitado = Usuario.objects.create_user("invitado_test", password="ClaveSegura123!")
        cls.invitado.groups.add(Group.objects.get(name="Invitado"))

        cls.laboratorio = Laboratorio.objects.create(
            nombre="Laboratorio de Sistemas", codigo="LAB-SIS",
            ubicacion="Pabellón A", descripcion="Cómputo",
        )
        cls.equipo = Equipo.objects.create(
            codigo_patrimonial="SIS-PC-001", nombre="Computadora HP",
            marca="HP", modelo="ProDesk", categoria="Cómputo",
            laboratorio=cls.laboratorio, stock_total=3,
            fecha_ultimo_mantenimiento=timezone.localdate() - timedelta(days=10),
        )
        cls.equipo2 = Equipo.objects.create(
            codigo_patrimonial="SIS-PC-002", nombre="Computadora Dell",
            marca="Dell", modelo="OptiPlex", categoria="Cómputo",
            laboratorio=cls.laboratorio, stock_total=1,
        )
        cls.equipo3 = Equipo.objects.create(
            codigo_patrimonial="SIS-PC-003", nombre="Computadora Lenovo",
            marca="Lenovo", modelo="ThinkCentre", categoria="Cómputo",
            laboratorio=cls.laboratorio, stock_total=1,
        )
        cls.equipo_mantenimiento = Equipo.objects.create(
            codigo_patrimonial="SIS-PC-004", nombre="Computadora en taller",
            marca="HP", modelo="EliteDesk", categoria="Cómputo",
            laboratorio=cls.laboratorio, stock_total=1,
            estado=Equipo.Estado.MANTENIMIENTO,
        )

    def _prestamo_activo(self, docente=None, equipo=None, cantidad=1, dias=3):
        hoy = timezone.localdate()
        return Prestamo.objects.create(
            docente=docente or self.docente,
            equipo=equipo or self.equipo,
            cantidad=cantidad,
            fecha_prestamo=hoy,
            fecha_prevista_devolucion=hoy + timedelta(days=dias),
            estado=Prestamo.Estado.ACTIVO,
        )


class EquipoFormTests(BasePrestamosTest):
    def test_formulario_equipo_valido(self):
        formulario = EquipoForm(data={
            "codigo_patrimonial": "RED-SW-001",
            "nombre": "Switch Cisco",
            "marca": "Cisco",
            "modelo": "C9200",
            "categoria": "Redes",
            "estado": Equipo.Estado.OPERATIVO,
            "laboratorio": self.laboratorio.pk,
            "stock_total": 2,
            "fecha_ultimo_mantenimiento": timezone.localdate().isoformat(),
        })
        self.assertTrue(formulario.is_valid(), formulario.errors)
        equipo = formulario.save()
        self.assertEqual(equipo.codigo_patrimonial, "RED-SW-001")

    def test_codigo_patrimonial_duplicado(self):
        formulario = EquipoForm(data={
            "codigo_patrimonial": "SIS-PC-001",
            "nombre": "Otra PC", "marca": "HP", "modelo": "X",
            "categoria": "Cómputo", "estado": Equipo.Estado.OPERATIVO,
            "laboratorio": self.laboratorio.pk, "stock_total": 1,
        })
        self.assertFalse(formulario.is_valid())
        self.assertIn("codigo_patrimonial", formulario.errors)

    def test_codigo_patrimonial_formato_invalido(self):
        formulario = EquipoForm(data={
            "codigo_patrimonial": "pc con espacios", "nombre": "PC", "marca": "HP",
            "modelo": "X", "categoria": "Cómputo", "estado": Equipo.Estado.OPERATIVO,
            "laboratorio": self.laboratorio.pk, "stock_total": 1,
        })
        self.assertFalse(formulario.is_valid())
        self.assertIn("codigo_patrimonial", formulario.errors)


class SolicitudPrestamoTests(BasePrestamosTest):
    def test_solicitud_valida_crea_pendiente(self):
        self.client.force_login(self.docente)
        hoy = timezone.localdate()
        respuesta = self.client.post(reverse("prestamos:solicitar_prestamo"), {
            "equipo": self.equipo.pk,
            "cantidad": 2,
            "fecha_prestamo": hoy.isoformat(),
            "fecha_prevista_devolucion": (hoy + timedelta(days=5)).isoformat(),
            "observaciones": "Clase de laboratorio",
        })
        self.assertRedirects(respuesta, reverse("prestamos:mis_prestamos"))
        prestamo = Prestamo.objects.get(docente=self.docente)
        self.assertEqual(prestamo.estado, Prestamo.Estado.PENDIENTE)
        self.assertTrue(
            Auditoria.objects.filter(
                accion=Auditoria.Accion.SOLICITUD, entidad_id=str(prestamo.pk)
            ).exists()
        )

    def test_solicitud_invitado_denegada(self):
        self.client.force_login(self.invitado)
        respuesta = self.client.get(reverse("prestamos:solicitar_prestamo"))
        self.assertEqual(respuesta.status_code, 403)

    def test_fechas_invalidas(self):
        hoy = timezone.localdate()
        formulario = PrestamoSolicitudForm(data={
            "equipo": self.equipo.pk, "cantidad": 1,
            "fecha_prestamo": hoy.isoformat(),
            "fecha_prevista_devolucion": hoy.isoformat(),
            "observaciones": "",
        })
        self.assertFalse(formulario.is_valid())
        self.assertIn("fecha_prevista_devolucion", formulario.errors)

    def test_fecha_prestamo_pasada(self):
        ayer = timezone.localdate() - timedelta(days=1)
        formulario = PrestamoSolicitudForm(data={
            "equipo": self.equipo.pk, "cantidad": 1,
            "fecha_prestamo": ayer.isoformat(),
            "fecha_prevista_devolucion": (ayer + timedelta(days=3)).isoformat(),
            "observaciones": "",
        })
        self.assertFalse(formulario.is_valid())
        self.assertIn("fecha_prestamo", formulario.errors)

    def test_mas_de_tres_prestamos_activos(self):
        self._prestamo_activo(equipo=self.equipo)
        self._prestamo_activo(equipo=self.equipo2)
        self._prestamo_activo(equipo=self.equipo3)
        hoy = timezone.localdate()
        with self.assertRaises(ValidationError):
            services.crear_prestamo(
                docente=self.docente, equipo=self.equipo, cantidad=1,
                fecha_prestamo=hoy, fecha_prevista_devolucion=hoy + timedelta(days=4),
            )

    def test_equipo_en_mantenimiento_no_prestable(self):
        hoy = timezone.localdate()
        with self.assertRaises(ValidationError):
            services.crear_prestamo(
                docente=self.docente, equipo=self.equipo_mantenimiento, cantidad=1,
                fecha_prestamo=hoy, fecha_prevista_devolucion=hoy + timedelta(days=4),
            )
        formulario = PrestamoSolicitudForm(data={
            "equipo": self.equipo_mantenimiento.pk, "cantidad": 1,
            "fecha_prestamo": hoy.isoformat(),
            "fecha_prevista_devolucion": (hoy + timedelta(days=4)).isoformat(),
        })
        self.assertFalse(formulario.is_valid())

    def test_stock_insuficiente(self):
        self._prestamo_activo(equipo=self.equipo2, cantidad=1)
        hoy = timezone.localdate()
        with self.assertRaises(ValidationError) as contexto:
            services.crear_prestamo(
                docente=self.docente, equipo=self.equipo2, cantidad=1,
                fecha_prestamo=hoy, fecha_prevista_devolucion=hoy + timedelta(days=4),
            )
        self.assertIn("Stock insuficiente", str(contexto.exception))

    def test_cantidad_cero_invalida(self):
        hoy = timezone.localdate()
        with self.assertRaises(ValidationError):
            services.crear_prestamo(
                docente=self.docente, equipo=self.equipo, cantidad=0,
                fecha_prestamo=hoy, fecha_prevista_devolucion=hoy + timedelta(days=4),
            )
        formulario = PrestamoSolicitudForm(data={
            "equipo": self.equipo.pk, "cantidad": 0,
            "fecha_prestamo": hoy.isoformat(),
            "fecha_prevista_devolucion": (hoy + timedelta(days=4)).isoformat(),
        })
        self.assertFalse(formulario.is_valid())

    def test_observaciones_se_sanitizan(self):
        self.assertEqual(sanitizar_texto("<script>alert(1)</script>Hola"), "alert(1)Hola")
        hoy = timezone.localdate()
        formulario = PrestamoSolicitudForm(data={
            "equipo": self.equipo.pk, "cantidad": 1,
            "fecha_prestamo": hoy.isoformat(),
            "fecha_prevista_devolucion": (hoy + timedelta(days=4)).isoformat(),
            "observaciones": "<b>uso</b> de clases",
        })
        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertNotIn("<", formulario.cleaned_data["observaciones"])


class DevolucionTests(BasePrestamosTest):
    def test_devolucion_valida(self):
        prestamo = self._prestamo_activo()
        devolucion = services.registrar_devolucion(
            prestamo, asistente=self.asistente,
            estado_equipo=Devolucion.EstadoEquipo.MANTENIMIENTO,
            observaciones="Requiere revisión",
        )
        prestamo.refresh_from_db()
        self.equipo.refresh_from_db()
        self.assertEqual(prestamo.estado, Prestamo.Estado.DEVUELTO)
        self.assertEqual(prestamo.fecha_real_devolucion, devolucion.fecha)
        self.assertEqual(self.equipo.estado, Equipo.Estado.MANTENIMIENTO)
        self.assertTrue(
            Auditoria.objects.filter(accion=Auditoria.Accion.DEVOLUCION).exists()
        )

    def test_devolucion_duplicada(self):
        prestamo = self._prestamo_activo()
        services.registrar_devolucion(prestamo, asistente=self.asistente)
        with self.assertRaises(ValidationError):
            services.registrar_devolucion(prestamo, asistente=self.asistente)
        self.assertEqual(Devolucion.objects.filter(prestamo=prestamo).count(), 1)

    def test_devolucion_por_vista(self):
        prestamo = self._prestamo_activo()
        self.client.force_login(self.asistente)
        respuesta = self.client.post(
            reverse("prestamos:registrar_devolucion", args=[prestamo.pk]),
            {"estado_equipo": "operativo", "observaciones": "Devuelto conforme"},
        )
        self.assertRedirects(respuesta, reverse("prestamos:devoluciones_pendientes"))
        prestamo.refresh_from_db()
        self.assertEqual(prestamo.estado, Prestamo.Estado.DEVUELTO)


class AccesoYAuditoriaTests(BasePrestamosTest):
    def test_docente_no_accede_listado_global(self):
        self.client.force_login(self.docente)
        respuesta = self.client.get(reverse("prestamos:lista_prestamos"))
        self.assertEqual(respuesta.status_code, 403)

    def test_docente_no_ve_prestamo_ajeno(self):
        prestamo_ajeno = self._prestamo_activo(docente=self.docente2)
        self.client.force_login(self.docente)
        respuesta = self.client.get(
            reverse("prestamos:prestamo_detalle", args=[prestamo_ajeno.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_invitado_no_registra_devolucion(self):
        prestamo = self._prestamo_activo()
        self.client.force_login(self.invitado)
        respuesta = self.client.get(
            reverse("prestamos:registrar_devolucion", args=[prestamo.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_acceso_denegado_se_audita(self):
        self.client.force_login(self.docente)
        self.client.get(reverse("prestamos:lista_prestamos"))
        self.assertTrue(
            Auditoria.objects.filter(accion=Auditoria.Accion.ACCESO_DENEGADO).exists()
        )

    def test_login_fallido_se_audita(self):
        respuesta = self.client.post(
            reverse("prestamos:login"),
            {"username": "docente_test", "password": "incorrecta"},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(
            Auditoria.objects.filter(accion=Auditoria.Accion.LOGIN_FALLIDO).exists()
        )

    def test_login_correcto_redirige_al_panel(self):
        respuesta = self.client.post(
            reverse("prestamos:login"),
            {"username": "docente_test", "password": "ClaveSegura123!"},
        )
        self.assertRedirects(respuesta, reverse("prestamos:dashboard"))
        self.assertTrue(
            Auditoria.objects.filter(accion=Auditoria.Accion.LOGIN).exists()
        )

    def test_logout_solo_post(self):
        self.client.force_login(self.docente)
        self.assertEqual(self.client.get(reverse("prestamos:logout")).status_code, 405)
        respuesta = self.client.post(reverse("prestamos:logout"))
        self.assertRedirects(respuesta, reverse("prestamos:catalogo"))

    @override_settings(SESSION_TIMEOUT=30 * 60)
    def test_timeout_de_sesion_por_inactividad(self):
        self.client.force_login(self.docente)
        sesion = self.client.session
        sesion["ultima_actividad"] = (
            timezone.now() - timedelta(minutes=31)
        ).isoformat()
        sesion.save()
        respuesta = self.client.get(reverse("prestamos:dashboard"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("prestamos:login"), respuesta["Location"])
        self.assertIn("expirada=1", respuesta["Location"])

    def test_sesion_activa_no_expira(self):
        self.client.force_login(self.docente)
        respuesta = self.client.get(reverse("prestamos:dashboard"))
        self.assertEqual(respuesta.status_code, 200)


class ReglasDeNegocioTests(BasePrestamosTest):
    def test_no_eliminar_equipo_con_prestamo_activo(self):
        self._prestamo_activo()
        with self.assertRaises(ValidationError):
            services.eliminar_equipo(self.equipo, usuario=self.admin)
        self.assertTrue(Equipo.objects.filter(pk=self.equipo.pk).exists())

    def test_eliminar_equipo_sin_prestamos_activos(self):
        equipo = Equipo.objects.create(
            codigo_patrimonial="SIS-PC-099", nombre="Equipo antiguo", marca="Genérico",
            categoria="Cómputo", laboratorio=self.laboratorio, stock_total=1,
        )
        services.eliminar_equipo(equipo, usuario=self.admin)
        self.assertFalse(Equipo.objects.filter(pk=equipo.pk).exists())

    def test_disponibilidad_calculada(self):
        self._prestamo_activo(cantidad=2)
        self.assertEqual(self.equipo.cantidad_disponible, 1)

    def test_marcar_vencidos(self):
        prestamo = self._prestamo_activo()
        prestamo.fecha_prestamo = timezone.localdate() - timedelta(days=10)
        prestamo.fecha_prevista_devolucion = timezone.localdate() - timedelta(days=1)
        prestamo.save(update_fields=["fecha_prestamo", "fecha_prevista_devolucion"])
        total = services.marcar_vencidos(usuario=self.admin)
        prestamo.refresh_from_db()
        self.assertGreaterEqual(total, 1)
        self.assertEqual(prestamo.estado, Prestamo.Estado.VENCIDO)

    def test_admin_marca_equipos_en_mantenimiento(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("admin:prestamos_equipo_changelist"),
            {"action": "marcar_en_mantenimiento", "_selected_action": [self.equipo.pk]},
            follow=True,
        )
        self.assertEqual(respuesta.status_code, 200)
        self.equipo.refresh_from_db()
        self.assertEqual(self.equipo.estado, Equipo.Estado.MANTENIMIENTO)

    def test_busqueda_catalogo_publico(self):
        respuesta = self.client.get(reverse("prestamos:catalogo"), {"q": "HP"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Computadora HP")
        self.assertNotContains(respuesta, "Computadora Dell")

    def test_busqueda_form_valida(self):
        formulario = BusquedaEquipoForm(data={"q": "HP", "laboratorio": self.laboratorio.pk})
        self.assertTrue(formulario.is_valid(), formulario.errors)


class DatosDemoTests(TestCase):
    def test_comando_demo_es_idempotente(self):
        call_command("crear_datos_demo", verbosity=0)
        call_command("crear_datos_demo", verbosity=0)
        self.assertEqual(Laboratorio.objects.count(), 5)
        self.assertEqual(Equipo.objects.count(), 10)
        self.assertEqual(Prestamo.objects.count(), 15)
        self.assertGreaterEqual(Usuario.objects.count(), 6)
        self.assertTrue(
            Prestamo.objects.filter(estado=Prestamo.Estado.VENCIDO).exists()
        )
        self.assertTrue(
            Prestamo.objects.filter(estado=Prestamo.Estado.DEVUELTO).exists()
        )
        self.assertTrue(
            Prestamo.objects.filter(estado=Prestamo.Estado.ACTIVO).exists()
        )
