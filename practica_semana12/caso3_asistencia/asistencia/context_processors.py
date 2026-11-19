from .permissions import empleado_de, rol_principal


def contexto_asistencia(request):
    user = getattr(request, "user", None)
    return {
        "rol_actual": rol_principal(user) if user and user.is_authenticated else None,
        "empleado_actual": empleado_de(user) if user and user.is_authenticated else None,
        "solicitudes_pendientes": getattr(request, "solicitudes_pendientes", 0),
    }
