# Velo

Herramienta local para archiveros y profesionales de la gestión documental orientada a **detectar, revisar y redactar** datos sensibles en documentos.

## Posicionamiento del proyecto

Velo está concebido para **uso personal y estrictamente local** en el puesto de trabajo del profesional. No es una aplicación pensada para despliegue multiusuario, publicación en red o tratamiento automatizado sin supervisión.

La herramienta **asiste** al proceso, pero **no sustituye la decisión profesional**: cada hallazgo debe ser confirmado, descartado o añadido manualmente por la persona revisora.

## Estado del proyecto

Versión actual del código: **0.4.0**.

Esta revisión endurece el proyecto en varias capas:

- mayor coherencia de trazabilidad y versionado;
- mejor aislamiento de instalación mediante entorno virtual local;
- reducción de superficie de ataque en el instalador de Windows;
- poda automática de sesiones antiguas;
- control más explícito de la aplicación de redacciones sobre el original;
- preflight defensivo para DOCX y límites homogéneos para PDF.

## Principios de diseño

- **Procesamiento local**: la aplicación escucha en `127.0.0.1`.
- **Revisión humana obligatoria**: Velo detecta y propone; el archivero valida.
- **No altera el máster original**: cuando redacta un PDF, genera una **copia derivada**.
- **Trazabilidad**: el informe JSON conserva hallazgos, decisiones y metadatos.
- **Persistencia mínima**: los temporales no visuales se eliminan y las sesiones visuales son efímeras.

## Flujo de trabajo

1. **Entrada**: carga de TXT, DOCX o PDF, o pegado de texto.
2. **Análisis**: detección automática de datos sensibles.
3. **Revisión**: confirmación, descarte o marcación manual de hallazgos.
4. **Vista original PDF**: proyección de máscaras sobre la imagen del PDF original.
5. **Aplicación sobre el original**: generación explícita de una copia derivada redactada.
6. **Exportación**: informe JSON y copia derivada textual o PDF redactado.

## Capacidades actuales

### Detección base (regex)

- DNI y NIE con validación.
- Direcciones postales por patrones.
- Teléfonos, correos electrónicos e IBAN.
- Números de Seguridad Social y tarjetas por patrones.
- Marcación manual desde la interfaz.

### Detección NER (spaCy, opcional)

- Nombres de personas.
- Organizaciones e instituciones.
- Lugares y topónimos.

### Soporte documental

- **TXT**: soporte nativo.
- **DOCX**: extracción textual mediante `python-docx`, con preflight ZIP defensivo.
- **PDF con capa de texto**: extracción y alineación visual mediante `PyMuPDF`.
- **PDF escaneado**: OCR local opcional mediante `pytesseract` + Tesseract.

## Requisitos

### Mínimos

- Python **3.10 o superior**.
- Entorno de escritorio local.

### Dependencias base

Instaladas desde `requirements.txt`:

- Flask 3.1.3
- waitress 3.0.2
- python-docx 1.2.0
- pypdf 6.10.0

### Dependencias visuales opcionales

Instaladas desde `requirements-visual.txt`:

- PyMuPDF 1.27.2
- Pillow 12.2.0
- pytesseract 0.3.13

### Dependencias NLP opcionales

Instaladas desde `requirements-nlp.txt`:

- spaCy 3.x
- modelo español `es_core_news_md` o `es_core_news_sm`

## Instalación

### Windows

Ejecuta `install.bat`.

El instalador **ya no descarga Python automáticamente** ni ejecuta bootstrap remoto. Si Python 3.10+ no está presente, debes instalarlo previamente o distribuir Velo con un runtime empaquetado. Esta decisión se ha tomado para reducir la exposición de cadena de suministro.

### macOS

Ejecuta `install.command`.

### Linux

```bash
chmod +x install.sh
./install.sh
```

### Comportamiento del instalador

Los instaladores crean un entorno virtual local `.venv` dentro de la carpeta del proyecto para aislar dependencias y reducir conflictos con el sistema.

## Estructura relevante

```text
velo/
├── .github/workflows/security-checks.yml
├── build.py
├── install.bat
├── install.command
├── install.sh
├── requirements.txt
├── requirements-nlp.txt
├── requirements-visual.txt
├── run.py
└── velo_engine/
    ├── app.py
    ├── constants.py
    ├── detector.py
    ├── reader.py
    ├── security.py
    ├── visual.py
    └── templates/
        └── index.html
```

## Mejoras introducidas en esta revisión

- Se unifica la versión de aplicación en backend e informes.
- Se corrige la inicialización del audit log para usar siempre el `workspace` real.
- Se podan sesiones visuales antiguas al arranque.
- Se evita la aplicación automática de redacciones al entrar en la fase correspondiente.
- Se endurece el tratamiento de DOCX con validaciones ZIP previas.
- Se sustituye `PyPDF2` por `pypdf` como fallback moderno.
- Se fuerza instalación aislada mediante `.venv`.
- Se añaden controles CI mínimos de seguridad y dependencias.

## Limitaciones conocidas

- La alineación visual en OCR puede no ser perfecta en documentos escaneados complejos.
- No se incorpora todavía sandboxing a nivel de sistema operativo.
- La herramienta sigue siendo principalmente sintáctica y puede producir falsos positivos o falsos negativos.
- No hay firma de código para ejecutables o instaladores generados.

## Seguridad y privacidad

Consulta [`SECURITY.md`](SECURITY.md).

## Licencia

Mantén la licencia original del repositorio al integrar estos cambios.
