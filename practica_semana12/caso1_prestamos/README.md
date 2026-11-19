# Caso 1 · Sistema de Gestión de Préstamos de Equipos de Laboratorio

Aplicación Django 5.2 LTS desarrollada para la **Práctica Grupal Semana 12** del curso **IS093A (UNCP)**.
Permite administrar el catálogo de laboratorios y equipos, solicitar y aprobar préstamos,
registrar devoluciones y auditar las acciones sensibles.

> Todos los datos incluidos son ficticios y se generan con el comando `crear_datos_demo`.

---

## 1. Objetivo

Digitalizar el préstamo de equipos de laboratorio de una universidad, controlando:

- disponibilidad real de stock por equipo;
- fechas coherentes de préstamo y devolución;
- cupo máximo de préstamos activos por docente;
- devoluciones únicas y atómicas;
- trazabilidad completa (auditoría en base de datos y archivo de log).

## 2. Roles y permisos

| Rol | Puede hacer |
|---|---|
| **Administrador** | Gestiona laboratorios, equipos, préstamos, devoluciones, reportes y auditoría. |
| **Docente** | Consulta el catálogo y registra solicitudes de préstamo propias. |
| **Asistente** | Aprueba/rechaza solicitudes, registra préstamos directos y devoluciones. |
| **Invitado** | Solo consulta el catálogo de equipos. |

Los permisos se implementan con **grupos de Django** y se verifican siempre en el servidor
(`prestamos/permissions.py`). Ningún control se delega al navegador.

## 3. Funcionalidades principales

- Catálogo público de equipos con filtros por laboratorio, categoría y estado.
- Ficha de equipo con stock total, cantidad prestada y disponible calculada.
- Solicitud de préstamo con validación de fechas, cantidad, stock y cupo.
- Aprobación o rechazo por parte del asistente/administrador.
- Préstamo directo en ventanilla (el asistente lo deja `activo`).
- Registro de devolución única, atómica, con estado del equipo al retornar.
- Reportes con exportación CSV y auditoría paginada.
- Gestión de equipos con protección contra eliminación si tienen préstamos activos.

## 4. Modelo de datos

| Modelo | Campos relevantes |
|---|---|
| `Laboratorio` | nombre, código, ubicación, descripción, activo. |
| `Equipo` | código patrimonial, nombre, marca, modelo, categoría, estado, laboratorio, stock, último mantenimiento. |
| `Prestamo` | docente, equipo, cantidad, fechas, estado, observaciones, asistente responsable. |
| `Devolucion` | préstamo (1:1), fecha, estado del equipo, observaciones, asistente. |
| `Auditoria` | usuario, fecha/hora, IP, acción, entidad, descripción. |

Estados de préstamo: `pendiente`, `activo`, `devuelto`, `vencido`, `rechazado`.
Los estados `pendiente`, `activo` y `vencido` ocupan stock.

### Reglas de negocio implementadas

1. **Máximo 3 préstamos activos por docente** (pendientes, activos o vencidos).
2. **La fecha prevista de devolución debe ser posterior** a la fecha de préstamo.
3. **Solo equipos operativos** pueden prestarse.
4. **Stock suficiente** validado al crear, aprobar y devolver.
5. **Una sola devolución por préstamo**; el préstamo pasa a `devuelto`.
6. **No se elimina un equipo** con préstamos pendientes, activos o vencidos.
7. **Sanitización** de textos y rechazo de HTML en observaciones.
8. **Transacciones atómicas** con `select_for_update()` para evitar sobreasignación.
9. **Sesión de 30 minutos** de inactividad, renovada en cada petición.
10. **Auditoría** de login, logout, login fallido, solicitud, aprobación, rechazo, devolución, equipo y acceso denegado.

## 5. Seguridad y middleware

