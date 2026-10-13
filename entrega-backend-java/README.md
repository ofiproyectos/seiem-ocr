# Referencias para iniciar la plataforma institucional en Java

Preparado el 6 de octubre de 2026 a partir del código de este repositorio.

Esta carpeta contiene documentación, ejemplos ficticios y copias seleccionadas de código. No es un backend ejecutable ni una migración de datos. El proyecto Python original sigue siendo la fuente de los extractores OCR.

## Cómo usarla

1. Genera `plataforma-api` en Spring Initializr siguiendo `SPRING_INITIALIZR.md`.
2. Extrae el proyecto en la nueva carpeta donde desarrollarás la plataforma.
3. Copia esta carpeta completa dentro del proyecto generado y renómbrala `referencias`.
4. Abre en tu IDE la carpeta que contiene `pom.xml`.
5. Copia el contenido de `PROMPT_BACKEND_JAVA.md` en la IA de esa nueva sesión.
6. La IA debe leer primero `CONTEXTO_Y_CONTRATOS.md` y distinguir lo existente de lo propuesto.

La estructura resultante será:

```text
plataforma-api/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
├── src/
└── referencias/
    ├── README.md
    ├── CONTEXTO_Y_CONTRATOS.md
    ├── SPRING_INITIALIZR.md
    ├── PROMPT_BACKEND_JAVA.md
    ├── ejemplos/
    └── codigo-python/
```

## Contenido

- `CONTEXTO_Y_CONTRATOS.md`: responsabilidades, API actual, campos, reglas observadas, límites y propuestas para Java.
- `SPRING_INITIALIZR.md`: configuración exacta del generador y requisitos para arrancar.
- `PROMPT_BACKEND_JAVA.md`: instrucciones completas para la IA del nuevo proyecto.
- `ejemplos/`: cuerpos y respuestas sintéticos para comprender los formatos. No son resultados reales de OCR ni registros de personas.
- `codigo-python/`: instantánea de fuentes seleccionadas, con sus rutas originales, para consulta. No incluye todos los archivos necesarios para ejecutarlas.

## Qué se excluyó

No se copiaron `.env`, credenciales, tokens reales, cuentas de servicio, bases de datos, documentos personales, fotos, uploads, exports, entornos virtuales, dependencias instaladas ni plantillas Excel.

La configuración Python y la conexión de base de datos se describen sin copiar contraseñas o valores de conexión. Las copias de código que mencionan credenciales contienen lógica de lectura de configuración, no las credenciales.

## Alcance del cambio de tecnología

- El sistema existente trabaja con MySQL; la base PostgreSQL del proyecto nuevo será independiente.
- La API nueva `/api/v1` tendrá un contrato propio. El frontend actual no es compatible automáticamente.
- El OCR, la generación de Excel con imágenes y la integración con Google Sheets se documentan para etapas posteriores.
- Las transiciones de estado y reglas más estrictas propuestas para Java no existen todas en el backend actual.

No copies el código Python dentro de `src/main/java` ni intentes ejecutarlo desde Java como un script del sistema. La futura integración OCR será mediante una API HTTP interna.
