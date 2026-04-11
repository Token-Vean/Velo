# Velo

Herramienta local para archiveros y profesionales de la gestión documental orientada a detectar, revisar y anonimizar datos sensibles en documentos. Velo **asiste** al proceso, pero **no sustituye la decisión profesional**: cada hallazgo debe ser confirmado o descartado por la persona revisora.

## Estado del proyecto

Versión actual del código: **0.2.5**.

El proyecto es funcional para revisión local y generación de copias derivadas redactadas. No debe presentarse como certificación de cumplimiento normativo automático ni como sustituto de una revisión archivística, jurídica o de protección de datos.

## Principios de diseño

- **Procesamiento local**: la aplicación escucha en `127.0.0.1` y no necesita enviar documentos a servicios externos para funcionar.
- **Revisión humana obligatoria**: la herramienta detecta y propone; el archivero confirma, descarta o añade hallazgos manualmente.
- **Salida trazable**: el proceso genera un informe JSON con hallazgos, decisiones y metadatos de revisión.
- **No altera el máster original**: cuando redacta un PDF, genera una **copia derivada** del original, no modifica el archivo fuente in situ.

## Flujo de trabajo

1. **Entrada**: carga de TXT, DOCX o PDF, o pegado de texto.
2. **Análisis**: detección automática de datos sensibles.
3. **Revisión textual**: confirmación, descarte o marcación manual de hallazgos.
4. **Vista original PDF**: previsualización de las máscaras sobre la imagen del PDF original cuando hay soporte visual.
5. **Aplicación sobre el original**: materialización de la redacción sobre una copia derivada del PDF original.
6. **Exportación**: descarga de informe JSON y, según el caso, copia textual o PDF visual redactado.

## Capacidades actuales

### Detección base

- DNI y NIE con validación básica.
- Direcciones postales por patrones.
- Teléfonos, correos electrónicos y cuentas IBAN.
- Números de Seguridad Social y tarjetas por patrones.
- Marcación manual desde la interfaz.

### Soporte documental

- **TXT**: soporte nativo.
- **DOCX**: extracción textual mediante `python-docx`.
- **PDF con capa de texto**: extracción y alineación visual mediante `PyMuPDF`.
- **PDF escaneado**: soporte opcional con OCR local usando `pytesseract` + Tesseract instalado en el sistema.

## Requisitos

### Base

- Python 3.9 o superior.
- Dependencias de `requirements.txt`.

### Visual/OCR opcional

- Dependencias de `requirements-visual.txt`.
- Para OCR de PDF escaneado: Tesseract OCR instalado en el sistema y disponible en `PATH`.

## Instalación

### Windows

Ejecuta `install.bat`.

El instalador intenta usar Python del sistema. Si no existe una versión compatible, ofrece descargar Python embebido desde `python.org`.

### macOS

Ejecuta `install.command`.

### Linux

```bash
chmod +x install.sh
./install.sh
```

### Instalación manual

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-visual.txt  # opcional
python run.py
```

## Estructura del repositorio

```text
velo/
├── .github/workflows/python-smoke.yml
├── build.py
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── SECURITY.md
├── docs/
├── install.bat
├── install.command
├── install.sh
├── requirements.txt
├── requirements-visual.txt
├── run.py
└── velo_engine/
    ├── app.py
    ├── detector.py
    ├── reader.py
    ├── visual.py
    ├── static/
    └── templates/
```

## Publicación en GitHub

Este paquete ya está saneado para repositorio público:

- sin `__pycache__`;
- sin `workspace/` ni sesiones locales;
- sin artefactos de prueba generados por ejecución;
- con documentación de instalación y soporte;
- con `CHANGELOG.md`, `CONTRIBUTING.md` y una comprobación básica de CI.

## Limitaciones conocidas

- La alineación visual puede requerir ajuste fino en PDFs escaneados con OCR, porque las cajas OCR no siempre coinciden con precisión perfecta con el renderizado visual.
- La detección sigue siendo principalmente sintáctica y puede producir falsos positivos o falsos negativos.
- No hay firma de código para los instaladores ni binarios generados.
- No se han incorporado todavía tests funcionales amplios con corpus archivístico real.

## Seguridad y privacidad

Consulta [`SECURITY.md`](SECURITY.md).

## Licencia

Este repositorio se distribuye bajo **AGPLv3**. Revisa el archivo [`LICENSE`](LICENSE) antes de redistribuirlo o integrarlo en otros desarrollos.
