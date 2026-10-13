# Contexto y contratos del sistema actual

Fecha de revisión: 6 de octubre de 2026. Fuente: código local, incluyendo cambios existentes sin confirmar en Git. Esta es una descripción estática del código, no una comprobación contra un servidor en ejecución.

## 1. Objetivo institucional

El usuario quiere una plataforma donde reunir proyectos de la dependencia. Java será el núcleo de gestión; React con TypeScript será un frontend independiente. Python quedará para procesamiento OCR.

El primer módulo candidato es filiación. Usuarios, permisos, catálogo de aplicaciones y otros módulos podrán añadirse progresivamente. La elección final entre módulos internos y sistemas independientes dependerá de sus responsabilidades y equipos.

La propuesta inicial es un monolito Java modular, con una sola aplicación desplegable, sin una infraestructura de microservicios para cada función.

## 2. Componentes existentes, según el código

| Componente | Situación actual |
|---|---|
| API | Python, FastAPI, SQLAlchemy, Pydantic |
| Persistencia | MySQL |
| Interfaz | React, TypeScript, Vite |
| OCR de INE | OpenCV, Tesseract; PDF mediante PyMuPDF |
| Actas | Texto digital o procesamiento OCR de imagen/PDF |
| QR de acta | Decodificación de QR; en ciertas condiciones consulta HTTP de verificación |
| Exportación | Generación de Excel a partir de una plantilla, con fotografías y procesamiento de imagen |
| Registro externo | Integración opcional con Google Sheets |

El backend incluye gestión de solicitudes y usuarios, además del OCR. Por eso no se debe conservar todo Python como si fuera solamente un extractor ni traducirlo íntegramente a Java.

## 3. API actual

Prefijo general: `/api`. El contrato Python emplea snake_case en la solicitud exterior y camelCase en numerosos campos de `datos`.

| Método | Ruta | Entrada / salida | Acceso actual observado |
|---|---|---|---|
| GET | `/api/health` | Estado de la conexión a MySQL | Sin autenticación |
| POST | `/api/auth/login` | JSON `username`, `password`; devuelve `token`, `username`, `nombre`, `rol` | Sin sesión previa |
| GET | `/api/auth/me` | Devuelve `username` | Bearer de operador |
| POST | `/api/solicitudes` | JSON de solicitud; devuelve el registro | Sin autenticación |
| GET | `/api/solicitudes` | Lista de hasta 50 solicitudes, más recientes primero | Bearer de operador |
| GET | `/api/solicitudes/{id}` | Registro individual; 404 si no existe | Bearer de operador |
| PUT | `/api/solicitudes/{id}` | Actualización de los campos presentes; devuelve el registro | Bearer de operador |
| GET | `/api/solicitudes/{id}/excel` | Archivo `.xlsx` usando los datos guardados | Bearer de operador |
| POST | `/api/solicitudes/{id}/excel` | Cuerpo de actualización; genera Excel usando `datos` si se proporcionan | Bearer de operador |
| GET | `/api/codigos-postales/{cp}` | JSON `cp`, `opciones` | Sin autenticación |
| POST | `/api/extracciones` | Multipart `tipo`, `pagina`, `archivo`; JSON `tipo`, `resultado` | Sin autenticación |

El POST de Excel no guarda una revisión por sí mismo. Su propósito es exportar los datos recibidos, o los persistidos si no se envían nuevos datos.

La limitación de 50 registros no es paginación. Para Java se propone implementar paginación real y filtros.

### Formato de error actual

Los errores HTTP personalizados suelen devolver `{"detail": "mensaje"}`. FastAPI puede devolver `detail` como una lista en errores de validación de la petición. La nueva API Java podrá usar ProblemDetail; deberá documentar esa diferencia.

## 4. Modelo de solicitud persistido

Fuente: `backend/app/models/solicitud.py` y `backend/app/schemas/solicitud.py`.

