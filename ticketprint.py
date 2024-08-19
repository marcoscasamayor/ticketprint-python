#!/usr/bin/env python3
import requests
from escpos.printer import Usb
import base64
import os
import time
import random
from datetime import datetime, timedelta
from PIL import Image
from PIL import ImageOps
from io import BytesIO
import configparser
import urllib.request

#!-----------------------------------------Carga configuracion
# Lee el archivo config.ini
ruta_actual = os.getcwd()
config = configparser.ConfigParser()
config.read(ruta_actual + '/config.ini')

pto_vta = config["General"]["pto_vta"]
dias_a_eliminar = int(config["General"]["dias_a_eliminar"])
frecuencia_actualizacion = int(config["General"]["frecuencia_actualizacion"])
url_base = config["General"]["url_base"]
local_path_logo = ruta_actual + "/logo.jpg"
 
 
if url_base.endswith("/") != True: 
    url_base += "/"
    
#LINUX: lsusb en una terminal para ver estos 2 datos 
#EJ LINUX: us 001 Device 004: ID 28e9:0289 GEZHI micro-printer idvendor=28e9, idproduct=0289
#WINDOWS: ir a "Device manager", encontra impresora, segundo click y "Properties", ir a "Details" => "Hardware IDs"
#EJ WINDOWS:HID\VID_046D&PID_C05A => idvendor=046D, productid=C05a
idvendor = int(config["Impresora"]["idvendor"], 16)
idproduct = int(config["Impresora"]["idproduct"], 16)
ancho_impresora = int(config["Impresora"]["ancho"])

#Obtiene el comprobante como tal EJ: https://laespigadeoro.sc3-app2.com.ar/app-get-comprobante.php?id=<IDCOMPROBANTE>
#Y luego lo retorna como array
def obtener_detalle_comprobante(url_detalle_comprobante):
    try:
        response = requests.get(url_detalle_comprobante)
        response.raise_for_status()
        detalle_comprobante = response.text
        lineas_comprobante = detalle_comprobante.split('\r\n')
        return lineas_comprobante
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener detalle del comprobante: {e}")
        return None
    
