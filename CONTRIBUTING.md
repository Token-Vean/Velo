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

## Dependencias

- Las versiones se declaran en `requirements*.txt` (los mantiene Dependabot).
- Lo que se instala son los locks de `locks/`, con versión exacta y SHA-256 de
  cada fichero. Se generan en GitHub Actions con `tools/generar_locks.sh` (uv,
  resolución universal Windows/macOS/Linux, Python ≥ 3.11).
- Tras cambiar un `requirements*.txt` (también en un PR de Dependabot), el
  control «Locks coherentes» falla hasta regenerar los locks: *Actions →
  dependencias-bloqueadas → Run workflow* sobre esa rama con «regenerar»
  marcado. El workflow hace commit de los locks; después relanza los checks.
- El modelo spaCy se fija por URL y hash, y `tools/verificar_modelo_spacy.py`
  contrasta su contenido con los paquetes que conda-forge y Anaconda
  construyeron de forma independiente.

## Validación recomendada antes de enviar un cambio

```bash
python -m compileall run.py velo_engine
```
