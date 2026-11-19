from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Centro Médico UNCP · Administración"
admin.site.site_title = "Centro Médico UNCP"
admin.site.index_title = "Gestión de citas y consultas"

handler403 = "consultas.views.acceso_denegado"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("consultas.urls")),
]
