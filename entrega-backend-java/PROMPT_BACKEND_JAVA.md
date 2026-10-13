Actúa como desarrollador senior de Java y Spring Boot. Ayúdame a implementar el backend de una plataforma institucional que reunirá proyectos de una dependencia pública. Quiero aprender mientras construimos: explica brevemente las decisiones importantes y entrega código funcional, con pasos verificables.

Trabajarás en una carpeta nueva. Ya generé el proyecto con Spring Initializr y el pom.xml está en esta carpeta. No crees otro proyecto dentro del existente.

ANTES DE PROGRAMAR

1. Lee las instrucciones del repositorio y revisa pom.xml, la versión del JDK y los archivos generados.
2. Lee referencias/README.md y referencias/CONTEXTO_Y_CONTRATOS.md. Consulta referencias/ejemplos y referencias/codigo-python cuando necesites comprobar un formato.
3. Las referencias describen el backend anterior y, por separado, propuestas para Java. No presentes una propuesta como una regla ya implementada. Los JSON son ejemplos ficticios, no datos reales ni resultados obtenidos mediante OCR.
4. Conserva los archivos existentes, Maven Wrapper y referencias. No copies Python a src/main/java, no modifiques el proyecto original ni conectes a su MySQL.
5. Verifica compatibilidad en documentación oficial. Usa el pom generado como base; no bajes la versión de Spring Boot ni cambies de base de datos silenciosamente.

TECNOLOGÍAS Y ESTRUCTURA

- Java 21, Spring Boot 4.1.1 estable si es la versión generada, Maven y PostgreSQL.
- Spring Web MVC, Data JPA, Jakarta Validation, Security, Flyway y Actuator.
- Documentación OpenAPI con una versión de springdoc compatible con este Spring Boot.
- JUnit y pruebas de integración contra PostgreSQL; Testcontainers cuando Docker esté disponible.
- Paquete raíz mx.gob.seiem.plataforma, salvo que el proyecto generado use otro que debamos conservar.
- Monolito modular organizado por funcionalidad. Empieza por filiacion y seguridad; no crees módulos vacíos para todos los proyectos futuros.
- Dentro de filiacion organiza controladores, servicios, DTO, entidades y repositorios con responsabilidades claras. Usa composición y evita un BaseService genérico o capas vacías.
- No expongas entidades JPA ni Page de Spring directamente como contratos públicos; define DTO de respuesta y paginación estable.
- Usa records para DTO cuando resulte adecuado y mapeos explícitos. No añadas Lombok o MapStruct en esta primera etapa para ocultar lo que debo aprender.

PRIMERA ETAPA: SOLICITUDES DE FILIACIÓN

Implementa solamente crear borradores, consultar, actualizar borradores propios y enviar solicitudes. El servidor controla estados y propiedad.

Modelo mínimo:
- id UUID.
- nombreCompleto, curp y correoElectronico.
- estado BORRADOR o ENVIADA en esta etapa.
- creadoPor, tomado de la identidad autenticada, nunca del cuerpo de la petición.
- createdAt y updatedAt como eventos UTC mediante Instant, generados por el servidor.
- version con bloqueo optimista mediante @Version.

Los datos completos de domicilio, referencias, registro civil, rasgos y fotos están documentados para ampliar el módulo después. Explica cómo los incorporaremos sin implementarlos todavía ni afirmar que el modelo mínimo reemplaza toda la filiación anterior.

API nueva:
- POST /api/v1/solicitudes: crea BORRADOR, responde 201 y Location.
- GET /api/v1/solicitudes: paginación, filtros por estado/nombre y ordenación limitada a campos permitidos; tamaño por defecto 20 y máximo 100.
- GET /api/v1/solicitudes/{id}: consulta autorizada.
- PUT /api/v1/solicitudes/{id}: actualiza un borrador propio; recibe la versión esperada.
- POST /api/v1/solicitudes/{id}/enviar: recibe la versión esperada, valida y cambia BORRADOR a ENVIADA.

Reglas:
- En borrador pueden faltar nombre, CURP y correo. Si hay valores, valida longitudes y formatos aplicables; convierte cadenas en blanco a ausencia de manera consistente.
- Nombre máximo 220 caracteres y correo máximo 180.
- Para enviar exige nombre no vacío, CURP de formato válido y correo válido. Documenta que el formato de CURP no verifica identidad oficial.
- Normaliza CURP a mayúsculas. No modifiques arbitrariamente el correo ni otros datos personales.
- No impongas unicidad de CURP sin requisito institucional confirmado.
- Una ENVIADA no se edita ni se vuelve a enviar en esta etapa.
- Una versión antigua devuelve 409; maneja conflictos tanto al comparar la versión como al confirmar la transacción concurrente.
- Las transiciones y permisos se verifican en el servicio además de proteger las rutas.
- No aceptes estado, creador, timestamps o metadatos de revisión como valores que el cliente pueda controlar.

