"""Datos ficticios de demostración para el caso 2 (idempotente).

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

from consultas.models import (
    Cita, Consulta, Especialidad, HorarioAtencion, Medico, NotaClinica, Paciente,
)

Usuario = get_user_model()
CLAVE_DEMO = os.environ.get("DEMO_PASSWORD", "Demo12345!")

PERMISOS = {
    "Admins": "__all__",
    "Médicos": [
        "view_cita", "view_consulta", "add_consulta", "view_notaclinica",
        "add_notaclinica", "view_paciente", "view_medico", "view_especialidad",
        "ver_historial_clinico",
    ],
    "Recepcionistas": [
        "add_paciente", "change_paciente", "view_paciente",
        "add_cita", "change_cita", "view_cita", "view_medico", "view_especialidad",
        "agendar_cita", "cancelar_cita",
    ],
    "Pacientes": ["add_cita", "view_cita", "cancelar_cita"],
}

ESPECIALIDADES = [
    ("Medicina General", "Atención primaria y control general."),
    ("Pediatría", "Atención de niñas, niños y adolescentes."),
    ("Cardiología", "Evaluación cardiovascular."),
    ("Dermatología", "Diagnóstico y tratamiento de la piel."),
    ("Psicología", "Apoyo emocional y salud mental."),
]

MEDICOS = [
    ("Lucía", "Ramírez Ponce", "50001", "Medicina General", "101"),
    ("Jorge", "Salazar Vega", "50002", "Pediatría", "102"),
    ("María", "Huamán Castro", "50003", "Cardiología", "103"),
    ("Diego", "Torres Ayala", "50004", "Dermatología", "104"),
    ("Ana", "Flores Mendoza", "50005", "Psicología", "105"),
    ("Carlos", "Rojas Paredes", "50006", "Medicina General", "106"),
    ("Sofía", "Vargas León", "50007", "Pediatría", "107"),
    ("Pedro", "Cárdenas Ruiz", "50008", "Cardiología", "108"),
]

PACIENTES = [
    ("70000001", "Camila", "Quispe Rojas", "estudiante", "20240001", "camila.quispe@uncp.edu.pe", "Penicilina"),
    ("70000002", "Mateo", "Paredes Silva", "estudiante", "20240002", "mateo.paredes@uncp.edu.pe", ""),
    ("70000003", "Valeria", "Huamán Soto", "estudiante", "20240003", "valeria.huaman@uncp.edu.pe", ""),
    ("70000004", "Sebastián", "Rojas Ccahuana", "estudiante", "20240004", "sebastian.rojas@uncp.edu.pe", "Polen"),
    ("70000005", "Daniela", "Mendoza López", "estudiante", "20240005", "daniela.mendoza@uncp.edu.pe", ""),
    ("70000006", "Diego", "Sulca Ramos", "estudiante", "20240006", "diego.sulca@uncp.edu.pe", "Ibuprofeno"),
    ("70000007", "Luciana", "Vega Torres", "estudiante", "20240007", "luciana.vega@uncp.edu.pe", ""),
    ("70000008", "Adrián", "Castro Flores", "estudiante", "20240008", "adrian.castro@uncp.edu.pe", ""),
    ("70000009", "Fátima", "Ayala Quispe", "estudiante", "20240009", "fatima.ayala@uncp.edu.pe", "Mariscos"),
    ("70000010", "Rodrigo", "León Cárdenas", "estudiante", "20240010", "rodrigo.leon@uncp.edu.pe", ""),
    ("70000011", "Elena", "Ponce Huamán", "docente", "D001", "elena.ponce@uncp.edu.pe", ""),
    ("70000012", "Julio", "Ramos Salazar", "docente", "D002", "julio.ramos@uncp.edu.pe", "Látex"),
    ("70000013", "Rosa", "Silva Mendoza", "docente", "D003", "rosa.silva@uncp.edu.pe", ""),
    ("70000014", "Marco", "Quispe Vega", "docente", "D004", "marco.quispe@uncp.edu.pe", ""),
    ("70000015", "Patricia", "Rojas Ayala", "docente", "D005", "patricia.rojas@uncp.edu.pe", "Sulfas"),
]


class Command(BaseCommand):
    help = "Genera especialidades, médicos, pacientes, horarios, citas y consultas ficticias."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Generando datos demo · Caso 2"))
        self._crear_grupos()
        especialidades = self._crear_especialidades()
        medicos = self._crear_medicos(especialidades)
        self._crear_horarios(medicos)
        pacientes = self._crear_pacientes()
        citas, consultas = self._crear_citas_y_consultas(medicos, pacientes)
        usuarios = Usuario.objects.filter(
            groups__name__in=["Admins", "Médicos", "Recepcionistas", "Pacientes"]
        ).distinct()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Datos demo listos."))
        self.stdout.write(f"  Especialidades: {Especialidad.objects.count()}")
        self.stdout.write(f"  Médicos:        {Medico.objects.count()}")
        self.stdout.write(f"  Pacientes:      {Paciente.objects.count()}")
        self.stdout.write(f"  Citas:          {Cita.objects.count()} (sembradas: {citas})")
        self.stdout.write(f"  Consultas:      {Consulta.objects.count()} (sembradas: {consultas})")
        self.stdout.write(f"  Usuarios:       {Usuario.objects.count()}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Credenciales de demostración (contraseña única):"))
        for username in ["admin_medico", "recepcion1", "medico1", "paciente1"]:
            self.stdout.write(f"  {username:<14} {CLAVE_DEMO}")
        self.stdout.write("  (También: medico1..medico8, paciente1..paciente15)")
        self.stdout.write("")
        self.stdout.write("  Todos los datos clínicos son ficticios.")

    # ------------------------------------------------------------------
    def _crear_grupos(self):
        for nombre, codenames in PERMISOS.items():
            grupo, _ = Group.objects.get_or_create(name=nombre)
            if codenames == "__all__":
                permisos = Permission.objects.filter(content_type__app_label="consultas")
            else:
                permisos = Permission.objects.filter(
                    content_type__app_label="consultas", codename__in=codenames
                )
            grupo.permissions.set(permisos)

    def _crear_especialidades(self):
        resultado = {}
        for nombre, descripcion in ESPECIALIDADES:
            resultado[nombre], _ = Especialidad.objects.update_or_create(
                nombre=nombre, defaults={"descripcion": descripcion}
            )
        return resultado

    def _crear_usuarios_base(self, username, nombres, apellidos, email, grupo, staff=False, superuser=False):
        usuario, _ = Usuario.objects.get_or_create(username=username)
        usuario.first_name = nombres
        usuario.last_name = apellidos
        usuario.email = email
        usuario.is_active = True
        usuario.is_staff = staff
        usuario.is_superuser = superuser
        usuario.set_password(CLAVE_DEMO)
        usuario.save()
        usuario.groups.set([Group.objects.get(name=grupo)])
        return usuario

    def _crear_medicos(self, especialidades):
        self._crear_usuarios_base(
            "admin_medico", "Administrador", "del Centro Médico",
            "admin.medico@uncp.edu.pe", "Admins", staff=True, superuser=True,
        )
        self._crear_usuarios_base(
            "recepcion1", "Karla", "Núñez Torres",
            "recepcion@uncp.edu.pe", "Recepcionistas",
        )
        medicos = {}
        for indice, (nombres, apellidos, cmp, especialidad, consultorio) in enumerate(MEDICOS, start=1):
            usuario = self._crear_usuarios_base(
                f"medico{indice}", nombres, apellidos,
                f"medico{indice}@uncp.edu.pe", "Médicos",
            )
            medico, _ = Medico.objects.update_or_create(
                cmp=cmp,
                defaults={
                    "nombres": nombres, "apellidos": apellidos,
                    "especialidad": especialidades[especialidad],
                    "consultorio": consultorio, "activo": True, "usuario": usuario,
                },
            )
            medicos[indice] = medico
        return medicos

    def _crear_horarios(self, medicos):
        for medico in medicos.values():
            for dia in range(5):  # lunes a viernes
                for inicio, fin in ((time(8, 0), time(12, 0)), (time(14, 0), time(18, 0))):
                    HorarioAtencion.objects.update_or_create(
                        medico=medico, dia_semana=dia, hora_inicio=inicio,
                        defaults={"hora_fin": fin},
                    )
            HorarioAtencion.objects.update_or_create(
                medico=medico, dia_semana=5, hora_inicio=time(8, 0),
                defaults={"hora_fin": time(13, 0)},
            )

    def _crear_pacientes(self):
        pacientes = {}
        for indice, (dni, nombres, apellidos, tipo, codigo, email, alergias) in enumerate(PACIENTES, start=1):
            usuario = self._crear_usuarios_base(
                f"paciente{indice}", nombres, apellidos, email, "Pacientes",
            )
            paciente, _ = Paciente.objects.update_or_create(
                dni=dni,
                defaults={
                    "nombres": nombres, "apellidos": apellidos,
                    "fecha_nacimiento": timezone.localdate() - timedelta(days=20 * 365 + indice * 97),
                    "tipo": tipo, "codigo_uncp": codigo, "email": email,
                    "alergias": alergias, "usuario": usuario,
                },
            )
            pacientes[indice] = paciente
        return pacientes

    def _crear_citas_y_consultas(self, medicos, pacientes):
        hoy = timezone.localdate()

        # Dos días laborables pasados y dos futuros, sin domingos.
        pasados, futuros = [], []
        cursor = hoy - timedelta(days=1)
        while len(pasados) < 2:
            if cursor.weekday() != 6:
                pasados.append(cursor)
            cursor -= timedelta(days=1)
        cursor = hoy + timedelta(days=1)
        while len(futuros) < 2:
            if cursor.weekday() != 6:
                futuros.append(cursor)
            cursor += timedelta(days=1)
        dias = sorted(pasados) + sorted(futuros)

        # Reinicia solo las citas demo para mantener la idempotencia entre días.
        Consulta.objects.filter(cita__motivo__startswith="[DEMO]").delete()
        Cita.objects.filter(motivo__startswith="[DEMO]").delete()

        motivos = [
            "Control general y evaluación de síntomas persistentes.",
            "Dolor de cabeza recurrente durante la última semana.",
            "Revisión de resultados de laboratorio y control.",
            "Molestias estomacales después de las comidas.",
            "Evaluación dermatológica de lesión en el brazo.",
            "Seguimiento de tratamiento indicado previamente.",
            "Dificultad para dormir y estrés académico.",
            "Control preventivo de presión arterial.",
            "Dolor muscular tras actividad física intensa.",
            "Consulta por alergias estacionales.",
        ]
        total_citas = 0
        total_consultas = 0
        for indice in range(30):
            dia = dias[indice // 8]
            medico = medicos[(indice % 8) + 1]
            paciente = pacientes[(indice * 7) % 15 + 1]
            hora = time(8, 0 + 0) if False else time(8 + (indice % 8) // 2, 30 * (indice % 2))
            # Horas 08:00, 08:30, 09:00 ... 11:30 (una por médico y día).
            hora = time(8 + (indice % 8) // 2, 30 * (indice % 2))
            es_pasada = indice // 8 < 2
            if es_pasada:
                estado = Cita.Estado.CANCELADA if indice % 3 == 0 else Cita.Estado.COMPLETADA
            else:
                estado = Cita.Estado.CONFIRMADA if indice % 2 == 0 else Cita.Estado.PENDIENTE
            cita, creada = Cita.objects.get_or_create(
                paciente=paciente, medico=medico, fecha=dia, hora=hora,
                defaults={
                    "especialidad": medico.especialidad,
                    "motivo": f"[DEMO] {motivos[indice % len(motivos)]}",
                    "estado": estado,
                },
            )
            if not creada:
                cita.especialidad = medico.especialidad
                cita.motivo = f"[DEMO] {motivos[indice % len(motivos)]}"
                cita.estado = estado
                cita.save()
            total_citas += 1

            if cita.estado == Cita.Estado.COMPLETADA and not Consulta.objects.filter(cita=cita).exists():
                consulta = Consulta.objects.create(
                    cita=cita,
                    medico=medico,
                    diagnostico=(
                        "Cuadro clínico leve compatible con un proceso transitorio; "
                        "sin signos de alarma al examen."
                    ),
                    tratamiento=(
                        "Reposo relativo, hidratación y control de síntomas. "
                        "Reevaluar si persiste por más de 72 horas."
                    ),
                    medicamentos="Paracetamol 500 mg cada 8 horas por 2 días (ficticio).",
                    proxima_cita=hoy + timedelta(days=8 + (indice % 5)),
                    archivos_referencia=f"informe_demo_{indice:02d}.pdf (simulado)",
                )
                total_consultas += 1
                if indice < 6:
                    NotaClinica.objects.create(
                        consulta=consulta,
                        autor=medico.usuario,
                        contenido="Nota de demostración: paciente refiere mejoría parcial.",
                    )
        return total_citas, total_consultas