#descarga una imagen desde url y retorna un objeto image
def descargar_imagen_desde_url(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        imagen_binaria = response.content
        imagen = Image.open(BytesIO(imagen_binaria))
        return imagen
    except Exception as e:
        print(f"Error al descargar la imagen desde la URL: {e}")
        return None

def reescalar_imagen(imagen):
     # Calcula la escala para ajustar la imagen proporcionalmente
    factor_escala_ancho = ancho_impresora / float(imagen.width)
    factor_escala_altura = factor_escala_ancho  # Para mantener la proporción
    nueva_anchura = int(imagen.width * factor_escala_ancho)
    nueva_altura = int(imagen.height * factor_escala_altura)
    
    # Escala y ajusta la imagen
    imagen.info['dpi'] = (300, 300)  # Establece la resolución a 300 DPI (puedes ajustar esto según tus necesidades)
    imagen = ImageOps.exif_transpose(imagen)  # Gira la imagen si es necesario
    imagen = imagen.resize((nueva_anchura, nueva_altura), Image.ANTIALIAS)
    return imagen

#Verifica que no se haya impreso, en caso de no, lo imprime y lo guarda.
def imprimir_y_guardar_comprobante(detalle_comprobante, numero_completo):
    try:
        #verifica si no existe la ruta
        carpeta_guardado = 'comprobantes_guardados'
        if not os.path.exists(carpeta_guardado):
            os.makedirs(carpeta_guardado)

        nombre_archivo = f"{numero_completo}.txt"
        ruta_archivo = os.path.join(carpeta_guardado, nombre_archivo)

        if os.path.exists(ruta_archivo):
            # Si el archivo existe, comparar el contenido con el nuevo detalle
            with open(ruta_archivo, 'r') as archivo_existente:
                contenido_existente = archivo_existente.read()

            contenido_existente = contenido_existente.replace("\n", "\r\n")
            if contenido_existente == '\r\n'.join(detalle_comprobante):
                # El contenido no ha cambiado, ignorar el comprobante
                print(f"Comprobante {numero_completo} ya impreso y sin cambios. Ignorando.")
                return
            
        # Imprimir el comprobante
        p = Usb(idvendor,idproduct)# Modifica estos valores con los adecuados
        for linea in detalle_comprobante:
            if linea != "":
                if "#img#" in linea:
                     # Extraer el código base64 después de la etiqueta
                    codigo_base64 = linea.split("#img#")[1]
                    # Decodificar el código base64 a imagen binaria
                    imagen_binaria = base64.b64decode(codigo_base64)
                    # Crear una imagen desde la binaria
                    imagen = Image.open(BytesIO(imagen_binaria))
                    imagen = reescalar_imagen(imagen)
    
                    p.image(imagen)
                    p.text("\r\n")  # Agrega 3 líneas en blanco como margen
                elif "#url#" in linea:
                    url_imagen = linea.split("#img#")[1]
                    # Descargar la imagen desde la URL
                    imagen = descargar_imagen_desde_url(url_imagen)
                    imagen = reescalar_imagen(imagen)
                    
                    p.image(imagen)
                elif "#logo#" in linea:
                    if not os.path.exists(local_path_logo):
                        # La imagen no está presente localmente, descárgala
                        url_imagen = url_base + "app/logo.jpg"
                        urllib.request.urlretrieve(url_imagen, local_path_logo)
                
                    # Levanta la imagen local
                    imagen = Image.open(local_path_logo)
                    imagen = reescalar_imagen(imagen)
                    
                    p.image(imagen)
                elif "#fin#" in linea:
                    p.cut()
                else:
                    aDetalleLinea = linea.split(";")
                    # Configurar la fuente y otros parámetros según la línea
                    # Establecer configuraciones
                    p.set(align=u'left', font=u'a', height=int(aDetalleLinea[1]) + 5, bold=True if aDetalleLinea[0]=="B" else False)
                    p.text(aDetalleLinea[2] + '\n')
        p.cut()
        p.close()

        # Guardar el comprobante en un archivo
        carpeta_guardado = 'comprobantes_guardados'
        if not os.path.exists(carpeta_guardado):
            os.makedirs(carpeta_guardado)

        nombre_archivo = f"{numero_completo}.txt"
        ruta_archivo = os.path.join(carpeta_guardado, nombre_archivo)

        with open(ruta_archivo, 'w') as archivo:
            archivo.write('\r\n'.join(detalle_comprobante))

        print(f"Comprobante impreso y guardado en: {ruta_archivo}")
    except Exception as e:
        print(f"Error al imprimir y guardar comprobanteI: {e}")

def obtener_comprobantes(url_comprobantes, reintentos=3):
    intento = 0
    while intento < reintentos:
        try:
            response = requests.get(url_comprobantes)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            intento += 1
            espera = 2 ** intento + random.uniform(0, 1)
            print(f"Error al obtener comprobantes: {e}. Reintentando en {espera:.2f} segundos...")
            time.sleep(espera)
    print("Error persistente al obtener comprobantes. Saltando este ciclo.")
    return None


def procesar_comprobantes(comprobantes):
    if comprobantes:
        for comprobante in comprobantes:
            numero_completo = comprobante.get('numero_completo', '')
            fecha = comprobante.get('fecha', '')
            id_comprobante = comprobante.get('idcomprobante', '')
            
            # Puedes realizar aquí cualquier procesamiento adicional que necesites
            print(f"Comprobante: {numero_completo}, Fecha: {fecha}, ID: {id_comprobante}")
    else:
        print("No se encontraron comprobantes.")

# Función para eliminar comprobantes guardados de más de N días
def eliminar_comprobantes_antiguos(carpeta_guardado, dias_limite):
    for archivo in os.listdir(carpeta_guardado):
        ruta_archivo = os.path.join(carpeta_guardado, archivo)
        
        # Obtener la fecha de creación del archivo
        fecha_creacion = datetime.fromtimestamp(os.path.getctime(ruta_archivo))
        
        # Calcular la diferencia en días
        dias_diferencia = (datetime.now() - fecha_creacion).days
        
        if dias_diferencia > dias_limite:
            # Eliminar el archivo
            os.remove(ruta_archivo)
            print(f"Comprobante {archivo} eliminado por tener más de {dias_limite} días.")

# En tu bucle principal
while True:
    # Para saber si se sigue ejecutando
    with open('en_ejecucion.txt', 'w') as estado:
        estado.write('En ejecución')
    
    
    # Obtener comprobantes
    comprobantes = obtener_comprobantes(f"{url_base}app-get-comprobantes.php?ptoVta={pto_vta}")

    # Procesar comprobantes
    for comprobante in comprobantes:
        numero_completo = comprobante.get('numero_completo', '')
        idcomprobante = comprobante.get('idcomprobante', '')
        url_detalle_comprobante = f"{url_base}app-get-comprobante.php?id={idcomprobante}"

        # Obtener detalle del comprobante
        detalle_comprobante = obtener_detalle_comprobante(url_detalle_comprobante)

        # Imprimir y guardar el comprobante
        imprimir_y_guardar_comprobante(detalle_comprobante, numero_completo)
        
        
        eliminar_comprobantes_antiguos('comprobantes_guardados', dias_a_eliminar)
    
    
    # Para saber si se sigue ejecutando
    os.remove('en_ejecucion.txt')

    time.sleep(frecuencia_actualizacion)