| Campo | Tipo actual / observación |
|---|---|
| `id` | UUID generado y almacenado como cadena de 36 caracteres |
| `folio` | Cadena opcional, única; no se identificó generación automática en estas rutas |
| `estado` | Cadena de hasta 30 caracteres; valor predeterminado `borrador` |
| `curp` | Cadena opcional, longitud de columna 18, con índice |
| `nombre_completo` | Cadena opcional, hasta 220 caracteres en columna |
| `correo_electronico` | Cadena opcional, hasta 180 caracteres en columna |
| `datos` | Objeto JSON con la información completa de filiación |
| `extracciones` | Lista JSON de resultados de extracción |
| `notas_operador` | Texto opcional |
| `revisado_por` | Username del operador, opcional |
| `revisado_at` | Fecha/hora UTC sin información de zona explícita en el tipo Python |
| `created_at`, `updated_at` | Fechas UTC sin zona explícita en el tipo Python |

La longitud de una columna no equivale a validación del DTO. Actualmente los esquemas aceptan objetos genéricos y estados libres; no hay un catálogo de estados ni una máquina de transiciones en el servicio.

Los metadatos superiores duplican algunos valores de `datos`, como CURP, nombre y correo. En Java deberá definirse una sola fuente de verdad para impedir discrepancias.

## 5. Información completa de filiación

Los nombres siguientes son claves actuales del formulario; no obligan a copiar la misma estructura de tablas a Java.

### Datos personales y administrativos

- `rfc`, `curp`.
- `nombrePartes`: `{apellidos, nombres}`; `nombreCompleto` se compone con apellidos antes de nombres en la interfaz.
- `fechaNacimiento`, `lugarNacimiento`, `sexo`.
- `correoElectronico`, `telefono`, `estadoCivil`.
- `conyugeNombrePartes`, `nombreConyuge`.
- `padreNombrePartes`, `padre`; `madreNombrePartes`, `madre`.
- `noActa`, `anioActa`, `libro`, `clase`, `cartillaSmn`.
- `claveCobro`, `descripcionClave`.
- `lugar`, `fechaFiliacion`.

El formulario usa fechas civiles `YYYY-MM-DD`; son fechas sin hora, distintas de los timestamps de auditoría. Para Java corresponde evaluar `LocalDate` para estas fechas e `Instant` para eventos.

### Domicilio

`domicilio`: `{cp, calle, numeroExterior, numeroInterior, colonia, municipio, estado}`.

CP y números de acta/libro deben preservarse como cadenas donde se necesiten ceros iniciales. No convertir identificadores a números solamente por contener dígitos.

### Referencias

`referencias`: cuatro objetos del formulario actual; dos con `parentesco = Conocido` y dos con `parentesco = Familiar`.

Cada uno contiene `nombre`, `nombrePartes`, `domicilio`, `parentesco`. El nombre y domicilio tienen la misma estructura descrita antes.

La cantidad y distribución son una regla de la interfaz actual, no una validación implementada en el esquema del backend. Deben confirmarse como requisito institucional antes de exigirlas en todos los estados.

### Fotografías

`fotos`: `frenteCuadro`, `frenteOvalo`, `perfilOvalo`. Existen campos heredados `frente` y `perfil` como alternativas.

Actualmente se guardan imágenes como data URLs base64 dentro del JSON. Para una etapa posterior de Java se propone almacenamiento de archivos y referencias, con autorización de acceso, en lugar de replicar este formato de persistencia.

### Rasgos

`rasgos`: `tonoPiel`, `pelo`, `frente`, `cejas`, `ojos`, `nariz`, `boca`, `estatura`, `senasVisibles`.

Estos datos y fotografías no se requieren para construir el CRUD mínimo de la primera etapa, pero no deben perderse en el diseño ni en una futura migración.

## 6. Flujo y reglas observados

1. El formulario del solicitante envía `estado = enviada` directamente al crear el registro.
2. El backend acepta el estado que reciba; el predeterminado del esquema es `borrador`.
3. El operador inicia sesión y consulta la lista de solicitudes.
4. Carga un documento para extracción y aplica la información al formulario.
5. La combinación de datos OCR con el formulario ocurre principalmente en React: suele conservar datos ya capturados y completar vacíos. No es una regla central implementada en el backend.
6. Guarda una revisión mediante PUT, normalmente con `estado = revisada`.
7. Cada PUT registra automáticamente `revisado_por` y `revisado_at`, cualquiera que sea el estado recibido.
8. Si el estado final es exactamente `revisada`, se intenta añadir una fila a Google Sheets cuando la integración está habilitada. Su fallo no revierte la revisión guardada; se registra en logs.
9. El usuario puede descargar el Excel con información persistida o con los cambios del formulario enviados por POST.