SEGURIDAD DE DESARROLLO

- Implementa exclusivamente para el perfil local usuarios en memoria con roles SOLICITANTE, REVISOR y ADMIN, HTTP Basic y contraseñas mediante variables de entorno sin valores predeterminados incrustados.
- Usa un PasswordEncoder apropiado. No registres contraseñas ni Authorization.
- SOLICITANTE lista/consulta sus solicitudes y actualiza/envía solo sus borradores. REVISOR y ADMIN pueden consultar todas; no modifican borradores ajenos en esta etapa.
- Protege contra acceso a solicitudes de otras personas y documenta si devuelves 403 o 404 para esos casos.
- No implementes JWT casero, registro de usuarios ni SSO todavía. No habilites accidentalmente los usuarios locales fuera de ese perfil.
- Define una política explícita de CORS para el futuro frontend, con orígenes configurables y sin comodines indiscriminados. Explica cómo se maneja CSRF con la autenticación elegida; no lo desactives globalmente sin justificar su alcance.
- Actuator puede exponer solamente salud básica sin detalles sensibles; protege el resto.

PERSISTENCIA Y CALIDAD

- Usa una base PostgreSQL nueva, no la base MySQL anterior.
- Crea migraciones Flyway y verifica su soporte PostgreSQL. Configura Hibernate ddl-auto=validate y open-in-view=false.
- Define constraints e índices para las consultas. Usa transacciones y permite probar fechas con un Clock controlable cuando sea útil.
- Implementa manejo global de errores con ProblemDetail: validación, 400, 401, 403, 404, 409 y fallos internos sin filtrar SQL, rutas privadas ni stack traces.
- Añade ejemplos de peticiones y respuestas a OpenAPI. Configura la documentación para el entorno local y decide explícitamente su acceso.
- No fijes versiones de dependencias administradas por Spring Boot innecesariamente. Revisa las diferencias de imports, starters y pruebas de Boot 4 frente a ejemplos antiguos.

CONFIGURACIÓN Y PRUEBAS

- Usa YAML con valores sensibles desde variables de entorno.
- Crea compose.yml solo para PostgreSQL local, con puerto publicado en 127.0.0.1 y credenciales configurables.
- Un .env de Docker Compose no es cargado automáticamente por el proceso Java. Documenta cómo pasar las variables a PowerShell y al IDE sin guardar secretos.
- Conserva la posibilidad de usar PostgreSQL local sin Docker.
- Prueba creación, validación, envío, edición de una enviada, envío repetido, versión antigua, aislamiento entre propietarios y permisos de consulta.
- Prueba persistencia y migraciones con PostgreSQL real. Si Docker no está disponible, ejecuta las pruebas independientes y documenta las pendientes; no sustituyas silenciosamente PostgreSQL por H2.
- Una prueba que carga el contexto necesita configuración de base y seguridad. No elimines dependencias o pruebas para ocultar fallos de entorno.

LÍMITES DE ESTA ETAPA

No implementes frontend, OCR, fotografías, catálogo postal, Excel, Google Sheets, aprobación/rechazo, borrado ni migración de datos. No añadas Redis, Kafka, Kubernetes ni infraestructura de microservicios. Python seguirá siendo un servicio OCR separado y se integrará por HTTP en otra etapa, con URL y tiempos de espera configurables. No crees clientes o servicios ficticios vacíos para simular que ya está integrado.

La API nueva usa /api/v1 y camelCase. Documenta las diferencias con las referencias: el frontend anterior no funcionará automáticamente. No copies el token opaco Python ni sus permisos implícitos como autenticación Java.

ENTREGA

Entrega código ejecutable, migraciones, configuración de ejemplo sin secretos, README, comandos PowerShell con Maven Wrapper, pruebas y documentación OpenAPI. Explica el flujo de una solicitud desde controlador hasta base de datos y las razones de las decisiones principales. Indica exactamente lo implementado, las comprobaciones ejecutadas y lo pendiente.

Comienza con una revisión del entorno y un plan breve. Después implementa esta etapa de forma autónoma. Pregunta solo cuando falte una decisión indispensable; no me pidas confirmación para cada archivo o elección rutinaria. No publiques ni despliegues a producción.
