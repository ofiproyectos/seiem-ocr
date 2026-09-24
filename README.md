# Extracción de datos de INE y actas de nacimiento

`prueba.py` detecta la tarjeta en una fotografía y extrae datos del anverso
mediante OpenCV y Tesseract. `acta_nacimiento.py` extrae actas en PDF o imagen.
El procesamiento es local; no envía documentos ni consulta las URLs impresas.

## Elegir un archivo desde una ventana

```powershell
.\venv\Scripts\python.exe interfaz.py
```

1. Selecciona **INE (anverso)** o **Acta de nacimiento**.
2. Pulsa **Elegir imagen o PDF…**. El selector permite filtrar por documentos
   PDF o por imágenes, además de mostrar ambos juntos.
3. Si la INE está en un PDF, indica la página donde aparece el frente. Para
   imágenes deja página 1; en actas se procesan todas las páginas.
4. Pulsa **Extraer datos** y después **Guardar JSON…**.

No necesitas indicar si un PDF es digital o escaneado: el programa revisa el
contenido. Para actas utiliza texto digital cuando está disponible y activa OCR
en páginas que solo contienen un escaneo. Para la INE convierte la página del
PDF en imagen y aplica el mismo OCR de las fotografías. La extracción se ejecuta
en segundo plano para que la ventana siga respondiendo.

La ventana utiliza Tkinter, incluido en la instalación de Python de este equipo.

## Entrada unificada por consola

```powershell
.\venv\Scripts\python.exe extraer_documento.py ine "C:\ruta\ine.jpg" --salida ine.json
.\venv\Scripts\python.exe extraer_documento.py ine "C:\ruta\ine_escaneada.pdf" --pagina 2 --salida ine.json
.\venv\Scripts\python.exe extraer_documento.py acta "C:\ruta\acta_escaneada.pdf" --salida acta.json
.\venv\Scripts\python.exe extraer_documento.py acta "C:\ruta\acta.png" --salida acta.json
```

El formato se detecta por el contenido del archivo. El JSON incluye `entrada`
con formato, cantidad de páginas y, para INE, la página elegida. En INE se
procesa una página por ejecución; no se mezclan datos del frente y reverso.
La deteccion localiza la credencial dentro de la foto, corrige perspectiva
moderada y analiza solo el area de la tarjeta.

## Uso en PowerShell

Con el entorno virtual existente:

```powershell
.\venv\Scripts\python.exe prueba.py "C:\Users\UsuarioGEM\Downloads\prueba.jpeg"
```

El script original también acepta PDF directamente:

```powershell
.\venv\Scripts\python.exe prueba.py "C:\ruta\ine_escaneada.pdf" --pagina 1 --salida resultado.json
```

Sin argumentos utiliza `Downloads/prueba.jpeg` del usuario actual. Para guardar
el JSON e incluir las lecturas originales de cada campo:

```powershell
.\venv\Scripts\python.exe prueba.py "C:\ruta\credencial.jpeg" --salida resultado.json --incluir-ocr
```

Requiere Python 3.10 o superior, los paquetes de `requirements.txt` y Tesseract
con `spa.traineddata`. Busca Tesseract en PATH y en sus ubicaciones habituales
de Windows; también admite `--tesseract "C:\ruta\tesseract.exe"` o la variable
`TESSERACT_CMD`.

## Resultado

El objeto `datos` contiene nombre en el orden impreso, apellidos y nombres
separados cuando se reconocen tres líneas, domicilio, código postal, CURP,
clave de elector, sexo, fecha de nacimiento, sección, año de registro,
número de emisión y vigencia. Los valores son cadenas para conservar ceros
iniciales. Los campos no reconocidos se devuelven como `null`.

En los campos con formato definido compara tres variantes de imagen. Si falta
acuerdo o confianza, hace otras tres lecturas con distintos umbrales y
normalización de iluminación, usando segmentación de una sola línea.

La advertencia se resuelve cuando al menos dos variantes coinciden con confianza
OCR de 75 o más y no hay una alternativa de confianza 60 o más. También acepta
un consenso de cinco o más variantes, sin alternativas, con una lectura de 75
o más y al menos tres de 60 o más. Los empates devuelven `null`; los desacuerdos
fuertes y las lecturas débiles mantienen sus avisos. Estas puntuaciones son
indicadores de Tesseract, no probabilidades ni garantías de exactitud.

