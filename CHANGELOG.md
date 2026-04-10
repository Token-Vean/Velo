# Changelog

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
