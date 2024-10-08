import os
import time
import random
import requests
import base64
import logging
from datetime import datetime, timedelta
from PIL import Image, ImageOps
from io import BytesIO
import configparser
import urllib.request
from escpos.printer import Usb
import tkinter as tk
from tkinter import ttk, messagebox
from pystray import MenuItem as item
import pystray
from PIL import Image as PILImage
import threading

global error_detectado
error_detectado = False

# Configura el logging
logging.basicConfig(filename=f'comprobante_{datetime.now().strftime("%Y-%m-%d")}.log', level=logging.INFO, 
                    format='%(asctime)s %(message)s')

# Eliminar el log anterior si existe
log_anterior = f'comprobante_{(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")}.log'
if os.path.exists(log_anterior):
    os.remove(log_anterior)

# Clase de la aplicación
class AplicacionComprobantes:
    def __init__(self, root):
        self.root = root
        self.root.title("Gestor de Comprobantes By SC3 Sistemas")

        # Configurar la ventana principal
        self.frame = ttk.Frame(self.root)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Agregar la lista de comprobantes impresos
        self.listbox_comprobantes = tk.Listbox(self.frame, height=10)
        self.listbox_comprobantes.pack(fill=tk.BOTH, expand=True)

        # Barra de estado
        self.status_bar = tk.Label(self.root, text="Listo", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Cargar configuración
        self.cargar_configuracion()

        # Iniciar el proceso después de que la interfaz se haya cargado completamente
        self.root.after_idle(self.iniciar_proceso)

    def cargar_configuracion(self):
        # Cargar la configuración desde el archivo config.ini
        ruta_actual = os.getcwd()
        config = configparser.ConfigParser()
        config.read(os.path.join(ruta_actual, 'config.ini'))

        self.pto_vta = config["General"]["pto_vta"]
        self.dias_a_eliminar = int(config["General"]["dias_a_eliminar"])
        self.frecuencia_actualizacion = int(config["General"]["frecuencia_actualizacion"])
        self.frecuencia_error = 60
        self.url_base = config["General"]["url_base"]
        # Agrega barra al final por las dudas
        if not self.url_base.endswith("/"):
            self.url_base += "/"
        
        # Variables de la conexión a la impresora
        self.idvendor = int(config["Impresora"]["idvendor"], 16)
        self.idproduct = int(config["Impresora"]["idproduct"], 16)
        self.ancho_impresora = int(config["Impresora"]["ancho"])
        
    def iniciar_proceso(self):
        self.actualizar_status('Iniciando proceso de comprobantes.')
        self.ciclo_principal()

    def ciclo_principal(self):   
        global error_detectado
        try:
            url = f"{self.url_base}app-get-comprobantes.php?ptoVta={self.pto_vta}"
            comprobantes = self.obtener_comprobantes(url)
            if comprobantes:
                for comprobante in comprobantes:
                    self.procesar_comprobante(comprobante)
                    if error_detectado:
                       break
                self.eliminar_comprobantes_antiguos('comprobantes_guardados', self.dias_a_eliminar)
            else:
                logging.info("No se encontraron comprobantes.")
                self.mostrar_error(f"No se encontraron comprobantes.\n URL: {url}")
            if error_detectado:
                self.root.after(self.frecuencia_error * 1000, self.reiniciar_proceso)
                return
            self.root.after(self.frecuencia_actualizacion * 1000, self.ciclo_principal)
        except Exception as e:
            mensaje_error = f"Ocurrió un error: {str(e)}"
            logging.error(mensaje_error)
            self.mostrar_error(mensaje_error)
            # Detenemos el ciclo aquí, no llamamos a after()
            self.actualizar_status("Proceso detenido debido a un error. Haga clic en 'Reiniciar' para continuar.")

    # Descarga y guarda el comprobante, para luego mandar a imprimir
    def procesar_comprobante(self, comprobante):
        numero_completo = comprobante.get('numero_completo', '')
        idcomprobante = comprobante.get('idcomprobante', '')
        url_detalle_comprobante = f"{self.url_base}app-get-comprobante.php?id={idcomprobante}"
    
        carpeta_guardado = 'comprobantes_guardados'
        ruta_archivo = os.path.join(carpeta_guardado, f"{numero_completo}.txt")
    
        if not os.path.exists(ruta_archivo):
            detalle_comprobante = self.obtener_detalle_comprobante(url_detalle_comprobante)
            if detalle_comprobante:
                try:
                    # Reiniciar la conexión con la impresora para cada comprobante
                    impresora = Impresora(self.idvendor, self.idproduct, self.ancho_impresora)
                    self.imprimir_y_guardar_comprobante(detalle_comprobante, numero_completo, impresora)
                    self.actualizar_status(f"Comprobante procesado: {numero_completo}")
                    # Agregar comprobante a la lista
                    self.listbox_comprobantes.insert(tk.END, numero_completo)
                except RuntimeError as e:
                    error_str = str(e)
    
                    if "device not found" in error_str.lower():
                        mensaje_error = f"Impresora no conectada."
                    else:
                        mensaje_error = f"Error al procesar el comprobante {numero_completo}: {error_str}"
                    
                    self.mostrar_error(mensaje_error)
                    logging.error(mensaje_error)

    # Obtiene todos los comprobantes de la web
    def obtener_comprobantes(self, url_comprobantes, reintentos=3):
        intento = 0
        while intento < reintentos:
            try:
                response = requests.get(url_comprobantes)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                intento += 1
                espera = 2 ** intento + random.uniform(0, 1)
                mensaje_error = f"Error al obtener comprobantes: {e}. Reintentando en {espera:.2f} segundos..."
                logging.error(mensaje_error)
                self.mostrar_error(mensaje_error)
                time.sleep(espera)
        mensaje_final = "Error persistente al obtener comprobantes. Saltando este ciclo."
        logging.error(mensaje_final)
        self.mostrar_error(mensaje_final)
        return None

    
    def obtener_detalle_comprobante(self, url_detalle_comprobante, reintentos=3):
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

    def imprimir_y_guardar_comprobante(self, detalle_comprobante, numero_completo, impresora):
        try:
            carpeta_guardado = 'comprobantes_guardados'
            if not os.path.exists(carpeta_guardado):
                os.makedirs(carpeta_guardado)
    
            nombre_archivo = f"{numero_completo}.txt"
            ruta_archivo = os.path.join(carpeta_guardado, nombre_archivo)
    
            with open(ruta_archivo, 'w') as archivo:
                archivo.write("\n".join(detalle_comprobante))
    
            self.imprimir_comprobante(detalle_comprobante, impresora)
    
            logging.info(f"Comprobante {numero_completo} guardado en {ruta_archivo}")
    
        except Exception as e:
            mensaje_error = f"Error al imprimir y guardar comprobante {numero_completo}: {str(e)}"
            logging.error(mensaje_error)
            self.mostrar_error(mensaje_error)

    def imprimir_comprobante(self, detalle_comprobante, impresora):
        for linea in detalle_comprobante:
            impresora.text(linea + "\n")
        impresora.cut()

    def eliminar_comprobantes_antiguos(self, carpeta, dias_a_eliminar):
        tiempo_limite = time.time() - (dias_a_eliminar * 86400)
        for archivo in os.listdir(carpeta):
            ruta_archivo = os.path.join(carpeta, archivo)
            if os.path.isfile(ruta_archivo):
                if os.path.getmtime(ruta_archivo) < tiempo_limite:
                    os.remove(ruta_archivo)
                    logging.info(f"Archivo antiguo eliminado: {ruta_archivo}")
    
    def reiniciar_proceso(self):
        global error_detectado
        error_detectado = False
        self.actualizar_status("Reiniciando proceso...")
        self.ciclo_principal()

    def actualizar_status(self, mensaje, tipo = ''):
        if tipo == 'error':
            self.status_bar.config(bg='red', fg='white', text=mensaje)
        elif tipo == 'exito':
            self.status_bar.config(bg='green', fg='white', text=mensaje)
        else:
            self.status_bar.config(bg='gray', fg='white', text=mensaje)
        logging.info(mensaje)

    def mostrar_error(self, mensaje):
        self.mostrar_mensaje(mensaje, 'error')

    def mostrar_exito(self, mensaje):
        self.mostrar_mensaje(mensaje, 'exito')

    def mostrar_error(self, mensaje):
        global error_detectado
        error_detectado = True
        self.status_bar.config(text=f"Error: {mensaje}")
        logging.error(mensaje)
        

# Clase para manejar la impresora
class Impresora:
    def __init__(self, idvendor, idproduct, ancho):
        try:
            self.impresora = Usb(idvendor, idproduct)
            self.ancho = ancho
        except Exception as e:
            mensaje_error = f"Error al conectar con la impresora: {str(e)}"
            logging.error(mensaje_error)
            raise RuntimeError(mensaje_error)
    
    def text(self, texto):
        self.impresora.text(texto)

    def cut(self):
        self.impresora.cut()

def iniciar_interfaz():
    root = tk.Tk()
    app = AplicacionComprobantes(root)
    root.mainloop()

if __name__ == "__main__":
    iniciar_interfaz()
