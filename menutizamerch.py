import sys
import os
import json
import math
import hashlib
import base64
from datetime import datetime, date
from decimal import Decimal

# ==============================================================================
# 🎯 [ZONA DE CONEXIÓN 0]: PARCHE GLOBAL JSON PARA FECHAS Y DECIMALES (POSTGRESQL)
# Evita al 100% el error "Object of type date / Decimal is not JSON serializable"
# cuando ConexionPostgres convierte las filas de un SELECT a formato JSON.
# ==============================================================================
_original_json_dumps = json.dumps

def _serializador_sql_seguro(obj):
    if isinstance(obj, (datetime, date)):
        return obj.strftime("%Y-%m-%d %H:%M:%S") if isinstance(obj, datetime) else obj.strftime("%Y-%m-%d")
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)

def _json_dumps_parcheado(obj, *args, **kwargs):
    kwargs["default"] = _serializador_sql_seguro
    return _original_json_dumps(obj, *args, **kwargs)

json.dumps = _json_dumps_parcheado


from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QFrame, QMessageBox, QHeaderView, QStackedWidget,
    QComboBox, QDialog, QFormLayout, QScrollArea, QProgressBar,
    QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt6.QtGui import (
    QAction, QColor, QFont, QPainter, QLinearGradient, QRadialGradient,
    QPen, QBrush, QPainterPath, QPolygonF
)
from PyQt6.QtCore import Qt, QRectF, QPointF


# ==============================================================================
# 🎯 [ZONA DE CONEXIÓN 1]: IMPORTACIÓN DE TUS CLASES DE CONEXIÓN EXISTENTES
# Reutilizamos tus archivos ConexionPostgres y ConecionSqlServer tal como pide el profesor.
# ==============================================================================
try:
    import conexionpostgres as mod_pg
    mod_pg.json.dumps = _json_dumps_parcheado
    ConexionPostgres = mod_pg.ConexionPostgres
except ImportError:
    import conexion_posgress as mod_pg
    mod_pg.json.dumps = _json_dumps_parcheado
    ConexionPostgres = mod_pg.ConexionPostgres

try:
    import conexionsqlserver as mod_sql
    mod_sql.json.dumps = _json_dumps_parcheado
    ConexionSqlServer = getattr(mod_sql, "ConexionSqlServer", getattr(mod_sql, "ConecionSqlServer", None))
except ImportError:
    import conexion_sqlserver as mod_sql
    mod_sql.json.dumps = _json_dumps_parcheado
    ConexionSqlServer = getattr(mod_sql, "ConexionSqlServer", getattr(mod_sql, "ConecionSqlServer", None))

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False


# ==============================================================================
# 🎯 [ZONA DE CONEXIÓN Y CONSULTAS 2]: GESTOR DE BASE DE DATOS (DOMINAR AL 100%)
# Centraliza todas las operaciones sobre ConexionPostgres y ConecionSqlServer.
# ==============================================================================
class GestorConsultasTizamerch:
    """
    Administra la conexión y todas las consultas SQL hacia PostgreSQL y SQL Server
    utilizando los métodos de tus clases: crear_conexion(), ejecutar_consulta() y cerrar_conexion().
    """

    HASH_INICIAL_123456 = "$2a$10$RJSsnw1WECu8JGNj.5k8/eYmtGS8ojqFKT88vuneEuYHQ9Iyf23wm"

    def __init__(self):
        self.motor = "postgres"  # 'postgres' o 'sqlserver'
        self.conexion = None     # Instancia activa de tu clase de conexión

    def conectar(self, motor: str) -> bool:
        """
        PASO 1 DE CONEXIÓN: Cierra cualquier conexión previa, instancia tu clase
        según el motor seleccionado y llama a crear_conexion().
        """
        self.cerrar()
        self.motor = motor

        if self.motor == "postgres":
            self.conexion = ConexionPostgres()
        else:
            self.conexion = ConexionSqlServer()

        # Aseguramos que el módulo json interno de la instancia use nuestro serializador de fechas
        objeto_cnx = self.conexion.crear_conexion()
        return objeto_cnx is not None

    def cerrar(self):
        """
        PASO 2 DE CONEXIÓN: Cierra limpiamente el cursor y la conexión activa.
        """
        if self.conexion is not None:
            try:
                self.conexion.cerrar_conexion()
            except Exception:
                pass
            self.conexion = None

    def marcador(self) -> str:
        """
        DIFERENCIA DE PARÁMETROS ENTRE MOTORES:
        - PostgreSQL (psycopg2) usa '%s'
        - SQL Server (mssql-python) usa '?'
        """
        return "%s" if self.motor == "postgres" else "?"

    def valor_booleano(self, activo: bool):
        """
        DIFERENCIA DE TIPO BOOLEANO ENTRE SCRIPTS:
        - PostgreSQL (BOOLEAN) -> True / False
        - SQL Server (BIT)     -> 1 / 0
        """
        return bool(activo) if self.motor == "postgres" else (1 if activo else 0)

    def _obtener_cursor_nativo(self):
        if self.conexion is None:
            return None, None
        cnx = getattr(self.conexion, "cnx", None) or getattr(self.conexion, "CNX", None)
        cur = getattr(self.conexion, "cursor", None) or getattr(self.conexion, "CURSOR", None)
        return cnx, cur

    def _limpiar_transaccion(self):
        """ Ejecuta rollback() si una consulta previa falló para desbloquear PostgreSQL. """
        cnx, _ = self._obtener_cursor_nativo()
        if cnx:
            try:
                cnx.rollback()
            except Exception:
                pass

    # --------------------------------------------------------------------------
    # 🎯 [EJECUCIÓN DE SELECT]: Lee registros y garantiza que las fechas (date)
    # y decimales (Decimal) se conviertan siempre sin errores.
    # --------------------------------------------------------------------------
    def ejecutar_select(self, sql: str, parametros=None):
        """
        Ejecuta una sentencia SELECT a través de ejecutar_consulta().
        Si tu clase ConexionPostgres llegara a lanzar 'Object of type date is not JSON serializable',
        recupera las filas directamente del cursor convirtiendo fechas y decimales a texto.
        """
        if self.conexion is None:
            return False, [], "No hay conexión activa con la base de datos."

        sql_limpio = " ".join(sql.strip().split())
        respuesta_raw = self.conexion.ejecutar_consulta(sql_limpio, parametros)
        datos = json.loads(respuesta_raw) if isinstance(respuesta_raw, str) else respuesta_raw

        if datos.get("estado") is True:
            return True, datos.get("registros", []), "OK"

        # Respaldo directo con el cursor si falló por serialización JSON de fechas (date)
        err_texto = str(datos.get("error") or datos.get("mensaje") or "")
        if "not JSON serializable" in err_texto:
            try:
                cnx, cur = self._obtener_cursor_nativo()
                if cur is not None:
                    if parametros:
                        cur.execute(sql_limpio, parametros)
                    else:
                        cur.execute(sql_limpio)
                    columnas = [col[0] for col in cur.description]
                    filas = cur.fetchall()
                    resultado = []
                    for fila in filas:
                        dic = {}
                        for i, val in enumerate(fila):
                            dic[columnas[i]] = _serializador_sql_seguro(val) if isinstance(val, (date, datetime, Decimal)) else val
                        resultado.append(dic)
                    return True, resultado, "OK"
            except Exception as e_cur:
                self._limpiar_transaccion()
                return False, [], str(e_cur)

        self._limpiar_transaccion()
        return False, [], err_texto

    # --------------------------------------------------------------------------
    # 🎯 [EJECUCIÓN DE INSERT / UPDATE / DELETE]: Con confirmación commit()
    # --------------------------------------------------------------------------
    def ejecutar_crud(self, sql: str, parametros=None):
        if self.conexion is None:
            return False, "No hay conexión activa con la base de datos."

        sql_limpio = " ".join(sql.strip().split())
        respuesta_raw = self.conexion.ejecutar_consulta(sql_limpio, parametros)
        datos = json.loads(respuesta_raw) if isinstance(respuesta_raw, str) else respuesta_raw

        if datos.get("estado") is True:
            filas = datos.get("filas_afectadas", 1)
            return True, f"{datos.get('mensaje', 'Operación exitosa')} ({filas} fila afectada)"
        else:
            self._limpiar_transaccion()
            err = datos.get("error") or datos.get("mensaje") or "Error en operación CRUD"
            return False, str(err)

    # --------------------------------------------------------------------------
    # 🎯 [AUTENTICACIÓN LOGIN]: Consulta parametrizada en la tabla Usuarios
    # --------------------------------------------------------------------------
    @classmethod
    def asegurar_hash_bcrypt(cls, contrasena_raw: str) -> str:
        texto = contrasena_raw.strip()
        if texto.startswith("$2a$") or texto.startswith("$2b$") or texto.startswith("$2y$"):
            return texto
        if texto == "123456":
            return cls.HASH_INICIAL_123456
        if HAS_BCRYPT:
            return bcrypt.hashpw(texto.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")
        digest = base64.b64encode(hashlib.sha256(texto.encode("utf-8")).digest()).decode("ascii")
        limpio = digest.replace("+", ".").replace("/", "O").replace("=", "")
        return f"$2a$10${limpio[:53].ljust(53, 'A')}"

    @classmethod
    def verificar_contrasena(cls, password_ingresada: str, hash_almacenado: str) -> bool:
        pwd = password_ingresada.strip()
        guardado = (hash_almacenado or "").strip()
        if pwd == "123456" and guardado == cls.HASH_INICIAL_123456:
            return True
        if HAS_BCRYPT and (guardado.startswith("$2a$") or guardado.startswith("$2b$") or guardado.startswith("$2y$")):
            try:
                if bcrypt.checkpw(pwd.encode("utf-8"), guardado.encode("utf-8")):
                    return True
            except Exception:
                pass
        return pwd == guardado or cls.asegurar_hash_bcrypt(pwd) == guardado

    def autenticar_usuario(self, usuario_login: str, password_ingresada: str):
        """
        Consulta la tabla Usuarios filtrando con WHERE Usuario = %s / ?
        y verifica que la cuenta esté Activa y la contraseña coincida con el hash bcrypt.
        """
        ph = self.marcador()
        sql = (
            f"SELECT id_usuario, nombre, usuario, contrasena, estado FROM usuarios WHERE usuario = {ph}"
            if self.motor == "postgres" else
            f"SELECT Id_Usuario, Nombre, Usuario, Contrasena, Estado FROM Usuarios WHERE Usuario = {ph}"
        )
        exito, registros, err = self.ejecutar_select(sql, (usuario_login.strip(),))
        if not exito:
            return False, {}, f"Error de base de datos: {err}"
        if not registros:
            return False, {}, f"El usuario '{usuario_login}' no existe."

        fila = {str(k).lower(): v for k, v in registros[0].items()}
        if str(fila.get("estado", "True")).upper() in ("FALSE", "0"):
            return False, {}, "Esta cuenta de usuario se encuentra dada de baja (Inactiva)."

        if not self.verificar_contrasena(password_ingresada, str(fila.get("contrasena", ""))):
            return False, {}, "Contraseña incorrecta."

        return True, {
            "id_usuario": fila.get("id_usuario", 1),
            "nombre": fila.get("nombre", usuario_login),
            "usuario": fila.get("usuario", usuario_login),
        }, "Sesión iniciada correctamente."

    # --------------------------------------------------------------------------
    # 🎯 [LAS 4 OPERACIONES CRUD DE CATÁLOGOS MAESTROS]:
    # 1. Consultar, 2. Insertar, 3. Actualizar, 4. Eliminar (o Baja Lógica)
    # --------------------------------------------------------------------------
    def consultar_catalogo(self, tabla: str, pk: str):
        sql = f"SELECT * FROM {tabla} ORDER BY {pk}"
        return self.ejecutar_select(sql)

    def insertar_catalogo(self, tabla: str, columnas: list, valores: tuple):
        ph = self.marcador()
        marcadores = ", ".join([ph] * len(columnas))
        sql = f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({marcadores})"
        return self.ejecutar_crud(sql, valores)

    def actualizar_catalogo(self, tabla: str, pk: str, id_val: int, columnas: list, valores: tuple):
        ph = self.marcador()
        asignaciones = ", ".join([f"{c} = {ph}" for c in columnas])
        sql = f"UPDATE {tabla} SET {asignaciones} WHERE {pk} = {ph}"
        return self.ejecutar_crud(sql, tuple(list(valores) + [id_val]))

    def eliminar_o_baja_catalogo(self, tabla: str, pk: str, id_val: int, tiene_estado: bool = True):
        """
        Intenta el DELETE físico; si tiene historial vinculado (llave foránea),
        aplica Baja Lógica cambiando Estado = FALSE / 0.
        """
        ph = self.marcador()
        exito, msg = self.ejecutar_crud(f"DELETE FROM {tabla} WHERE {pk} = {ph}", (id_val,))
        if exito:
            return True, msg
        if tiene_estado:
            inactivo = self.valor_booleano(False)
            ok_baja, _ = self.ejecutar_crud(f"UPDATE {tabla} SET Estado = {ph} WHERE {pk} = {ph}", (inactivo, id_val))
            if ok_baja:
                return True, f"Registro #{id_val} con historial: se aplicó Baja Lógica (Estado = Inactivo)."
        return False, msg


# ==============================================================================
# 🎯 [ZONA DE BASE DE DATOS 3]: CONFIGURACIÓN DE LAS TABLAS MAESTRAS (CATÁLOGOS)
# ==============================================================================
CATALOGOS_MAESTROS = {
    "productos": {
        "pestana": "Productos",
        "titulo": "Catálogo Maestro de Productos",
        "tabla_pg": "productos", "tabla_sql": "Productos",
        "pk_pg": "id_producto", "pk_sql": "Id_Producto",
        "tiene_estado": True,
        "campos": [
            ("nombre", "Nombre", "Nombre del producto", "str"),
            ("descripcion", "Descripcion", "Descripción", "str_null"),
            ("precio", "Precio", "Precio unitario ($)", "float"),
            ("stock_actual", "Stock_Actual", "Stock actual", "int"),
            ("stock_minimo", "Stock_Minimo", "Stock mínimo", "int"),
            ("id_categoria", "Id_Categoria", "ID Categoría (ej. 1)", "int"),
            ("id_marca", "Id_Marca", "ID Marca (ej. 1)", "int"),
            ("id_ubicacion", "Id_Ubicacion", "ID Ubicación (ej. 1)", "int"),
            ("imagen_url", "Imagen_URL", "URL/Ruta de Imagen (opcional)", "str_null"),
            ("estado", "Estado", "Estado", "bool"),
        ]
    },
    "categorias": {
        "pestana": "Categorías",
        "titulo": "Catálogo de Categorías",
        "tabla_pg": "categorias", "tabla_sql": "Categorias",
        "pk_pg": "id_categoria", "pk_sql": "Id_Categoria",
        "tiene_estado": True,
        "campos": [
            ("nombre", "Nombre", "Nombre de la categoría", "str"),
            ("descripcion", "Descripcion", "Descripción", "str_null"),
            ("estado", "Estado", "Estado", "bool"),
        ]
    },
    "marcas": {
        "pestana": "Marcas",
        "titulo": "Catálogo de Marcas",
        "tabla_pg": "marcas", "tabla_sql": "Marcas",
        "pk_pg": "id_marca", "pk_sql": "Id_Marca",
        "tiene_estado": True,
        "campos": [
            ("nombre", "Nombre", "Nombre de la marca", "str"),
            ("descripcion", "Descripcion", "Descripción", "str_null"),
            ("estado", "Estado", "Estado", "bool"),
        ]
    },
    "ubicaciones": {
        "pestana": "Ubicaciones",
        "titulo": "Catálogo de Ubicaciones",
        "tabla_pg": "ubicaciones", "tabla_sql": "Ubicaciones",
        "pk_pg": "id_ubicacion", "pk_sql": "Id_Ubicacion",
        "tiene_estado": True,
        "campos": [
            ("nombre", "Nombre", "Nombre de ubicación", "str"),
            ("descripcion", "Descripcion", "Descripción", "str_null"),
            ("estado", "Estado", "Estado", "bool"),
        ]
    },
    "proveedores": {
        "pestana": "Proveedores",
        "titulo": "Catálogo de Proveedores",
        "tabla_pg": "proveedores", "tabla_sql": "Proveedores",
        "pk_pg": "id_proveedor", "pk_sql": "Id_Proveedor",
        "tiene_estado": True,
        "campos": [
            ("nombre", "Nombre", "Nombre del proveedor", "str"),
            ("telefono", "Telefono", "Teléfono", "str_null"),
            ("correo", "Correo", "Correo electrónico", "str_null"),
            ("estado", "Estado", "Estado", "bool"),
        ]
    },
    "usuarios": {
        "pestana": "Usuarios",
        "titulo": "Catálogo de Usuarios",
        "tabla_pg": "usuarios", "tabla_sql": "Usuarios",
        "pk_pg": "id_usuario", "pk_sql": "Id_Usuario",
        "tiene_estado": True,
        "campos": [
            ("nombre", "Nombre", "Nombre completo", "str"),
            ("usuario", "Usuario", "Usuario (Login)", "str"),
            ("contrasena", "Contrasena", "Contraseña (hash bcrypt)", "bcrypt"),
            ("estado", "Estado", "Estado", "bool"),
        ]
    },
    "motivossalida": {
        "pestana": "Motivos de Salida",
        "titulo": "Catálogo de Motivos de Salida",
        "tabla_pg": "motivossalida", "tabla_sql": "MotivosSalida",
        "pk_pg": "id_motivo", "pk_sql": "Id_Motivo",
        "tiene_estado": False,
        "campos": [
            ("nombre", "Nombre", "Nombre del motivo", "str"),
            ("descripcion", "Descripcion", "Descripción", "str_null"),
        ]
    },
}


# ==============================================================================
# 🎨 COMPONENTES VECTORIALES HD (0% PIXELEADOS, IDÉNTICOS A TU APP WEB)
# ==============================================================================
class LogoCircularVectorWidget(QWidget):
    """
    Dibuja el logotipo circular de TIZAMERCH con vectores matemáticos (QPainter):
    Aro exterior rosa neón, 4 arcos interiores cian y texto TIZA / MERCH.
    Resolución infinita sin pixeleo.
    """
    def __init__(self, diametro=105, parent=None):
        super().__init__(parent)
        self.setFixedSize(diametro, diametro)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0

        # Resplandor radial suave de fondo
        grad = QRadialGradient(cx, cy, w * 0.5)
        grad.setColorAt(0.0, QColor(45, 12, 65, 220))
        grad.setColorAt(0.7, QColor(255, 0, 128, 45))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(0, 0, w, h))

        # Aro exterior Rosa Neón (#ff007f) + halo
        r_ext = w * 0.42
        rect_ext = QRectF(cx - r_ext, cy - r_ext, r_ext * 2, r_ext * 2)
        p.setPen(QPen(QColor(255, 0, 128, 70), 6.0))
        p.drawEllipse(rect_ext)
        p.setPen(QPen(QColor("#ff1a8c"), 2.4))
        p.drawEllipse(rect_ext)

        # 4 Arcos interiores Cian Neón (#00f0ff)
        r_int = w * 0.35
        rect_int = QRectF(cx - r_int, cy - r_int, r_int * 2, r_int * 2)
        pen_cyan_glow = QPen(QColor(0, 240, 255, 65), 5.0)
        pen_cyan = QPen(QColor("#00f0ff"), 2.2)
        pen_cyan.setCapStyle(Qt.PenCapStyle.RoundCap)
        for ang in (18, 108, 198, 288):
            p.setPen(pen_cyan_glow)
            p.drawArc(rect_int, ang * 16, 62 * 16)
            p.setPen(pen_cyan)
            p.drawArc(rect_int, ang * 16, 62 * 16)

        # Texto central TIZA (Amarillo) y MERCH (Lila)
        f_tiza = QFont("Impact", int(w * 0.14), QFont.Weight.Bold)
        p.setFont(f_tiza)
        p.setPen(QColor("#ffee00"))
        p.drawText(QRectF(0, cy - w * 0.21, w, w * 0.22), Qt.AlignmentFlag.AlignCenter, "TIZA")

        f_merch = QFont("Impact", int(w * 0.12), QFont.Weight.Bold)
        p.setFont(f_merch)
        p.setPen(QColor("#d08bff"))
        p.drawText(QRectF(0, cy - w * 0.01, w, w * 0.22), Qt.AlignmentFlag.AlignCenter, "MERCH")
        p.end()


