# Verificación de MESA Formación

Fecha: 3 de noviembre de 2026.

- Se extrajeron los seis Word originales y se conservaron sus huellas SHA-256 en `data/source_manifest.json`.
- Las copias se exportaron con Word a PDF y se revisaron las 15 páginas renderizadas. Las figuras de los formularios se recortaron de estas copias, conservando las flechas de medición y los dibujos. Los originales permanecen intactos.
- Se recrearon 47 preguntas. Los cambios de interacción (relaciones por listas, marcas en imágenes y celdas para conversiones) se describen en README.
- `python -m unittest discover -s tests -v`: 12 pruebas correctas. Se usó una SQLite temporal separada de la base operativa. Cubren acceso administrativo y CSRF, protección de claves públicas, envío idempotente, respuestas requeridas, validación de marcas/tablas, límites de puntos, revisión manual, dashboard, versiones, borradores, archivo y CSV seguro.
- `node tests/check_render.cjs`: correcto. Comprueba generación de formularios para todas las preguntas importadas, nueve tipos del editor y resultados pendientes. No sustituye una prueba de navegación o de layout real.
- `node --check static/app.js` y compilación de Python: correctas.
- La base operativa tiene seis exámenes y cero intentos sintéticos.
- El servicio local se inició en http://127.0.0.1:55290. El puerto 58300 fue rechazado por Windows; todos los archivos de configuración usan 55290.

La comprobación visual en navegador no se completó: el host de navegador integrado no estaba disponible y las ventanas nativas de Edge y Brave estaban minimizadas e inaccesibles para el adaptador. Sí se revisaron las imágenes y documentos de origen. No se afirma una certificación visual en dispositivos móviles ni un despliegue público.

Las claves de respuesta y puntajes oficiales no estaban en los Word. Las preguntas importadas se califican manualmente hasta que Capacitación configure y publique claves. Los criterios iniciales de un punto por pregunta, 80% aprobatorio y 20 minutos sugeridos son editables y requieren validación operativa.
