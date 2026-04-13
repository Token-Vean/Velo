# Changelog

## 0.3.0

- **Detección de nombres**: los instaladores preguntan si se desea instalar spaCy + modelo español para detectar nombres de personas, organizaciones y lugares. Si ya estaba instalado, se reutiliza.
- **Límites ampliados**: tamaño máximo de fichero subido a 100 MB (antes 16 MB), límite de texto extraído a 2.000.000 caracteres (antes 500.000), límite de páginas PDF a 500 (antes 100).
- **Logging centralizado**: nuevo sistema de logs rotativos en `workspace/logs/velo.log` con registros detallados de cada fichero procesado, errores de extracción, límites alcanzados y estado de las capas de detección.
- **Mejor gestión de errores**: manejador HTTP 413 con mensaje informativo cuando un fichero excede el tamaño máximo; los mensajes de error al usuario incluyen el tipo de excepción para facilitar diagnóstico.
- Nuevo fichero `requirements-nlp.txt` para dependencias de detección NER.

## 0.2.5

- Corrección del desfase de offsets en la alineación visual entre texto reconstruido y cajas proyectadas.
- Mantenimiento del flujo de cinco pasos para PDF: revisión textual, vista original, aplicación sobre el original y exportación.
- Separación entre dependencias base y dependencias visuales opcionales.
- Interfaz en modo claro y sin fuentes remotas.

## 0.2.4

- Arranque robusto aunque no esté disponible `waitress`.
- Instaladores preparados para degradación elegante cuando fallan dependencias visuales.

## 0.2.3

- Activación por defecto del flujo visual PDF cuando las dependencias están disponibles.

## 0.2.2

- Paso explícito de “Aplicación sobre el original” en la interfaz.

## 0.2.1

- Primera integración del flujo visual para PDF y exportación de copia derivada redactada.
