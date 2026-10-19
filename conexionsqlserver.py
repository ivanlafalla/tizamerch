import os
import mssql_python
import json
from dotenv import load_dotenv

load_dotenv()

class ConexionSqlServer():
    def __init__(self):
        self.SERVER = os.getenv("SQL_SERVER")
        self.DATABASE_NAME = os.getenv("SQL_DB")

        self.CNX = None 
        self.CURSOR = None 

    def crear_conexion(self):
        try:
            # Cadena de conexión para Autenticación de Windows
            cadena_conexion = (
                f"Server={self.SERVER};"
                f"Database={self.DATABASE_NAME};"
                "Trusted_Connection=yes;"
                "Encrypt=yes;"
                "TrustServerCertificate=yes;"
            )

            self.CNX = mssql_python.connect(cadena_conexion)
            self.CURSOR = self.CNX.cursor()
            print(f"Conectado al servidor {self.SERVER} con Autenticación de Windows")
            return self.CNX
        except mssql_python.Error as e:
            print(f"Error al conectarse al servidor {self.SERVER}")
            print(e)
            self.CNX = None
            self.CURSOR = None
            return None
        
    def ejecutar(self, sql, parametros=None):
        try:
            if self.CNX is None:
                if self.crear_conexion() is None:
                    return json.dumps(
                        {
                            "estado": False,
                            "mensaje": "No fue posible establecer la conexión"
                        },
                        ensure_ascii=False
                    )
 
            if parametros:
                self.CURSOR.execute(sql, parametros)
            else:
                self.CURSOR.execute(sql)
 
            tipo = sql.strip().split()[0].upper()
            
            if tipo == "SELECT":
                columnas = [columna[0] for columna in self.CURSOR.description]
                registros = self.CURSOR.fetchall()
 
                resultado = []
                for registro in registros:
                    fila = {}
                    for i, valor in enumerate(registro):
                        fila[columnas[i]] = valor
                    resultado.append(fila)
 
                return json.dumps(
                    {
                        "estado": True,
                        "tipo": "SELECT",
                        "registros": resultado
                    },
                    default=str,
                    ensure_ascii=False
                )
            elif tipo in ["INSERT", "UPDATE", "DELETE"]:
                filas = self.CURSOR.rowcount
                self.CNX.commit()
                return json.dumps(
                    {
                        "estado": True,
                        "tipo": tipo,
                        "mensaje": f"Registro {tipo.lower()} correctamente",
                        "filas_afectadas": filas
                    },
                    ensure_ascii=False
                )
            else:
                filas = self.CURSOR.rowcount
                self.CNX.commit()
                return json.dumps(
                    {
                        "estado": True,
                        "tipo": tipo,
                        "mensaje": "Consulta ejecutada correctamente",
                        "filas_afectadas": filas
                    },
                    ensure_ascii=False
                )
        except mssql_python.IntegrityError as e:
            if self.CNX:
                self.CNX.rollback()
            return json.dumps({"estado": False, "tipo": "IntegrityError", "mensaje": "Violación de integridad", "error": str(e)}, ensure_ascii=False)
        except mssql_python.ProgrammingError as e:
            if self.CNX:
                self.CNX.rollback()
            return json.dumps({"estado": False, "tipo": "ProgrammingError", "mensaje": "Error en la consulta SQL", "error": str(e)}, ensure_ascii=False)
        except mssql_python.Error as e:
            if self.CNX:
                self.CNX.rollback()
            return json.dumps({"estado": False, "tipo": "DatabaseError", "mensaje": "Error en la base de datos", "error": str(e)}, ensure_ascii=False)
        except Exception as e:
            if self.CNX:
                self.CNX.rollback()
            return json.dumps({"estado": False, "tipo": "Error", "mensaje": "Error inesperado", "error": str(e)}, ensure_ascii=False)

    def ejecutar_consulta(self, sql, parametros=None):
        return self.ejecutar(sql, parametros)

    def cerrar_conexion(self):
        try:
            if self.CURSOR:
                self.CURSOR.close()
                self.CURSOR = None

            if self.CNX:
                self.CNX.close()
                self.CNX = None

            print(f"Se ha cerrado la conexión al servidor {self.SERVER}")
            return True
        except mssql_python.Error as e:
            print("Error al desconectarse del servidor de Base de Datos")
            print(e)
            return False

if __name__ == '__main__':
    cnn = ConexionSqlServer()
    # cnn.crear_conexion()
    # cnn.cerrar_conexion()
    sql1 = "select * from Products"
    sql2 = " DELETE Categories WHERE CategoryID=5"
    sql3 = "UPDATE Products SET UnitPrice = UnitPrice * 1.20 WHERE ProductID=30"
    sql4 = "este-es-un-mensaje-para-separar/por-cadenas"
    a = sql1.split()[0].upper()
    print(a)