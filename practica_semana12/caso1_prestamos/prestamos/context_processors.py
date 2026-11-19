from .permissions import rol_principal


def alertas_globales(request):
    """Variables disponibles en todas las plantillas."""
    user = getattr(request, "user", None)
    return {
        "prestamos_vencidos_usuario": getattr(request, "prestamos_vencidos", 0),
        "rol_actual": rol_principal(user) if user and user.is_authenticated else None,
    }
