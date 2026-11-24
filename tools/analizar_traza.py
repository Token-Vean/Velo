#!/usr/bin/env python3
"""Analiza una traza de strace de Velo: red y escrituras en disco.

Fallos (código de salida 1):
  - Cualquier conexión o envío por red a una dirección que no sea la propia
    interfaz local de Velo (127.0.0.1 / ::1 en el puerto en el que escucha).
    Incluye consultas DNS (puerto 53), aunque vayan al resolvedor local.
  - Escuchar en una interfaz que no sea la local.
  - Crear o modificar ficheros fuera de las carpetas permitidas (la carpeta
    de Velo y su directorio de datos), salvo temporales y /dev.
  - Temporales creados durante la ejecución que siguen existiendo al final.

Uso:
  analizar_traza.py TRAZA --permitida DIR [--permitida DIR ...] [--sin-red]
  --sin-red: no evalúa la red (p. ej. al trazar pip, que sí descarga).
La traza se obtiene con: strace -f -y -qq -s 512 -e trace=%network,%file -o TRAZA ...
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

ESCRITURA = re.compile(r"O_(WRONLY|RDWR|CREAT|TRUNC|APPEND)")
RESULTADO_OK = re.compile(r"\)\s+=\s+(\d+)")
INET = re.compile(r'sa_family=AF_INET6?,\s*sin6?_port=htons\((\d+)\),\s*(?:sin6_flowinfo=[^,]+,\s*)?'
                  r'(?:sin_addr=inet_addr\("([^"]+)"\)|inet_pton\(AF_INET6,\s*"([^"]+)"[^)]*\))')
LLAMADA = re.compile(r"^(\d+)\s+(\w+)\((.*)$")
# Con -y, strace decora los descriptores: «AT_FDCWD</cwd>» o «3</dir>».
RUTA_FD = re.compile(r'^(?:AT_FDCWD(?:<([^>]*)>)?|\d+<([^>]*)>),\s*"([^"]*)"')
RUTA_SIMPLE = re.compile(r'^"([^"]*)"')
TEMPORALES = tuple(
    str(Path(p).resolve()) for p in {tempfile.gettempdir(), "/tmp", "/var/tmp", "/dev/shm"} if os.path.exists(p)
)
ESPECIALES = ("/dev/", "/proc/", "/sys/")


def _local(direccion: str) -> bool:
    return direccion.startswith("127.") or direccion in ("::1", "::ffff:127.0.0.1")


def _resolver(base: str | None, ruta: str, cwd: str) -> str:
    if os.path.isabs(ruta):
        return os.path.normpath(ruta)
    return os.path.normpath(os.path.join(base or cwd, ruta))


def _dentro(ruta: str, raices) -> bool:
    return any(ruta == r or ruta.startswith(r.rstrip("/") + "/") for r in raices)


def _rutas_de(llamada: str, argumentos: str, cwd: str) -> list[str]:
    rutas: list[str] = []
    if llamada in ("open", "creat", "mkdir", "unlink", "rmdir", "rename"):
        partes = re.findall(r'"([^"]*)"', argumentos)
        destinos = partes[1:2] if llamada == "rename" else partes[:1]
        rutas.extend(_resolver(None, r, cwd) for r in destinos)
    elif llamada in ("openat", "mkdirat", "unlinkat", "openat2"):
        coincidencia = RUTA_FD.match(argumentos)
        if coincidencia:
            rutas.append(_resolver(coincidencia[1] or coincidencia[2], coincidencia[3], cwd))
    elif llamada in ("renameat", "renameat2"):
        # renameat(dirfd, "origen", dirfd2, "destino"): interesa el destino
        trozos = re.findall(r'(?:AT_FDCWD(?:<([^>]*)>)?|\d+<([^>]*)>),\s*"([^"]*)"', argumentos)
        if len(trozos) >= 2:
            rutas.append(_resolver(trozos[1][0] or trozos[1][1] or None, trozos[1][2], cwd))
    return rutas


def main() -> int:
    analizador = argparse.ArgumentParser()
    analizador.add_argument("traza")
    analizador.add_argument("--permitida", action="append", default=[])
    analizador.add_argument("--sin-red", action="store_true")
    analizador.add_argument("--cwd", default=os.getcwd())
    opciones = analizador.parse_args()
    permitidas = [str(Path(p).resolve()) for p in opciones.permitida]

    puertos_propios: set[int] = set()
    conexiones: list[tuple[str, str, int, str]] = []
    escuchas_externas: list[str] = []
    unix: set[str] = set()
    fuera: dict[str, str] = {}
    ilegibles: list[str] = []
    escrituras_evaluadas = 0
    temporales_creados: set[str] = set()

    with open(opciones.traza, encoding="utf-8", errors="replace") as handle:
        lineas = handle.readlines()

    for linea in lineas:
        coincidencia = LLAMADA.match(linea.strip())
        if not coincidencia:
            continue
        _pid, llamada, argumentos = coincidencia.groups()
        if llamada == "bind":
            red = INET.search(argumentos)
            if red:
                direccion = red[2] or red[3]
                if _local(direccion):
                    if " = 0" in argumentos:
                        puertos_propios.add(int(red[1]))
                elif " = 0" in argumentos:
                    escuchas_externas.append(f"{direccion}:{red[1]}")

    for linea in lineas:
        coincidencia = LLAMADA.match(linea.strip())
        if not coincidencia:
            continue
        _pid, llamada, argumentos = coincidencia.groups()

        if llamada in ("connect", "sendto", "sendmsg", "sendmmsg"):
            red = INET.search(argumentos)
            if red:
                direccion, puerto = red[2] or red[3], int(red[1])
                if not (_local(direccion) and puerto in puertos_propios):
                    conexiones.append((llamada, direccion, puerto, linea.strip()[:200]))
            elif "AF_UNIX" in argumentos:
                destino = re.search(r'sun_path="([^"]*)"', argumentos)
                unix.add(destino[1] if destino else "(abstracto)")
            continue

        es_escritura = (
            llamada in ("open", "openat", "openat2", "creat") and (ESCRITURA.search(argumentos) or llamada == "creat")
        ) or llamada in ("mkdir", "mkdirat", "rename", "renameat", "renameat2", "unlink", "unlinkat", "rmdir")
        if not es_escritura or not RESULTADO_OK.search(argumentos):
            continue
        rutas = _rutas_de(llamada, argumentos, opciones.cwd)
        if not rutas:
            # Nunca ignorar en silencio una escritura que no se sabe leer.
            ilegibles.append(linea.strip()[:200])
            continue
        escrituras_evaluadas += 1
        for ruta in rutas:
            if _dentro(ruta, permitidas) or ruta.startswith(ESPECIALES):
                continue
            if llamada in ("mkdir", "mkdirat") and any(r.startswith(ruta.rstrip("/") + "/") for r in permitidas):
                continue  # carpeta padre necesaria para crear una permitida
            if _dentro(ruta, TEMPORALES):
                if llamada in ("open", "openat", "openat2", "creat", "mkdir", "mkdirat"):
                    temporales_creados.add(ruta)
                continue
            fuera.setdefault(ruta, llamada)

    restos = sorted(
        r for r in temporales_creados
        if os.path.exists(r) and r not in TEMPORALES
        and not any(p.startswith(r.rstrip("/") + "/") or p == r for p in permitidas)
        and not _dentro(r, permitidas)
    )
    fallos = 0

    print(f"Puertos propios (127.0.0.1/::1): {sorted(puertos_propios) or '-'}")
    if not opciones.sin_red:
        print(f"Conexiones de red fuera de la interfaz local de Velo: {len(conexiones)}")
        for llamada, direccion, puerto, texto in conexiones[:50]:
            print(f"  [X] {llamada} -> {direccion}:{puerto}   {texto}")
        fallos += len(conexiones)
        if escuchas_externas:
            print(f"  [X] Escucha en interfaces no locales: {escuchas_externas}")
            fallos += len(escuchas_externas)
        if unix:
            print(f"Sockets locales del sistema (informativo): {sorted(unix)}")

    print(f"Escrituras evaluadas: {escrituras_evaluadas}")
    if ilegibles:
        print(f"  [X] Llamadas de escritura que no se pudieron interpretar: {len(ilegibles)}")
        for texto in ilegibles[:10]:
            print(f"      {texto}")
        fallos += len(ilegibles)
    print(f"Escrituras fuera de {permitidas} y temporales: {len(fuera)}")
    for ruta, llamada in sorted(fuera.items())[:100]:
        print(f"  [X] {llamada}: {ruta}")
    fallos += len(fuera)

    print(f"Temporales creados: {len(temporales_creados)}; siguen existiendo al terminar: {len(restos)}")
    for ruta in restos[:50]:
        print(f"  [X] resto: {ruta}")
    fallos += len(restos)

    if fallos:
        print(f"[ERROR] {fallos} incidencia(s)")
        return 1
    print("[OK] Sin conexiones externas, sin escrituras fuera de las carpetas permitidas y sin restos temporales")
    return 0


if __name__ == "__main__":
    sys.exit(main())