`calidad_campos` conserva el acuerdo, las alternativas y si hubo relectura,
incluso cuando se resuelve una advertencia. `--incluir-ocr` agrega el texto y la
confianza de cada lectura. Nombre y domicilio usan la imagen con iluminación
normalizada. Se comprueba la concordancia entre fecha, sexo y CURP; no se
rellenan datos faltantes a partir de otros documentos.

## Actas de nacimiento

```powershell
.\venv\Scripts\python.exe acta_nacimiento.py "C:\ruta\acta.pdf" --salida resultado_acta.json
```

Tambien acepta JPEG/PNG de la pagina completa. Usa el texto digital del PDF
cuando esta disponible; en paginas escaneadas aplica OCR con preparacion para
fotos: localiza la hoja si aparece sobre una mesa o fondo oscuro, corrige una
perspectiva moderada, normaliza sombras y compara mas de una configuracion de
Tesseract. Para probar la lectura como imagen:

```powershell
.\venv\Scripts\python.exe acta_nacimiento.py "C:\ruta\acta.pdf" --forzar-ocr --salida resultado_acta_ocr.json
```

El JSON incluye:

- Identificador electrónico, CURP y número de certificado de nacimiento.
- Entidad y municipio de registro, oficialía, fecha, libro y número de acta.
- Nombres, apellidos, sexo, fecha y lugar de nacimiento de la persona registrada.
- Filas de filiación, con nombres, apellidos, nacionalidad y CURP si aparece.
- Anotaciones marginales, certificación, fecha de expedición, cargo y funcionario.
- Texto y cadena de la firma electrónica, código y URL de verificación y leyenda.
- Contenido de ambos QR. El QR de datos se separa además en campos como tomo,
  foja, acta, fechas y personas, manteniendo los nombres de campos y convenciones
  originales del QR (por ejemplo, su código de sexo puede diferir del de la INE).
- Método de extracción y texto completo por página, para conservar información
  adicional que no corresponda a un campo conocido.

Los guiones impresos en campos opcionales se representan como `null`. Las filas
de filiación mantienen el orden del documento sin inferir parentescos. Si un PDF
contiene varias actas, la primera queda en `datos` y las otras en
`actas_adicionales`. Cada página conserva su texto en `paginas`.

Necesita PyMuPDF además de las dependencias de la INE. Tesseract solo es necesario
cuando se usa OCR. Para instalar las dependencias en el entorno existente:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

La transcripción no verifica firmas criptográficas ni la autenticidad de los
documentos. El OCR de cadenas largas de firma puede confundir caracteres;
en ese modo se indica que hay que revisar el texto literal y se conserva el
contenido de los QR por separado.

## Alcance y comprobaciones

La distribucion de regiones corresponde al modelo de INE de la imagen de
ejemplo: foto a la izquierda, nombre y domicilio al centro, sexo arriba a la
derecha y fechas en la parte inferior. El programa intenta detectar la tarjeta
horizontal dentro de la foto, recortarla y rectificarla antes del OCR. Otros
disenos, recortes incompletos, reflejos fuertes o rotaciones grandes requieren
ajustar `REGIONES`. Si ya recortaste la tarjeta, usa `--recortada`.

Probado con los dos archivos proporcionados: la INE pasó de dos advertencias a
cero con los mismos valores correctos; el acta digital se extrae sin advertencias
y se decodifican ambos QR. También se probó el acta renderizada como imagen:
coinciden los campos personales y registrales, con aviso para revisar la
transcripción literal de certificación y firma.

Además se crearon PDFs de prueba sin ninguna capa de texto, insertando las
imágenes de los documentos. Se verificó el OCR automático del acta y una INE
pequeña dentro de una hoja completa, en la página 2. Son simulaciones de un
escaneo; no sustituyen pruebas con distintas impresoras y escáneres reales.

El extractor de actas esta adaptado al formato nacional de pagina carta vertical.
Las etiquetas guian la separacion de columnas y la deteccion del documento ya no
depende de encontrar dos titulos exactos: tambien acepta evidencia de campos como
entidad, municipio, identificador electronico y numero de acta. En fotos reales
conviene que salga la hoja completa y legible; la preparacion corrige inclinacion
moderada, sombras y desplazamiento, pero no reconstruye texto borroso, reflejos
fuertes, recortes incompletos o documentos manuscritos. No se promete eliminar
todas las advertencias: se conservan para que el operador revise valores dudosos.

Las pruebas usan datos sintéticos y no necesitan los documentos personales ni
ejecutar Tesseract:

```powershell
.\venv\Scripts\python.exe -m unittest -v
```
