import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkcalendar import Calendar
from datetime import datetime, timedelta
import re
import csv
import os
import mysql.connector

# =========================
#  CONEXIÓN MYSQL + DDL
# =========================
def conectar_mysql():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Neno@1981@",
            database="facturacionfabre"
        )
        cur = conn.cursor()
        # Tabla base (compatibilidad con instalaciones previas)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS temporal3 (
            id INT AUTO_INCREMENT PRIMARY KEY,
            registro INT NOT NULL,
            ticket VARCHAR(50),
            precio DECIMAL(10,2),
            cant DECIMAL(10,2),
            descuento DECIMAL(10,2),
            total DECIMAL(10,2),
            estado VARCHAR(20) DEFAULT 'pendiente'
        )
        """)
        conn.commit()

        # Asegurar columnas de semana (si tabla es vieja)
        cur.execute("SHOW COLUMNS FROM temporal3")
        cols = {row[0] for row in cur.fetchall()}
        if "semana_inicio" not in cols:
            cur.execute("ALTER TABLE temporal3 ADD COLUMN semana_inicio DATE NULL")
        if "semana_fin" not in cols:
            cur.execute("ALTER TABLE temporal3 ADD COLUMN semana_fin DATE NULL")
        conn.commit()

        # Tabla brokers (opcional)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS t_broker (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(100),
            descuento DECIMAL(5,2)
        )
        """)
        conn.commit()

        return conn
    except mysql.connector.Error as err:
        messagebox.showerror("Error de conexión", f"No se pudo conectar a MySQL:\n{err}")
        return None


def _to_date(obj):
    """Convierte str/date/datetime a datetime.date para formateo seguro."""
    if obj is None:
        return None
    if isinstance(obj, datetime):
        return obj.date()
    try:
        # puede venir como date de MySQL (ya es date), o como str 'YYYY-MM-DD'
        return obj if hasattr(obj, "strftime") and not isinstance(obj, str) else datetime.strptime(str(obj), "%Y-%m-%d").date()
    except Exception:
        return None


