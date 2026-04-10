# Contribuir

## Cómo proponer cambios

1. Abre una *issue* describiendo el problema o la mejora.
2. Crea una rama específica.
3. Mantén cambios pequeños y trazables.
4. Documenta cualquier cambio funcional en `CHANGELOG.md`.
5. Si tocas el flujo visual PDF, indica claramente si afecta a:
   - detección textual;
   - alineación coordenada;
   - exportación de copia derivada.

## Criterios mínimos para aceptar cambios

- El proyecto debe seguir arrancando en modo base con `requirements.txt`.
- Las dependencias visuales deben seguir siendo opcionales.
- No se deben introducir conexiones remotas en tiempo de uso sin documentarlas de forma explícita.
- No se deben añadir datos reales, sesiones locales ni binarios generados al repositorio.

## Validación recomendada antes de enviar un cambio

```bash
python -m compileall run.py velo_engine
```
