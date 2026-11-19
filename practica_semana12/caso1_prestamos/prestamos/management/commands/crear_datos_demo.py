"""Datos de demostración idempotentes para el caso 1.

Uso: python manage.py crear_datos_demo
"""
from datetime import timedelta
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from prestamos.models import Devolucion, Equipo, Laboratorio, Prestamo

Usuario = get_user_model()
CLAVE_DEMO = os.environ.get("DEMO_PASSWORD", "Demo12345!")

PERMISOS_POR_GRUPO = {
    "Administrador": [
        "add_laboratorio", "change_laboratorio", "delete_laboratorio", "view_laboratorio",
        "add_equipo", "change_equipo", "delete_equipo", "view_equipo",
        "add_prestamo", "change_prestamo", "delete_prestamo", "view_prestamo",
        "add_devolucion", "change_devolucion", "view_devolucion",
        "view_auditoria", "ver_reportes", "gestionar_equipos", "registrar_prestamo",
    ],
    "Docente": [
        "add_prestamo", "view_prestamo", "view_equipo", "view_laboratorio",
    ],
    "Asistente": [
        "add_prestamo", "change_prestamo", "view_prestamo",
        "add_devolucion", "view_devolucion",
        "view_equipo", "view_laboratorio", "registrar_prestamo",
    ],
    "Invitado": ["view_equipo", "view_laboratorio"],
}


