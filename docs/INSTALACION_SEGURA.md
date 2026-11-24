# Instalar y eliminar Velo sin temor

Este documento explica qué hace Velo en tu equipo, qué se comprueba antes de
cada versión y cómo eliminarlo por completo. Ninguna comprobación puede
demostrar que un programa no contiene nada malicioso; lo que sigue es un
conjunto de pruebas independientes, automáticas y repetibles, cada una con su
alcance y sus límites.

## Qué toca Velo en tu equipo

| Dónde | Qué contiene | Cómo se elimina |
|---|---|---|
| La carpeta de Velo | El programa y su entorno `.venv` | Borrando la carpeta |
| Windows: `%LOCALAPPDATA%\Velo` · macOS: `~/Library/Application Support/Velo` · Linux: `~/.local/state/velo` | Documentos en revisión (se borran al apagar o a las 24 h), informes, registros y la clave del registro de auditoría | `desinstalar.bat` / `desinstalar.sh` |

Nada más: Velo no instala servicios, no modifica el registro de Windows, no
toca el Python del sistema, no deja cachés de pip (`--no-cache-dir`) ni de
Python (`PYTHONDONTWRITEBYTECODE=1`) y no se conecta a internet mientras
funciona. Tesseract (OCR) es opcional y se instala aparte; si lo instalaste,
se desinstala desde el sistema.

## Cómo eliminarlo

1. Apaga Velo con el botón «Apagar» de la interfaz.
2. Ejecuta `desinstalar.bat` (Windows) o `./desinstalar.sh` (macOS/Linux).
   Muestra lo que va a borrar y pide confirmación.
3. Borra la carpeta de Velo.

## Qué se comprueba (workflow `dependencias-bloqueadas`)

Se ejecuta en cada cambio y una vez por semana, en Windows, macOS y Linux con
Python 3.11 y 3.13.

**1. Instalación verificada por hash.** Cada paquete, incluidos pip y el
modelo de spaCy, se instala con su versión exacta y el SHA-256 de cada
fichero (`locks/`). pip rechaza cualquier fichero que no coincida. No se
compilan paquetes fuente, así que nada se ejecuta durante la instalación.
*Límite:* el hash garantiza que nadie ha alterado el fichero después de
fijarlo, no que fuera benigno cuando se fijó.

**2. Sin red y sin escrituras fuera de su sitio (Linux, `strace`).** Se traza
cada llamada al sistema de red y de ficheros durante la instalación y durante
un uso completo (texto, DOCX, PDF, expurgo, informe). Falla si hay cualquier
conexión que no sea a la propia interfaz de Velo en `127.0.0.1`, incluidas
consultas DNS, o si se escribe fuera de la carpeta de Velo y su directorio de
datos. Un control negativo comprueba en cada ejecución que el analizador sí
detecta una conexión y una escritura indebidas. Además, Velo se ejecuta en un
espacio de red aislado, sin salida a internet, y funciona igual.
*Límite:* se vigila lo que hacen los flujos probados; una función que solo se
activara en condiciones muy concretas podría no ejercitarse.

**3. Entorno instalado limpio.** Tras instalar se comprueba que no hay
ficheros `.pth` ni `sitecustomize.py` que ejecuten código al arrancar Python
(salvo el de setuptools, conocido), que no hay paquetes fuera de los locks, que
no hay código suelto sin paquete y que cada fichero instalado coincide con el
registro (RECORD) de su paquete.

**4. Procedencia.** Cada hash de los locks corresponde a un fichero publicado
en PyPI. Para los paquetes que publican con atestaciones firmadas (Sigstore,
PEP 740), que son 36 de 68 y entre ellos Flask, Werkzeug, Jinja2, NumPy,
Pillow, pypdf, spaCy, thinc y pip, se verifica la firma y que el publicador
sea el repositorio oficial del proyecto (`locks/procedencia.json`). Falla si
un paquete deja de firmar o cambia de publicador.
*Límite:* PyMuPDF, lxml, onnxruntime, waitress y python-docx, entre otros,
aún no publican con atestaciones.

**5. Modelo de spaCy.** No está en PyPI. Su contenido se compara fichero a
fichero con los paquetes que conda-forge y Anaconda construyeron por su cuenta
en 2024 (26 de 26 ficheros idénticos). Se revisa que su único código sea el
`__init__.py` estándar de spaCy, que todas las funciones de su configuración
pertenezcan a spaCy o thinc y que no contenga ficheros pickle, que podrían
ejecutar código al cargarse.

**6. Escaneo heurístico (GuardDog).** Busca patrones típicos de paquetes
maliciosos (descarga y ejecución de código, exfiltración, ofuscación, código
al instalar). Da falsos positivos en paquetes grandes y legítimos: su informe
se revisa a mano.

**7. Avisos conocidos.** `pip-audit` comprueba los locks contra las bases de
datos de vulnerabilidades publicadas.

## Sobre las dependencias de red de spaCy

spaCy incluye bibliotecas de red (`requests`, `httpx`) para sus comandos de
descarga de modelos y gestión de proyectos, y las importa al cargarse. Velo
no las usa: el modelo se instala desde el lock y la vigilancia de red
(punto 2) comprueba que no hay ninguna conexión durante el uso.

## Resultados de la revisión de noviembre de 2026

- **Instalación** (Linux, trazada): 23 799 escrituras evaluadas, ninguna
  fuera de la carpeta de Velo; 164 temporales creados, ninguno queda.
- **Uso completo** (trazado): 0 conexiones fuera de `127.0.0.1` de Velo,
  ni DNS; todas las escrituras en la carpeta o en el directorio de datos.
  Funciona igual sin red.
- **Paquetes que Velo carga al usarse**: 46 de los 68 instalados. No se
  cargan nunca, entre otros, onnxruntime, pymupdf4llm, networkx ni psutil
  (los instala PyMuPDF 2.1 como dependencias).
- **Entorno**: 6 756 ficheros coinciden con el registro de su paquete; el
  único `.pth` con código es el conocido de setuptools; ningún paquete fuera
  de los locks.
- **Procedencia**: todos los hashes están publicados en PyPI; 1 143 de 1 639
  ficheros (36 de 68 paquetes) con atestación firmada, todas válidas y de los
  repositorios oficiales.
- **Modelo spaCy**: 26 de 26 ficheros idénticos a los de conda-forge y
  Anaconda; solo el `__init__.py` estándar; 13 funciones de configuración, todas
  de spaCy o thinc; ningún pickle.
- **GuardDog**: 68 paquetes escaneados. Las alertas de tipo «threat» se
  revisaron una a una y corresponden a funciones documentadas o a ficheros de
  pruebas, por ejemplo:
  - la integración opcional de tqdm con Telegram;
  - el instalador de autocompletado de typer, que escribe en `~/.bashrc` solo
    si se le pide;
  - `spacy download`, que llama a pip;
  - cadenas como `/etc/passwd` en los tests de NumPy y spaCy;
  - caracteres Unicode en tablas de datos;
  - los lanzadores `.exe` de pip y setuptools para Windows.

  Ninguna presenta indicios de código malicioso.
- **Avisos conocidos** (pip-audit): ninguno.
