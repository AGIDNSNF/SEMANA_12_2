# Informe final · Práctica Grupal Semana 12

> **Plantilla editable.** Reemplace todos los campos entre corchetes con información real.
> No invente nombres, resultados ni capturas. Elimine las instrucciones en cursiva al entregar.

---

## Portada

**Universidad Nacional del Centro del Perú**
**Facultad de Ingeniería de Sistemas**
**Curso:** IS093A · Desarrollo de Aplicaciones Web
**Práctica:** Semana 12 · Sistemas Django con lógica de negocio

**Título:** Implementación de tres sistemas Django: préstamos de equipos, consultas médicas y control de asistencia

**Integrantes:**

| N° | Apellidos y nombres | Código | Rol en el equipo |
|---|---|---|---|
| 1 | [Apellidos, Nombres] | [Código] | [Rol] |
| 2 | [Apellidos, Nombres] | [Código] | [Rol] |
| 3 | [Apellidos, Nombres] | [Código] | [Rol] |
| 4 | [Apellidos, Nombres] | [Código] | [Rol] |

**Docente:** [Nombre completo del docente]
**Fecha de presentación:** [DD/MM/AAAA]
**Repositorio / medio de entrega:** [URL o descripción]

---

## Resumen ejecutivo

*Redactar en 150–250 palabras.* Describir qué se construyó, con qué tecnología, qué reglas de
negocio se implementaron, cuántas pruebas se ejecutaron y cuál fue el resultado. Mencionar que
los datos son ficticios y que las capturas se tomaron durante la ejecución real.

**Palabras clave:** Django, SQLite, lógica de negocio, seguridad, auditoría, pruebas automatizadas.

---

## 1. Introducción

### 1.1 Contexto

*Explicar brevemente la necesidad de digitalizar procesos de préstamo, atención médica y control
de asistencia en una institución.*

### 1.2 Problemática

*Describir los problemas actuales: registros manuales, pérdida de trazabilidad, riesgos de
privacidad, dificultad para controlar stock, horarios y saldos.*

### 1.3 Justificación

*Indicar por qué Django y SQLite son adecuados para la práctica y por qué se prioriza la
seguridad y la auditabilidad.*

---

## 2. Objetivos

### 2.1 Objetivo general

Implementar tres sistemas web independientes con Django 5.2 que automaticen procesos de préstamo,
consulta médica y asistencia, aplicando reglas de negocio, control de acceso, auditoría y pruebas.

### 2.2 Objetivos específicos

1. Diseñar modelos de datos coherentes con cada dominio.
2. Implementar validaciones y reglas de negocio en el servidor.
3. Aplicar autorización por roles y por objeto.
4. Incorporar middleware de sesión, alertas y auditoría.
5. Personalizar el admin de Django.
6. Generar datos ficticios de demostración.
7. Automatizar pruebas y documentar resultados reales.

---

## 3. Alcance y limitaciones

### 3.1 Alcance

- Tres proyectos Django independientes.
- Interfaz web con Bootstrap local.
- Base de datos SQLite.
- Roles, permisos y auditoría.
- Datos demo idempotentes.
- Scripts de instalación, ejecución y pruebas.

### 3.2 Limitaciones

- No se integra pasarela de correo, SMS, reloj biométrico ni almacenamiento real de archivos clínicos.
- No se implementa API REST ni aplicación móvil.
- SQLite no está orientada a alta concurrencia.
- Las capturas y el informe se completan manualmente.
- No se mide cobertura con herramientas externas.

---

## 4. Marco teórico

*Desarrollar brevemente:*

- Arquitectura MVC/MTV de Django.
- Modelos, vistas, plantillas y URLs.
- Formularios y validación.
- Middleware y ciclo petición/respuesta.
- Autenticación, grupos y permisos.
- Transacciones y bloqueo de filas.
- Seguridad web: CSRF, XSS, clickjacking, sesiones.
- Pruebas automatizadas con `TestCase`.

---

## 5. Metodología

*Describir el enfoque: análisis de requisitos, diseño de modelos, implementación por capas,
pruebas, documentación y revisión. Indicar la distribución real del trabajo del equipo.*

| Fase | Actividades | Responsable(s) | Entregable |
|---|---|---|---|
| Análisis | [Actividades] | [Nombres] | [Documento] |
| Diseño | [Actividades] | [Nombres] | [Diagramas] |
| Implementación | [Actividades] | [Nombres] | [Código] |
| Pruebas | [Actividades] | [Nombres] | [Resultados] |
| Documentación | [Actividades] | [Nombres] | [Informe] |

---

## 6. Desarrollo del Caso 1 · Préstamos de equipos

### 6.1 Requisitos

*Resumir roles, reglas y restricciones. Referenciar `MATRIZ_REQUISITOS.md`.*

### 6.2 Arquitectura y modelos

*Incluir el diagrama ER y explicar `Laboratorio`, `Equipo`, `Prestamo`, `Devolucion`, `Auditoria`.*

### 6.3 Reglas de negocio

*Explicar límite de 3 préstamos, fechas, stock, equipos operativos, devolución única,
eliminación protegida, sanitización y atomicidad.*

### 6.4 Seguridad y auditoría

*Explicar sesión de 30 minutos, permisos por rol/objeto, cookies y auditoría.*

### 6.5 Evidencias

*Insertar capturas reales desde `evidencias/caso1/`. Cada imagen debe tener pie de figura.*

**Figura 1.** [Descripción de la captura]. Fuente: elaboración propia.

### 6.6 Pruebas

*Indicar el comando ejecutado y el resultado real (32 pruebas OK). Adjuntar salida de consola.*

---

## 7. Desarrollo del Caso 2 · Consultas médicas

### 7.1 Requisitos