# =========================
#  APP PRINCIPAL
# =========================
class TicketForm(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        master.title("Fabre System - Control de Tickets")

        # Ventana centrada
        ancho, alto = 1200, 720
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        x = int((sw - ancho) / 2)
        y = int((sh - alto) / 2)
        master.geometry(f"{ancho}x{alto}+{x}+{y}")
        master.resizable(False, False)

        # 🎨 Estilos (mismo color base)
        style = ttk.Style()
        style.theme_use("clam")

        base_bg = "#e4e2dd"
        header_bg = "#2c3e50"
        header_fg = "white"

        style.configure("TFrame", background=base_bg)
        style.configure("TLabelframe", background=base_bg)
        style.configure("TLabelframe.Label", background=base_bg, font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", font=("Segoe UI", 10), background=base_bg, foreground="black")

        style.configure("Header.TLabel",
                        font=("Segoe UI", 18, "bold"),
                        background=header_bg,
                        foreground=header_fg,
                        padding=10,
                        anchor="center")

        style.configure("TButton",
                        font=("Segoe UI", 10, "bold"),
                        padding=6,
                        relief="flat",
                        background=base_bg,
                        foreground="black")
        style.map("TButton",
                  background=[("active", "#d5d3cf")],
                  relief=[("pressed", "groove")])

        # Botones (mismos nombres de estilo que ya usas)
        style.configure("Agregar.TButton", background="#27ae60", foreground="white")
        style.map("Agregar.TButton", background=[("active", "#2ecc71")])

        style.configure("Eliminar.TButton", background="#c0392b", foreground="white")
        style.map("Eliminar.TButton", background=[("active", "#e74c3c")])

        style.configure("Procesar.TButton", background="#f39c12", foreground="black")
        style.map("Procesar.TButton", background=[("active", "#f1c40f")])

        style.configure("Nuevo.TButton", background="#2980b9", foreground="white")
        style.map("Nuevo.TButton", background=[("active", "#3498db")])

        style.configure("Exportar.TButton", background="#16a085", foreground="white")
        style.map("Exportar.TButton", background=[("active", "#1abc9c")])

        style.configure("Imprimir.TButton",
                        background="#34495e",
                        foreground="white",
                        font=("Segoe UI", 10, "bold"),
                        padding=6,
                        relief="flat")
        style.map("Imprimir.TButton",
                  background=[("active", "#2c3e50")],
                  foreground=[("active", "white")])

        self.pack(fill="both", expand=True)
        self._crear_componentes()

        # Carga inicial
        self.cargar_brokers()
        self.txtregistro.insert(0, str(self.obtener_nuevo_registro()))
        self.mostrar_tickets_registro()
        self.mostrar_registros_generales()
        self.actualizar_contadores()
        self.actualizar_fecha_hora()

        # 🔹 ESC limpia el formulario desde cualquier lugar
        master.bind("<Escape>", self.limpiar_formulario_completo)

    # ---------- UI ----------
    def _crear_componentes(self):
        ttk.Label(self, text="FABRE SYSTEM - CONTROL DE TICKETS", style="Header.TLabel").pack(fill="x", pady=0)

        # Reloj
        self.lbl_datetime = ttk.Label(self, text="", font=("Segoe UI", 11, "bold"))
        self.lbl_datetime.pack(pady=(6, 5))

        # Semana mostrada
        self.lblSemanas = tk.Label(self, text="", font=("Segoe UI", 11, "bold"),
                                   bg="#333030", fg="gold", padx=10, pady=5)
        self.lblSemanas.pack(pady=(0, 12))
        self.actualizar_semana_actual()

        # Encabezado
        top = ttk.Frame(self)
        top.pack(pady=(0, 8))

        ttk.Label(top, text="Número de Registro:").grid(row=0, column=0, padx=6, pady=6, sticky="e")
        self.txtregistro = ttk.Entry(top, width=10)
        self.txtregistro.grid(row=0, column=1, padx=6, pady=6)
        self.txtregistro.bind("<Return>", lambda e: self.mostrar_tickets_registro())

        ttk.Label(top, text="Broker:").grid(row=0, column=2, padx=6, pady=6, sticky="e")
        self.cbbroker = ttk.Combobox(top, width=20, state="readonly")
        self.cbbroker.grid(row=0, column=3, padx=6, pady=6)

        self.var_desc = tk.BooleanVar(value=False)
        self.chk_desc = ttk.Checkbutton(top, text="Descuento del broker", variable=self.var_desc,
                                        command=self.aplicar_descuento_broker)
        self.chk_desc.grid(row=1, column=3, sticky="w", padx=6, pady=(0, 8))

        ttk.Label(top, text="Truck No:").grid(row=0, column=4, padx=6, pady=6, sticky="e")
        self.cbtruck = ttk.Combobox(top, values=["Truck 101", "Truck 102", "Truck 103"], width=15, state="readonly")
        self.cbtruck.grid(row=0, column=5, padx=6, pady=6)
        self.cbtruck.current(0)

        ttk.Label(top, text="Fecha:").grid(row=0, column=6, padx=6, pady=6, sticky="e")
        self.txtfecha = ttk.Entry(top, width=12)
        self.txtfecha.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.txtfecha.grid(row=0, column=7, padx=6, pady=6)
        ttk.Button(top, text="📅", width=3, command=self.mostrar_calendario).grid(row=0, column=8, padx=(6, 0))

        # Tipo de pago
        box_tipo = ttk.LabelFrame(self, text="Tipo de pago")
        box_tipo.pack(fill="x", padx=10, pady=(0, 6))
        self.tipo = tk.StringVar(value="Horas")
        for i, val in enumerate(["Horas", "Viajes", "Tonelada"]):
            ttk.Radiobutton(box_tipo, text=val, value=val, variable=self.tipo).grid(row=0, column=i, padx=10, pady=6)

        # Detalle Ticket
        detalle = ttk.LabelFrame(self, text="Detalle de ticket")
        detalle.pack(fill="x", padx=10, pady=8)

        ttk.Label(detalle, text="Ticket #:").grid(row=0, column=0, padx=6, pady=6, sticky="e")
        self.txtticket = ttk.Entry(detalle, width=20)
        self.txtticket.grid(row=0, column=1, padx=6, pady=6)

        ttk.Label(detalle, text="Precio:").grid(row=1, column=0, padx=6, pady=6, sticky="e")
        self.txtprecio = ttk.Entry(detalle, width=20)
        self.txtprecio.grid(row=1, column=1, padx=6, pady=6)

        ttk.Label(detalle, text="Cantidad:").grid(row=2, column=0, padx=6, pady=6, sticky="e")
        self.txtcantidad = ttk.Entry(detalle, width=20)
        self.txtcantidad.grid(row=2, column=1, padx=6, pady=6)

        ttk.Label(detalle, text="Descuento %:").grid(row=3, column=0, padx=6, pady=6, sticky="e")
        self.txtdesc = ttk.Entry(detalle, width=20)
        self.txtdesc.insert(0, "0")
        self.txtdesc.grid(row=3, column=1, padx=6, pady=6)

        ttk.Label(detalle, text="Total:").grid(row=4, column=0, padx=6, pady=6, sticky="e")
        self.txttotal = ttk.Entry(detalle, width=20)
        self.txttotal.insert(0, "0.00")
        self.txttotal.grid(row=4, column=1, padx=6, pady=6)

        # Info derecha
        info_frame = ttk.Frame(detalle)
        info_frame.grid(row=0, column=3, rowspan=5, padx=(40, 10), pady=6, sticky="nsw")
        self.lbl_cant_tickets = ttk.Label(info_frame, text="Tickets registrados: 0",
                                          font=("Segoe UI", 10, "bold"), foreground="blue")
        self.lbl_cant_tickets.pack(anchor="w", pady=4)
        self.lbl_monto_total = ttk.Label(info_frame, text="Monto total acumulado: $0.00",
                                         font=("Segoe UI", 10, "bold"), foreground="green")
        self.lbl_monto_total.pack(anchor="w", pady=4)

        # Navegación y ESC
        self.txtticket.bind("<Return>", lambda e: self.txtprecio.focus())
        self.txtprecio.bind("<Return>", lambda e: self.txtcantidad.focus())
        self.txtcantidad.bind("<Return>", lambda e: self.txtdesc.focus())
        self.txtdesc.bind("<Return>", lambda e: self.txttotal.focus())
        self.txttotal.bind("<Return>", lambda e: self.agregar_ticket())
        for w in [self.txtticket, self.txtprecio, self.txtcantidad, self.txtdesc, self.txttotal]:
            w.bind("<Escape>", self.limpiar_formulario_completo)
            w.bind("<KeyRelease>", lambda e: self.calcular_total())

        # Botones
        btns = ttk.Frame(self)
        btns.pack(pady=10)
        ttk.Button(btns, text="Agregar", style="Agregar.TButton",
                   command=self.agregar_ticket).grid(row=0, column=0, padx=8)
        ttk.Button(btns, text="Eliminar", style="Eliminar.TButton",
                   command=self.eliminar_ticket).grid(row=0, column=1, padx=8)
        ttk.Button(btns, text="Procesar", style="Procesar.TButton",
                   command=self.procesar_registro).grid(row=0, column=2, padx=8)
        ttk.Button(btns, text="Nuevo", style="Nuevo.TButton",
                   command=self.nuevo_registro).grid(row=0, column=3, padx=8)
        ttk.Button(btns, text="Exportar", style="Exportar.TButton",
                   command=self.exportar_excel).grid(row=0, column=4, padx=8)
        ttk.Button(btns, text="Ver Registros", style="Nuevo.TButton",
                   command=self.abrir_formulario_registros).grid(row=0, column=5, padx=8)
        ttk.Button(btns, text="🖨️ Imprimir", style="Imprimir.TButton",
                   command=self.imprimir_registro).grid(row=0, column=6, padx=8)
        ttk.Button(btns, text="🗓️ Imprimir Semana Actual", style="Imprimir.TButton",
                   command=self.imprimir_semana_actual).grid(row=0, column=7, padx=8)

        # Tabla + lista lateral
        bottom = ttk.Frame(self)
        bottom.pack(fill="both", expand=True, padx=10, pady=10)

        tabla_box = ttk.LabelFrame(bottom, text="Tickets del registro actual")
        tabla_box.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.grid = ttk.Treeview(
            tabla_box,
            columns=("registro", "ticket", "precio", "cant", "desc", "total"),
            show="headings", height=16
        )
        for col, txt in zip(self.grid["columns"], ["Registro", "Ticket", "Precio", "Cantidad", "Desc %", "Total"]):
            self.grid.heading(col, text=txt)
            self.grid.column(col, width=120, anchor="center")
        self.grid.pack(fill="both", expand=True, padx=6, pady=6)
        self.grid.bind("<<TreeviewSelect>>", self._on_grid_select)

        right = ttk.LabelFrame(bottom, text="Registros Activos (clic para cargar)")
        right.pack(side="right", fill="y", padx=(5, 0), pady=5)

        ttk.Button(right, text="🔄 Actualizar Lista", style="Agregar.TButton",
                   command=self.mostrar_registros_generales).pack(padx=6, pady=(8, 4))

        self.lista = tk.Text(right, height=26, width=40, bg="#f7f7f7", fg="#333333", font=("Segoe UI", 10))
        self.lista.pack(padx=6, pady=6)
        self.lista.bind("<ButtonRelease-1>", self.seleccionar_registro_de_lista)

        self.lbl_total = ttk.Label(self, text="Total general: 0.00",
                                   font=("Segoe UI", 10, "bold"), foreground="gold")
        self.lbl_total.pack(pady=(4, 2))
        self.lbl_registros_generados = ttk.Label(self, text="Registros generados: 0", font=("Segoe UI", 10, "bold"))
        self.lbl_registros_generados.pack()
        self.lbl_registros_pendientes = ttk.Label(self, text="Pendientes por procesar: 0",
                                                  font=("Segoe UI", 10, "bold"))
        self.lbl_registros_pendientes.pack()

    # ---------- UTILIDAD ----------
    def limpiar_formulario_completo(self, event=None):
        """Limpia ticket, precio, cantidad, descuento y total."""
        try:
            for w in [self.txtticket, self.txtprecio, self.txtcantidad, self.txtdesc, self.txttotal]:
                w.delete(0, "end")
            self.txtdesc.insert(0, "0")
            self.txttotal.insert(0, "0.00")
            for item in self.grid.selection():
                self.grid.selection_remove(item)
            self.txtticket.focus()
            self.lbl_cant_tickets.config(foreground="blue", text="Formulario limpiado (ESC)")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo limpiar el formulario:\n{e}")

    def actualizar_fecha_hora(self):
        ahora = datetime.now()
        fecha_hora = ahora.strftime("%A, %d de %B de %Y - %I:%M:%S %p")
        tmap = {
            "Monday":"Lunes","Tuesday":"Martes","Wednesday":"Miércoles","Thursday":"Jueves",
            "Friday":"Viernes","Saturday":"Sábado","Sunday":"Domingo",
            "January":"Enero","February":"Febrero","March":"Marzo","April":"Abril",
            "May":"Mayo","June":"Junio","July":"Julio","August":"Agosto",
            "September":"Septiembre","October":"Octubre","November":"Noviembre","December":"Diciembre"
        }
        for k,v in tmap.items():
            fecha_hora = fecha_hora.replace(k, v)
        self.lbl_datetime.config(text=f"🕒 {fecha_hora}")
        self.after(1000, self.actualizar_fecha_hora)

    def actualizar_semana_actual(self):
        hoy = datetime.now().date()
        lunes = hoy - timedelta(days=hoy.weekday())
        domingo = lunes + timedelta(days=6)
        self.lblSemanas.config(text=f"📅 Semana: {lunes.strftime('%d/%m/%Y')} a {domingo.strftime('%d/%m/%Y')}")

    # ---------- DATOS ----------
    def obtener_nuevo_registro(self):
        conn = conectar_mysql()
        if not conn:
            return 1
        cur = conn.cursor()
        cur.execute("SELECT IFNULL(MAX(registro),0)+1 FROM temporal3")
        reg = cur.fetchone()[0]
        conn.close()
        return reg

    def cargar_brokers(self):
        conn = conectar_mysql()
        if not conn:
            self.cbbroker["values"] = ["Sin conexión"]
            return
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT nombre, descuento FROM t_broker ORDER BY nombre ASC")
        brokers = cur.fetchall()
        if not brokers:
            self.cbbroker["values"] = ["(sin datos)"]
            self.cbbroker.set("(sin datos)")
        else:
            self.broker_desc = {b["nombre"]: b["descuento"] for b in brokers}
            self.cbbroker["values"] = [b["nombre"] for b in brokers]
            self.cbbroker.set(brokers[0]["nombre"])
            self.cbbroker.bind("<<ComboboxSelected>>", self._al_seleccionar_broker)
        conn.close()

    def _al_seleccionar_broker(self, event=None):
        broker = self.cbbroker.get()
        if hasattr(self, "broker_desc") and broker in self.broker_desc:
            self.txtdesc.delete(0, "end")
            self.txtdesc.insert(0, str(self.broker_desc[broker]))
            self.calcular_total()

    def aplicar_descuento_broker(self):
        self.calcular_total()

    def calcular_total(self):
        try:
            precio = float(self.txtprecio.get() or 0)
            cantidad = float(self.txtcantidad.get() or 0)
            desc = float(self.txtdesc.get() or 0)
            if self.var_desc.get():
                desc += 10
            total = precio * cantidad * (1 - desc/100)
            self.txttotal.delete(0, "end")
            self.txttotal.insert(0, f"{total:.2f}")
        except ValueError:
            pass

    # ---------- CRUD ----------
    def agregar_ticket(self):
        try:
            reg = int(self.txtregistro.get())
        except ValueError:
            messagebox.showerror("Error", "Número de registro inválido.")
            return
        ticket = self.txtticket.get().strip()
        if not ticket:
            messagebox.showwarning("Falta dato", "Ingrese el número de Ticket.")
            return
        try:
            precio = float(self.txtprecio.get() or 0)
            cant = float(self.txtcantidad.get() or 0)
            desc = float(self.txtdesc.get() or 0)
            total = float(self.txttotal.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Verifique precio/cantidad/descuento.")
            return

        conn = conectar_mysql()
        if not conn:
            return
        cur = conn.cursor()
        try:
            hoy = datetime.now().date()
            lunes = hoy - timedelta(days=hoy.weekday())
            domingo = lunes + timedelta(days=6)
            cur.execute("""
                INSERT INTO temporal3 (registro, ticket, precio, cant, descuento, total, semana_inicio, semana_fin)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (reg, ticket, precio, cant, desc, total, lunes.strftime("%Y-%m-%d"), domingo.strftime("%Y-%m-%d")))
            conn.commit()
            messagebox.showinfo("Éxito", "Ticket agregado correctamente.")
            self.limpiar_formulario_completo()
            self.mostrar_tickets_registro()
            self.mostrar_registros_generales()
            self.actualizar_contadores()
            self.lblSemanas.config(text=f"📅 Semana: {lunes.strftime('%d/%m/%Y')} a {domingo.strftime('%d/%m/%Y')}")
        except mysql.connector.Error as err:
            messagebox.showerror("Error", f"No se pudo agregar el ticket:\n{err}")
        finally:
            conn.close()

    def mostrar_tickets_registro(self):
        """Muestra todos los tickets del registro seleccionado en la tabla principal."""
        for i in self.grid.get_children():
            self.grid.delete(i)
        try:
            reg = int(self.txtregistro.get())
        except ValueError:
            return

        conn = conectar_mysql()
        if not conn:
            return
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("""
                SELECT id, registro, ticket, precio, cant, descuento, total
                FROM temporal3
                WHERE registro=%s
                ORDER BY id ASC
            """, (reg,))
            rows = cur.fetchall()
            suma = 0.0
            for r in rows:
                self.grid.insert(
                    "", "end", iid=str(r["id"]),
                    values=(r["registro"], r["ticket"],
                            f"{float(r['precio'] or 0):.2f}",
                            f"{float(r['cant'] or 0):.2f}",
                            f"{float(r['descuento'] or 0):.2f}",
                            f"{float(r['total'] or 0):.2f}")
                )
                suma += float(r["total"] or 0)
            self.lbl_cant_tickets.config(text=f"Tickets registrados: {len(rows)}")
            self.lbl_monto_total.config(text=f"Monto total acumulado: ${suma:.2f}")

            # Actualizar label de semana
            cur.execute("""
                SELECT semana_inicio, semana_fin
                FROM temporal3
                WHERE registro=%s
                ORDER BY id ASC LIMIT 1
            """, (reg,))
            w = cur.fetchone()
            if w and w["semana_inicio"] and w["semana_fin"]:
                si, sf = _to_date(w["semana_inicio"]), _to_date(w["semana_fin"])
                if si and sf:
                    self.lblSemanas.config(text=f"📅 Semana: {si.strftime('%d/%m/%Y')} a {sf.strftime('%d/%m/%Y')}")
        except mysql.connector.Error as err:
            messagebox.showerror("Error", f"No se pudieron cargar los tickets:\n{err}")
        finally:
            conn.close()
    def mostrar_registros_generales(self):
        """Lista lateral con registros, cantidad de tickets, semana y estado."""
        self.lista.delete("1.0", "end")
        conn = conectar_mysql()
        if not conn:
            return
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("""
                SELECT 
                    registro,
                    COUNT(*) AS cantidad_tickets,
                    MIN(semana_inicio) AS semana_inicio,
                    MAX(semana_fin) AS semana_fin,
                    CASE 
                        WHEN SUM(CASE WHEN estado='pendiente' THEN 1 ELSE 0 END) > 0 THEN 'pendiente'
                        ELSE 'procesado'
                    END AS estado
                FROM temporal3
                GROUP BY registro
                ORDER BY registro DESC
            """)
            regs = cur.fetchall()
            if not regs:
                self.lista.insert("end", "📭 No hay registros en la base de datos.")
                return
            for r in regs:
                si, sf = _to_date(r["semana_inicio"]), _to_date(r["semana_fin"])
                sem_text = f"Semana: {si.strftime('%d/%m/%Y')} - {sf.strftime('%d/%m/%Y')}" if si and sf else "Semana: (no registrada)"
                estado = (r["estado"] or "").capitalize()
                icono = "⚠️ Pendiente" if estado == "Pendiente" else "✅ Procesado"
                self.lista.insert("end", f"Registro {r['registro']} | {r['cantidad_tickets']} ticket(s) | {icono}\n{sem_text}\n{'-'*45}\n")
        except mysql.connector.Error as err:
            messagebox.showerror("Error", f"No se pudo cargar la lista de registros:\n{err}")
        finally:
            conn.close()

    def _on_grid_select(self, event=None):
        """Click en una fila de la tabla => llenar formulario con ese ticket."""
        try:
            sel = self.grid.selection()
            if not sel:
                return
            iid = sel[0]
            conn = conectar_mysql()
            if not conn:
                return
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT registro, ticket, precio, cant, descuento, total, semana_inicio, semana_fin
                FROM temporal3 
                WHERE id=%s
            """, (iid,))
            row = cur.fetchone()
            conn.close()
            if row:
                self.txtregistro.delete(0, tk.END); self.txtregistro.insert(0, str(row["registro"]))
                self.txtticket.delete(0, tk.END);   self.txtticket.insert(0, str(row["ticket"] or ""))
                self.txtprecio.delete(0, tk.END);   self.txtprecio.insert(0, f"{float(row['precio'] or 0):.2f}")
                self.txtcantidad.delete(0, tk.END); self.txtcantidad.insert(0, f"{float(row['cant'] or 0):.2f}")
                self.txtdesc.delete(0, tk.END);     self.txtdesc.insert(0, f"{float(row['descuento'] or 0):.2f}")
                self.txttotal.delete(0, tk.END);    self.txttotal.insert(0, f"{float(row['total'] or 0):.2f}")
                si, sf = _to_date(row["semana_inicio"]), _to_date(row["semana_fin"])
                if si and sf:
                    self.lblSemanas.config(text=f"📅 Semana: {si.strftime('%d/%m/%Y')} a {sf.strftime('%d/%m/%Y')}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar el ticket:\n{e}")

    def eliminar_ticket(self):
        sel = self.grid.selection()
        if not sel:
            messagebox.showwarning("Eliminar", "Seleccione un ticket en la tabla.")
            return
        iid = sel[0]
        if not messagebox.askyesno("Confirmar", "¿Desea eliminar el ticket seleccionado?"):
            return
        conn = conectar_mysql()
        if not conn:
            return
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM temporal3 WHERE id=%s", (iid,))
            conn.commit()
            messagebox.showinfo("Eliminado", "Ticket eliminado correctamente.")
            self.mostrar_tickets_registro()
            self.mostrar_registros_generales()
            self.actualizar_contadores()
        except mysql.connector.Error as err:
            messagebox.showerror("Error", f"No se pudo eliminar el ticket:\n{err}")
        finally:
            conn.close()

    def procesar_registro(self):
        try:
            reg = int(self.txtregistro.get())
        except ValueError:
            messagebox.showerror("Error", "Registro inválido.")
            return
        if not messagebox.askyesno("Procesar", f"Marcar registro {reg} como procesado?"):
            return
        conn = conectar_mysql()
        if not conn:
            return
        cur = conn.cursor()
        try:
            cur.execute("UPDATE temporal3 SET estado='procesado' WHERE registro=%s", (reg,))
            conn.commit()
            messagebox.showinfo("Procesado", f"Registro {reg} marcado como procesado.")
            self.mostrar_registros_generales()
            self.actualizar_contadores()
        except mysql.connector.Error as err:
            messagebox.showerror("Error", f"No se pudo procesar el registro:\n{err}")
        finally:
            conn.close()

    def nuevo_registro(self):
        nuevo = self.obtener_nuevo_registro()
        self.txtregistro.delete(0, tk.END)
        self.txtregistro.insert(0, str(nuevo))
        for iid in self.grid.get_children():
            self.grid.delete(iid)
        self.limpiar_formulario_completo()
        self.lbl_cant_tickets.config(text="Tickets registrados: 0")
        self.lbl_monto_total.config(text="Monto total acumulado: $0.00")
        self.actualizar_contadores()
        self.actualizar_semana_actual()

    def exportar_excel(self):
        try:
            reg = int(self.txtregistro.get())
        except ValueError:
            messagebox.showerror("Error", "Registro inválido para exportar.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")],
                                            title="Guardar como")
        if not path:
            return
        conn = conectar_mysql()
        if not conn:
            return
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT ticket, precio, cant, descuento, total
                FROM temporal3
                WHERE registro=%s
                ORDER BY id ASC
            """, (reg,))
            rows = cur.fetchall()
            with open(path, "w", newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Ticket","Precio","Cantidad","Descuento","Total"])
                for r in rows:
                    writer.writerow([r[0], float(r[1] or 0), float(r[2] or 0), float(r[3] or 0), float(r[4] or 0)])
            messagebox.showinfo("Exportado", f"Registro {reg} exportado a {path}")
        except mysql.connector.Error as err:
            messagebox.showerror("Error", f"No se pudo exportar:\n{err}")
        finally:
            conn.close()

    def actualizar_contadores(self):
        conn = conectar_mysql()
        if not conn:
            return
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(DISTINCT registro) FROM temporal3")
            total_regs = cur.fetchone()[0] or 0
            cur.execute("SELECT COUNT(*) FROM temporal3 WHERE estado='pendiente'")
            pendientes = cur.fetchone()[0] or 0
            cur.execute("SELECT IFNULL(SUM(total),0) FROM temporal3")
            suma = float(cur.fetchone()[0] or 0.0)
            self.lbl_total.config(text=f"Total general: ${suma:.2f}")
            self.lbl_registros_generados.config(text=f"Registros generados: {total_regs}")
            self.lbl_registros_pendientes.config(text=f"Pendientes por procesar: {pendientes}")
        except mysql.connector.Error:
            pass
        finally:
            conn.close()

    # ---------- LISTA LATERAL: clic carga tickets + llena formulario ----------
    def seleccionar_registro_de_lista(self, event=None):
        """Carga todos los tickets del registro seleccionado y llena el formulario con el primero."""
        try:
            idx = self.lista.index(f"@{event.x},{event.y}")
            line_no = int(idx.split(".")[0])
            line = self.lista.get(f"{line_no}.0", f"{line_no}.end").strip()
            m = re.search(r"Registro\s+(\d+)", line)
            if not m:
                return
            reg = int(m.group(1))

            # Mostrar TODOS los tickets en la tabla
            self.txtregistro.delete(0, tk.END)
            self.txtregistro.insert(0, str(reg))
            self.mostrar_tickets_registro()

            # Traer el primer ticket para llenar el formulario (opcional)
            conn = conectar_mysql()
            if not conn:
                return
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT ticket, precio, cant, descuento, total, semana_inicio, semana_fin
                FROM temporal3
                WHERE registro=%s
                ORDER BY id ASC
            """, (reg,))
            rows = cur.fetchall()
            conn.close()

            if rows:
                first = rows[0]
                self.txtticket.delete(0, tk.END); self.txtticket.insert(0, str(first["ticket"] or ""))
                self.txtprecio.delete(0, tk.END); self.txtprecio.insert(0, f"{float(first['precio'] or 0):.2f}")
                self.txtcantidad.delete(0, tk.END); self.txtcantidad.insert(0, f"{float(first['cant'] or 0):.2f}")
                self.txtdesc.delete(0, tk.END); self.txtdesc.insert(0, f"{float(first['descuento'] or 0):.2f}")
                self.txttotal.delete(0, tk.END); self.txttotal.insert(0, f"{float(first['total'] or 0):.2f}")

                si, sf = _to_date(first["semana_inicio"]), _to_date(first["semana_fin"])
                if si and sf:
                    self.lblSemanas.config(text=f"📅 Semana: {si.strftime('%d/%m/%Y')} a {sf.strftime('%d/%m/%Y')}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar el registro:\n{e}")

    # ---------- FORMULARIO SELECCIÓN DE REGISTROS ----------
    def abrir_formulario_registros(self):
        """Ventana con registros agrupados; al seleccionar, carga TODOS los tickets en la tabla principal."""
        conn = conectar_mysql()
        if not conn:
            messagebox.showerror("Error", "No se pudo conectar a la base de datos.")
            return

        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT 
                registro,
                MIN(semana_inicio) AS semana_inicio,
                MAX(semana_fin) AS semana_fin,
                SUM(total) AS total_acumulado,
                CASE 
                    WHEN SUM(CASE WHEN estado='pendiente' THEN 1 ELSE 0 END) > 0 THEN 'pendiente'
                    ELSE 'procesado'
                END AS estado
            FROM temporal3
            GROUP BY registro
            ORDER BY registro DESC
        """)
        registros = cur.fetchall()
        conn.close()

        if not registros:
            messagebox.showinfo("Sin datos", "No hay registros disponibles en la tabla temporal3.")
            return

        # Ventana emergente centrada
        top = tk.Toplevel(self)
        top.title("📋 Registros Agrupados por Número")
        width, height = 720, 420
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        x = int((sw - width) / 2)
        y = int((sh - height) / 2)
        top.geometry(f"{width}x{height}+{x}+{y}")
        top.resizable(False, False)
        top.configure(bg="#e4e2dd")
        top.grab_set()

        ttk.Label(top, text="Seleccione un registro:", font=("Segoe UI", 11, "bold")).pack(pady=10)

        frame_lista = ttk.Frame(top)
        frame_lista.pack(fill="both", expand=True, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(frame_lista)
        scrollbar.pack(side="right", fill="y")

        lista = tk.Listbox(frame_lista, height=15, width=100, font=("Segoe UI", 10))
        lista.pack(side="left", fill="both", expand=True)
        lista.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=lista.yview)

        # Llenar lista
        for r in registros:
            si = _to_date(r["semana_inicio"])
            sf = _to_date(r["semana_fin"])
            total = float(r["total_acumulado"] or 0)
            estado = (r["estado"] or "pendiente").capitalize()
            if si and sf:
                texto = f"Registro {r['registro']} | Semana: {si.strftime('%d/%m/%Y')} - {sf.strftime('%d/%m/%Y')} | Total: ${total:.2f} | Estado: {estado}"
            else:
                texto = f"Registro {r['registro']} | Semana: (no registrada) | Total: ${total:.2f} | Estado: {estado}"
            lista.insert("end", texto)

        def cargar_registro(event=None):
            sel = lista.curselection()
            if not sel:
                return
            texto = lista.get(sel[0])
            m = re.search(r"Registro\s+(\d+)", texto)
            if not m:
                return
            registro = int(m.group(1))

            # Cargar TODOS los tickets del registro en la tabla principal
            self.txtregistro.delete(0, tk.END)
            self.txtregistro.insert(0, str(registro))
            self.mostrar_tickets_registro()

            # Llenar formulario con el primero (y mostrar semana)
            conn2 = conectar_mysql()
            if conn2:
                cur2 = conn2.cursor(dictionary=True)
                cur2.execute("""
                    SELECT ticket, precio, cant, descuento, total, semana_inicio, semana_fin
                    FROM temporal3
                    WHERE registro=%s
                    ORDER BY id ASC
                """, (registro,))
                rows = cur2.fetchall()
                conn2.close()
                if rows:
                    first = rows[0]
                    self.txtticket.delete(0, tk.END); self.txtticket.insert(0, str(first["ticket"] or ""))
                    self.txtprecio.delete(0, tk.END); self.txtprecio.insert(0, f"{float(first['precio'] or 0):.2f}")
                    self.txtcantidad.delete(0, tk.END); self.txtcantidad.insert(0, f"{float(first['cant'] or 0):.2f}")
                    self.txtdesc.delete(0, tk.END); self.txtdesc.insert(0, f"{float(first['descuento'] or 0):.2f}")
                    self.txttotal.delete(0, tk.END); self.txttotal.insert(0, f"{float(first['total'] or 0):.2f}")
                    si, sf = _to_date(first["semana_inicio"]), _to_date(first["semana_fin"])
                    if si and sf:
                        self.lblSemanas.config(text=f"📅 Semana: {si.strftime('%d/%m/%Y')} a {sf.strftime('%d/%m/%Y')}")
            top.destroy()

        lista.bind("<Double-1>", cargar_registro)
        ttk.Button(top, text="Cerrar", command=top.destroy).pack(pady=8)

    # ---------- Fecha ----------
    def mostrar_calendario(self):
        top = tk.Toplevel(self)
        top.title("Seleccionar fecha")
        cal = Calendar(
            top, selectmode="day",
            year=datetime.now().year, month=datetime.now().month, day=datetime.now().day,
            date_pattern="yyyy-mm-dd"
        )
        cal.pack(padx=10, pady=10)

        def _sel():
            self.txtfecha.delete(0, tk.END)
            self.txtfecha.insert(0, cal.get_date())
            top.destroy()

        ttk.Button(top, text="Seleccionar", command=_sel).pack(pady=(0, 10))

    # ---------- IMPRESIÓN: PDF por registro ----------
    def imprimir_registro(self):
        """Genera un PDF imprimible con los tickets del registro actual."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
        except Exception:
            messagebox.showerror("Falta librería", "Instala reportlab con:\n\npip install reportlab")
            return

        try:
            reg = int(self.txtregistro.get())
        except ValueError:
            messagebox.showerror("Error", "Registro inválido para imprimir.")
            return

        conn = conectar_mysql()
        if not conn:
            return
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT ticket, precio, cant, descuento, total, semana_inicio, semana_fin
            FROM temporal3
            WHERE registro=%s
            ORDER BY id ASC
        """, (reg,))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            messagebox.showinfo("Sin datos", "No hay tickets para este registro.")
            return

        semana_inicio = _to_date(rows[0]["semana_inicio"])
        semana_fin = _to_date(rows[0]["semana_fin"])
        broker = self.cbbroker.get() or "(Sin broker)"
        tipo_pago = self.tipo.get() or "(Sin tipo)"
        fecha_actual = datetime.now().strftime("%d/%m/%Y %I:%M %p")

        pdf_name = f"Registro_{reg}.pdf"
        doc = SimpleDocTemplate(pdf_name, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        title_style = styles["Title"]
        title_style.textColor = colors.HexColor("#2c3e50")
        elements.append(Paragraph("<b>FABRE SYSTEM - CONTROL DE TICKETS</b>", title_style))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"<b>Registro:</b> {reg}", styles["Heading2"]))
        if semana_inicio and semana_fin:
            elements.append(Paragraph(f"<b>Semana:</b> {semana_inicio.strftime('%d/%m/%Y')} - {semana_fin.strftime('%d/%m/%Y')}", styles["Normal"]))
        elements.append(Paragraph(f"<b>Broker:</b> {broker}", styles["Normal"]))
        elements.append(Paragraph(f"<b>Tipo de Pago:</b> {tipo_pago}", styles["Normal"]))
        elements.append(Paragraph(f"<b>Fecha de Impresión:</b> {fecha_actual}", styles["Normal"]))
        elements.append(Spacer(1, 12))

        data = [["Ticket", "Precio", "Cantidad", "Descuento (%)", "Total ($)"]]
        total_general = 0
        for r in rows:
            data.append([
                str(r["ticket"]),
                f"{float(r['precio'] or 0):.2f}",
                f"{float(r['cant'] or 0):.2f}",
                f"{float(r['descuento'] or 0):.2f}",
                f"{float(r['total'] or 0):.2f}"
            ])
            total_general += float(r["total"] or 0)
        data.append(["", "", "", "TOTAL", f"{total_general:.2f}"])

        table = Table(data, colWidths=[100, 80, 80, 100, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 15))
        elements.append(Paragraph("<b>Generado automáticamente por Fabre System</b>", styles["Italic"]))
        doc.build(elements)

        try:
            os.startfile(pdf_name)  # Windows
        except Exception:
            pass
        messagebox.showinfo("Impresión lista", f"Se generó el archivo PDF:\n{pdf_name}")

    # ---------- IMPRESIÓN: PDF semanal (procesados de semana actual) ----------
    def imprimir_semana_actual(self):
        """Genera un PDF con todos los registros procesados de la semana actual."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
        except Exception:
            messagebox.showerror("Falta librería", "Instala reportlab con:\n\npip install reportlab")
            return

        hoy = datetime.now().date()
        lunes = hoy - timedelta(days=hoy.weekday())
        domingo = lunes + timedelta(days=6)
        semana_inicio = lunes.strftime("%Y-%m-%d")
        semana_fin = domingo.strftime("%Y-%m-%d")

        conn = conectar_mysql()
        if not conn:
            return
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT 
                registro, ticket, precio, cant, descuento, total, 
                semana_inicio, semana_fin, estado
            FROM temporal3
            WHERE estado='procesado' 
              AND semana_inicio=%s 
              AND semana_fin=%s
            ORDER BY registro, id ASC
        """, (semana_inicio, semana_fin))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            messagebox.showinfo("Sin datos", "No hay registros procesados en la semana actual.")
            return

        pdf_name = f"Reporte_Semana_{lunes.strftime('%Y%m%d')}.pdf"
        doc = SimpleDocTemplate(pdf_name, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        title_style = styles["Title"]; title_style.textColor = colors.HexColor("#2c3e50")

        elements.append(Paragraph("<b>FABRE SYSTEM - REPORTE SEMANAL</b>", title_style))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"<b>Semana:</b> {lunes.strftime('%d/%m/%Y')} - {domingo.strftime('%d/%m/%Y')}", styles["Heading2"]))
        elements.append(Paragraph(f"<b>Fecha de Generación:</b> {datetime.now().strftime('%d/%m/%Y %I:%M %p')}", styles["Normal"]))
        elements.append(Spacer(1, 12))

        total_general = 0
        registro_actual = None
        data = [["Ticket", "Precio", "Cantidad", "Descuento (%)", "Total ($)"]]
        subtotal = 0

        broker_actual = self.cbbroker.get() or "(Sin broker)"
        tipo_pago_actual = self.tipo.get() or "(Sin tipo)"

        for r in rows:
            if registro_actual != r["registro"]:
                if registro_actual is not None:
                    data.append(["", "", "", "Subtotal", f"{subtotal:.2f}"])
                    table = Table(data, colWidths=[100, 80, 80, 100, 100])
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
                    ]))
                    elements.append(table)
                    elements.append(Spacer(1, 12))
                    elements.append(PageBreak())
                registro_actual = r["registro"]
                subtotal = 0
                elements.append(Paragraph(f"<b>Registro #{registro_actual}</b>", styles["Heading2"]))
                if _to_date(r["semana_inicio"]) and _to_date(r["semana_fin"]):
                    elements.append(Paragraph(
                        f"<b>Semana:</b> {_to_date(r['semana_inicio']).strftime('%d/%m/%Y')} - {_to_date(r['semana_fin']).strftime('%d/%m/%Y')}",
                        styles["Normal"]))
                elements.append(Paragraph(f"<b>Broker:</b> {broker_actual}", styles["Normal"]))
                elements.append(Paragraph(f"<b>Tipo de Pago:</b> {tipo_pago_actual}", styles["Normal"]))
                elements.append(Spacer(1, 8))
                data = [["Ticket", "Precio", "Cantidad", "Descuento (%)", "Total ($)"]]

            data.append([
                str(r["ticket"]),
                f"{float(r['precio'] or 0):.2f}",
                f"{float(r['cant'] or 0):.2f}",
                f"{float(r['descuento'] or 0):.2f}",
                f"{float(r['total'] or 0):.2f}"
            ])
            subtotal += float(r["total"] or 0)
            total_general += float(r["total"] or 0)

        # Último bloque
        data.append(["", "", "", "Subtotal", f"{subtotal:.2f}"])
        table = Table(data, colWidths=[100, 80, 80, 100, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"<b>Total General Semana:</b> ${total_general:.2f}", styles["Heading2"]))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("<b>Generado automáticamente por Fabre System</b>", styles["Italic"]))
        doc.build(elements)

        try:
            os.startfile(pdf_name)
        except Exception:
            pass
        messagebox.showinfo("Reporte generado", f"Se generó el reporte semanal:\n{pdf_name}")


# =========================
#  MAIN
# =========================
if __name__ == "__main__":
    root = tk.Tk()
    app = TicketForm(root)
    root.mainloop()

