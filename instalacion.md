Aqui puedes ver la guia de instalacion completa: https://github.com/marcoscasamayor/ticketprint-python/blob/master/instalacion.md

---

# 🖨️ **Guía de Instalación – TicketPrint (Linux)**

## 📌 **1. Instalación de Python y dependencias**

Asegurarse de tener Python 3.10+ instalado:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
```

## 📌 **2. Crear entorno virtual dentro del proyecto**

Ubicarse en la carpeta donde está el proyecto:

```bash
cd /home/sc3/Documentos/TicketPrint/
```

Crear el entorno:

```bash
python3 -m venv venv
```

Activarlo:

```bash
source venv/bin/activate
```

Instalar las dependencias dentro del entorno virtual:

```bash
sudo apt install python-tk
pip install python-escpos escpos
pip install requests
pip install Pillow
pip install pystray
```

---

## 📌 **3. Crear el archivo ejecutar.sh**

Este script permite ejecutar la aplicación con entorno gráfico.

Crear el archivo:

```bash
nano /home/sc3/Documentos/TicketPrint/ejecutar.sh
```

Contenido:

```bash
#!/bin/bash

cd /home/sc3/Documentos/TicketPrint/
export DISPLAY=:0
source venv/bin/activate
python3 ticketprint-new.py &
```

### 🔍 **¿Por qué se usa `export DISPLAY=:0`?**

Cuando Linux ejecuta programas automáticamente al iniciar, muchas veces el entorno gráfico aún no está asociado al usuario.
`pystray` (el icono en la bandeja del sistema) necesita conectarse al servidor gráfico “Xorg”.

El valor `DISPLAY=:0` le indica explícitamente qué pantalla usar.

Sin esto, aparece el error:

```
Xlib.error.DisplayNameError: Bad display name ""
```

### Dar permisos de ejecución:

```bash
sudo chmod +x /home/sc3/Documentos/TicketPrint/ejecutar.sh
```

---

## 📌 **4. Crear archivo .desktop para que se inicie al prender la PC**

Crear la carpeta si no existe:

```bash
mkdir -p ~/.config/autostart
```

Crear el archivo:

```bash
nano ~/.config/autostart/ticketprint.desktop
```

Contenido:

```ini
[Desktop Entry]
Type=Application
Name=TicketPrint
Exec=/home/sc3/Documentos/TicketPrint/ejecutar.sh
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
```

### Dar permisos:

```bash
sudo chmod +x ~/.config/autostart/ticketprint.desktop
```

---

## 📌 **5. Probar el ejecutar.sh sin reiniciar**

Para confirmar que funciona:

```bash
/home/sc3/Documentos/TicketPrint/ejecutar.sh
```

Si abre la aplicación sin errores, el autostart también funcionará.

---

## 📌 **6. (Opcional) Configuración de impresora térmica**

### ➤ **Obtener idVendor y idProduct**

Conectar la impresora y ejecutar:

```bash
lsusb
```

Ejemplo de salida:

```
Bus 001 Device 008: ID 28e9:0289 GEZHI Thermal Printer
```

* **idVendor** = `28e9`
* **idProduct** = `0289`

---

### ➤ **Habilitar permisos de impresión (udev rule)**

Crear archivo:

```bash
sudo nano /etc/udev/rules.d/99-usb-printer.rules
```

Agregar:

```bash
SUBSYSTEM=="usb", ATTR{idVendor}=="28e9", ATTR{idProduct}=="0289", MODE="0666"
```

Recargar reglas:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Reconectar la impresora.

---

### ➤ **Verificar permisos del dispositivo**

```bash
ls -l /dev/bus/usb/1/8
```

Debe mostrar permisos **rw** para otros usuarios:

```
crw-rw-rw-
```

Si es así, Python podrá acceder sin errores como:

```
Access denied (insufficient permissions)
```

---