class Command(BaseCommand):
    help = "Crea laboratorios, equipos, usuarios, grupos y préstamos de demostración."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Generando datos demo · Caso 1"))
        self._crear_grupos()
        laboratorios = self._crear_laboratorios()
        equipos = self._crear_equipos(laboratorios)
        usuarios = self._crear_usuarios()
        total_prestamos = self._crear_prestamos(equipos, usuarios)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Datos demo listos."))
        self.stdout.write(f"  Laboratorios: {Laboratorio.objects.count()}")
        self.stdout.write(f"  Equipos:      {Equipo.objects.count()}")
        self.stdout.write(f"  Usuarios:     {Usuario.objects.count()}")
        self.stdout.write(f"  Préstamos:    {Prestamo.objects.count()} (creados/actualizados: {total_prestamos})")
        self.stdout.write(f"  Devoluciones: {Devolucion.objects.count()}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Credenciales de demostración (contraseña única):"))
        for usuario in usuarios.values():
            self.stdout.write(
                f"  {usuario.username:<14} {CLAVE_DEMO}   rol={', '.join(usuario.groups.values_list('name', flat=True))}"
            )
        self.stdout.write("")
        self.stdout.write("  Admin Django: admin_uncp / " + CLAVE_DEMO)

    # ------------------------------------------------------------------
    def _crear_grupos(self):
        for nombre, codenames in PERMISOS_POR_GRUPO.items():
            grupo, _ = Group.objects.get_or_create(name=nombre)
            permisos = Permission.objects.filter(
                content_type__app_label="prestamos", codename__in=codenames
            )
            grupo.permissions.set(permisos)

    def _crear_laboratorios(self):
        datos = [
            ("Laboratorio de Sistemas", "LAB-SIS", "Pabellón A, 2.º piso", "Cómputo y desarrollo de software"),
            ("Laboratorio de Redes", "LAB-RED", "Pabellón B, 1.er piso", "Cisco, MikroTik y cableado estructurado"),
            ("Laboratorio de Base de Datos", "LAB-BD", "Pabellón A, 3.er piso", "Servidores y almacenamiento"),
            ("Laboratorio de Hardware", "LAB-HW", "Pabellón C, 1.er piso", "Mantenimiento y electrónica"),
            ("Laboratorio Multimedia", "LAB-MUL", "Pabellón B, 2.º piso", "Producción audiovisual"),
        ]
        laboratorios = {}
        for nombre, codigo, ubicacion, descripcion in datos:
            laboratorios[codigo], _ = Laboratorio.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "nombre": nombre, "ubicacion": ubicacion,
                    "descripcion": descripcion, "activo": True,
                },
            )
        return laboratorios

    def _crear_equipos(self, labs):
        hoy = timezone.localdate()
        datos = [
            ("SIS-PC-001", "Computadora HP ProDesk", "HP", "ProDesk 400 G7", "Cómputo",
             "LAB-SIS", 3, Equipo.Estado.OPERATIVO, 40),
            ("SIS-PC-002", "Computadora Dell OptiPlex", "Dell", "OptiPlex 7090", "Cómputo",
             "LAB-SIS", 2, Equipo.Estado.OPERATIVO, 25),
            ("RED-SW-001", "Switch Cisco Catalyst", "Cisco", "C9200L", "Redes",
             "LAB-RED", 2, Equipo.Estado.OPERATIVO, 60),
            ("RED-RT-001", "Router MikroTik", "MikroTik", "RB4011", "Redes",
             "LAB-RED", 1, Equipo.Estado.OPERATIVO, 12),
            ("BD-SV-001", "Servidor Dell PowerEdge", "Dell", "R740", "Servidores",
             "LAB-BD", 2, Equipo.Estado.OPERATIVO, 15),
            ("HW-PY-001", "Kit Raspberry Pi 4", "Raspberry", "Pi 4B", "Electrónica",
             "LAB-HW", 2, Equipo.Estado.OPERATIVO, 90),
            ("HW-MON-001", "Monitor LG 24\"", "LG", "24MK430H", "Periféricos",
             "LAB-HW", 1, Equipo.Estado.MANTENIMIENTO, 8),
            ("MUL-PR-001", "Proyector Epson", "Epson", "PowerLite X49", "Audiovisual",
             "LAB-MUL", 1, Equipo.Estado.OPERATIVO, 30),
            ("MUL-TV-001", "Televisor Samsung 55\"", "Samsung", "AU7000", "Audiovisual",
             "LAB-MUL", 1, Equipo.Estado.OPERATIVO, 45),
            ("BD-NAS-001", "NAS Synology", "Synology", "DS220+", "Almacenamiento",
             "LAB-BD", 1, Equipo.Estado.BAJA, 120),
        ]
        equipos = {}
        for codigo, nombre, marca, modelo, categoria, lab, stock, estado, dias in datos:
            equipos[codigo], _ = Equipo.objects.update_or_create(
                codigo_patrimonial=codigo,
                defaults={
                    "nombre": nombre, "marca": marca, "modelo": modelo,
                    "categoria": categoria, "laboratorio": labs[lab],
                    "stock_total": stock, "estado": estado,
                    "fecha_ultimo_mantenimiento": hoy - timedelta(days=dias),
                },
            )
        return equipos

    def _crear_usuarios(self):
        definiciones = [
            ("admin_uncp", "Administrador", "UNCP", "Administrador", "admin@uncp.edu.pe", True, True),
            ("docente1", "Rosa", "Quispe Huamán", "Docente", "rquispe@uncp.edu.pe", False, False),
            ("docente2", "Julio", "Paredes Rojas", "Docente", "jparedes@uncp.edu.pe", False, False),
            ("docente3", "Elena", "Astuhuamán León", "Docente", "eastuhuaman@uncp.edu.pe", False, False),
            ("asistente1", "Marco", "Sulca Torres", "Asistente", "msulca@uncp.edu.pe", False, True),
            ("invitado1", "Invitado", "Consulta Pública", "Invitado", "invitado@uncp.edu.pe", False, False),
        ]
        usuarios = []
        for username, nombres, apellidos, grupo, email, superuser, staff in definiciones:
            usuario, _ = Usuario.objects.get_or_create(username=username)
            usuario.first_name = nombres
            usuario.last_name = apellidos
            usuario.email = email
            usuario.is_superuser = superuser
            usuario.is_staff = staff
            usuario.is_active = True
            usuario.set_password(CLAVE_DEMO)
            usuario.save()
            usuario.groups.set([Group.objects.get(name=grupo)])
            usuarios.append(usuario)
        return {usuario.username: usuario for usuario in usuarios}

    def _crear_prestamos(self, equipos, usuarios):
        hoy = timezone.localdate()
        asistente = usuarios["asistente1"]
        admin = usuarios["admin_uncp"]
        d1, d2, d3 = usuarios["docente1"], usuarios["docente2"], usuarios["docente3"]

        definiciones = [
            # tag, docente, equipo, cantidad, inicio, prevista, estado, devolución, asistente
            ("DEMO-01", d1, "SIS-PC-001", 1, -3, 4, Prestamo.Estado.ACTIVO, None, asistente),
            ("DEMO-02", d1, "SIS-PC-002", 1, -20, -6, Prestamo.Estado.VENCIDO, None, asistente),
            ("DEMO-03", d1, "RED-SW-001", 1, 0, 7, Prestamo.Estado.PENDIENTE, None, None),
            ("DEMO-04", d1, "SIS-PC-001", 1, -30, -25, Prestamo.Estado.DEVUELTO, -24, asistente),
            ("DEMO-05", d1, "RED-RT-001", 1, -40, -35, Prestamo.Estado.DEVUELTO, -36, admin),
            ("DEMO-06", d2, "BD-SV-001", 1, -5, 9, Prestamo.Estado.ACTIVO, None, asistente),
            ("DEMO-07", d2, "HW-PY-001", 1, -2, 12, Prestamo.Estado.ACTIVO, None, asistente),
            ("DEMO-08", d2, "HW-MON-001", 1, -50, -45, Prestamo.Estado.DEVUELTO, -44, asistente),
            ("DEMO-09", d2, "SIS-PC-002", 1, -60, -55, Prestamo.Estado.DEVUELTO, -54, asistente),
            ("DEMO-10", d3, "MUL-PR-001", 1, -1, 6, Prestamo.Estado.ACTIVO, None, asistente),
            ("DEMO-11", d3, "MUL-TV-001", 1, -15, -2, Prestamo.Estado.VENCIDO, None, asistente),
            ("DEMO-12", d3, "BD-NAS-001", 1, -70, -65, Prestamo.Estado.DEVUELTO, -63, asistente),
            ("DEMO-13", d1, "RED-SW-001", 1, -8, -1, Prestamo.Estado.RECHAZADO, None, asistente),
            ("DEMO-14", d3, "BD-SV-001", 1, -35, -30, Prestamo.Estado.DEVUELTO, -29, asistente),
            ("DEMO-15", d2, "RED-RT-001", 1, -25, -20, Prestamo.Estado.DEVUELTO, -19, asistente),
        ]
        total = 0
        for tag, docente, codigo, cantidad, ini, fin, estado, devuelto, resp in definiciones:
            equipo = equipos[codigo]
            fecha_inicio = hoy + timedelta(days=ini)
            fecha_prevista = hoy + timedelta(days=fin)
            fecha_real = hoy + timedelta(days=devuelto) if devuelto is not None else None
            prestamo, _ = Prestamo.objects.update_or_create(
                observaciones=f"[{tag}] Registro de demostración",
                defaults={
                    "docente": docente,
                    "equipo": equipo,
                    "cantidad": cantidad,
                    "fecha_prestamo": fecha_inicio,
                    "fecha_prevista_devolucion": fecha_prevista,
                    "fecha_real_devolucion": fecha_real,
                    "estado": estado,
                    "asistente_responsable": resp,
                },
            )
            if estado == Prestamo.Estado.DEVUELTO:
                Devolucion.objects.update_or_create(
                    prestamo=prestamo,
                    defaults={
                        "fecha": fecha_real or hoy,
                        "estado_equipo_al_retornar": Devolucion.EstadoEquipo.OPERATIVO,
                        "observaciones": f"[{tag}] Devolución de demostración",
                        "asistente_responsable": asistente,
                    },
                )
            total += 1
        return total
