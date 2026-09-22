"""Selector local de imágenes y documentos PDF para INE y actas."""

import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from extraer_documento import procesar_documento


class Aplicacion(ttk.Frame):
    def __init__(self, ventana):
        super().__init__(ventana, padding=18)
        self.pack(fill="both", expand=True)
        ventana.title("Extraer datos de INE o acta")
        ventana.geometry("850x690")
        ventana.minsize(680, 520)
        self.tipo = tk.StringVar(value="ine")
        self.archivo = tk.StringVar()
        self.pagina = tk.StringVar(value="1")
        self.estado = tk.StringVar(value="Selecciona el documento y el archivo que quieres analizar.")
        self.resultado = None
        self.origen_resultado = None
        self.cola = queue.Queue()
        self.ocupado = False

        ttk.Label(self, text="¿Qué documento quieres analizar?", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        opciones = ttk.Frame(self)
        opciones.pack(fill="x", pady=(10, 14))
        self.ine = ttk.Radiobutton(opciones, text="INE (anverso)", variable=self.tipo, value="ine", command=self.cambiar_tipo)
        self.ine.pack(side="left", padx=(0, 25))
        self.acta = ttk.Radiobutton(opciones, text="Acta de nacimiento", variable=self.tipo, value="acta", command=self.cambiar_tipo)
        self.acta.pack(side="left")

        ttk.Label(self, text="Puedes elegir una fotografía, una imagen escaneada o un PDF.").pack(anchor="w")
        archivo_fila = ttk.Frame(self)
        archivo_fila.pack(fill="x", pady=8)
        self.ruta = ttk.Entry(archivo_fila, textvariable=self.archivo)
        self.ruta.pack(side="left", fill="x", expand=True)
        self.elegir = ttk.Button(archivo_fila, text="Elegir imagen o PDF…", command=self.seleccionar)
        self.elegir.pack(side="left", padx=(8, 0))

        pagina_fila = ttk.Frame(self)
        pagina_fila.pack(fill="x", pady=(4, 8))
        ttk.Label(pagina_fila, text="Página del PDF con el frente de la INE:").pack(side="left")
        self.numero = ttk.Spinbox(pagina_fila, from_=1, to=9999, width=6, textvariable=self.pagina)
        self.numero.pack(side="left", padx=8)
        ttk.Label(self, text="Para imágenes, usa página 1. En actas se revisan todas las páginas del PDF.").pack(anchor="w")

        acciones = ttk.Frame(self)
        acciones.pack(fill="x", pady=14)
        self.analizar = ttk.Button(acciones, text="Extraer datos", command=self.procesar)
        self.analizar.pack(side="left")
        self.guardar = ttk.Button(acciones, text="Guardar JSON…", command=self.exportar, state="disabled")
        self.guardar.pack(side="left", padx=8)
        self.progreso = ttk.Progressbar(acciones, mode="indeterminate", length=180)
        self.progreso.pack(side="right")
        ttk.Label(self, textvariable=self.estado, wraplength=780).pack(anchor="w", pady=(0, 8))
        self.salida = ScrolledText(self, wrap="word", font=("Consolas", 10), state="disabled")
        self.salida.pack(fill="both", expand=True)
        ventana.after(150, self.recibir)

    def cambiar_tipo(self):
        self.pagina.set("1")
        self.numero.configure(state="normal" if self.tipo.get() == "ine" else "disabled")

    def seleccionar(self):
        nombre = filedialog.askopenfilename(
            title="Selecciona una imagen o un PDF",
            filetypes=[("Imágenes y PDF", "*.pdf *.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp"), ("Documentos PDF", "*.pdf"), ("Imágenes", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp")],
        )
        if nombre:
            self.archivo.set(nombre)

    def mostrar(self, texto):
        self.salida.configure(state="normal")
        self.salida.delete("1.0", "end")
        self.salida.insert("1.0", texto)
        self.salida.configure(state="disabled")

    def controles(self, ocupado):
        self.ocupado = ocupado
        for control in (self.ine, self.acta, self.ruta, self.elegir, self.analizar):
            control.configure(state="disabled" if ocupado else "normal")
        self.numero.configure(state="normal" if not ocupado and self.tipo.get() == "ine" else "disabled")
        self.guardar.configure(state="normal" if not ocupado and self.resultado is not None else "disabled")

    def procesar(self):
        if self.ocupado:
            return
        try:
            ruta = Path(self.archivo.get().strip().strip('"'))
            if not ruta.is_file():
                raise ValueError("Selecciona un archivo existente.")
            pagina = int(self.pagina.get())
            if pagina < 1:
                raise ValueError("La página debe ser un número mayor que cero.")
        except ValueError as exc:
            messagebox.showerror("Revisa el archivo y la página", str(exc))
            return
        tipo = self.tipo.get()
        self.resultado = None
        self.origen_resultado = ruta.resolve()
        self.controles(True)
        self.progreso.start(12)
        self.estado.set("Analizando el archivo. Los escaneos pueden tardar unos segundos…")
        self.mostrar("")

        def trabajar():
            try:
                self.cola.put((True, procesar_documento(tipo, ruta, pagina=pagina)))
            except Exception as exc:
                self.cola.put((False, str(exc)))

        threading.Thread(target=trabajar, daemon=True).start()

    def recibir(self):
        try:
            correcto, contenido = self.cola.get_nowait()
        except queue.Empty:
            pass
        else:
            self.progreso.stop()
            if correcto:
                self.resultado = contenido
                self.mostrar(json.dumps(contenido, ensure_ascii=False, indent=2))
                avisos = len(contenido.get("advertencias", []))
                self.estado.set(f"Extracción terminada: {avisos} aviso(s). Puedes revisar y guardar los datos.")
            else:
                self.estado.set("No se pudo procesar el archivo.")
                self.mostrar(contenido)
            self.controles(False)
        self.after(150, self.recibir)

    def exportar(self):
        if self.resultado is None:
            return
        nombre = filedialog.asksaveasfilename(title="Guardar datos extraídos", defaultextension=".json", initialfile="resultado.json", filetypes=[("JSON", "*.json")])
        if not nombre:
            return
        try:
            destino = Path(nombre)
            if destino.resolve() == self.origen_resultado:
                raise ValueError("El resultado no puede sobrescribir el documento original.")
            destino.write_text(json.dumps(self.resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.estado.set(f"Resultado guardado en {destino.name}.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("No se pudo guardar", str(exc))


def main():
    ventana = tk.Tk()
    Aplicacion(ventana)
    ventana.mainloop()


if __name__ == "__main__":
    main()
