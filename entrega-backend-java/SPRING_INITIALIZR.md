# Crear el proyecto en Spring Initializr

Referencia verificada el 6 de octubre de 2026. La captura del usuario muestra Spring Boot 4.1.1 y Java 21 disponibles. La documentación oficial confirma que Boot 4.1.1 admite Java 21.

## 1. Selecciones del formulario

En https://start.spring.io configura:

| Campo | Selección |
|---|---|
| Project | Maven |
| Language | Java |
| Spring Boot | 4.1.1, estable |
| Group | `mx.gob.seiem` |
| Artifact | `plataforma-api` |
| Package name | `mx.gob.seiem.plataforma` |
| Packaging | Jar |
| Configuration | YAML |
| Java | 21 |

El group y package son sugerencias; la dependencia puede tener sus propias convenciones. Cambia el package manualmente si el generador propone `mx.gob.seiem.plataformaapi` a partir del artifact.

Maven facilita seguir esta guía y usar Maven Wrapper. Jar permite ejecutar la aplicación con su servidor integrado. YAML es una preferencia de legibilidad; Properties también sería válido, pero mantén el formato seleccionado en la nueva sesión.

No selecciones SNAPSHOT ni M2 para este proyecto inicial. Si utilizas esta guía después y la versión cambia, verifica una versión estable compatible en la documentación; no copies ejemplos de Boot 2/3 dentro de Boot 4 sin revisar compatibilidad.

## 2. Add Dependencies

Busca y agrega estas dependencias:

| Nombre en el buscador | Uso |
|---|---|
| Spring Web | API HTTP con Spring MVC |
| Spring Data JPA | Persistencia y repositorios |
| PostgreSQL Driver | Conexión a PostgreSQL |
| Validation | Validación de DTO con Jakarta Validation |
| Spring Security | Autenticación y autorización |
| Flyway Migration | Migraciones versionadas |
| Spring Boot Actuator | Salud de la aplicación |

Si la etiqueta de Spring Web aparece como Spring Web MVC, elige la variante MVC/Servlet; no agregues WebFlux para este alcance.

No necesitas Lombok, Spring Data REST, OAuth2 Authorization Server, Spring AI, Kubernetes, Redis ni Kafka para esta primera etapa. Esta selección es una propuesta de alcance, no una limitación de esas herramientas.

Los starters de pruebas que genere Initializr se conservan. La IA añadirá Spring Security Test, Testcontainers y el starter OpenAPI compatible cuando implemente y pruebe las funcionalidades. Debe verificar también el módulo de soporte de Flyway para PostgreSQL y no fijar versiones de librerías administradas por Spring Boot innecesariamente.

OpenAPI con Swagger UI se puede añadir mediante `springdoc-openapi-starter-webmvc-ui`. La documentación consultada presenta la línea 3.x para Spring Boot 4; la IA debe confirmar la combinación exacta compatible al editar el pom. No añadir Springfox ni una versión 2.x de springdoc para este proyecto Boot 4.

## 3. Generate y extracción

1. Pulsa Generate y descarga `plataforma-api.zip`.
2. Extrae todo el ZIP en la nueva carpeta de trabajo.
3. Conserva `.mvn`, `mvnw`, `mvnw.cmd`, `pom.xml` y `src`.
4. Asegúrate de abrir en el IDE la carpeta que contiene directamente `pom.xml`. Evita abrir una carpeta superior vacía por una extracción con doble anidación.
5. Copia `entrega-backend-java` dentro de esa carpeta y renómbrala `referencias`.
6. Configura el SDK/JDK del proyecto a Java 21.

Se comprobó que en la terminal del proyecto original hay Temurin/OpenJDK 21 instalado. En el nuevo entorno verifica que tanto el IDE como Maven usen ese JDK:

```powershell
java -version
javac -version
.\mvnw.cmd --version
```

Maven Wrapper puede descargar Maven y dependencias en su primera ejecución; requiere acceso a los repositorios correspondientes. No necesitas instalar Maven globalmente para usar el wrapper.

## 4. Qué falta antes de arrancar

El generador crea la base del proyecto, no implementa solicitudes, permisos de negocio ni conexión completa a la base.

Como agregaste JPA, PostgreSQL y Flyway, necesitas configurar y tener disponible una base PostgreSQL antes de arrancar normalmente la aplicación o ejecutar pruebas que cargan el contexto completo. Una prueba generada puede fallar por falta de esa configuración; no lo resuelvas quitando JPA, seguridad o migraciones para ocultar el problema.

Usa el prompt para que la IA cree `application.yml`, el perfil local, las migraciones y un `compose.yml` para PostgreSQL independiente. Spring Boot no carga automáticamente un archivo `.env` como variables de entorno del proceso Java; la IA debe documentar el mecanismo elegido.

La app Java usará inicialmente el puerto 8080; el servicio Python existente usa 8000. La primera etapa no necesita que Python esté ejecutándose.

Después de que la IA configure la base y credenciales locales, los comandos orientativos serán:

```powershell
docker compose up -d
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run -Dspring-boot.run.profiles=local
```

El compose que se implemente en esta etapa debe contener solamente PostgreSQL local y bind de su puerto a 127.0.0.1. Si no dispones de Docker, utiliza PostgreSQL instalado localmente y documenta la configuración alternativa.

## Fuentes oficiales

- Generador: https://start.spring.io/
- Requisitos Spring Boot: https://docs.spring.io/spring-boot/system-requirements.html
- Spring Initializr: https://docs.spring.io/initializr/docs/current/reference/html/
- Inicialización y migraciones: https://docs.spring.io/spring-boot/how-to/data-initialization.html
- Documentación de springdoc: https://springdoc.org/
