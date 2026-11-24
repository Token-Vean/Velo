#!/usr/bin/env python3
"""Prueba de humo de extremo a extremo contra un Velo en ejecución.

Recorre el flujo completo de un usuario a través de HTTP real (como el
navegador): página principal y token CSRF, análisis de texto, de DOCX y de PDF
con revisión visual, aplicación sobre el original, expurgo nativo, informe
JSON, limpieza de sesión y apagado. Comprueba que el expurgo elimina de verdad
los datos del PDF descargado.

Uso:  python tools/prueba_humo.py [--puerto N] [--sin-apagar]
Busca el puerto en 7780-7800 si no se indica. Sale con código 0 si todo va bien.
Usa solo la biblioteca estándar más python-docx y PyMuPDF (ya instalados por
los locks); si falta alguno, omite esa parte y lo indica.
"""

from __future__ import annotations

import argparse
import http.client
import io
import json
import re
import sys
import time
import uuid

DNI = "12345678Z"
IBAN = "ES91 2100 0418 4502 0005 1332"
NOMBRE = "Ana García López"
TEXTO = f"Expediente de {NOMBRE}, vecina de Toledo, DNI {DNI}, IBAN {IBAN}, correo ana@example.org."


class Cliente:
    def __init__(self, puerto: int):
        self.puerto = puerto
        self.cookie = ""
        self.token = ""

    def _peticion(self, metodo: str, ruta: str, cuerpo: bytes | None = None, cabeceras: dict | None = None):
        conexion = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=300)
        todas = {"Host": f"localhost:{self.puerto}"}
        if self.cookie:
            todas["Cookie"] = self.cookie
        if metodo != "GET":
            todas["Origin"] = f"http://localhost:{self.puerto}"
            todas["X-CSRF-Token"] = self.token
        todas.update(cabeceras or {})
        conexion.request(metodo, ruta, body=cuerpo, headers=todas)
        respuesta = conexion.getresponse()
        datos = respuesta.read()
        nueva = respuesta.getheader("Set-Cookie")
        if nueva:
            self.cookie = nueva.split(";", 1)[0]
        conexion.close()
        return respuesta.status, dict(respuesta.getheaders()), datos

    def get(self, ruta: str):
        return self._peticion("GET", ruta)

    def post_json(self, ruta: str, carga: dict):
        estado, cabeceras, datos = self._peticion(
            "POST", ruta, json.dumps(carga).encode(), {"Content-Type": "application/json"}
        )
        return estado, cabeceras, datos

    def post_fichero(self, ruta: str, nombre: str, contenido: bytes):
        frontera = uuid.uuid4().hex
        cuerpo = (
            f"--{frontera}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nombre}\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + contenido + f"\r\n--{frontera}--\r\n".encode()
        return self._peticion("POST", ruta, cuerpo, {"Content-Type": f"multipart/form-data; boundary={frontera}"})


def _buscar_puerto() -> int:
    limite = time.time() + 90
    while time.time() < limite:
        for puerto in range(7780, 7801):
            try:
                conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=2)
                conexion.request("GET", "/api/status", headers={"Host": f"localhost:{puerto}"})
                respuesta = conexion.getresponse()
                if respuesta.status == 200 and json.loads(respuesta.read()).get("tool") == "velo":
                    return puerto
            except (OSError, ValueError):
                continue
        time.sleep(1)
    sys.exit("[ERROR] No se encontró Velo escuchando en 127.0.0.1:7780-7800")


def _comprobar(condicion: bool, mensaje: str) -> None:
    if not condicion:
        print(f"[ERROR] {mensaje}")
        sys.exit(1)
    print(f"[OK] {mensaje}")


def _tipos(resultado: dict) -> set[str]:
    return {h["type"] for h in resultado.get("findings", [])}


def _confirmar(hallazgos: list[dict]) -> list[dict]:
    return [{**h, "status": "confirmed", "technique": "suppression"} for h in hallazgos]


