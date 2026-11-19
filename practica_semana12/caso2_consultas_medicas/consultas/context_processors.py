from .permissions import rol_principal


def alertas_medicas(request):
    user = getattr(request, "user", None)
    return {
        "citas_pendientes_medico": getattr(request, "citas_pendientes_medico", 0),
        "rol_actual": rol_principal(user) if user and user.is_authenticated else None,
    }
