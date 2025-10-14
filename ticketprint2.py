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
from tkinter.scrolledtext import ScrolledText
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

        self.text_area = ScrolledText(self.frame, wrap=tk.WORD, height=15)
        self.text_area.pack(fill=tk.BOTH, expand=True)
        
        # Configurar etiquetas para colores
        self.text_area.tag_configure('error', foreground='red')
        self.text_area.tag_configure('neutro', foreground='gray')
        self.text_area.tag_configure('exito', foreground='green')
        
         # Botón para reiniciar
        self.boton_reiniciar = tk.Button(self.root, text="Reiniciar", command=self.reiniciar_proceso)
        self.boton_reiniciar.pack()
        
        # Cargar configuración
        self.cargar_configuracion()
        
        # Iniciar el proceso después de que la interfaz se haya cargado completamente
        self.root.after_idle(self.iniciar_proceso)
        
        
    def minimize_to_tray(self):
        # Esconder la ventana principal
        self.root.withdraw()
        # Iniciar el icono en la bandeja del sistema
        self.icon = pystray.Icon("ComprobanteApp", Image.open("logo.png"), "ComprobanteApp", self.create_menu())
        self.icon.run()

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
        self.mostrar_mensaje('Iniciando proceso de comprobantes.', 'neutro')
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
            self.mostrar_mensaje("Proceso detenido debido a un error.\nHaga clic en 'Reiniciar' para continuar.")



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
                    self.mostrar_mensaje(f"Comprobante procesado: {numero_completo}", 'exito')
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
    
            if os.path.exists(ruta_archivo):
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
                        url_imagen = linea.split("#url#")[1]
                        imagen = descargar_imagen_desde_url(url_imagen)
                        impresora.imprimir_imagen(imagen)
                    elif "#logo#" in linea:
                        if not os.path.exists("logo.jpg"):
                            url_imagen = self.url_base + "app/logo.jpg"
                            urllib.request.urlretrieve(url_imagen, "logo.jpg")
                        imagen = Image.open("logo.jpg")
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
            
            impresora.cortar()
            impresora.cerrar()
    
            with open(ruta_archivo, 'w') as archivo:
                archivo.write('\r\n'.join(detalle_comprobante))
    
            logging.info(f"Comprobante impreso y guardado en: {ruta_archivo}")
        except RuntimeError as e:
            mensaje_error = f"Error en la impresora: {e}, comprobante: {detalle_comprobante}"
            logging.error(mensaje_error)
            self.mostrar_error(mensaje_error)
        except Exception as e:
            mensaje_error = f"Error al imprimir y guardar comprobante: {e}, comprobante: {detalle_comprobante}"
            logging.error(mensaje_error)
            self.mostrar_error(mensaje_error)



    def eliminar_comprobantes_antiguos(self, carpeta_guardado, dias_limite):
        for archivo in os.listdir(carpeta_guardado):
            ruta_archivo = os.path.join(carpeta_guardado, archivo)
            fecha_creacion = datetime.fromtimestamp(os.path.getctime(ruta_archivo))
            dias_diferencia = (datetime.now() - fecha_creacion).days
            if dias_diferencia > dias_limite:
                os.remove(ruta_archivo)
                logging.info(f"Comprobante {archivo} eliminado por tener más de {dias_limite} días.")
                
    # Reiniciamos el ciclo principal
    def reiniciar_proceso(self):
        global error_detectado
        error_detectado = False
        self.mostrar_mensaje("Proceso reiniciado.", 'exito')
        self.ciclo_principal()

    def salir(self):
        self.root.quit()

    def crear_icono_bandeja(self):
        imagen = PILImage.open("logo.png")
        menu = (item('Abrir', self.mostrar_ventana), item('Salir', self.salir))
        self.icono_bandeja = pystray.Icon("Gestor de Comprobantes", imagen, "Gestor de Comprobantes", menu)
        threading.Thread(target=self.icono_bandeja.run).start()


    def ocultar_ventana(self):
        self.root.withdraw()

    def mostrar_ventana(self):
        self.root.deiconify()

    def minimizar_ventana(self, event=None):
        if self.root.state() == 'iconic':
            self.ocultar_ventana()
    
    def mostrar_mensaje(self, mensaje, tipo):
        hora_actual = datetime.now().strftime("%H:%M:%S")
        mensaje_con_hora = f"[{hora_actual}] {mensaje}"
        self.text_area.insert(tk.END, mensaje_con_hora + '\n', tipo)
        self.text_area.yview(tk.END)
        
    def mostrar_error(self, mensaje):
        global error_detectado
        error_detectado = True
        hora_actual = datetime.now().strftime("%H:%M:%S")
        mensaje_con_hora = f"[{hora_actual}] {mensaje}"
        self.text_area.insert(tk.END, f"ERROR: {mensaje_con_hora}\n", 'error')
        self.text_area.yview(tk.END)


# Clase para gestionar la impresora
class Impresora:
    def __init__(self, idvendor, idproduct, ancho_impresora):
        try:
            self.printer = Usb(idvendor, idproduct)
        except Exception as e:
            raise RuntimeError(f"Error al inicializar la impresora: {e}")
        self.ancho_impresora = ancho_impresora

    def imprimir_texto(self, texto, opciones):
        try:
            if opciones.get("align") == u'right':
                texto = texto.rjust(self.ancho_impresora)
            elif opciones.get("align") == u'center':
                texto = texto.center(self.ancho_impresora)
            self.printer.text(texto)
        except Exception as e:
            raise RuntimeError(f"Error al imprimir texto: {e}")

    def imprimir_imagen(self, imagen):
        try:
            imagen_rescalada = self.reescalar_imagen(imagen)
            self.printer.image(imagen_rescalada)
        except Exception as e:
            raise RuntimeError(f"Error al imprimir imagen: {e}")
        
    def reescalar_imagen(self, imagen):
        try:
            factor_escala_ancho = self.ancho_impresora / float(imagen.width)
            factor_escala_altura = factor_escala_ancho
            nueva_anchura = int(imagen.width * factor_escala_ancho)
            nueva_altura = int(imagen.height * factor_escala_altura)
            imagen.info['dpi'] = (300, 300)
            imagen = ImageOps.exif_transpose(imagen)
            imagen = imagen.resize((nueva_anchura, nueva_altura), Image.ANTIALIAS)
            return imagen
        except Exception as e:
            raise RuntimeError(f"Error al reescalar imagen: {e}")

    def cortar(self):
        try:
            self.printer.cut()
        except Exception as e:
            raise RuntimeError(f"Error al cortar el papel: {e}")

    def cerrar(self):
        try:
            self.printer.close()
        except Exception as e:
            raise RuntimeError(f"Error al cerrar la impresora: {e}")

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

root = tk.Tk()
 # Asignar el comportamiento al cerrar la ventana
app = AplicacionComprobantes(root)
root.protocol("WM_DELETE_WINDOW", app.minimize_to_tray)
root.mainloop()