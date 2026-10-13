# Ejemplos ficticios de contratos

Estos archivos se construyeron manualmente a partir de los nombres y estructuras observados en el código. No proceden de solicitudes ni documentos reales; no son fixtures que acrediten una extracción OCR correcta.

- `solicitud-actual-create.json`: cuerpo del POST Python, con el contenido completo de filiación dentro de `datos`.
- `solicitud-actual-read.json`: ejemplo de respuesta Python con campos del registro.
- `extraccion-ine.json`, `extraccion-acta.json`, `extraccion-qr-acta.json`: respuestas ilustrativas; pueden omitir detalles adicionales del extractor. Se muestran resultados incompletos con advertencias para recordar que `null` es válido.
- `codigo-postal.json`: estructura de respuesta con valores ficticios; CP `00000` no acredita una entrada real del catálogo.
- `error-actual.json`: error HTTP personalizado del backend Python. No representa todos los posibles errores de validación FastAPI.
- `solicitud-java-create-propuesta.json`: DTO mínimo propuesto para la API nueva. No es un contrato actualmente implementado.

Las CURP están ausentes deliberadamente. Estos ejemplos no deben usarse como prueba de validación de CURP ni como datos suficientes para enviar una solicitud nueva en Java. Fechas, nombres, direcciones, correo e identificadores son de demostración.
