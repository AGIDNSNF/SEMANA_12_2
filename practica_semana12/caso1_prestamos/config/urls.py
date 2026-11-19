from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "UNCP · Administración de Préstamos"
admin.site.site_title = "Préstamos UNCP"
admin.site.index_title = "Panel administrativo"

handler403 = "prestamos.views.acceso_denegado"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("prestamos.urls")),
]