Las llamadas repetidas que terminan en `revisada` pueden intentar repetir la escritura a Sheets. No se observó un control de idempotencia en la ruta.

No se observaron reglas backend de propiedad de solicitudes, restricciones de transición, control de concurrencia con versión o comprobación de permisos específicos por rol. La autenticación de operador verifica sesión y usuario activo; la columna `rol` no implica que las rutas hagan autorización por rol.

### Autenticación actual

Usuarios en `usuarios_revision`: `id`, `username`, `nombre`, `password_hash`, `rol`, `activo`, `session_token`, `ultimo_acceso`, `created_at`, `updated_at`.

La contraseña se verifica con PBKDF2-SHA256. Al iniciar sesión se genera un token opaco, almacenado en la base. Es un Bearer, no un JWT. No se observó expiración ni una ruta de cierre de sesión en el archivo revisado.

Estos hechos son referencia, no instrucciones para replicar la autenticación en Java. La autenticación definitiva institucional debe diseñarse por separado.

## 7. Contrato del servicio OCR que podrá consumir Java

Endpoint existente: `POST /api/extracciones`, `multipart/form-data`.

| Campo | Significado |
|---|---|
| `tipo` | `ine`, `acta` o `qr_acta` |
| `pagina` | Entero, predeterminado 1; INE usa la página seleccionada del PDF |
| `archivo` | Archivo de imagen o PDF |

Para `acta` se procesan todas las páginas automáticamente y `pagina` debe ser 1. Para `qr_acta` no se selecciona página: debe enviarse 1 y, si es PDF, la función actual trabaja sobre la primera página.

Extensiones admitidas por la API: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, `.tiff`, `.webp`, `.pdf`.

El límite predeterminado definido en configuración es 15 MiB, sujeto a la configuración de ejecución. El archivo se copia de forma limitada a un temporal, se procesa en un threadpool y se elimina en el bloque final. La extracción actual devuelve su resultado en la misma petición HTTP, sin un identificador de trabajo asíncrono.

El procesamiento de PDF/imagen revisa su contenido dentro de los extractores; el filtro exterior de extensiones no reemplaza la validación real del archivo.

### Respuesta

```json
{
  "tipo": "ine",
  "resultado": {
    "datos": {},
    "advertencias": [],
    "entrada": {}
  }
}
```

El contenido exacto de `resultado` depende del tipo. Véanse los ejemplos y el código; no exigir todas las claves para todos los documentos.

- INE: campos como nombre, CURP, domicilio, código postal, nacimiento y sexo; incluye información de calidad por campo y metadatos de entrada. Los valores no reconocidos pueden ser null. La API no solicita el texto OCR detallado.
- Acta: `persona_registrada`, `registro`, `filiacion`, QR y otros datos; incluye método, página principal y metadatos de páginas. Puede haber actas adicionales.
- QR de acta: estructura de acta con `metodo = qr`; puede completar datos embebidos o consultar la URL de verificación cuando no hay datos estructurados suficientes. No describir esta modalidad como siempre desconectada de Internet.
- `advertencias` son observaciones de extracción; una advertencia no implica por sí sola un error HTTP.
- La confianza OCR expresa evidencia de reconocimiento, no validación oficial de identidad ni autenticidad del documento.

Errores observados: 400 para tipo/formato o argumentos inválidos; 413 para tamaño excesivo; 422 para fallos de extracción; FastAPI también usa 422 si faltan campos multipart obligatorios.

### Propuesta de integración posterior

Java enviará el multipart mediante un cliente HTTP con URL y tiempos de espera configurables. Mantendrá los resultados separados de los datos confirmados por una persona. No sobrescribirá valores confirmados silenciosamente.

El servicio Python deberá tener acceso restringido y autenticación entre servicios antes de exponerse fuera del entorno local. La integración y su implementación están fuera de la primera etapa.