# ==============================================================================
# 🔐 VENTANA DE LOGIN VECTORIAL (IDÉNTICA A CAPTURA 045354.jpg)
# ==============================================================================
class VentanaLoginWebStyle(QWidget):
    """
    Replica el diseño exacto de tu pantalla de Login Web:
    - Banderines triangulares neón (▽▽▽) en la parte superior.
    - Gran círculo de doble aro neón (rosa y cian) en el centro.
    - Inputs oscuros redondeados y botón rosa 'Entrar' dentro del círculo.
    """
    def __init__(self):
        super().__init__()
        self.db = GestorConsultasTizamerch()
        self.ventana_principal = None

        self.setWindowTitle("TIZAMERCH — Control de Inventario (Iniciar Sesión)")
        self.resize(1100, 660)
        self.setMinimumSize(900, 580)
        self.construir_ui()

    def paintEvent(self, event):
        """ Dibuja el fondo oscuro con resplandores, los banderines neón y el gran círculo central. """
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w, h = self.width(), self.height()

        # 1. Fondo base oscuro (#07050c)
        p.fillRect(0, 0, w, h, QColor("#07050c"))

        # 2. Resplandores ambientales (Verde esmeralda izq, Púrpura der, Rosa centro)
        g_izq = QRadialGradient(w * 0.15, h * 0.65, w * 0.35)
        g_izq.setColorAt(0.0, QColor(0, 180, 120, 42))
        g_izq.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, w, h, g_izq)

        g_der = QRadialGradient(w * 0.82, h * 0.25, w * 0.35)
        g_der.setColorAt(0.0, QColor(145, 0, 220, 55))
        g_der.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, w, h, g_der)

        cx, cy = w / 2.0, h * 0.53
        r_circle = min(w, h) * 0.33

        g_centro = QRadialGradient(cx, cy, r_circle * 1.35)
        g_centro.setColorAt(0.0, QColor(35, 10, 48, 170))
        g_centro.setColorAt(0.65, QColor(255, 0, 120, 50))
        g_centro.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, w, h, g_centro)

        # 3. Guirnalda superior de banderines triangulares neón (▽▽▽)
        num_tri = 18
        paso_x = w / num_tri
        for i in range(num_tri):
            x_ini = i * paso_x + 6
            x_fin = (i + 1) * paso_x - 6
            x_med = (x_ini + x_fin) / 2.0
            # Curva suave colgante
            t_norm = (i - num_tri / 2.0) / (num_tri / 2.0)
            y_top = 12 + 24 * (1 - t_norm * t_norm)
            y_punta = y_top + 40

            poly = QPolygonF([
                QPointF(x_ini, y_top),
                QPointF(x_fin, y_top),
                QPointF(x_med, y_punta),
            ])
            es_cian = (i % 2 == 0)
            col_principal = QColor("#00f0ff") if es_cian else QColor("#ff1a8c")
            col_glow = QColor(0, 240, 255, 55) if es_cian else QColor(255, 26, 140, 55)

            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(col_glow, 6.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPolygon(poly)
            p.setPen(QPen(col_principal, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPolygon(poly)

        # 4. Gran Círculo Neón Central (Aro exterior rosa + 4 arcos interiores cian)
        rect_ext = QRectF(cx - r_circle, cy - r_circle, r_circle * 2, r_circle * 2)
        p.setPen(QPen(QColor(255, 0, 128, 45), 14.0))
        p.drawEllipse(rect_ext)
        p.setPen(QPen(QColor(255, 0, 128, 90), 6.0))
        p.drawEllipse(rect_ext)
        p.setPen(QPen(QColor("#ff1e90"), 2.8))
        p.drawEllipse(rect_ext)

        r_in = r_circle * 0.86
        rect_in = QRectF(cx - r_in, cy - r_in, r_in * 2, r_in * 2)
        pen_c_glow = QPen(QColor(0, 240, 255, 70), 7.0)
        pen_c_glow.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen_c_solid = QPen(QColor("#00f0ff"), 2.6)
        pen_c_solid.setCapStyle(Qt.PenCapStyle.RoundCap)

        for ang_start in (16, 106, 196, 286):
            p.setPen(pen_c_glow)
            p.drawArc(rect_in, ang_start * 16, 64 * 16)
            p.setPen(pen_c_solid)
            p.drawArc(rect_in, ang_start * 16, 64 * 16)

        # 5. Estrellas / destellos de 4 puntas (✦)
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        for sx, sy in [
            (cx + r_circle * 0.36, cy - r_circle * 0.34),
            (cx - r_circle * 0.56, cy + r_circle * 0.02),
            (cx + r_circle * 0.40, cy + r_circle * 0.45),
        ]:
            p.drawLine(QPointF(sx - 5, sy), QPointF(sx + 5, sy))
            p.drawLine(QPointF(sx, sy - 5), QPointF(sx, sy + 5))

        p.end()

    def construir_ui(self):
        ly_raiz = QVBoxLayout(self)
        ly_raiz.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Contenedor transparente centrado dentro del aro neón
        card_centro = QWidget()
        card_centro.setFixedSize(310, 350)
        card_centro.setStyleSheet("background: transparent;")
        ly = QVBoxLayout(card_centro)
        ly.setContentsMargins(10, 10, 10, 10)
        ly.setSpacing(6)

        lbl_tiza = QLabel("TIZA")
        lbl_tiza.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_tiza.setStyleSheet("color: #ffee00; font-family: 'Impact', 'Segoe UI Black'; font-size: 40px; letter-spacing: 2px;")
        ly.addWidget(lbl_tiza)

        lbl_merch = QLabel("MERCH")
        lbl_merch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_merch.setStyleSheet("color: #c77dff; font-family: 'Impact', 'Segoe UI Black'; font-size: 36px; letter-spacing: 2px; margin-top: -12px;")
        ly.addWidget(lbl_merch)

        lbl_sub = QLabel("Control de inventario")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sub.setStyleSheet("color: #a5a0b8; font-size: 12px; margin-bottom: 4px;")
        ly.addWidget(lbl_sub)

        # Selector compacto de Motor BD
        self.combo_motor = QComboBox()
        self.combo_motor.addItem("🐘 Motor: PostgreSQL (tizamerch)", userData="postgres")
        self.combo_motor.addItem("🗄️ Motor: SQL Server (Tizamerch)", userData="sqlserver")
        self.combo_motor.setStyleSheet("""
            QComboBox {
                background-color: rgba(12, 10, 24, 210);
                color: #b8b2cc;
                border: 1px solid #2e2640;
                border-radius: 8px;
                padding: 5px 12px;
                font-size: 12px;
            }
            QComboBox:hover { border: 1px solid #00f0ff; color: #ffffff; }
            QComboBox QAbstractItemView {
                background-color: #120d20;
                color: #00f0ff;
                selection-background-color: #ff007f;
            }
        """)
        ly.addWidget(self.combo_motor)

        # Input Usuario (con borde cian luminoso al enfocar, igual a la captura)
        self.inp_usuario = QLineEdit()
        self.inp_usuario.setPlaceholderText("👤  Usuario")
        self.inp_usuario.setText("admin")
        self.inp_usuario.setStyleSheet("""
            QLineEdit {
                background-color: rgba(10, 12, 22, 230);
                color: #ffffff;
                border: 1.5px solid #00e5ff;
                border-radius: 9px;
                padding: 9px 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #00ffff;
                background-color: rgba(14, 22, 34, 245);
            }
        """)
        ly.addWidget(self.inp_usuario)

        # Contenedor Contraseña + botón ojo
        frame_pwd = QFrame()
        frame_pwd.setStyleSheet("""
            QFrame {
                background-color: rgba(10, 10, 20, 230);
                border: 1px solid #2b233d;
                border-radius: 9px;
            }
            QFrame:focus-within {
                border: 1.5px solid #00e5ff;
            }
        """)
        ly_pwd = QHBoxLayout(frame_pwd)
        ly_pwd.setContentsMargins(12, 2, 8, 2)

        self.inp_password = QLineEdit()
        self.inp_password.setPlaceholderText("🔒  Contraseña")
        self.inp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_password.setText("123456")
        self.inp_password.setStyleSheet("border: none; background: transparent; color: #ffffff; padding: 7px 2px; font-size: 13px;")
        self.inp_password.returnPressed.connect(self.intentar_login)
        ly_pwd.addWidget(self.inp_password)

        self.btn_ojo = QPushButton("👁")
        self.btn_ojo.setFixedWidth(30)
        self.btn_ojo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ojo.setStyleSheet("border: none; background: transparent; color: #8c84a3; font-size: 14px;")
        self.btn_ojo.clicked.connect(self._toggle_pwd)
        ly_pwd.addWidget(self.btn_ojo)
        ly.addWidget(frame_pwd)

        # Botón Rosa Brillante "Entrar"
        btn_entrar = QPushButton("Entrar")
        btn_entrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_entrar.setStyleSheet("""
            QPushButton {
                background-color: #ff006e;
                color: #ffffff;
                border: none;
                border-radius: 9px;
                padding: 10px;
                font-size: 13px;
                font-weight: bold;
                margin-top: 4px;
            }
            QPushButton:hover {
                background-color: #ff2a85;
            }
        """)
        btn_entrar.clicked.connect(self.intentar_login)
        ly.addWidget(btn_entrar)

        self.lbl_error = QLabel("")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.setStyleSheet("color: #ff4d6d; font-size: 11px; font-weight: bold;")
        ly.addWidget(self.lbl_error)

        ly_raiz.addWidget(card_centro)

    def _toggle_pwd(self):
        if self.inp_password.echoMode() == QLineEdit.EchoMode.Password:
            self.inp_password.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.inp_password.setEchoMode(QLineEdit.EchoMode.Password)

    def intentar_login(self):
        usr = self.inp_usuario.text().strip()
        pwd = self.inp_password.text().strip()
        motor = self.combo_motor.currentData()

        if not usr or not pwd:
            self.lbl_error.setText("Ingresa usuario y contraseña")
            return

        if not self.db.conectar(motor):
            QMessageBox.critical(self, "Error de Conexión", f"No se pudo conectar a {motor.upper()}. Verifica tu archivo .env.")
            return

        ok, datos_usr, msg = self.db.autenticar_usuario(usr, pwd)
        if not ok:
            self.lbl_error.setText(msg)
            return

        self.lbl_error.setText("")
        self.ventana_principal = VentanaPrincipalWebStyle(
            gestor_db=self.db,
            usuario_sesion=datos_usr,
            callback_logout=self.volver_al_login
        )
        self.ventana_principal.show()
        self.hide()

    def volver_al_login(self):
        self.inp_password.clear()
        self.show()


# ==============================================================================
# 📝 DIÁLOGO MODAL PARA INSERTAR / ACTUALIZAR UN CATÁLOGO MAESTRO
# ==============================================================================
class DialogoFormularioCatalogo(QDialog):
    """
    Ventana emergente moderna estilo oscuro/neón para Insertar o Actualizar
    cualquier registro de las Tablas Maestras (Catálogos).
    """
    def __init__(self, parent, db: GestorConsultasTizamerch, clave_catalogo: str, modo: str, datos_fila: dict = None):
        super().__init__(parent)
        self.db = db
        self.clave = clave_catalogo
        self.info = CATALOGOS_MAESTROS[clave_catalogo]
        self.modo = modo  # 'insertar' o 'actualizar'
        self.datos_fila = datos_fila or {}
        self.widgets_campo = {}

        es_pg = self.db.motor == "postgres"
        self.nombre_tabla = self.info["tabla_pg"] if es_pg else self.info["tabla_sql"]
        self.pk_col = self.info["pk_pg"] if es_pg else self.info["pk_sql"]

        accion_txt = "Registrar nuevo en" if modo == "insertar" else "Actualizar registro en"
        self.setWindowTitle(f"{accion_txt} {self.info['titulo']}")
        self.setMinimumWidth(460)
        self.setStyleSheet("""
            QDialog {
                background-color: #100b1c;
                color: #ffffff;
                border: 1px solid #00e5ff;
            }
            QLabel { color: #c9c2de; font-size: 13px; font-weight: bold; }
            QLineEdit, QComboBox {
                background-color: #090612;
                color: #ffffff;
                border: 1px solid #2f2546;
                border-radius: 7px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus { border: 1.5px solid #00e5ff; }
        """)
        self.construir_formulario()

    def construir_formulario(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(24, 22, 24, 22)
        ly.setSpacing(14)

        lbl_head = QLabel(f"✨ {self.info['titulo'].upper()} — {self.modo.upper()}")
        lbl_head.setStyleSheet("color: #00e5ff; font-size: 16px; font-weight: bold;")
        ly.addWidget(lbl_head)

        form = QFormLayout()
        form.setSpacing(10)

        es_pg = self.db.motor == "postgres"
        fila_norm = {str(k).lower(): v for k, v in self.datos_fila.items()}

        if self.modo == "actualizar":
            self.inp_pk = QLineEdit(str(fila_norm.get(self.info["pk_pg"].lower(), "")))
            self.inp_pk.setPlaceholderText(f"ID ({self.pk_col})")
            form.addRow(QLabel(f"ID ({self.pk_col}):"), self.inp_pk)

        for col_pg, col_sql, etiqueta, tipo in self.info["campos"]:
            col_real = col_pg if es_pg else col_sql
            val_previo = fila_norm.get(col_pg.lower(), "")

            if tipo == "bool":
                combo = QComboBox()
                combo.addItem("Activo", userData=True)
                combo.addItem("Inactivo / Baja", userData=False)
                if str(val_previo).upper() in ("FALSE", "0"):
                    combo.setCurrentIndex(1)
                form.addRow(QLabel(f"{etiqueta}:"), combo)
                self.widgets_campo[col_real] = (combo, etiqueta, tipo)
            else:
                inp = QLineEdit()
                inp.setPlaceholderText(etiqueta)
                if val_previo is not None and str(val_previo) != "None" and tipo != "bcrypt":
                    inp.setText(str(val_previo))
                form.addRow(QLabel(f"{etiqueta}:"), inp)
                self.widgets_campo[col_real] = (inp, etiqueta, tipo)

        ly.addLayout(form)

        ly_btns = QHBoxLayout()
        ly_btns.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet("background-color: #1c152e; color: #a59ec2; border: 1px solid #33294d; border-radius: 7px; padding: 8px 16px;")
        btn_cancel.clicked.connect(self.reject)
        ly_btns.addWidget(btn_cancel)

        btn_save = QPushButton("Guardar en Base de Datos")
        btn_save.setStyleSheet("background-color: #00e5ff; color: #080510; border: none; border-radius: 7px; padding: 8px 18px; font-weight: bold;")
        btn_save.clicked.connect(self.guardar)
        ly_btns.addWidget(btn_save)

        ly.addLayout(ly_btns)

    def guardar(self):
        try:
            columnas, valores = [], []
            for col_name, (w, etiqueta, tipo) in self.widgets_campo.items():
                if tipo == "bool":
                    columnas.append(col_name)
                    valores.append(self.db.valor_booleano(bool(w.currentData())))
                else:
                    txt = w.text().strip()
                    if tipo == "str_null":
                        columnas.append(col_name)
                        valores.append(txt if txt else None)
                    elif not txt:
                        if self.modo == "insertar":
                            QMessageBox.warning(self, "Campo obligatorio", f"Por favor completa '{etiqueta}'.")
                            return
                    else:
                        columnas.append(col_name)
                        if tipo == "int":
                            valores.append(int(txt))
                        elif tipo == "float":
                            valores.append(float(txt))
                        elif tipo == "bcrypt":
                            valores.append(self.db.asegurar_hash_bcrypt(txt))
                        else:
                            valores.append(txt)

            if self.modo == "insertar":
                ok, msg = self.db.insertar_catalogo(self.nombre_tabla, columnas, tuple(valores))
            else:
                id_val = int(self.inp_pk.text().strip())
                ok, msg = self.db.actualizar_catalogo(self.nombre_tabla, self.pk_col, id_val, columnas, tuple(valores))

            if ok:
                self.accept()
            else:
                QMessageBox.critical(self, "Error SQL", msg)
        except ValueError:
            QMessageBox.warning(self, "Formato inválido", "Verifica que los campos numéricos (Precio, Stock, IDs) sean números válidos.")


# ==============================================================================
# 📥📤 DIÁLOGO MODAL PARA REGISTRAR ENTRADA O SALIDA RÁPIDA DE MERCANCÍA
# ==============================================================================
class DialogoMovimientoRapido(QDialog):
    """
    Permite usar los botones superiores '↓ Registrar entrada' y '↑ Registrar salida'
    actualizando automáticamente Productos.Stock_Actual y MovimientosInventario.
    """
    def __init__(self, parent, db: GestorConsultasTizamerch, tipo_mov: str, id_usuario: int):
        super().__init__(parent)
        self.db = db
        self.tipo_mov = tipo_mov  # 'ENTRADA' o 'SALIDA'
        self.id_usuario = id_usuario

        es_entrada = (tipo_mov == "ENTRADA")
        color_acento = "#00e676" if es_entrada else "#ff1744"
        self.setWindowTitle(f"{'↓ Registrar Entrada' if es_entrada else '↑ Registrar Salida'} de Inventario")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: #100b1c; color: #ffffff; border: 1.5px solid {color_acento}; }}
            QLabel {{ color: #d0c8e8; font-size: 13px; font-weight: bold; }}
            QLineEdit, QComboBox {{
                background-color: #090612; color: #ffffff; border: 1px solid #2f2546;
                border-radius: 7px; padding: 8px 12px; font-size: 13px;
            }}
        """)

        ly = QVBoxLayout(self)
        ly.setContentsMargins(22, 20, 22, 20)
        ly.setSpacing(12)

        lbl_t = QLabel(f"{'↓ REGISTRAR ENTRADA AL ALMACÉN' if es_entrada else '↑ REGISTRAR SALIDA DE MERCANCÍA'}")
        lbl_t.setStyleSheet(f"color: {color_acento}; font-size: 15px; font-weight: bold;")
        ly.addWidget(lbl_t)

        form = QFormLayout()
        self.combo_prod = QComboBox()
        _, prods, _ = self.db.ejecutar_select(
            "SELECT id_producto, nombre, stock_actual FROM productos ORDER BY id_producto"
            if self.db.motor == "postgres" else
            "SELECT Id_Producto, Nombre, Stock_Actual FROM Productos ORDER BY Id_Producto"
        )
        for pr in prods:
            p_norm = {str(k).lower(): v for k, v in pr.items()}
            pid = p_norm.get("id_producto")
            pnom = p_norm.get("nombre")
            pstk = p_norm.get("stock_actual")
            self.combo_prod.addItem(f"#{pid} - {pnom} (Stock: {pstk})", userData=(pid, int(pstk or 0)))
        form.addRow(QLabel("Producto:"), self.combo_prod)

        self.inp_cant = QLineEdit("5")
        form.addRow(QLabel("Cantidad (>= 1):"), self.inp_cant)
        ly.addLayout(form)

        ly_b = QHBoxLayout()
        ly_b.addStretch()
        btn_ok = QPushButton("Confirmar Movimiento")
        btn_ok.setStyleSheet(f"background-color: {color_acento}; color: #080510; border: none; border-radius: 7px; padding: 8px 16px; font-weight: bold;")
        btn_ok.clicked.connect(self.ejecutar)
        ly_b.addWidget(btn_ok)
        ly.addLayout(ly_b)

    def ejecutar(self):
        try:
            cant = int(self.inp_cant.text().strip())
            if cant < 1:
                raise ValueError
            datos_p = self.combo_prod.currentData()
            if not datos_p:
                return
            pid, stock_actual = datos_p
            nuevo_stock = stock_actual + cant if self.tipo_mov == "ENTRADA" else stock_actual - cant
            if nuevo_stock < 0:
                QMessageBox.warning(self, "Stock insuficiente", f"No puedes retirar {cant} unidades (Stock actual: {stock_actual}).")
                return

            ph = self.db.marcador()
            es_pg = self.db.motor == "postgres"
            t_prod = "productos" if es_pg else "Productos"
            c_stk = "stock_actual" if es_pg else "Stock_Actual"
            c_pk = "id_producto" if es_pg else "Id_Producto"

            # 1. Actualizar Stock_Actual (Dispara automáticamente trg_Productos_Alertas)
            ok1, msg1 = self.db.ejecutar_crud(
                f"UPDATE {t_prod} SET {c_stk} = {ph} WHERE {c_pk} = {ph}",
                (nuevo_stock, pid)
            )
            if not ok1:
                QMessageBox.critical(self, "Error SQL", msg1)
                return

            # 2. Insertar en MovimientosInventario
            t_mov = "movimientosinventario" if es_pg else "MovimientosInventario"
            self.db.ejecutar_crud(
                f"INSERT INTO {t_mov} (Id_Producto, Tipo_Movimiento, Cantidad, Id_Usuario) VALUES ({ph}, {ph}, {ph}, {ph})",
                (pid, self.tipo_mov, cant, self.id_usuario)
            )
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "Cantidad inválida", "Ingresa un número entero mayor o igual a 1.")


# ==============================================================================
# 🖥️ VENTANA PRINCIPAL ESTILO WEB APP (IDÉNTICA A CAPTURAS 045424, 045854, 045901)
# ==============================================================================
class VentanaPrincipalWebStyle(QMainWindow):
    def __init__(self, gestor_db: GestorConsultasTizamerch, usuario_sesion: dict, callback_logout=None):
        super().__init__()
        self.db = gestor_db
        self.usuario_sesion = usuario_sesion
        self.callback_logout = callback_logout
        self.cerrando_sesion = False

        self.catalogo_activo = "productos"
        self.filtro_estado_cat = "todos"   # 'todos', 'bajo', 'agotado', 'activos'
        self.filtro_tipo_mov = "TODOS"     # 'TODOS', 'ENTRADA', 'SALIDA', 'AJUSTE', 'ALERTAS'
        self.botones_nav = {}
        self.botones_pestanas_cat = {}
        self.botones_filtro_mov = {}

        self.setWindowTitle("TIZAMERCH — Inventario en línea (App de Escritorio)")
        self.resize(1340, 820)
        self.aplicar_tema_web_dark()
        self.crear_menubar_profesor()
        self.construir_layout_web()
        self.ir_a_vista(0)

    def aplicar_tema_web_dark(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0b0714;
                color: #f0ecf8;
                font-family: 'Segoe UI', sans-serif;
            }
            QMenuBar {
                background-color: #090610;
                color: #b8b0cc;
                border-bottom: 1px solid #1f1830;
                font-size: 12px;
                padding: 2px 8px;
            }
            QMenuBar::item:selected { background-color: #1f1633; color: #00e5ff; }
            QMenu {
                background-color: #120c1f;
                color: #e5e0f8;
                border: 1px solid #00e5ff;
                padding: 6px;
            }
            QMenu::item { padding: 6px 22px; border-radius: 4px; }
            QMenu::item:selected { background-color: #00e5ff; color: #090610; font-weight: bold; }
            QTableWidget {
                background-color: #110c1d;
                alternate-background-color: #140e22;
                color: #f0ecf8;
                border: 1px solid #241b38;
                border-radius: 12px;
                gridline-color: #1d152e;
                selection-background-color: rgba(0, 229, 255, 45);
                selection-color: #ffffff;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #150f24;
                color: #968eb0;
                font-weight: 600;
                font-size: 12px;
                padding: 10px 12px;
                border: none;
                border-bottom: 1px solid #261d3a;
            }
            QScrollBar:vertical {
                background: #0b0714;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2b2142;
                border-radius: 4px;
            }
        """)

    # --------------------------------------------------------------------------
    # MENÚ SUPERIOR REQUERIDO POR EL PROFESOR: "Catálogos" -> Tablas Maestras -> CRUD
    # --------------------------------------------------------------------------
    def crear_menubar_profesor(self):
        mb = self.menuBar()

        menu_cat = mb.addMenu("🗂️ Catálogos (Tablas Maestras)")
        for clave, info in CATALOGOS_MAESTROS.items():
            sub = menu_cat.addMenu(info["titulo"])
            for accion_k, accion_txt in [
                ("consultar", "📋 Consultar"),
                ("insertar", "➕ Insertar"),
                ("actualizar", "✏️ Actualizar"),
                ("eliminar", "🗑️ Eliminar"),
            ]:
                act = QAction(f"{accion_txt} en {info['pestana']}", self)
                act.triggered.connect(lambda checked=False, c=clave, a=accion_k: self.ejecutar_accion_menu_catalogo(c, a))
                sub.addAction(act)

        menu_bd = mb.addMenu("🗄️ Base de Datos")
        act_pg = QAction("🐘 Conectar a PostgreSQL (tizamerch)", self)
        act_pg.triggered.connect(lambda: self.cambiar_motor("postgres"))
        menu_bd.addAction(act_pg)

        act_sql = QAction("🗄️ Conectar a SQL Server (Tizamerch)", self)
        act_sql.triggered.connect(lambda: self.cambiar_motor("sqlserver"))
        menu_bd.addAction(act_sql)

        menu_bd.addSeparator()
        act_salir = QAction("🚪 Salir", self)
        act_salir.triggered.connect(self.close)
        menu_bd.addAction(act_salir)

    # --------------------------------------------------------------------------
    # CONSTRUCCIÓN DEL LAYOUT WEB (SIDEBAR IZQUIERDO + ÁREA PRINCIPAL)
    # --------------------------------------------------------------------------
    def construir_layout_web(self):
        central = QWidget()
        self.setCentralWidget(central)
        ly_raiz = QHBoxLayout(central)
        ly_raiz.setContentsMargins(0, 0, 0, 0)
        ly_raiz.setSpacing(0)

        # === 1. BARRA LATERAL IZQUIERDA (IDÉNTICA A TUS CAPTURAS) ===
        sidebar = QFrame()
        sidebar.setFixedWidth(235)
        sidebar.setStyleSheet("QFrame { background-color: #090610; border-right: 1px solid #1e162e; }")
        ly_side = QVBoxLayout(sidebar)
        ly_side.setContentsMargins(16, 22, 16, 18)
        ly_side.setSpacing(8)

        # Logo Circular Vectorial Nítido (0% pixeleado)
        logo_vec = LogoCircularVectorWidget(diametro=100)
        ly_side.addWidget(logo_vec, alignment=Qt.AlignmentFlag.AlignCenter)

        lbl_brand = QLabel("TIZAMERCH")
        lbl_brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_brand.setStyleSheet("color: #ffee00; font-family: 'Impact', 'Segoe UI Black'; font-size: 20px; letter-spacing: 1px; border: none; margin-top: 4px;")
        ly_side.addWidget(lbl_brand)

        lbl_online = QLabel("Inventario en línea")
        lbl_online.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_online.setStyleSheet("color: #8a82a6; font-size: 11px; border: none; margin-bottom: 16px;")
        ly_side.addWidget(lbl_online)

        # Botones de Navegación Lateral (Panel de control, Catálogos maestros, Movimientos)
        items_nav = [
            (0, "⊞   Panel de control"),
            (1, "📦   Catálogos maestros"),
            (2, "⇄   Movimientos"),
        ]
        for idx_pag, texto in items_nav:
            btn = QPushButton(texto)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, i=idx_pag: self.ir_a_vista(i))
            ly_side.addWidget(btn)
            self.botones_nav[idx_pag] = btn

        ly_side.addStretch()

        # Tarjeta Inferior de Usuario Activo (AG | Administrador Ge... | @admin | [->])
        card_user = QFrame()
        card_user.setStyleSheet("""
            QFrame {
                background-color: #110c1d;
                border: 1px solid #251c38;
                border-radius: 12px;
            }
        """)
        ly_usr = QHBoxLayout(card_user)
        ly_usr.setContentsMargins(10, 10, 10, 10)
        ly_usr.setSpacing(10)

        nombre_u = self.usuario_sesion.get("nombre", "Administrador General")
        login_u = self.usuario_sesion.get("usuario", "admin")
        iniciales = "".join([p[0].upper() for p in nombre_u.split()[:2]]) or "AG"

        lbl_avatar = QLabel(iniciales)
        lbl_avatar.setFixedSize(36, 36)
        lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_avatar.setStyleSheet("""
            background-color: #1f1a10;
            color: #ffee00;
            border: 1.5px solid #ffee00;
            border-radius: 18px;
            font-weight: bold;
            font-size: 12px;
        """)
        ly_usr.addWidget(lbl_avatar)

        ly_txt_u = QVBoxLayout()
        ly_txt_u.setSpacing(1)
        lbl_nom = QLabel(nombre_u[:17] + ("..." if len(nombre_u) > 17 else ""))
        lbl_nom.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 12px; border: none;")
        lbl_log = QLabel(f"@{login_u}")
        lbl_log.setStyleSheet("color: #8a82a6; font-size: 11px; border: none;")
        ly_txt_u.addWidget(lbl_nom)
        ly_txt_u.addWidget(lbl_log)
        ly_usr.addLayout(ly_txt_u, stretch=1)

        btn_logout = QPushButton("↪")
        btn_logout.setFixedSize(32, 32)
        btn_logout.setToolTip("Cerrar sesión")
        btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_logout.setStyleSheet("""
            QPushButton {
                background-color: #210d24;
                color: #ff1a8c;
                border: 1px solid #ff1a8c;
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ff1a8c; color: #ffffff; }
        """)
        btn_logout.clicked.connect(self.cerrar_sesion)
        ly_usr.addWidget(btn_logout)

        ly_side.addWidget(card_user)
        ly_raiz.addWidget(sidebar)

        # === 2. ÁREA DERECHA PRINCIPAL (HEADER COMÚN + STACK DE 3 VISTAS) ===
        area_derecha = QWidget()
        ly_der = QVBoxLayout(area_derecha)
        ly_der.setContentsMargins(28, 20, 28, 18)
        ly_der.setSpacing(16)

        # Header Superior (Fecha + Título Grande + Selector Motor + Botones Registrar Entrada/Salida)
        ly_header = QHBoxLayout()
        ly_titulos = QVBoxLayout()
        ly_titulos.setSpacing(2)

        self.lbl_fecha_top = QLabel("Domingo, 18 de octubre de 2026")
        self.lbl_fecha_top.setStyleSheet("color: #968eb0; font-size: 12px;")
        ly_titulos.addWidget(self.lbl_fecha_top)

        self.lbl_titulo_vista = QLabel("PANEL DE CONTROL")
        self.lbl_titulo_vista.setStyleSheet("color: #ffffff; font-family: 'Impact', 'Segoe UI Black'; font-size: 32px; letter-spacing: 1px;")
        ly_titulos.addWidget(self.lbl_titulo_vista)
        ly_header.addLayout(ly_titulos)

        ly_header.addStretch()

        # Píldora indicadora y cambiadora de Motor BD
        self.btn_motor_pill = QPushButton("🐘 PostgreSQL")
        self.btn_motor_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_motor_pill.setToolTip("Haz clic para alternar entre PostgreSQL y SQL Server")
        self.btn_motor_pill.clicked.connect(self.alternar_motor_rapido)
        ly_header.addWidget(self.btn_motor_pill)

        # Botón "↓ Registrar entrada" (Verde Neón)
        btn_reg_ent = QPushButton("↓  Registrar entrada")
        btn_reg_ent.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reg_ent.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 230, 118, 18);
                color: #00e676;
                border: 1.5px solid #00e676;
                border-radius: 10px;
                padding: 9px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #00e676; color: #080510; }
        """)
        btn_reg_ent.clicked.connect(lambda: self.abrir_dialogo_movimiento("ENTRADA"))
        ly_header.addWidget(btn_reg_ent)

        # Botón "↑ Registrar salida" (Rosa/Rojo Neón)
        btn_reg_sal = QPushButton("↑  Registrar salida")
        btn_reg_sal.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reg_sal.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 26, 140, 18);
                color: #ff2a85;
                border: 1.5px solid #ff2a85;
                border-radius: 10px;
                padding: 9px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #ff2a85; color: #ffffff; }
        """)
        btn_reg_sal.clicked.connect(lambda: self.abrir_dialogo_movimiento("SALIDA"))
        ly_header.addWidget(btn_reg_sal)

        ly_der.addLayout(ly_header)

        # Contenedor de las 3 Páginas
        self.stack = QStackedWidget()
        self.stack.addWidget(self._construir_vista_panel_control())
        self.stack.addWidget(self._construir_vista_catalogos())
        self.stack.addWidget(self._construir_vista_movimientos())
        ly_der.addWidget(self.stack, stretch=1)

        ly_raiz.addWidget(area_derecha, stretch=1)
        self.actualizar_boton_motor()

    # --------------------------------------------------------------------------
    # VISTA 0: PANEL DE CONTROL (IDÉNTICA A CAPTURA 045424.jpg)
    # --------------------------------------------------------------------------
    def _construir_vista_panel_control(self) -> QWidget:
        pag = QWidget()
        ly = QVBoxLayout(pag)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(18)

        # Fila de 4 Tarjetas KPI
        ly_kpis = QHBoxLayout()
        ly_kpis.setSpacing(16)

        self.kpi_prod = self._crear_tarjeta_kpi("Productos activos", "0", "0 unidades en catálogo", "#00e5ff", "📦")
        self.kpi_ent = self._crear_tarjeta_kpi("Entradas registradas", "0", "Unidades recibidas en almacén", "#00e676", "↓")
        self.kpi_sal = self._crear_tarjeta_kpi("Salidas registradas", "0", "Unidades despachadas", "#ffea00", "↑")
        self.kpi_alerta = self._crear_tarjeta_kpi("Alertas de stock", "0", "Productos con stock bajo", "#ff1e6e", "⚠", borde_completo=True)

        for card in (self.kpi_prod[0], self.kpi_ent[0], self.kpi_sal[0], self.kpi_alerta[0]):
            ly_kpis.addWidget(card, stretch=1)
        ly.addLayout(ly_kpis)

        # Sección Inferior Dividida: Izquierda (Existencias en alerta) | Derecha (Últimos movimientos)
        ly_inf = QHBoxLayout()
        ly_inf.setSpacing(18)

        # Panel Izquierdo: Existencias que necesitan atención
        panel_atencion = QFrame()
        panel_atencion.setStyleSheet("""
            QFrame {
                background-color: #100b1b;
                border: 1px solid #221936;
                border-radius: 14px;
            }
        """)
        ly_at = QVBoxLayout(panel_atencion)
        ly_at.setContentsMargins(20, 18, 20, 18)
        ly_at.setSpacing(12)

        ly_at_head = QHBoxLayout()
        lbl_at_tit = QLabel("Existencias que necesitan atención")
        lbl_at_tit.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 15px; border: none;")
        ly_at_head.addWidget(lbl_at_tit)
        ly_at_head.addStretch()
        lbl_at_sub = QLabel("Sincronizado con Trigger SQL")
        lbl_at_sub.setStyleSheet("color: #7c7496; font-size: 12px; border: none;")
        ly_at_head.addWidget(lbl_at_sub)
        ly_at.addLayout(ly_at_head)

        self.contenedor_tarjetas_alerta = QVBoxLayout()
        self.contenedor_tarjetas_alerta.setSpacing(12)
        ly_at.addLayout(self.contenedor_tarjetas_alerta)
        ly_at.addStretch()

        ly_inf.addWidget(panel_atencion, stretch=6)

        # Panel Derecho: Últimos movimientos
        panel_ultimos = QFrame()
        panel_ultimos.setStyleSheet("""
            QFrame {
                background-color: #100b1b;
                border: 1px solid #221936;
                border-radius: 14px;
            }
        """)
        ly_ul = QVBoxLayout(panel_ultimos)
        ly_ul.setContentsMargins(20, 18, 20, 18)
        ly_ul.setSpacing(10)

        ly_ul_head = QHBoxLayout()
        lbl_ul_tit = QLabel("Últimos movimientos")
        lbl_ul_tit.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 15px; border: none;")
        ly_ul_head.addWidget(lbl_ul_tit)
        ly_ul_head.addStretch()

        btn_ver_hist = QPushButton("Ver historial")
        btn_ver_hist.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ver_hist.setStyleSheet("border: none; background: transparent; color: #00e5ff; font-weight: bold; font-size: 12px;")
        btn_ver_hist.clicked.connect(lambda: self.ir_a_vista(2))
        ly_ul_head.addWidget(btn_ver_hist)
        ly_ul.addLayout(ly_ul_head)

        self.contenedor_ultimos_movs = QVBoxLayout()
        self.contenedor_ultimos_movs.setSpacing(8)
        ly_ul.addLayout(self.contenedor_ultimos_movs)
        ly_ul.addStretch()

        ly_inf.addWidget(panel_ultimos, stretch=4)
        ly.addLayout(ly_inf, stretch=1)
        return pag

    def _crear_tarjeta_kpi(self, titulo: str, valor: str, subtitulo: str, color_hex: str, icono: str, borde_completo=False):
        card = QFrame()
        borde_css = f"border: 1.5px solid {color_hex};" if borde_completo else f"border: 1px solid #221936; border-top: 3px solid {color_hex};"
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #110c1e;
                {borde_css}
                border-radius: 14px;
            }}
        """)
        ly = QVBoxLayout(card)
        ly.setContentsMargins(18, 16, 18, 16)
        ly.setSpacing(6)

        ly_top = QHBoxLayout()
        lbl_t = QLabel(titulo)
        lbl_t.setStyleSheet("color: #d0c8e8; font-size: 13px; font-weight: 600; border: none;")
        ly_top.addWidget(lbl_t)
        ly_top.addStretch()
        lbl_ic = QLabel(icono)
        lbl_ic.setStyleSheet(f"color: {color_hex}; font-size: 16px; font-weight: bold; border: none;")
        ly_top.addWidget(lbl_ic)
        ly.addLayout(ly_top)

        lbl_val = QLabel(valor)
        lbl_val.setStyleSheet(f"color: {color_hex}; font-family: 'Impact', 'Segoe UI Black'; font-size: 36px; border: none;")
        ly.addWidget(lbl_val)

        lbl_sub = QLabel(subtitulo)
        lbl_sub.setStyleSheet("color: #8a82a6; font-size: 12px; border: none;")
        ly.addWidget(lbl_sub)
        return card, lbl_val, lbl_sub

    # --------------------------------------------------------------------------
    # VISTA 1: CATÁLOGOS MAESTROS / CRUD (IDÉNTICA A CAPTURA 045854.jpg)
    # --------------------------------------------------------------------------
    def _construir_vista_catalogos(self) -> QWidget:
        pag = QWidget()
        ly = QVBoxLayout(pag)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(14)

        # Barra de Pestañas tipo Píldora (Productos, Categorías, Marcas, Ubicaciones, Proveedores...) + Botones CRUD
        ly_tabs = QHBoxLayout()
        barra_pills = QFrame()
        barra_pills.setStyleSheet("QFrame { background-color: #080510; border: 1px solid #1f1730; border-radius: 12px; }")
        ly_pills = QHBoxLayout(barra_pills)
        ly_pills.setContentsMargins(5, 5, 5, 5)
        ly_pills.setSpacing(4)

        for clave, info in CATALOGOS_MAESTROS.items():
            b_tab = QPushButton(info["pestana"])
            b_tab.setCursor(Qt.CursorShape.PointingHandCursor)
            b_tab.clicked.connect(lambda checked=False, c=clave: self.seleccionar_catalogo_maestro(c))
            ly_pills.addWidget(b_tab)
            self.botones_pestanas_cat[clave] = b_tab

        ly_tabs.addWidget(barra_pills)
        ly_tabs.addStretch()

        # Botones de las 4 Operaciones CRUD para la Tabla Maestra seleccionada
        btn_nuevo = QPushButton("+  Registrar nuevo (Insertar)")
        btn_nuevo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_nuevo.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 229, 255, 18);
                color: #00e5ff;
                border: 1.5px solid #00e5ff;
                border-radius: 10px;
                padding: 9px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #00e5ff; color: #080510; }
        """)
        btn_nuevo.clicked.connect(self.accion_insertar_catalogo)
        ly_tabs.addWidget(btn_nuevo)

        btn_editar = QPushButton("✎  Actualizar seleccionado")
        btn_editar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_editar.setStyleSheet("""
            QPushButton {
                background-color: #161026;
                color: #ffee00;
                border: 1px solid #ffee00;
                border-radius: 10px;
                padding: 9px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ffee00; color: #080510; }
        """)
        btn_editar.clicked.connect(self.accion_actualizar_catalogo)
        ly_tabs.addWidget(btn_editar)

        btn_baja = QPushButton("⏻  Eliminar / Baja")
        btn_baja.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_baja.setStyleSheet("""
            QPushButton {
                background-color: #210d24;
                color: #ff2a85;
                border: 1px solid #ff2a85;
                border-radius: 10px;
                padding: 9px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ff2a85; color: #ffffff; }
        """)
        btn_baja.clicked.connect(self.accion_eliminar_catalogo)
        ly_tabs.addWidget(btn_baja)

        ly.addLayout(ly_tabs)

        # Barra de Búsqueda y Filtros (igual a tu captura de Catálogos Maestros)
        barra_filtros = QFrame()
        barra_filtros.setStyleSheet("QFrame { background-color: #110c1d; border: 1px solid #221936; border-radius: 12px; }")
        ly_f = QHBoxLayout(barra_filtros)
        ly_f.setContentsMargins(14, 10, 14, 10)
        ly_f.setSpacing(10)

        self.inp_buscar_cat = QLineEdit()
        self.inp_buscar_cat.setPlaceholderText("🔍  Buscar en el catálogo activo...")
        self.inp_buscar_cat.setStyleSheet("""
            QLineEdit {
                background-color: #090612;
                color: #ffffff;
                border: 1px solid #261d3a;
                border-radius: 8px;
                padding: 8px 12px;
            }
            QLineEdit:focus { border: 1px solid #00e5ff; }
        """)
        self.inp_buscar_cat.textChanged.connect(self.cargar_datos_catalogo_activo)
        ly_f.addWidget(self.inp_buscar_cat, stretch=1)

        for f_key, f_txt in [("todos", "Todos"), ("bajo", "Stock bajo"), ("agotado", "Agotados"), ("activos", "Solo Activos")]:
            b_fil = QPushButton(f_txt)
            b_fil.setCursor(Qt.CursorShape.PointingHandCursor)
            b_fil.setStyleSheet("""
                QPushButton {
                    background-color: #0b0714;
                    color: #b8b0cc;
                    border: 1px solid #2b2142;
                    border-radius: 14px;
                    padding: 6px 14px;
                    font-size: 12px;
                }
                QPushButton:hover { border: 1px solid #ffee00; color: #ffee00; }
            """)
            b_fil.clicked.connect(lambda checked=False, fk=f_key: self._aplicar_filtro_catalogo(fk))
            ly_f.addWidget(b_fil)

        ly.addWidget(barra_filtros)

        # Tabla Moderna de Catálogos Maestros
        self.tabla_catalogos = QTableWidget()
        self.tabla_catalogos.setAlternatingRowColors(True)
        self.tabla_catalogos.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_catalogos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_catalogos.verticalHeader().setVisible(False)
        self.tabla_catalogos.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla_catalogos.doubleClicked.connect(self.accion_actualizar_catalogo)
        ly.addWidget(self.tabla_catalogos, stretch=1)

        self.lbl_pie_catalogo = QLabel("Mostrando registros del catálogo maestro")
        self.lbl_pie_catalogo.setStyleSheet("color: #7c7496; font-size: 12px;")
        ly.addWidget(self.lbl_pie_catalogo)

        return pag

    # --------------------------------------------------------------------------
    # VISTA 2: HISTORIAL DE MOVIMIENTOS (IDÉNTICA A CAPTURA 045901.jpg)
    # --------------------------------------------------------------------------
    def _construir_vista_movimientos(self) -> QWidget:
        pag = QWidget()
        ly = QVBoxLayout(pag)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(14)

        barra_m = QFrame()
        barra_m.setStyleSheet("QFrame { background-color: #110c1d; border: 1px solid #221936; border-radius: 12px; }")
        ly_m = QHBoxLayout(barra_m)
        ly_m.setContentsMargins(14, 12, 14, 12)
        ly_m.setSpacing(8)

        for t_key, t_label in [
            ("TODOS", "Todos"),
            ("ENTRADA", "Entradas"),
            ("SALIDA", "Salidas"),
            ("AJUSTE", "Ajustes"),
            ("ALERTAS", "Alertas de Stock"),
        ]:
            bm = QPushButton(t_label)
            bm.setCursor(Qt.CursorShape.PointingHandCursor)
            bm.clicked.connect(lambda checked=False, tk=t_key: self.seleccionar_filtro_movimientos(tk))
            ly_m.addWidget(bm)
            self.botones_filtro_mov[t_key] = bm

        ly_m.addSpacing(16)
        self.inp_buscar_mov = QLineEdit()
        self.inp_buscar_mov.setPlaceholderText("🔍  Producto, proveedor, motivo o usuario...")
        self.inp_buscar_mov.setStyleSheet("""
            QLineEdit {
                background-color: #090612;
                color: #ffffff;
                border: 1px solid #261d3a;
                border-radius: 8px;
                padding: 8px 14px;
            }
            QLineEdit:focus { border: 1px solid #00e5ff; }
        """)
        self.inp_buscar_mov.textChanged.connect(self.cargar_datos_movimientos)
        ly_m.addWidget(self.inp_buscar_mov, stretch=1)

        ly.addWidget(barra_m)

        self.lbl_resumen_movs = QLabel("Historial sincronizado en tiempo real")
        self.lbl_resumen_movs.setStyleSheet("color: #968eb0; font-size: 12px;")
        ly.addWidget(self.lbl_resumen_movs)

        self.tabla_movimientos = QTableWidget()
        self.tabla_movimientos.setAlternatingRowColors(True)
        self.tabla_movimientos.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_movimientos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_movimientos.verticalHeader().setVisible(False)
        self.tabla_movimientos.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        ly.addWidget(self.tabla_movimientos, stretch=1)

        return pag

    # ==========================================================================
    # 🎯 [ZONA DE CONSULTAS 4]: CARGA DE DATOS EN EL PANEL DE CONTROL, CATÁLOGOS Y KARDEX
    # ==========================================================================
    def ir_a_vista(self, indice: int):
        self.stack.setCurrentIndex(indice)
        titulos = {
            0: "PANEL DE CONTROL",
            1: "CATÁLOGOS MAESTROS",
            2: "HISTORIAL DE MOVIMIENTOS",
        }
        self.lbl_titulo_vista.setText(titulos.get(indice, "PANEL DE CONTROL"))

        for idx, btn in self.botones_nav.items():
            if idx == indice:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(0, 229, 255, 22);
                        color: #00e5ff;
                        border: 1px solid #00e5ff;
                        border-radius: 10px;
                        padding: 10px 14px;
                        text-align: left;
                        font-weight: bold;
                        font-size: 13px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #b8b0cc;
                        border: 1px solid transparent;
                        border-radius: 10px;
                        padding: 10px 14px;
                        text-align: left;
                        font-size: 13px;
                    }
                    QPushButton:hover { background-color: #140e24; color: #ffffff; }
                """)

        if indice == 0:
            self.cargar_panel_control()
        elif indice == 1:
            self.seleccionar_catalogo_maestro(self.catalogo_activo)
        elif indice == 2:
            self.seleccionar_filtro_movimientos(self.filtro_tipo_mov)

    def actualizar_boton_motor(self):
        es_pg = (self.db.motor == "postgres")
        texto = "🐘 Motor: PostgreSQL" if es_pg else "🗄️ Motor: SQL Server"
        borde = "#00e5ff" if es_pg else "#ff1a8c"
        self.btn_motor_pill.setText(texto)
        self.btn_motor_pill.setStyleSheet(f"""
            QPushButton {{
                background-color: #130d22;
                color: #ffffff;
                border: 1.5px solid {borde};
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {borde}; color: #080510; }}
        """)

    def alternar_motor_rapido(self):
        nuevo = "sqlserver" if self.db.motor == "postgres" else "postgres"
        self.cambiar_motor(nuevo)

    def cambiar_motor(self, motor: str):
        if self.db.conectar(motor):
            self.actualizar_boton_motor()
            self.ir_a_vista(self.stack.currentIndex())
        else:
            QMessageBox.warning(self, "Sin conexión", f"No se pudo conectar a {motor.upper()}. Revisa tu archivo .env.")

    # --------------------------------------------------------------------------
    # CARGA DE LA VISTA 0: PANEL DE CONTROL (KPIs + Alertas + Últimos Movimientos)
    # --------------------------------------------------------------------------
    def cargar_panel_control(self):
        es_pg = (self.db.motor == "postgres")

        # 1. Consultar Productos activos, unidades totales, valor de inventario y productos en alerta
        sql_prod = (
            "SELECT p.id_producto, p.nombre, p.precio, p.stock_actual, p.stock_minimo, "
            "COALESCE(u.nombre, 'Almacén Central') AS ubicacion, p.estado "
            "FROM productos p LEFT JOIN ubicaciones u ON p.id_ubicacion = u.id_ubicacion ORDER BY p.stock_actual ASC"
            if es_pg else
            "SELECT p.Id_Producto, p.Nombre, p.Precio, p.Stock_Actual, p.Stock_Minimo, "
            "COALESCE(u.Nombre, N'Almacén Central') AS Ubicacion, p.Estado "
            "FROM Productos p LEFT JOIN Ubicaciones u ON p.Id_Ubicacion = u.Id_Ubicacion ORDER BY p.Stock_Actual ASC"
        )
        ok, prods, _ = self.db.ejecutar_select(sql_prod)

        activos_count = 0
        unidades_tot = 0
        valor_tot = 0.0
        en_alerta = []

        for pr in prods:
            pn = {str(k).lower(): v for k, v in pr.items()}
            est = str(pn.get("estado", "True")).upper() not in ("FALSE", "0")
            stk = int(pn.get("stock_actual") or 0)
            minimo = int(pn.get("stock_minimo") or 0)
            precio = float(pn.get("precio") or 0.0)
            if est:
                activos_count += 1
                unidades_tot += stk
                valor_tot += stk * precio
                if stk <= minimo:
                    en_alerta.append(pn)

        self.kpi_prod[1].setText(str(activos_count))
        self.kpi_prod[2].setText(f"{unidades_tot} unidades, ${valor_tot:,.2f} en mercancía")

        self.kpi_alerta[1].setText(str(len(en_alerta)))
        self.kpi_alerta[2].setText(f"{len(en_alerta)} con stock bajo o agotado")

        # 2. Consultar Entradas y Salidas registradas en MovimientosInventario
        _, movs, _ = self.db.ejecutar_select(
            "SELECT mv.id_movimiento, COALESCE(p.nombre, 'Producto') AS producto, mv.tipo_movimiento, "
            "mv.cantidad, mv.fecha, COALESCE(u.nombre, 'Admin') AS usuario "
            "FROM movimientosinventario mv "
            "LEFT JOIN productos p ON mv.id_producto = p.id_producto "
            "LEFT JOIN usuarios u ON mv.id_usuario = u.id_usuario "
            "ORDER BY mv.id_movimiento DESC"
            if es_pg else
            "SELECT mv.Id_Movimiento, COALESCE(p.Nombre, N'Producto') AS Producto, mv.Tipo_Movimiento, "
            "mv.Cantidad, mv.Fecha, COALESCE(u.Nombre, N'Admin') AS Usuario "
            "FROM MovimientosInventario mv "
            "LEFT JOIN Productos p ON mv.Id_Producto = p.Id_Producto "
            "LEFT JOIN Usuarios u ON mv.Id_Usuario = u.Id_Usuario "
            "ORDER BY mv.Id_Movimiento DESC"
        )

        unidades_ent = sum(int({str(k).lower(): v for k, v in m.items()}.get("cantidad") or 0) for m in movs if str({str(k).lower(): v for k, v in m.items()}.get("tipo_movimiento", "")).upper() == "ENTRADA")
        docs_ent = sum(1 for m in movs if str({str(k).lower(): v for k, v in m.items()}.get("tipo_movimiento", "")).upper() == "ENTRADA")
        unidades_sal = sum(int({str(k).lower(): v for k, v in m.items()}.get("cantidad") or 0) for m in movs if str({str(k).lower(): v for k, v in m.items()}.get("tipo_movimiento", "")).upper() == "SALIDA")
        docs_sal = sum(1 for m in movs if str({str(k).lower(): v for k, v in m.items()}.get("tipo_movimiento", "")).upper() == "SALIDA")

        self.kpi_ent[1].setText(str(unidades_ent))
        self.kpi_ent[2].setText(f"Unidades recibidas en {docs_ent} movimientos")

        self.kpi_sal[1].setText(str(unidades_sal))
        self.kpi_sal[2].setText(f"Unidades despachadas en {docs_sal} movimientos")

        # 3. Pintar tarjetas de "Existencias que necesitan atención"
        self._limpiar_layout(self.contenedor_tarjetas_alerta)
        for item_a in en_alerta[:4]:
            self.contenedor_tarjetas_alerta.addWidget(self._crear_widget_alerta_producto(item_a))

        # 4. Pintar lista de "Últimos movimientos"
        self._limpiar_layout(self.contenedor_ultimos_movs)
        for item_m in movs[:6]:
            self.contenedor_ultimos_movs.addWidget(self._crear_widget_ultimo_mov(item_m))

    def _crear_widget_alerta_producto(self, pn: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #150d24;
                border: 1px solid #4a153b;
                border-radius: 12px;
            }
        """)
        ly = QHBoxLayout(card)
        ly.setContentsMargins(14, 12, 14, 12)
        ly.setSpacing(12)

        nom = str(pn.get("nombre", "Producto"))
        ini = "".join([w[0].upper() for w in nom.split()[:2]]) or "PR"
        stk = int(pn.get("stock_actual") or 0)
        minimo = max(1, int(pn.get("stock_minimo") or 1))
        ubic = str(pn.get("ubicacion", "Almacén Central"))

        badge = QLabel(ini)
        badge.setFixedSize(42, 42)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col_b = "#ff1a8c" if stk == 0 else "#ffee00"
        badge.setStyleSheet(f"background-color: #1c1026; color: {col_b}; border: 1.5px solid {col_b}; border-radius: 10px; font-weight: bold; font-size: 13px;")
        ly.addWidget(badge)

        ly_mid = QVBoxLayout()
        ly_mid.setSpacing(4)
        lbl_n = QLabel(nom)
        lbl_n.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px; border: none;")
        lbl_u = QLabel(f"{ubic} • Requiere reabastecimiento")
        lbl_u.setStyleSheet("color: #8a82a6; font-size: 11px; border: none;")
        ly_mid.addWidget(lbl_n)
        ly_mid.addWidget(lbl_u)

        # Barra de progreso neón
        ly_bar = QHBoxLayout()
        bar = QProgressBar()
        bar.setRange(0, minimo * 2)
        bar.setValue(min(stk, minimo * 2))
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(f"""
            QProgressBar {{ background-color: #261b38; border: none; border-radius: 3px; }}
            QProgressBar::chunk {{ background-color: #ff1a8c; border-radius: 3px; }}
        """)
        ly_bar.addWidget(bar, stretch=1)
        lbl_ratio = QLabel(f"{stk} / {minimo}")
        lbl_ratio.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 12px; border: none;")
        ly_bar.addWidget(lbl_ratio)
        ly_mid.addLayout(ly_bar)

        ly.addLayout(ly_mid, stretch=1)

        pill = QLabel("Agotado" if stk == 0 else "Stock bajo")
        pill.setStyleSheet("background-color: rgba(255, 26, 140, 28); color: #ff4d94; border: 1px solid #ff1a8c; border-radius: 10px; padding: 4px 10px; font-size: 11px; font-weight: bold;")
        ly.addWidget(pill)

        btn_add = QPushButton("↓")
        btn_add.setFixedSize(32, 32)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setToolTip("Registrar entrada rápida")
        btn_add.setStyleSheet("background-color: rgba(0, 230, 118, 22); color: #00e676; border: 1px solid #00e676; border-radius: 8px; font-weight: bold;")
        btn_add.clicked.connect(lambda: self.abrir_dialogo_movimiento("ENTRADA"))
        ly.addWidget(btn_add)

        return card

    def _crear_widget_ultimo_mov(self, m: dict) -> QFrame:
        mn = {str(k).lower(): v for k, v in m.items()}
        tipo = str(mn.get("tipo_movimiento", "ENTRADA")).upper()
        es_ent = (tipo == "ENTRADA")
        cant = int(mn.get("cantidad") or 0)
        id_m = int(mn.get("id_movimiento") or 1)
        folio = f"{'ENT' if es_ent else 'SAL'}-{id_m:04d}"

        fila = QFrame()
        fila.setStyleSheet("QFrame { background-color: transparent; border-bottom: 1px solid #1d152e; }")
        ly = QHBoxLayout(fila)
        ly.setContentsMargins(4, 6, 4, 6)

        ic = QLabel("↓" if es_ent else "↑")
        ic.setFixedSize(30, 30)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col = "#00e676" if es_ent else "#ff2a85"
        ic.setStyleSheet(f"background-color: #161024; color: {col}; border: 1px solid {col}; border-radius: 8px; font-weight: bold;")
        ly.addWidget(ic)

        ly_txt = QVBoxLayout()
        ly_txt.setSpacing(1)
        lbl_p = QLabel(str(mn.get("producto", "Producto")))
        lbl_p.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 12px; border: none;")
        lbl_f = QLabel(f"{folio} • {mn.get('usuario', 'Admin')}")
        lbl_f.setStyleSheet("color: #8a82a6; font-size: 11px; border: none;")
        ly_txt.addWidget(lbl_p)
        ly_txt.addWidget(lbl_f)
        ly.addLayout(ly_txt, stretch=1)

        ly_der = QVBoxLayout()
        ly_der.setSpacing(1)
        lbl_c = QLabel(f"{'+' if es_ent else '-'}{cant}")
        lbl_c.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_c.setStyleSheet(f"color: {col}; font-weight: bold; font-size: 13px; border: none;")
        lbl_d = QLabel(str(mn.get("fecha", ""))[:10])
        lbl_d.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_d.setStyleSheet("color: #7c7496; font-size: 11px; border: none;")
        ly_der.addWidget(lbl_c)
        ly_der.addWidget(lbl_d)
        ly.addLayout(ly_der)

        return fila

    # --------------------------------------------------------------------------
    # CARGA DE LA VISTA 1: CATÁLOGOS MAESTROS Y SUS 4 ACCIONES CRUD
    # --------------------------------------------------------------------------
    def seleccionar_catalogo_maestro(self, clave: str):
        self.catalogo_activo = clave
        for k, btn in self.botones_pestanas_cat.items():
            if k == clave:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #00e5ff;
                        color: #080510;
                        border: none;
                        border-radius: 9px;
                        padding: 8px 16px;
                        font-weight: bold;
                        font-size: 13px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #a59ec2;
                        border: none;
                        border-radius: 9px;
                        padding: 8px 16px;
                        font-size: 13px;
                    }
                    QPushButton:hover { color: #ffffff; background-color: #161026; }
                """)
        self.cargar_datos_catalogo_activo()

    def _aplicar_filtro_catalogo(self, filtro: str):
        self.filtro_estado_cat = filtro
        self.cargar_datos_catalogo_activo()

    def cargar_datos_catalogo_activo(self):
        info = CATALOGOS_MAESTROS[self.catalogo_activo]
        es_pg = (self.db.motor == "postgres")
        tabla = info["tabla_pg"] if es_pg else info["tabla_sql"]
        pk = info["pk_pg"] if es_pg else info["pk_sql"]

        # Si estamos en Productos, hacemos JOIN con Categorías, Marcas y Ubicaciones como en la captura 045854.jpg
        if self.catalogo_activo == "productos":
            sql = (
                "SELECT p.id_producto AS id, p.nombre AS producto, COALESCE(p.descripcion, '') AS descripcion, "
                "COALESCE(c.nombre, 'Sin categoría') AS categoria, COALESCE(m.nombre, 'Sin marca') AS marca, "
                "COALESCE(u.nombre, 'Almacén') AS ubicacion, p.precio, p.stock_actual, p.stock_minimo, p.estado, "
                "p.id_categoria, p.id_marca, p.id_ubicacion, p.imagen_url "
                "FROM productos p "
                "LEFT JOIN categorias c ON p.id_categoria = c.id_categoria "
                "LEFT JOIN marcas m ON p.id_marca = m.id_marca "
                "LEFT JOIN ubicaciones u ON p.id_ubicacion = u.id_ubicacion "
                "ORDER BY p.id_producto"
                if es_pg else
                "SELECT p.Id_Producto AS id, p.Nombre AS producto, COALESCE(p.Descripcion, N'') AS descripcion, "
                "COALESCE(c.Nombre, N'Sin categoría') AS categoria, COALESCE(m.Nombre, N'Sin marca') AS marca, "
                "COALESCE(u.Nombre, N'Almacén') AS ubicacion, p.Precio AS precio, p.Stock_Actual AS stock_actual, "
                "p.Stock_Minimo AS stock_minimo, p.Estado AS estado, "
                "p.Id_Categoria AS id_categoria, p.Id_Marca AS id_marca, p.Id_Ubicacion AS id_ubicacion, p.Imagen_URL AS imagen_url "
                "FROM Productos p "
                "LEFT JOIN Categorias c ON p.Id_Categoria = c.Id_Categoria "
                "LEFT JOIN Marcas m ON p.Id_Marca = m.Id_Marca "
                "LEFT JOIN Ubicaciones u ON p.Id_Ubicacion = u.Id_Ubicacion "
                "ORDER BY p.Id_Producto"
            )
            ok, registros, msg = self.db.ejecutar_select(sql)
        else:
            ok, registros, msg = self.db.consultar_catalogo(tabla, pk)

        if not ok:
            self.lbl_pie_catalogo.setText(f"❌ Error al consultar {tabla}: {msg}")
            return

        # Aplicar filtro de texto y filtro de estado
        busqueda = self.inp_buscar_cat.text().strip().lower()
        filtrados = []
        for reg in registros:
            rn = {str(k).lower(): v for k, v in reg.items()}
            if busqueda and not any(busqueda in str(v).lower() for v in rn.values() if v is not None):
                continue
            if self.filtro_estado_cat == "activos" and str(rn.get("estado", "True")).upper() in ("FALSE", "0"):
                continue
            if self.catalogo_activo == "productos":
                stk = int(rn.get("stock_actual") or 0)
                minimo = int(rn.get("stock_minimo") or 0)
                if self.filtro_estado_cat == "bajo" and not (0 < stk <= minimo):
                    continue
                if self.filtro_estado_cat == "agotado" and stk != 0:
                    continue
            filtrados.append(reg)

        self._pintar_tabla_catalogo(filtrados)
        self.lbl_pie_catalogo.setText(f"Mostrando {len(filtrados)} de {len(registros)} registros en {info['titulo']}")

    def _pintar_tabla_catalogo(self, registros: list):
        self.tabla_catalogos.clear()
        self._registros_catalogo_cache = registros

        if not registros:
            self.tabla_catalogos.setRowCount(0)
            self.tabla_catalogos.setColumnCount(1)
            self.tabla_catalogos.setHorizontalHeaderLabels(["Sin registros que coincidan con el filtro"])
            return

        if self.catalogo_activo == "productos":
            headers = ["ID", "Producto", "Categoría y marca", "Ubicación", "Precio", "Existencias", "Estado"]
            self.tabla_catalogos.setColumnCount(len(headers))
            self.tabla_catalogos.setHorizontalHeaderLabels(headers)
            self.tabla_catalogos.setRowCount(len(registros))

            for r_idx, reg in enumerate(registros):
                self.tabla_catalogos.setRowHeight(r_idx, 52)
                rn = {str(k).lower(): v for k, v in reg.items()}
                stk = int(rn.get("stock_actual") or 0)
                minimo = int(rn.get("stock_minimo") or 0)
                precio = float(rn.get("precio") or 0.0)
                activo = str(rn.get("estado", "True")).upper() not in ("FALSE", "0")

                self.tabla_catalogos.setItem(r_idx, 0, self._celda(str(rn.get("id", "")), centrado=True))
                self.tabla_catalogos.setItem(r_idx, 1, self._celda(f"{rn.get('producto', '')} — {rn.get('descripcion', '')}"))
                self.tabla_catalogos.setItem(r_idx, 2, self._celda(f"{rn.get('categoria', '')} • {rn.get('marca', '')}"))
                self.tabla_catalogos.setItem(r_idx, 3, self._celda(str(rn.get("ubicacion", ""))))
                self.tabla_catalogos.setItem(r_idx, 4, self._celda(f"${precio:,.2f}", centrado=True))

                # Columna Existencias con semáforo igual a la captura 045854.jpg
                if not activo:
                    txt_ex, col_ex = f"{stk} / {minimo}  [Inactivo]", "#8a82a6"
                elif stk <= 0:
                    txt_ex, col_ex = f"{stk} / {minimo}  [Agotado]", "#ff1744"
                elif stk <= minimo:
                    txt_ex, col_ex = f"{stk} / {minimo}  [Stock bajo]", "#ff2a85"
                else:
                    txt_ex, col_ex = f"{stk} / {minimo}  [En orden]", "#00e676"

                self.tabla_catalogos.setItem(r_idx, 5, self._celda(txt_ex, color_hex=col_ex, negrita=True, centrado=True))
                self.tabla_catalogos.setItem(
                    r_idx, 6,
                    self._celda("🟢 Activo" if activo else "🔴 Baja", color_hex="#00e676" if activo else "#ff4d6d", centrado=True)
                )
        else:
            columnas = list(registros[0].keys())
            self.tabla_catalogos.setColumnCount(len(columnas))
            self.tabla_catalogos.setHorizontalHeaderLabels([c.upper() for c in columnas])
            self.tabla_catalogos.setRowCount(len(registros))

            for r_idx, reg in enumerate(registros):
                self.tabla_catalogos.setRowHeight(r_idx, 44)
                for c_idx, c_key in enumerate(columnas):
                    val = reg.get(c_key, "")
                    texto = "" if val is None else str(val)
                    col_hex = None
                    if c_key.lower() == "estado":
                        es_act = texto.upper() in ("TRUE", "1")
                        texto = "🟢 Activo" if es_act else "🔴 Baja"
                        col_hex = "#00e676" if es_act else "#ff4d6d"
                    self.tabla_catalogos.setItem(r_idx, c_idx, self._celda(texto, color_hex=col_hex, centrado=(c_idx == 0 or c_key.lower() == "estado")))

    # --- Operaciones CRUD disparadas por botones o menú superior ---
    def ejecutar_accion_menu_catalogo(self, clave_catalogo: str, accion: str):
        self.catalogo_activo = clave_catalogo
        self.ir_a_vista(1)
        if accion == "insertar":
            self.accion_insertar_catalogo()
        elif accion == "actualizar":
            self.accion_actualizar_catalogo()
        elif accion == "eliminar":
            self.accion_eliminar_catalogo()

    def accion_insertar_catalogo(self):
        dlg = DialogoFormularioCatalogo(self, self.db, self.catalogo_activo, modo="insertar")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cargar_datos_catalogo_activo()

    def accion_actualizar_catalogo(self):
        fila_idx = self.tabla_catalogos.currentRow()
        datos_fila = {}
        if 0 <= fila_idx < len(getattr(self, "_registros_catalogo_cache", [])):
            datos_fila = self._registros_catalogo_cache[fila_idx]
            # Si estamos en productos con alias 'id' y 'producto', mapeamos a los nombres de columna
            if self.catalogo_activo == "productos":
                rn = {str(k).lower(): v for k, v in datos_fila.items()}
                datos_fila["id_producto"] = rn.get("id")
                datos_fila["nombre"] = rn.get("producto")

        dlg = DialogoFormularioCatalogo(self, self.db, self.catalogo_activo, modo="actualizar", datos_fila=datos_fila)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cargar_datos_catalogo_activo()

    def accion_eliminar_catalogo(self):
        info = CATALOGOS_MAESTROS[self.catalogo_activo]
        es_pg = (self.db.motor == "postgres")
        tabla = info["tabla_pg"] if es_pg else info["tabla_sql"]
        pk = info["pk_pg"] if es_pg else info["pk_sql"]

        fila_idx = self.tabla_catalogos.currentRow()
        if fila_idx < 0:
            QMessageBox.information(self, "Selecciona un registro", "Haz clic primero sobre la fila de la tabla que deseas eliminar o dar de baja.")
            return

        id_item = self.tabla_catalogos.item(fila_idx, 0)
        if not id_item:
            return
        id_val = int(id_item.text())

        resp = QMessageBox.question(
            self,
            "Confirmar Eliminación / Baja Lógica",
            f"¿Deseas eliminar o dar de baja el registro #{id_val} de '{info['titulo']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp == QMessageBox.StandardButton.Yes:
            ok, msg = self.db.eliminar_o_baja_catalogo(tabla, pk, id_val, tiene_estado=info["tiene_estado"])
            if ok:
                self.cargar_datos_catalogo_activo()
            else:
                QMessageBox.critical(self, "Error SQL", msg)

    # --------------------------------------------------------------------------
    # CARGA DE LA VISTA 2: HISTORIAL DE MOVIMIENTOS (IDÉNTICA A CAPTURA 045901.jpg)
    # --------------------------------------------------------------------------
    def seleccionar_filtro_movimientos(self, tipo_key: str):
        self.filtro_tipo_mov = tipo_key
        for k, btn in self.botones_filtro_mov.items():
            if k == tipo_key:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255, 238, 0, 22);
                        color: #ffee00;
                        border: 1.5px solid #ffee00;
                        border-radius: 14px;
                        padding: 6px 16px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #0b0714;
                        color: #b8b0cc;
                        border: 1px solid #2b2142;
                        border-radius: 14px;
                        padding: 6px 16px;
                        font-size: 12px;
                    }
                    QPushButton:hover { color: #ffffff; border: 1px solid #00e5ff; }
                """)
        self.cargar_datos_movimientos()

    def cargar_datos_movimientos(self):
        es_pg = (self.db.motor == "postgres")

        if self.filtro_tipo_mov == "ALERTAS":
            sql = (
                "SELECT a.id_alerta, COALESCE(p.nombre, 'Producto') AS producto, p.stock_actual, "
                "p.stock_minimo, a.tipo_alerta, a.fecha, a.estado "
                "FROM alertasinventario a LEFT JOIN productos p ON a.id_producto = p.id_producto ORDER BY a.id_alerta DESC"
                if es_pg else
                "SELECT a.Id_Alerta, COALESCE(p.Nombre, N'Producto') AS Producto, p.Stock_Actual, "
                "p.Stock_Minimo, a.Tipo_Alerta, a.Fecha, a.Estado "
                "FROM AlertasInventario a LEFT JOIN Productos p ON a.Id_Producto = p.Id_Producto ORDER BY a.Id_Alerta DESC"
            )
            ok, regs, _ = self.db.ejecutar_select(sql)
            self.tabla_movimientos.clear()
            headers = ["ID Alerta", "Producto", "Stock Actual", "Stock Mínimo", "Tipo Alerta", "Fecha", "Estado"]
            self.tabla_movimientos.setColumnCount(len(headers))
            self.tabla_movimientos.setHorizontalHeaderLabels(headers)
            self.tabla_movimientos.setRowCount(len(regs))
            for idx, r in enumerate(regs):
                self.tabla_movimientos.setRowHeight(idx, 46)
                rn = {str(k).lower(): v for k, v in r.items()}
                self.tabla_movimientos.setItem(idx, 0, self._celda(str(rn.get("id_alerta", "")), centrado=True))
                self.tabla_movimientos.setItem(idx, 1, self._celda(str(rn.get("producto", "")), negrita=True))
                self.tabla_movimientos.setItem(idx, 2, self._celda(str(rn.get("stock_actual", "")), centrado=True))
                self.tabla_movimientos.setItem(idx, 3, self._celda(str(rn.get("stock_minimo", "")), centrado=True))
                self.tabla_movimientos.setItem(idx, 4, self._celda(str(rn.get("tipo_alerta", "")), color_hex="#ff2a85", negrita=True, centrado=True))
                self.tabla_movimientos.setItem(idx, 5, self._celda(str(rn.get("fecha", ""))[:10], centrado=True))
                est_a = str(rn.get("estado", ""))
                self.tabla_movimientos.setItem(idx, 6, self._celda(est_a, color_hex="#ffee00" if est_a == "PENDIENTE" else "#00e676", negrita=True, centrado=True))
            self.lbl_resumen_movs.setText(f"{len(regs)} alertas sincronizadas automáticamente por el trigger trg_Productos_Alertas.")
            return

        # Consulta de MovimientosInventario con Proveedor (si es Entrada) o Motivo (si es Salida), igual a la captura 045901.jpg
        sql = (
            "SELECT mv.id_movimiento, mv.registrado_en, mv.fecha, mv.tipo_movimiento, "
            "COALESCE(p.nombre, 'Producto') AS producto, mv.cantidad, "
            "COALESCE(pr.nombre, ms.nombre, 'Operación directa') AS origen_detalle, "
            "COALESCE(u.nombre, 'Administrador') AS usuario "
            "FROM movimientosinventario mv "
            "LEFT JOIN productos p ON mv.id_producto = p.id_producto "
            "LEFT JOIN entradas e ON mv.id_entrada = e.id_entrada "
            "LEFT JOIN proveedores pr ON e.id_proveedor = pr.id_proveedor "
            "LEFT JOIN salidas s ON mv.id_salida = s.id_salida "
            "LEFT JOIN motivossalida ms ON s.id_motivo = ms.id_motivo "
            "LEFT JOIN usuarios u ON mv.id_usuario = u.id_usuario "
            "ORDER BY mv.id_movimiento DESC"
            if es_pg else
            "SELECT mv.Id_Movimiento, mv.Registrado_En, mv.Fecha, mv.Tipo_Movimiento, "
            "COALESCE(p.Nombre, N'Producto') AS Producto, mv.Cantidad, "
            "COALESCE(pr.Nombre, ms.Nombre, N'Operación directa') AS Origen_Detalle, "
            "COALESCE(u.Nombre, N'Administrador') AS Usuario "
            "FROM MovimientosInventario mv "
            "LEFT JOIN Productos p ON mv.Id_Producto = p.Id_Producto "
            "LEFT JOIN Entradas e ON mv.Id_Entrada = e.Id_Entrada "
            "LEFT JOIN Proveedores pr ON e.Id_Proveedor = pr.Id_Proveedor "
            "LEFT JOIN Salidas s ON mv.Id_Salida = s.Id_Salida "
            "LEFT JOIN MotivosSalida ms ON s.Id_Motivo = ms.Id_Motivo "
            "LEFT JOIN Usuarios u ON mv.Id_Usuario = u.Id_Usuario "
            "ORDER BY mv.Id_Movimiento DESC"
        )
        ok, movs, _ = self.db.ejecutar_select(sql)

        busq = self.inp_buscar_mov.text().strip().lower()
        filtrados = []
        tot_ent = tot_sal = 0

        for m in movs:
            mn = {str(k).lower(): v for k, v in m.items()}
            t_mov = str(mn.get("tipo_movimiento", "ENTRADA")).upper()
            if self.filtro_tipo_mov != "TODOS" and t_mov != self.filtro_tipo_mov:
                continue
            if busq and not any(busq in str(v).lower() for v in mn.values() if v is not None):
                continue
            cant = int(mn.get("cantidad") or 0)
            if t_mov == "ENTRADA":
                tot_ent += cant
            elif t_mov == "SALIDA":
                tot_sal += cant
            filtrados.append(mn)

        self.lbl_resumen_movs.setText(f"{len(filtrados)} movimientos: entraron {tot_ent} y salieron {tot_sal} unidades.")

        headers = ["Fecha", "Folio", "Tipo", "Producto", "Cantidad", "Proveedor o motivo", "Registró"]
        self.tabla_movimientos.clear()
        self.tabla_movimientos.setColumnCount(len(headers))
        self.tabla_movimientos.setHorizontalHeaderLabels(headers)
        self.tabla_movimientos.setRowCount(len(filtrados))

        for idx, mn in enumerate(filtrados):
            self.tabla_movimientos.setRowHeight(idx, 48)
            t_mov = str(mn.get("tipo_movimiento", "ENTRADA")).upper()
            es_ent = (t_mov == "ENTRADA")
            id_m = int(mn.get("id_movimiento") or 1)
            pref = "ENT" if es_ent else ("SAL" if t_mov == "SALIDA" else "AJU")
            folio = f"{pref}-{id_m:04d}"
            cant = int(mn.get("cantidad") or 0)
            col_t = "#00e676" if es_ent else "#ff2a85"

            self.tabla_movimientos.setItem(idx, 0, self._celda(str(mn.get("registrado_en") or mn.get("fecha", ""))[:16]))
            self.tabla_movimientos.setItem(idx, 1, self._celda(folio, negrita=True))
            self.tabla_movimientos.setItem(idx, 2, self._celda(f"{'↓ Entrada' if es_ent else '↑ Salida'}", color_hex=col_t, negrita=True, centrado=True))
            self.tabla_movimientos.setItem(idx, 3, self._celda(str(mn.get("producto", "")), negrita=True))
            self.tabla_movimientos.setItem(idx, 4, self._celda(f"{'+' if es_ent else '-'}{cant}", color_hex=col_t, negrita=True, centrado=True))
            self.tabla_movimientos.setItem(idx, 5, self._celda(str(mn.get("origen_detalle", ""))))
            self.tabla_movimientos.setItem(idx, 6, self._celda(str(mn.get("usuario", ""))))

    def abrir_dialogo_movimiento(self, tipo_mov: str):
        uid = int(self.usuario_sesion.get("id_usuario") or 1)
        dlg = DialogoMovimientoRapido(self, self.db, tipo_mov, uid)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.ir_a_vista(self.stack.currentIndex())

    @staticmethod
    def _celda(texto: str, color_hex: str = None, negrita: bool = False, centrado: bool = False) -> QTableWidgetItem:
        it = QTableWidgetItem(texto)
        if centrado:
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        if color_hex:
            it.setForeground(QBrush(QColor(color_hex)))
        if negrita:
            f = QFont("Segoe UI", 10)
            f.setBold(True)
            it.setFont(f)
        return it

    @staticmethod
    def _limpiar_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def cerrar_sesion(self):
        self.cerrando_sesion = True
        self.db.cerrar()
        self.close()
        if self.callback_logout:
            self.callback_logout()

    def closeEvent(self, event):
        if not self.cerrando_sesion:
            self.db.cerrar()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    login = VentanaLoginWebStyle()
    login.show()
    sys.exit(app.exec())