- `ActividadSesionMiddleware`: cierra la sesión tras 30 minutos de inactividad.
- `AlertaPrestamosMiddleware`: calcula vencidos y alertas para la barra superior.
- `AuditoriaMiddleware`: registra respuestas 403 y eventos de acceso.
- Cookies `HttpOnly`, `SameSite=Lax`, protección CSRF y `X-Frame-Options: DENY`.
- Configuración para HTTPS mediante variables de entorno:
  - `DJANGO_SECURE_COOKIES=1`
  - `DJANGO_SSL_REDIRECT=1`
  - `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`.

## 6. Instalación y ejecución

Requisitos: **Python 3.12+** y **Django 5.2 LTS**.

```powershell
# Desde practica_semana12/caso1_prestamos
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py crear_datos_demo
python manage.py runserver 8001
```

Abrir <http://127.0.0.1:8001/>.

También se puede usar el script general desde `practica_semana12`:

```powershell
.\instalar.ps1
.\iniciar_caso1.ps1
```

## 7. Credenciales de demostración

Contraseña única: **`Demo12345!`** (se puede cambiar con la variable `DEMO_PASSWORD`).

| Usuario | Rol |
|---|---|
| `admin_uncp` | Administrador |
| `docente1`, `docente2`, `docente3` | Docente |
| `asistente1` | Asistente |
| `invitado1` | Invitado |

## 8. Datos de demostración

Al ejecutar `python manage.py crear_datos_demo` se generan:

- 5 laboratorios;
- 10 equipos;
- 6 usuarios;
- 15 préstamos en distintos estados;
- 7 devoluciones.

El comando es **idempotente**: puede ejecutarse nuevamente sin duplicar registros.

## 9. Rutas principales

| Ruta | Descripción |
|---|---|
| `/` | Catálogo de equipos |
| `/login/`, `/logout/` | Autenticación |
| `/dashboard/` | Panel según rol |
| `/mis-prestamos/` | Préstamos del docente |
| `/prestamos/` | Listado general (asistente/admin) |
| `/prestamos/solicitar/` | Nueva solicitud |
| `/prestamos/rapido/` | Préstamo directo en ventanilla |
| `/devoluciones/` | Devoluciones pendientes |
| `/reportes/` | Reportes y exportación CSV |
| `/auditoria/` | Bitácora de auditoría |
| `/admin/` | Administración Django |

## 10. Pruebas automatizadas

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test prestamos -v 2
```

Cobertura funcional (32 pruebas):

- validación de DNI/códigos, stock y fechas;
- límite de 3 préstamos activos;
- equipos no operativos;
- devolución única y actualización de estado;
- protección de eliminación;
- permisos por rol y objeto;
- expiración de sesión a los 30 minutos;
- vistas principales y admin.

> El resultado real de la última ejecución se documenta en
> `../RESULTADOS_PRUEBAS.md`. No se incluyen capturas inventadas.

## 11. Estructura del proyecto

```
caso1_prestamos/
├── config/                 # settings, urls, wsgi/asgi
├── prestamos/
│   ├── management/commands/crear_datos_demo.py
│   ├── migrations/
│   ├── admin.py            # admin personalizado
│   ├── forms.py
│   ├── middleware.py       # sesión, alertas, auditoría
│   ├── models.py
│   ├── permissions.py
│   ├── services.py         # reglas transaccionales
│   ├── tests.py
│   ├── urls.py
│   ├── utils.py
│   ├── validators.py
│   └── views.py
├── static/                 # Bootstrap 5.3.3 local + CSS propio
├── templates/
├── logs/                   # auditoria.log (generado)
├── manage.py
├── requirements.txt
└── README.md
```

## 12. Limitaciones y decisiones

- SQLite es suficiente para la práctica; no se usa Docker, Redis ni Celery.
- El correo usa el backend de consola (no se envían correos reales).
- Las capturas de pantalla y el informe final se completan manualmente; este repositorio
  no incluye imágenes simuladas.
- Bootstrap se almacena localmente para funcionar sin Internet.
- Las decisiones ampliadas están en `../DECISIONES_TECNICAS.md`.