def main() -> int:
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument("--puerto", type=int)
    argumentos.add_argument("--sin-apagar", action="store_true")
    opciones = argumentos.parse_args()

    puerto = opciones.puerto or _buscar_puerto()
    cliente = Cliente(puerto)

    estado, _, pagina = cliente.get("/")
    coincidencia = re.search(rb'name="csrf-token" content="([^"]+)"', pagina)
    _comprobar(estado == 200 and coincidencia is not None, f"Interfaz servida en el puerto {puerto} con token CSRF")
    cliente.token = coincidencia.group(1).decode()

    estado, _, datos = cliente.get("/api/status")
    capas = json.loads(datos)
    spacy_activo = bool(capas["layers"]["spacy"])
    print(f"     capas: spaCy={capas['layers']['spacy_model']} visual={capas['visual_redaction']['implemented']}")

    # Texto
    estado, _, datos = cliente.post_json("/api/analyze/text", {"text": TEXTO})
    resultado = json.loads(datos)
    _comprobar(estado == 200 and {"dni", "iban", "email"} <= _tipos(resultado), "Análisis de texto: DNI, IBAN y correo")
    if spacy_activo:
        _comprobar("person_name" in _tipos(resultado), "spaCy detecta el nombre de persona")

    estado, _, datos = cliente.post_json(
        "/api/export",
        {"document_id": "DOC-HUMO", "findings": _confirmar(resultado["findings"]),
         "layers_active": resultado["layers_active"], "layers_available": resultado["layers_available"]},
    )
    _comprobar(estado == 200 and json.loads(datos)["envelope"]["summary"]["confirmed"] > 0, "Informe JSON exportado")

    # DOCX
    try:
        import docx

        documento = docx.Document()
        documento.add_paragraph("Solicitud.")
        tabla = documento.add_table(rows=1, cols=2)
        tabla.cell(0, 0).text = "DNI"
        tabla.cell(0, 1).text = DNI
        documento.sections[0].header.paragraphs[0].text = f"Interesada: {NOMBRE}"
        bufer = io.BytesIO()
        documento.save(bufer)
        estado, _, datos = cliente.post_fichero("/api/analyze/file", "Expediente Ñúñez.docx", bufer.getvalue())
        resultado = json.loads(datos)
        _comprobar(estado == 200 and "dni" in _tipos(resultado), "Análisis DOCX (DNI en tabla)")
    except ImportError:
        print("[--] python-docx no disponible: se omite DOCX")

    # PDF con revisión visual y expurgo nativo
    try:
        import pymupdf
    except ImportError:
        print("[--] PyMuPDF no disponible: se omite el flujo PDF")
    else:
        pdf = pymupdf.open()
        pagina_pdf = pdf.new_page()
        pagina_pdf.insert_text((72, 72), f"Interesada: {NOMBRE}")
        pagina_pdf.insert_text((72, 96), f"DNI {DNI} y correo ana@example.org")
        pagina_pdf.add_text_annot((72, 140), f"Nota: DNI {DNI}")
        pdf.set_metadata({"author": NOMBRE})
        contenido_pdf = pdf.tobytes()
        pdf.close()

        estado, _, datos = cliente.post_fichero("/api/analyze/file", "expediente.pdf", contenido_pdf)
        resultado = json.loads(datos)
        sesion = resultado.get("visual_session")
        _comprobar(estado == 200 and sesion and "dni" in _tipos(resultado), "Análisis PDF con revisión visual")

        estado, _, datos = cliente.get(resultado["visual_pages"][0]["image_url"])
        _comprobar(estado == 200 and datos.startswith(b"\x89PNG"), "Imagen de página servida")

        confirmados = _confirmar(resultado["findings"])
        estado, _, datos = cliente.post_json("/api/session/apply-original", {"session_id": sesion, "findings": confirmados})
        aplicado = json.loads(datos)
        _comprobar(estado == 200 and aplicado["applied"]["total_rectangles"] > 0, "Aplicación sobre el original (modo imagen)")

        estado, cabeceras, datos = cliente.post_json(
            "/api/export/redacted-pdf",
            {"session_id": sesion, "document_id": "DOC-HUMO", "findings": confirmados, "redaction_mode": "native"},
        )
        _comprobar(estado == 200 and datos.startswith(b"%PDF"), "Expurgo nativo descargado")
        expurgado = pymupdf.open(stream=datos, filetype="pdf")
        texto_restante = "".join(p.get_text() for p in expurgado)
        anotaciones = sum(1 for p in expurgado for _ in p.annots())
        autor = expurgado.metadata.get("author", "")
        expurgado.close()
        _comprobar(DNI not in texto_restante and DNI.encode() not in datos, "El DNI no queda en el PDF expurgado")
        _comprobar(anotaciones == 0 and not autor, "Sin anotaciones ni autor en el PDF expurgado")
        print(f"     sin proyectar: {cabeceras.get('X-Velo-Sin-Proyectar', '') or '(ninguno)'}")

        estado, _, _ = cliente.post_json("/api/session/cleanup", {"session_id": sesion})
        _comprobar(estado == 200, "Sesión visual eliminada")

    if not opciones.sin_apagar:
        estado, _, _ = cliente.post_json("/api/shutdown", {})
        _comprobar(estado == 200, "Apagado solicitado")
    print("[OK] Prueba de humo completada")
    return 0


if __name__ == "__main__":
    sys.exit(main())