## 8. Exportación Excel y Google Sheets

La exportación depende de una plantilla `.xlsx` externa y una hoja llamada `Plantilla`. El código asigna campos a celdas y añade fotografías. Además de Excel, utiliza OpenCV, NumPy y MediaPipe para preparar imágenes.

La plantilla no está incluida en este paquete. No es suficiente reemplazar todo por un listado genérico de columnas. Antes de portar o delegar la exportación se necesita la plantilla institucional, el mapeo y criterios de aceptación.

Google Sheets está controlado por configuración. Utiliza credenciales de una cuenta de servicio y añade filas. No se copiaron cuentas, identificadores de documentos ni llaves. Esta integración será evaluada en otra etapa.

## 9. Propuesta para la primera etapa Java — no describe el sistema actual

Tecnologías propuestas: Java 21, Spring Boot estable compatible, Maven, PostgreSQL independiente, Spring Web MVC, JPA, Validation, Security, Flyway y documentación OpenAPI compatible.

Paquete raíz sugerido: `mx.gob.seiem.plataforma`; identificador Maven `mx.gob.seiem:plataforma-api`. Son propuestas de nomenclatura, sujetas a las convenciones de la dependencia.

Estados mínimos a implementar: `BORRADOR` y `ENVIADA`. `EN_REVISION`, `REVISADA` o `RECHAZADA` pertenecen a una etapa posterior. `REVISADA` no equivale automáticamente a `APROBADA`.

| Método | Ruta nueva propuesta | Comportamiento |
|---|---|---|
| POST | `/api/v1/solicitudes` | Crea borrador del usuario autenticado; estado decidido por el servidor |
| GET | `/api/v1/solicitudes` | Lista paginada y filtrada según permisos |
| GET | `/api/v1/solicitudes/{id}` | Consulta autorizada de una solicitud |
| PUT | `/api/v1/solicitudes/{id}` | Actualiza solo un borrador del propietario; exige versión |
| POST | `/api/v1/solicitudes/{id}/enviar` | Verifica campos y versión, cambia de BORRADOR a ENVIADA |

DTO mínimo: `nombreCompleto`, `curp`, `correoElectronico`. Respuesta: UUID, esos campos, estado, fecha de creación, fecha de modificación y versión. La entidad registra además el identificador del creador tomado de la identidad autenticada.

Propuesta de reglas: permitir vacíos en borrador; validar formato/longitud si se proporciona un dato; exigir nombre, CURP de formato válido y correo al enviar; limitar nombre a 220 y correo a 180 caracteres; normalizar CURP y no confundir validación de formato con verificación oficial. No imponer unicidad de CURP sin un requisito institucional confirmado.

Para la fase local se proponen usuarios en memoria, autenticación HTTP Basic y roles `SOLICITANTE`, `REVISOR`, `ADMIN`, con credenciales únicamente por variables de entorno. No habrá tabla definitiva de usuarios todavía; es una identidad provisional para probar autorización, no la estrategia de producción.

Un SOLICITANTE consulta y modifica sus propios borradores. REVISOR y ADMIN pueden consultar los registros, pero no modificar borradores ajenos en esta etapa. Los campos del creador y estado no se aceptan como datos confiables enviados por el cliente.

No reutilizar automáticamente tokens del sistema Python ni conectar a la base MySQL existente. No implementar todavía OCR, Excel, Google Sheets, fotos ni la migración del frontend.

## 10. Decisiones a revisar antes de producción

- Identidad institucional, inicio de sesión único, áreas y permisos por módulo.
- Acceso público o autenticado para solicitantes; la propuesta local asume autenticación.
- Estados definitivos y quién puede realizar cada transición.
- Alcance y retención de documentos, fotografías y datos personales.
- Modelo de filiación completo, archivos y trazabilidad.
- Plantilla Excel, catálogo postal, reportes e integración externa.
- Compatibilidad y migración de contratos anteriores.
- Procesamiento OCR síncrono o mediante trabajos en segundo plano según tiempos medidos.

Estas decisiones no deben bloquear el desarrollo del módulo mínimo local ni convertirse en supuestos ocultos de la IA.
