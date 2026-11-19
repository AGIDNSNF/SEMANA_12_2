"""Datos ficticios de demostración para el caso 3 (idempotente).

Uso: python manage.py crear_datos_demo
Ningún dato corresponde a personas reales.
"""
import os
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from asistencia import services
from asistencia.models import (
    Area,
    CorreccionAsistencia,
    Empleado,
    RegistroAsistencia,
    Solicitud,
)

Usuario = get_user_model()
CLAVE_DEMO = os.environ.get("DEMO_PASSWORD", "Demo12345!")

PERMISOS = {
    "Administradores": "__all__",
    "Recursos Humanos": "__all__",
    "Jefes de área": [
        "view_empleado", "view_registroasistencia", "view_solicitud",
        "aprobar_solicitud", "ver_reportes_asistencia",
    ],
    "Empleados": [
        "marcar_asistencia", "crear_solicitud",
        "view_registroasistencia", "view_solicitud",
    ],
    "Contadores": [
        "view_empleado", "view_registroasistencia", "view_solicitud",
        "ver_reportes_asistencia",
    ],
}

AREAS = [
    ("Tecnología de la Información", "TI"),
    ("Recursos Humanos", "RRHH"),
    ("Contabilidad", "CONT"),
    ("Operaciones", "OPER"),
]

# dni, nombres, apellidos, cargo, area, email, usuario, grupos, sueldo
EMPLEADOS = [
    ("70100001", "Lucía", "Quispe Rojas", "Jefe de Tecnología", "TI",
     "lucia.quispe@tecnoandes.pe", "jefe_ti", ["Jefes de área", "Empleados"], "5200.00"),
    ("70100002", "Jorge", "Salazar Vega", "Jefe de Recursos Humanos", "RRHH",
     "jorge.salazar@tecnoandes.pe", "jefe_rrhh", ["Recursos Humanos", "Jefes de área"], "5100.00"),
    ("70100003", "María", "Huamán Castro", "Jefa de Contabilidad", "CONT",
     "maria.huaman@tecnoandes.pe", "jefe_contab", ["Jefes de área", "Empleados"], "5000.00"),
    ("70100004", "Diego", "Torres Ayala", "Jefe de Operaciones", "OPER",
     "diego.torres@tecnoandes.pe", "jefe_oper", ["Jefes de área", "Empleados"], "5000.00"),
    ("70100005", "Ana", "Flores Mendoza", "Analista de RRHH", "RRHH",
     "ana.flores@tecnoandes.pe", "rrhh1", ["Recursos Humanos"], "3500.00"),
    ("70100006", "Carlos", "Rojas Paredes", "Contador general", "CONT",
     "carlos.rojas@tecnoandes.pe", "contador1", ["Contadores"], "3800.00"),
    ("70100007", "Sofía", "Vargas León", "Desarrolladora backend", "TI",
     "sofia.vargas@tecnoandes.pe", "empleado1", ["Empleados"], "3200.00"),
    ("70100008", "Pedro", "Cárdenas Ruiz", "Analista de soporte", "TI",
     "pedro.cardenas@tecnoandes.pe", "empleado2", ["Empleados"], "2900.00"),
    ("70100009", "Camila", "Paredes Silva", "Asistente de operaciones", "OPER",
     "camila.paredes@tecnoandes.pe", "empleado3", ["Empleados"], "2400.00"),
    ("70100010", "Mateo", "Sulca Ramos", "Operario de planta", "OPER",
     "mateo.sulca@tecnoandes.pe", "empleado4", ["Empleados"], "2300.00"),
    ("70100011", "Valeria", "Vega Torres", "QA tester", "TI",
     "valeria.vega@tecnoandes.pe", "empleado5", ["Empleados"], "2800.00"),
    ("70100012", "Sebastián", "León Cárdenas", "Auxiliar de almacén", "OPER",
     "sebastian.leon@tecnoandes.pe", "empleado6", ["Empleados"], "2200.00"),
]


def siguiente_habil(dias=1):
    fecha = timezone.localdate() + timedelta(days=dias)
    while fecha.weekday() >= 5:
        fecha += timedelta(days=1)
    return fecha