*Resumir roles, validaciones, horarios y privacidad.*

### 7.2 Arquitectura y modelos

*Incluir diagrama ER y explicar `Paciente`, `Medico`, `HorarioAtencion`, `Cita`, `Consulta`,
`NotaClinica`, `AuditoriaMedica`.*

### 7.3 Reglas de negocio

*Explicar DNI, CMP, correo institucional, motivo mínimo, horarios, franjas, superposición,
duplicados, inmutabilidad y notas.*

### 7.4 Privacidad y auditoría

*Explicar acceso al historial, separación recepción/clínica y registro de accesos.*

### 7.5 Evidencias

*Insertar capturas reales desde `evidencias/caso2/`.*

**Figura 2.** [Descripción de la captura]. Fuente: elaboración propia.

### 7.6 Pruebas

*Indicar comando y resultado real (65 pruebas OK).*

---

## 8. Desarrollo del Caso 3 · Asistencia y permisos

### 8.1 Requisitos

*Resumir roles, marcación, correcciones, solicitudes y saldo.*

### 8.2 Arquitectura y modelos

*Incluir diagrama ER y explicar `Area`, `Empleado`, `RegistroAsistencia`,
`CorreccionAsistencia`, `Solicitud`, `AuditoriaAsistencia`.*

### 8.3 Reglas de negocio

*Explicar jornada de 8 horas, horas extra, correcciones, justificación, saldo de 30 días,
días hábiles, superposición y aprobaciones.*

### 8.4 Alcance por área y seguridad

*Explicar visibilidad por rol/área, prohibición de autoaprobación y sesión de 45 minutos.*

### 8.5 Evidencias

*Insertar capturas reales desde `evidencias/caso3/`.*

**Figura 3.** [Descripción de la captura]. Fuente: elaboración propia.

### 8.6 Pruebas

*Indicar comando y resultado real (61 pruebas OK).*

---

## 9. Pruebas y resultados

### 9.1 Entorno

| Elemento | Valor |
|---|---|
| Sistema operativo | [Windows 11 / otro] |
| Python | [3.13.17 u otro] |
| Django | [5.2.19] |
| Base de datos | SQLite |
| Fecha de ejecución | [DD/MM/AAAA] |

### 9.2 Resumen

| Caso | `check` | Migraciones | Pruebas | Resultado |
|---|---|---|---|---|
| 1 | [Sin observaciones] | [Sin cambios] | [32] | [OK] |
| 2 | [Sin observaciones] | [Sin cambios] | [65] | [OK] |
| 3 | [Sin observaciones] | [Sin cambios] | [61] | [OK] |

### 9.3 Análisis

*Comentar qué reglas se probaron, qué errores se encontraron y cómo se corrigieron. No ocultar
fallos; explicar el proceso de depuración.*

### 9.4 Pruebas manuales

| N° | Caso | Acción | Resultado esperado | Resultado obtenido | Evidencia |
|---|---|---|---|---|---|
| 1 | [Caso] | [Acción] | [Esperado] | [Obtenido] | [Figura/archivo] |
| 2 | [Caso] | [Acción] | [Esperado] | [Obtenido] | [Figura/archivo] |

---

## 10. Conclusiones

*Redactar conclusiones verificables, por ejemplo:*

1. Se implementaron tres sistemas independientes con reglas de negocio en el servidor.
2. La separación en servicios permitió reutilizar validaciones y probarlas directamente.
3. El control por rol y objeto redujo accesos indebidos; se verificó con pruebas de 403.
4. La auditoría permitió reconstruir acciones sensibles.
5. Las 158 pruebas automatizadas finalizaron correctamente.
6. La documentación distingue claramente lo ejecutado de lo pendiente.

*Ajustar según los resultados reales del equipo.*

---

## 11. Recomendaciones

- Migrar a PostgreSQL si se requiere concurrencia real.
- Integrar correo institucional y notificaciones.
- Agregar API REST para futuras integraciones.
- Implementar pruebas de carga y medición de cobertura.
- Incorporar respaldo y restauración automatizados.
- Ampliar la accesibilidad y el diseño responsive.
- Documentar políticas de privacidad y retención de datos.

---

## 12. Referencias

*Usar un formato consistente (APA 7 u otro indicado por el docente). Ejemplos:*

- Django Software Foundation. (2026). *Django documentation* (versión 5.2). https://docs.djangoproject.com/
- Python Software Foundation. (2026). *Python documentation*. https://docs.python.org/3/
- Bootstrap. (2026). *Bootstrap 5.3 documentation*. https://getbootstrap.com/docs/5.3/
- [Referencia adicional utilizada]

---

## 13. Anexos

### Anexo A · Credenciales de demostración

*Indicar usuarios y contraseña demo. No incluir contraseñas reales de producción.*

### Anexo B · Comandos de ejecución

```powershell
.\instalar.ps1
.\iniciar_caso1.ps1
.\iniciar_caso2.ps1
.\iniciar_caso3.ps1
.\probar_todo.ps1
```

### Anexo C · Estructura del repositorio

*Incluir árbol resumido.*

### Anexo D · Capturas adicionales

*Agregar las imágenes que no cupieron en el cuerpo del informe.*

### Anexo E · Declaración de honestidad académica

Declaramos que el código, las pruebas y la documentación presentados son de nuestra autoría o
están debidamente referenciados. Las capturas corresponden a la ejecución real del sistema.
Los resultados de pruebas reportados fueron obtenidos en el entorno descrito.

**Firmas:**

| Integrante | Firma |
|---|---|
| [Apellidos, Nombres] | ____________________ |
| [Apellidos, Nombres] | ____________________ |
| [Apellidos, Nombres] | ____________________ |
| [Apellidos, Nombres] | ____________________ |
