# Inicio rapido

Este proyecto ya tiene dos piezas:

- `backend`: API con FastAPI que usa los extractores de INE y acta existentes.
- `frontend`: formulario React para cargar documento, revisar datos propuestos y guardar solicitud.

## 1. Configurar MySQL

Instala MySQL Server 8.x si todavia no lo tienes. MySQL Workbench por si solo no basta.

Entra a MySQL:

```powershell
mysql -u root -p
```

Ejecuta:

```sql
CREATE DATABASE IF NOT EXISTS seiem_filiacion CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'seiem_app'@'localhost' IDENTIFIED BY 'CAMBIA_ESTA_CONTRASENA';
GRANT ALL PRIVILEGES ON seiem_filiacion.* TO 'seiem_app'@'localhost';
FLUSH PRIVILEGES;
```

Edita `.env` y cambia `CAMBIA_ESTA_CONTRASENA` por la contrasena real.

## 2. Arrancar backend

Desde la raiz del proyecto:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Prueba:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

## 3. Arrancar frontend

En otra terminal:

```powershell
cd "C:\Users\UsuarioGEM\Documents\Proyectos\seiem-ocr\frontend"
npm.cmd run dev
```

Abre:

```text
http://127.0.0.1:5173
```

## 4. Flujo inicial

La app tiene dos secciones:

- `Solicitante`: inicia la solicitud sin login. Captura RFC, nombre, telefono, correo, estado civil, domicilio y referencias. No analiza documentos.
- `Operador`: entra con usuario, revisa solicitudes, analiza INE/acta, completa el formulario de filiacion y guarda quien hizo la revision.

Para entrar al operador en local:

```text
usuario: operador
contrasena: cambia-esta-contrasena
```

Cambia esos valores en `.env` antes de usarlo con informacion real:

```text
OPERATOR_USERNAME=operador
OPERATOR_PASSWORD=cambia-esta-contrasena
OPERATOR_TOKEN=dev-operator-token
```

Para ver solicitudes, abre la app y entra a `Operador`. El endpoint requiere token:

```powershell
$login = Invoke-RestMethod http://127.0.0.1:8000/api/auth/login -Method Post -ContentType 'application/json' -Body '{"username":"operador","password":"cambia-esta-contrasena"}'
Invoke-RestMethod http://127.0.0.1:8000/api/solicitudes -Headers @{ Authorization = "Bearer $($login.token)" }
```

En el panel del operador, al abrir una solicitud aparece el boton `Descargar Excel`. Ese boton genera una copia de `Plantilla_filiacion.xlsx` con los datos revisados.

La ruta de la plantilla se configura en `.env`:

```text
FILIACION_TEMPLATE_PATH=C:\Users\UsuarioGEM\Downloads\Plantilla_filiacion.xlsx
EXPORT_DIR=exports
```

## 5. Enviar revisiones a Google Sheets

La integracion es opcional. Si no la activas, la app funciona igual.

Cuando el operador guarda una revision, el backend agrega una fila al spreadsheet
configurado. Si Google Sheets no responde, la revision se guarda en MySQL de
todas formas y el backend escribe una advertencia en consola.

Configura `.env`:

```text
GOOGLE_SHEETS_ENABLED=true
GOOGLE_SHEETS_SPREADSHEET_ID=ID_DEL_SPREADSHEET
GOOGLE_SHEETS_SHEET_NAME=Revisiones
GOOGLE_SERVICE_ACCOUNT_FILE=C:\ruta\service-account.json
```

Tambien puedes usar `GOOGLE_SERVICE_ACCOUNT_JSON` con el JSON completo de la
cuenta de servicio, pero en Windows suele ser mas comodo usar archivo.

La hoja debe tener estas columnas, en este orden:

```text
Exportado en
Folio
Solicitud ID
Estado
Nombre
CURP
Correo
Telefono
RFC
Clave de cobro
Descripcion clave
Estado civil
Domicilio
Revisado por
Revisado en
Creado en
Notas
```

Pasos en Google Cloud:

1. Crea un proyecto en Google Cloud.
2. Habilita Google Sheets API.
3. Crea una cuenta de servicio.
4. Descarga su JSON.
5. Abre tu Google Sheet y compartelo con el `client_email` del JSON como editor.
6. Copia el ID del spreadsheet desde la URL.

Ejemplo de URL:

```text
https://docs.google.com/spreadsheets/d/ESTE_ES_EL_ID/edit
```

## 6. Catalogo de codigos postales

Para que el CP autocomplete colonia, municipio y estado necesitas cargar el catalogo SEPOMEX.

1. Descarga el catalogo de codigos postales desde Correos de Mexico/SEPOMEX.
2. Descomprime el archivo hasta obtener el `.txt` nacional.
3. Importalo:

```powershell
.\venv\Scripts\python.exe -m backend.importar_sepomex "C:\RUTA\AL\CATALOGO.txt" --replace
```

Prueba un CP:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/codigos-postales/52280
```

Los datos extraidos son una propuesta. La captura confirmada debe quedar en el formulario.
