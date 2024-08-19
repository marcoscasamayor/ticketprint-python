#!/usr/bin/env python3
import os
import time
import random
import requests
import base64
import logging
from datetime import datetime
from PIL import Image
from PIL import ImageOps
from io import BytesIO
import configparser
import urllib.request
from escpos.printer import Usb

# Configura el logging
logging.basicConfig(filename='comprobante.log', level=logging.INFO, 
                    format='%(asctime)s %(levelname)s:%(message)s')

# Carga configuración
ruta_actual = os.getcwd()
config = configparser.ConfigParser()
config.read(os.path.join(ruta_actual, 'config.ini'))

pto_vta = config["General"]["pto_vta"]
dias_a_eliminar = int(config["General"]["dias_a_eliminar"])
frecuencia_actualizacion = int(config["General"]["frecuencia_actualizacion"])
url_base = config["General"]["url_base"]
local_path_logo = os.path.join(ruta_actual, "logo.jpg")

if not url_base.endswith("/"):
    url_base += "/"

idvendor = int(config["Impresora"]["idvendor"], 16)
idproduct = int(config["Impresora"]["idproduct"], 16)
ancho_impresora = int(config["Impresora"]["ancho"])

# Clase Impresora
class Impresora:
    def __init__(self, idvendor, idproduct, ancho):
        self.idvendor = idvendor
        self.idproduct = idproduct
        self.ancho = ancho
        self.conectar()

    def conectar(self):
        self.printer = Usb(self.idvendor, self.idproduct)
    
    def imprimir_texto(self, texto, opciones):
        align = opciones.get("align", 'left')
        font = opciones.get("font", 'a')
        height = opciones.get("height", 16)  # Valor predeterminado si no se proporciona
        bold = opciones.get("bold", False)
    
        # Configura la alineación, fuente, y estilo
        self.printer.set(align=align, font=font, height=height, width=height, bold=bold)
    
        self.printer.text(texto + '\n')

    def imprimir_imagen(self, imagen):
        imagen_rescalada = self.reescalar_imagen(imagen)
        self.printer.image(imagen_rescalada)

    def reescalar_imagen(self, imagen):
        factor_escala_ancho = self.ancho / float(imagen.width)
        factor_escala_altura = factor_escala_ancho
        nueva_anchura = int(imagen.width * factor_escala_ancho)
        nueva_altura = int(imagen.height * factor_escala_altura)
        imagen.info['dpi'] = (300, 300)
        imagen = ImageOps.exif_transpose(imagen)
        imagen = imagen.resize((nueva_anchura, nueva_altura), Image.ANTIALIAS)
        return imagen

    def cortar(self):
        self.printer.cut()

    def cerrar(self):
        self.printer.close()

# Funciones auxiliares
def obtener_comprobantes(url_comprobantes, reintentos=3):
    intento = 0
    while intento < reintentos:
        try:
            response = requests.get(url_comprobantes)
            response.raise_for_status()
            logging.info("Comprobantes obtenidos con éxito.")
            return response.json()
        except requests.exceptions.RequestException as e:
            intento += 1
            espera = 2 ** intento + random.uniform(0, 1)
            logging.error(f"Error al obtener comprobantes: {e}. Reintentando en {espera:.2f} segundos...")
            time.sleep(espera)
    logging.error("Error persistente al obtener comprobantes. Saltando este ciclo.")
    return None

def obtener_detalle_comprobante(url_detalle_comprobante, reintentos=3):
    intento = 0
    while intento < reintentos:
        try:
            response = requests.get(url_detalle_comprobante)
            response.raise_for_status()
            detalle_comprobante = response.text
            return detalle_comprobante.split('\r\n')
        except requests.exceptions.RequestException as e:
            intento += 1
            espera = 2 ** intento + random.uniform(0, 1)
            logging.error(f"Error al obtener detalle del comprobante: {e}. Reintentando en {espera:.2f} segundos...")
            time.sleep(espera)
    logging.error("Error persistente al obtener detalle del comprobante.")
    return None

def descargar_imagen_desde_url(url, reintentos=3):
    intento = 0
    while intento < reintentos:
        try:
            response = requests.get(url)
            response.raise_for_status()
            imagen_binaria = response.content
            return Image.open(BytesIO(imagen_binaria))
        except Exception as e:
            intento += 1
            espera = 2 ** intento + random.uniform(0, 1)
            logging.error(f"Error al descargar la imagen desde la URL: {e}. Reintentando en {espera:.2f} segundos...")
            time.sleep(espera)
    logging.error("Error persistente al descargar la imagen.")
    return None

