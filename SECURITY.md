# Seguridad

## Modelo de seguridad

Velo está diseñado para ejecutarse en local. Su objetivo es minimizar la exposición de documentación sensible durante el proceso de revisión archivística.

### Qué hace

- Escucha solo en `127.0.0.1`.
- Procesa documentos localmente.
- Genera copias derivadas redactadas, no modifica el archivo máster original.
- Mantiene los datos de sesión en `workspace/` únicamente durante la ejecución.

### Qué no hace

- No cifra automáticamente el `workspace/`.
- No firma digitalmente la copia derivada resultante.
- No sustituye la revisión humana ni la validación jurídica del acceso.
- No debe exponerse a red pública ni desplegarse detrás de un proxy inverso sin endurecimiento adicional.

## Persistencia de datos

- TXT y DOCX se procesan y el original temporal se elimina tras la extracción de texto.
- En el flujo visual de PDF, el original se conserva temporalmente dentro de una sesión efímera para poder renderizar la vista y exportar la copia derivada.
- La carpeta `workspace/` está excluida del control de versiones y no debe subirse al repositorio.

## Dependencias opcionales

La revisión visual utiliza `PyMuPDF` y `Pillow`. El OCR opcional usa `pytesseract` y requiere Tesseract OCR instalado en el sistema.

Antes de activar OCR en entornos institucionales conviene validar:

- idioma y calidad de reconocimiento;
- precisión de cajas OCR sobre documentos reales;
- política de conservación de copias derivadas y trazas;
- tratamiento de documentos con firma digital o valor probatorio.

## Instaladores

- `install.bat` puede descargar Python embebido y `pip` desde fuentes oficiales por HTTPS.
- `install.sh` e `install.command` asumen Python ya instalado en el sistema.
- No hay code signing ni notarización.

## Recomendaciones de despliegue

1. Ejecutar en estación de trabajo dedicada o perfil controlado.
2. Limpiar periódicamente `workspace/`.
3. No usar muestras con datos reales para demos públicas.
4. Añadir auditoría institucional si el proyecto se incorpora a un flujo formal de acceso o transparencia.



## Auditoría

Consulte [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) para el informe completo de la última auditoría de seguridad.

