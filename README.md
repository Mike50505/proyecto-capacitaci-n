# MESA Formación

Portal de evaluaciones para empleados y postulantes. Aplicación local con Python 3.11 o posterior, SQLite y HTML/CSS/JavaScript; no requiere instalar paquetes para ejecutarse.

## Inicio

Desde esta carpeta:

```powershell
python server.py
```

Abrir http://127.0.0.1:55290/. El panel administrativo está en http://127.0.0.1:55290/#dashboard. En el primer inicio se genera un usuario `admin` con contraseña aleatoria en `private/primer_acceso.txt`. Cambiarla desde el panel. No existe una contraseña universal ni se devuelve por la API.

Los participantes eligen examen, indican nombre, tipo (empleado o postulante), nómina cuando corresponde y departamento/puesto. Las respuestas se guardan en el servidor mientras responden y quedan cerradas al enviar. El enlace del intento permite continuarlo o consultar su resultado; debe conservarse como privado.

## Exámenes recreados

Se incluyeron 47 preguntas en los seis documentos originales: cinta métrica (8), interpretación básica de dibujo (8), liberación de primera pieza (7), política y objetivos de calidad (6), Master Web (10) y Vernier (8). Las figuras se recortaron de las copias PDF exportadas por Word, conservando flechas, dibujos y medidas. Los documentos originales no se modificaron.

Las preguntas de encerrar en dibujos se responden marcando la imagen. La identificación de partes del Vernier permite etiquetas por marca. Las relaciones por líneas se adaptaron a listas por concepto. La cinta métrica presenta un dibujo bajo la instrucción de convertir una tabla: se conservaron el dibujo y sus siete cotas, añadiendo un campo de conversión por cota.

Los documentos no contienen una clave oficial: todas las preguntas iniciales requieren revisión manual. No se asumieron respuestas correctas. Capacitación puede configurar claves en el editor y publicar una versión nueva. Se propone 80% de aprobación y 20 minutos sugeridos, editables; la duración no es un temporizador. Los puntajes iniciales son un punto por pregunta, también editables. Validar esos criterios antes de usar los resultados como calificación oficial.

## Administración

El apartado **Usuarios** está disponible únicamente para la cuenta administradora. Permite crear encargados de capacitación, editar sus nombres, activar/desactivar el acceso y restablecer contraseñas. Los encargados tienen las mismas funciones de exámenes, resultados, revisión y dashboards, excepto administrar cuentas. Desactivar una cuenta cierra sus sesiones y conserva sus registros. El administrador permanece activo; los permisos se comprueban en el servidor.

- Dashboard con participación, pendientes, promedio y aprobación solo de evaluaciones calificadas; filtros por examen, participante y fechas.
- Exámenes con borradores, publicación versionada, archivo/restauración y enlaces para compartir.
- Nueve tipos: opción única, selección múltiple, verdadero/falso, respuesta corta/larga, número, relaciones, tablas e imagen con marcas.
- Clave y tolerancia para calificación automática; revisión manual con puntos y observaciones por pregunta.
- Carga de imágenes PNG/JPEG de hasta 5 MB.
- Resultados individuales, impresión y CSV con protección contra fórmulas de hoja de cálculo.

Editar un examen no modifica intentos anteriores: cada intento conserva una copia de la versión y su criterio aprobatorio. Las claves nunca se incluyen en las respuestas públicas de la API. La administración usa sesiones de ocho horas, contraseña con scrypt, CSRF y control de origen. La base, credenciales y extracción de documentos no se sirven por HTTP.

## Datos y operación

SQLite se guarda en `private/capacitacion.sqlite3` con WAL. Las imágenes nuevas están en `assets/uploads`. Mantener ambos en respaldos coordinados. Para generar un respaldo consistente de la base e imágenes:

```powershell
python scripts/backup.py
```

Para red interna, configurar host/puerto y un proxy HTTPS autorizado. El proceso local se enlaza a loopback por omisión; no publica el portal a Internet. En HTTPS usar `TRAINING_SECURE_COOKIE=1`. `TRAINING_DATA_DIR` permite cambiar la carpeta privada. No colocar una base SQLite en una carpeta de red compartida.

Alternativa Docker (servicio independiente de los otros proyectos):

```powershell
docker compose up -d --build
docker compose exec web cat private/primer_acceso.txt
```

Conserva base e imágenes en volúmenes. No usar `docker compose down -v` si se desean conservar los datos. Para uso fuera del equipo hacen falta dominio, HTTPS y el alcance de acceso de empleados/postulantes.

## Verificación

```powershell
python -m unittest discover -s tests -v
node --check static/app.js
```

Las pruebas usan una base temporal y participantes sintéticos. No se cargan resultados de ejemplo en la base operativa. Las utilidades de `scripts/extract_sources.py`, `convert_word.ps1`, `render_sources.py` y `prepare_exams.py` documentan la extracción; los paquetes de lectura PDF solo se usan para preparar los documentos y no son dependencias de la aplicación.
