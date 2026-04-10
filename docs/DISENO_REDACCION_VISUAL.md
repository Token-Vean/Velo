# Redacción visual sobre el documento digitalizado original

Esta versión **no la implementa todavía** para preservar la estabilidad del núcleo, pero la arquitectura recomendable es esta:

## Objetivo
Usar OCR o texto embebido para localizar datos sensibles y permitir que el archivero aplique la redacción **sobre la visualización del facsímil digital**, no solo sobre la transcripción textual.

## Enfoque técnico seguro

### 1. Detección de texto por tipo de entrada
- **PDF con texto embebido**: usar `PyMuPDF` o `pdfplumber` para extraer texto y coordenadas.
- **PDF escaneado / imagen**: usar `Tesseract OCR` mediante `pytesseract` para obtener palabras y cajas.

### 2. Visor visual en cliente
- Renderizar cada página como imagen PNG local.
- Superponer una capa HTML/SVG/Canvas con rectángulos de redacción.
- Mantener siempre edición manual: mover, ampliar, borrar y añadir cajas.

### 3. Regla de estabilidad
- El módulo visual debe ser **opcional**.
- Si faltan dependencias visuales u OCR, Velo debe seguir arrancando y funcionando en modo texto.

## Dependencias recomendadas para una futura rama visual
- `PyMuPDF` para renderizar páginas y capturar coordenadas en PDF con texto.
- `Pillow` para normalización de imágenes.
- `pytesseract` + binario `Tesseract OCR` para OCR local.

## Flujo recomendado
1. Cargar PDF o imagen.
2. Extraer texto y cajas.
3. Detectar PII sobre el texto extraído.
4. Proyectar los hallazgos como cajas visuales en la página.
5. Revisión humana obligatoria.
6. Exportar:
   - copia visual testada,
   - JSON de auditoría,
   - opcionalmente texto derivado testado.

## Advertencia archivística
La salida debe describirse como **copia derivada testada** salvo que la futura implementación modifique de forma controlada una copia renderizada del original. No debe presentarse como alteración del documento auténtico.