class Command(BaseCommand):
    help = "Genera áreas, empleados, marcaciones, correcciones y solicitudes ficticias."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Generando datos demo · Caso 3"))
        self._crear_grupos()
        areas = self._crear_areas()
        empleados = self._crear_empleados(areas)
        self._asignar_jefes(areas, empleados)
        self._crear_registros(empleados)
        self._crear_correccion(empleados)
        self._crear_solicitudes(empleados)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Datos demo listos."))
        self.stdout.write(f"  Áreas:            {Area.objects.count()}")
        self.stdout.write(f"  Empleados:        {Empleado.objects.count()}")
        self.stdout.write(f"  Registros:        {RegistroAsistencia.objects.count()}")
        self.stdout.write(f"  Correcciones:     {CorreccionAsistencia.objects.count()}")
        self.stdout.write(f"  Solicitudes:      {Solicitud.objects.count()}")
        self.stdout.write(f"  Usuarios:         {Usuario.objects.count()}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Credenciales de demostración (contraseña única):"))
        for username in [
            "admin_asistencia", "rrhh1", "jefe_ti", "jefe_rrhh",
            "jefe_contab", "jefe_oper", "contador1",
            "empleado1", "empleado2", "empleado3",
        ]:
            self.stdout.write(f"  {username:<18} {CLAVE_DEMO}")
        self.stdout.write("  (También: empleado1..empleado6)")
        self.stdout.write("")
        self.stdout.write("  Todos los datos son ficticios.")

    # ------------------------------------------------------------------
    def _crear_grupos(self):
        for nombre, codenames in PERMISOS.items():
            grupo, _ = Group.objects.get_or_create(name=nombre)
            if codenames == "__all__":
                permisos = Permission.objects.filter(content_type__app_label="asistencia")
            else:
                permisos = Permission.objects.filter(
                    content_type__app_label="asistencia", codename__in=codenames
                )
            grupo.permissions.set(permisos)

    def _crear_areas(self):
        areas = {}
        for nombre, codigo in AREAS:
            area, _ = Area.objects.update_or_create(
                codigo=codigo, defaults={"nombre": nombre}
            )
            areas[codigo] = area
        return areas

    def _crear_usuario(self, username, nombres, apellidos, email, grupos,
                       staff=False, superuser=False):
        usuario, _ = Usuario.objects.get_or_create(username=username)
        usuario.first_name = nombres
        usuario.last_name = apellidos
        usuario.email = email
        usuario.is_active = True
        usuario.is_staff = staff
        usuario.is_superuser = superuser
        usuario.set_password(CLAVE_DEMO)
        usuario.save()
        usuario.groups.set([Group.objects.get(name=g) for g in grupos])
        return usuario

    def _crear_empleados(self, areas):
        self._crear_usuario(
            "admin_asistencia", "Administrador", "de Asistencia",
            "admin.asistencia@tecnoandes.pe", ["Administradores"],
            staff=True, superuser=True,
        )
        empleados = {}
        for dni, nombres, apellidos, cargo, area_codigo, email, username, grupos, sueldo in EMPLEADOS:
            usuario = self._crear_usuario(username, nombres, apellidos, email, grupos)
            empleado, _ = Empleado.objects.update_or_create(
                dni=dni,
                defaults={
                    "nombres": nombres, "apellidos": apellidos, "email": email,
                    "cargo": cargo, "area": areas[area_codigo],
                    "usuario": usuario, "activo": True, "sueldo_basico": sueldo,
                    "fecha_ingreso": timezone.localdate() - timedelta(days=400),
                },
            )
            empleados[username] = empleado
        return empleados

    def _asignar_jefes(self, areas, empleados):
        asignaciones = {
            "TI": empleados["jefe_ti"],
            "RRHH": empleados["jefe_rrhh"],
            "CONT": empleados["jefe_contab"],
            "OPER": empleados["jefe_oper"],
        }
        for codigo, jefe in asignaciones.items():
            area = areas[codigo]
            area.jefe = jefe
            area.save(update_fields=["jefe"])

    def _crear_registros(self, empleados):
        hoy = timezone.localdate()
        for username, empleado in empleados.items():
            for atras in range(1, 9):
                fecha = hoy - timedelta(days=atras)
                if fecha.weekday() >= 5:
                    continue
                salida = time(17, 0) if atras % 3 else time(17, 40)
                RegistroAsistencia.objects.update_or_create(
                    empleado=empleado, fecha=fecha,
                    defaults={
                        "hora_entrada": time(8, 0),
                        "hora_salida": salida,
                        "observacion": "[DEMO] Jornada registrada automáticamente.",
                    },
                )
        # Algunos empleados quedan con marcación abierta del día de hoy.
        for username in ("empleado1", "empleado3", "empleado5"):
            RegistroAsistencia.objects.update_or_create(
                empleado=empleados[username], fecha=hoy,
                defaults={
                    "hora_entrada": time(8, 0),
                    "hora_salida": None,
                    "observacion": "[DEMO] Entrada del día pendiente de salida.",
                },
            )

    def _crear_correccion(self, empleados):
        registro = (
            RegistroAsistencia.objects.filter(
                empleado=empleados["empleado1"], hora_salida__isnull=False
            ).order_by("-fecha").first()
        )
        if registro is None or correccion_existente(registro):
            return
        try:
            services.corregir_asistencia(
                registro,
                usuario=empleados["rrhh1"].usuario,
                hora_entrada=time(8, 5),
                hora_salida=registro.hora_salida,
                justificacion=(
                    "Corrección de demostración: el colaborador olvidó marcar su ingreso "
                    "a la hora exacta y Recursos Humanos regulariza el registro con sustento."
                ),
            )
        except Exception as exc:  # pragma: no cover - datos demo
            self.stderr.write(f"  Aviso: no se pudo crear la corrección demo: {exc}")

    def _crear_solicitudes(self, empleados):
        # Se reinician solo las solicitudes demo para mantener la idempotencia.
        Solicitud.objects.filter(motivo__startswith="[DEMO]").delete()
        base = siguiente_habil(2)
        while base.weekday() != 0:
            base += timedelta(days=1)

        def dias_habiles(desde, cantidad):
            fechas = []
            cursor = desde
            while len(fechas) < cantidad:
                if cursor.weekday() < 5:
                    fechas.append(cursor)
                cursor += timedelta(days=1)
            return fechas

        # Vacaciones aprobadas para empleado1 (jefe de TI aprueba).
        fechas = dias_habiles(base, 3)
        aprobada = services.crear_solicitud(
            empleado=empleados["empleado1"], tipo=Solicitud.Tipo.VACACIONES,
            fecha_inicio=fechas[0], fecha_fin=fechas[-1],
            motivo="[DEMO] Vacaciones programadas para descanso familiar.",
            usuario=empleados["empleado1"].usuario,
        )
        services.resolver_solicitud(
            aprobada, usuario=empleados["jefe_ti"].usuario, aprobar=True,
            comentario="Aprobado según cronograma del área.",
        )

        # Permiso pendiente para empleado2.
        fechas = dias_habiles(base + timedelta(days=7), 1)
        services.crear_solicitud(
            empleado=empleados["empleado2"], tipo=Solicitud.Tipo.PERMISO,
            fecha_inicio=fechas[0], fecha_fin=fechas[0],
            motivo="[DEMO] Permiso por trámite personal debidamente sustentado.",
            usuario=empleados["empleado2"].usuario,
        )

        # Solicitud pendiente para empleado3.
        fechas = dias_habiles(base + timedelta(days=14), 2)
        services.crear_solicitud(
            empleado=empleados["empleado3"], tipo=Solicitud.Tipo.VACACIONES,
            fecha_inicio=fechas[0], fecha_fin=fechas[-1],
            motivo="[DEMO] Vacaciones solicitadas con anticipación al jefe de área.",
            usuario=empleados["empleado3"].usuario,
        )

        # Solicitud rechazada para empleado4.
        fechas = dias_habiles(base + timedelta(days=21), 1)
        rechazada = services.crear_solicitud(
            empleado=empleados["empleado4"], tipo=Solicitud.Tipo.PERMISO,
            fecha_inicio=fechas[0], fecha_fin=fechas[0],
            motivo="[DEMO] Permiso solicitado en fecha de alta demanda operativa.",
            usuario=empleados["empleado4"].usuario,
        )
        services.resolver_solicitud(
            rechazada, usuario=empleados["jefe_oper"].usuario, aprobar=False,
            comentario="Rechazado por coincidir con cierre de producción.",
        )


def correccion_existente(registro):
    return CorreccionAsistencia.objects.filter(registro=registro).exists()
