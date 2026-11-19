# Práctica Grupal Semana 12 · IS093A (UNCP)

Tres sistemas Django 5.2 LTS independientes, con lógica de negocio real, seguridad,
middleware propio, administración personalizada, datos de demostración y pruebas automatizadas.

| Caso | Sistema | Puerto | Aplicación |
|---|---|---|---|
| 1 | Préstamos de equipos de laboratorio | 8001 | `caso1_prestamos` |
| 2 | Gestión de consultas médicas | 8002 | `caso2_consultas_medicas` |
| 3 | Control de asistencia y permisos | 8003 | `caso3_asistencia` |

> **Datos ficticios.** Los comandos de demostración generan personas, documentos y registros
> inventados. No se incluyen capturas de pantalla simuladas ni resultados de pruebas no ejecutadas.

---

## 1. Requisitos

- Windows 10/11 con PowerShell 5.1 o superior.
- Python 3.12 o 3.13 (probado con Python 3.13.17). Django 5.2 no está validado en Python 3.14/3.15.
- Django 5.2 LTS (se instala desde `requirements.txt`).
- Sin Docker, Redis, Celery, React ni Vue.

Si en el equipo hay varias versiones de Python, `instalar.ps1` busca automáticamente
`py -3.13` y luego `py -3.12`. También puede indicar el intérprete:

```powershell
.\instalar.ps1 -PythonExe "C:\Ruta\a\python.exe"
```

Cada caso usa SQLite y Bootstrap 5.3.3 almacenado localmente, por lo que funciona sin Internet.

## 2. Instalación rápida

Desde esta carpeta (`practica_semana12`):

```powershell
.\instalar.ps1
```

El script crea un entorno virtual por caso, instala dependencias, aplica migraciones y genera
los datos de demostración. Si ya existe un entorno, lo reutiliza.

Parámetros disponibles:

```powershell
.\instalar.ps1 -SinDemo                       # no genera datos demo
.\instalar.ps1 -PythonExe "C:\Ruta\python.exe" # intérprete explícito
```

Instalación manual de un caso:

```powershell
cd caso1_prestamos
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py crear_datos_demo
python manage.py runserver 8001
```

## 3. Ejecución

```powershell
.\iniciar_caso1.ps1   # http://127.0.0.1:8001
.\iniciar_caso2.ps1   # http://127.0.0.1:8002
.\iniciar_caso3.ps1   # http://127.0.0.1:8003
```

Cada script abre el navegador y mantiene el servidor en primer plano. Use `Ctrl+C` para detenerlo.
Antes de arrancar, si falta `db.sqlite3` aplica las migraciones y, si no hay usuarios, ejecuta
automáticamente `crear_datos_demo`. Use `-NoBrowser` si prefiere abrir la URL manualmente.

## 4. Credenciales de demostración

Contraseña única: **`Demo12345!`** (se puede cambiar con la variable de entorno `DEMO_PASSWORD`
antes de ejecutar `crear_datos_demo`).

| Caso | Usuarios (cada uno es una cuenta independiente) |
|---|---|
| 1 | `admin_uncp`, `docente1`, `docente2`, `docente3`, `asistente1`, `invitado1` |
| 2 | `admin_medico`, `recepcion1`, `medico1`, `medico2`, `medico3`, `medico4`, `medico5`, `medico6`, `medico7`, `medico8`, `paciente1`, `paciente2`, `paciente3`, `paciente4`, `paciente5`, `paciente6`, `paciente7`, `paciente8`, `paciente9`, `paciente10`, `paciente11`, `paciente12`, `paciente13`, `paciente14`, `paciente15` |
| 3 | `admin_asistencia`, `rrhh1`, `jefe_ti`, `jefe_rrhh`, `jefe_contab`, `jefe_oper`, `contador1`, `empleado1`, `empleado2`, `empleado3`, `empleado4`, `empleado5`, `empleado6` |

> **Importante:** escriba el nombre exacto del usuario. Por ejemplo, `docente1` es válido;
> `docente1-3` **no** es un usuario.