def imprimir_y_guardar_comprobante(detalle_comprobante, numero_completo, impresora):
    try:
        carpeta_guardado = 'comprobantes_guardados'
        if not os.path.exists(carpeta_guardado):
            os.makedirs(carpeta_guardado)

        nombre_archivo = f"{numero_completo}.txt"
        ruta_archivo = os.path.join(carpeta_guardado, nombre_archivo)

        if os.path.exists(ruta_archivo):
            with open(ruta_archivo, 'r') as archivo_existente:
                contenido_existente = archivo_existente.read()
            contenido_existente = contenido_existente.replace("\n", "\r\n")
            if contenido_existente == '\r\n'.join(detalle_comprobante):
                logging.info(f"Comprobante {numero_completo} ya impreso y sin cambios. Ignorando.")
                return
        
        for linea in detalle_comprobante:
            if linea:
                if "#img#" in linea:
                    codigo_base64 = linea.split("#img#")[1]
                    imagen_binaria = base64.b64decode(codigo_base64)
                    imagen = Image.open(BytesIO(imagen_binaria))
                    impresora.imprimir_imagen(imagen)
                    impresora.imprimir_texto("\r\n", {})
                elif "#url#" in linea:
                    url_imagen = linea.split("#img#")[1]
                    imagen = descargar_imagen_desde_url(url_imagen)
                    impresora.imprimir_imagen(imagen)
                elif "#logo#" in linea:
                    if not os.path.exists(local_path_logo):
                        url_imagen = url_base + "app/logo.jpg"
                        urllib.request.urlretrieve(url_imagen, local_path_logo)
                    imagen = Image.open(local_path_logo)
                    impresora.imprimir_imagen(imagen)
                elif "#fin#" in linea:
                    impresora.cortar()
                else:
                    aDetalleLinea = linea.split(";")
                    opciones = {
                        "align": u'left', 
                        "font": u'a', 
                        "height": int(aDetalleLinea[1]) + 5, 
                        "bold": aDetalleLinea[0] == "B"
                    }
                    impresora.imprimir_texto(aDetalleLinea[2], opciones)
        
        impresora.cerrar()

        with open(ruta_archivo, 'w') as archivo:
            archivo.write('\r\n'.join(detalle_comprobante))

        logging.info(f"Comprobante impreso y guardado en: {ruta_archivo}")
    except Exception as e:
        logging.error(f"Error al imprimir y guardar comprobante: {e}")

def eliminar_comprobantes_antiguos(carpeta_guardado, dias_limite):
    for archivo in os.listdir(carpeta_guardado):
        ruta_archivo = os.path.join(carpeta_guardado, archivo)
        fecha_creacion = datetime.fromtimestamp(os.path.getctime(ruta_archivo))
        dias_diferencia = (datetime.now() - fecha_creacion).days
        if dias_diferencia > dias_limite:
            os.remove(ruta_archivo)
            logging.info(f"Comprobante {archivo} eliminado por tener más de {dias_limite} días.")

def procesar_comprobante(comprobante):
    numero_completo = comprobante.get('numero_completo', '')
    idcomprobante = comprobante.get('idcomprobante', '')
    url_detalle_comprobante = f"{url_base}app-get-comprobante.php?id={idcomprobante}"

    detalle_comprobante = obtener_detalle_comprobante(url_detalle_comprobante)
    
    if detalle_comprobante:
        # Reiniciar la conexión con la impresora para cada comprobante
        impresora = Impresora(idvendor, idproduct, ancho_impresora)
        imprimir_y_guardar_comprobante(detalle_comprobante, numero_completo, impresora)

def marcar_en_ejecucion():
    with open('en_ejecucion.txt', 'w') as estado:
        estado.write('En ejecución')

def desmarcar_en_ejecucion():
    if os.path.exists('en_ejecucion.txt'):
        os.remove('en_ejecucion.txt')

def ciclo_principal():
    while True:
        marcar_en_ejecucion()

        comprobantes = obtener_comprobantes(f"{url_base}app-get-comprobantes.php?ptoVta={pto_vta}")
        if comprobantes:
            for comprobante in comprobantes:
                procesar_comprobante(comprobante)
            eliminar_comprobantes_antiguos('comprobantes_guardados', dias_a_eliminar)
        else:
            logging.info("No se encontraron comprobantes.")

        desmarcar_en_ejecucion()
        time.sleep(frecuencia_actualizacion)

if __name__ == "__main__":
    ciclo_principal()