Cada caso incluye un README con el detalle de roles y reglas.

## 5. Pruebas

```powershell
.\probar_todo.ps1
```

El script ejecuta, para cada caso:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test <app>
```

Resultados de la última ejecución (2026-11-19):

| Caso | Pruebas | Resultado |
|---|---|---|
| 1 | 32 | OK |
| 2 | 65 | OK |
| 3 | 61 | OK |
| **Total** | **158** | **OK** |

El detalle de comandos y salidas está en [`RESULTADOS_PRUEBAS.md`](RESULTADOS_PRUEBAS.md).
Las capturas se agregan manualmente según [`GUIA_EVIDENCIAS.md`](GUIA_EVIDENCIAS.md).

## 6. Documentación

| Documento | Contenido |
|---|---|
| [`DOCUMENTACION_TECNICA.md`](DOCUMENTACION_TECNICA.md) | Arquitectura, modelos, reglas, seguridad y despliegue. |
| [`MATRIZ_REQUISITOS.md`](MATRIZ_REQUISITOS.md) | Trazabilidad requisito → implementación → prueba. |
| [`GUIA_EVIDENCIAS.md`](GUIA_EVIDENCIAS.md) | Guion de capturas y evidencias verificables. |
| [`RESULTADOS_PRUEBAS.md`](RESULTADOS_PRUEBAS.md) | Comandos ejecutados y resultados reales. |
| [`DECISIONES_TECNICAS.md`](DECISIONES_TECNICAS.md) | Decisiones, ventajas y trade-offs. |
| [`INFORME_FINAL_PLANTILLA.md`](INFORME_FINAL_PLANTILLA.md) | Plantilla editable del informe final. |
| [`evidencias/README.md`](evidencias/README.md) | Organización de capturas por caso. |

## 7. Estructura

```
practica_semana12/
├── caso1_prestamos/
├── caso2_consultas_medicas/
├── caso3_asistencia/
├── evidencias/
│   ├── caso1/
│   ├── caso2/
│   └── caso3/
├── instalar.ps1
├── iniciar_caso1.ps1
├── iniciar_caso2.ps1
├── iniciar_caso3.ps1
├── probar_todo.ps1
├── DOCUMENTACION_TECNICA.md
├── MATRIZ_REQUISITOS.md
├── GUIA_EVIDENCIAS.md
├── RESULTADOS_PRUEBAS.md
├── DECISIONES_TECNICAS.md
└── INFORME_FINAL_PLANTILLA.md
```

## 8. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `... no se puede cargar el archivo ... porque la ejecución de scripts está deshabilitada` | Política de ejecución de PowerShell | `powershell -ExecutionPolicy Bypass -File .\instalar.ps1` |
| `No module named 'django'` | Se usó el Python global, no el del caso | Ejecute con `.\casoN_*\.venv\Scripts\python.exe manage.py ...` o use los scripts `.ps1`. |
| `No se encontró Python 3.12 o 3.13` | El equipo solo tiene 3.14/3.15 | Instale Python 3.13 o use `-PythonExe` con una ruta válida. |
| Acentos mal mostrados en la consola | Codificación de la terminal | Los scripts fijan `PYTHONIOENCODING=utf-8`; ejecute con `powershell -NoProfile`. |
| `database is locked` | Dos procesos sobre la misma SQLite | Detenga el otro proceso; SQLite admite un escritor a la vez. |
| “Usuario o contraseña incorrectos” con credenciales demo | La base no tiene los datos demo (por ejemplo, tras borrar `db.sqlite3`) | Ejecute `python manage.py crear_datos_demo` o simplemente inicie con `.\iniciar_casoN.ps1`: el script detecta que no hay usuarios y genera los datos. |

## 9. Nota de honestidad académica

- Los resultados de pruebas documentados corresponden a ejecuciones reales en este equipo.
- Las capturas de pantalla deben tomarlas los integrantes al ejecutar la aplicación.
- No se atribuyen repositorios, despliegues ni métricas que no hayan sido verificados.
- Complete el informe final con los nombres reales de los integrantes y del docente.
