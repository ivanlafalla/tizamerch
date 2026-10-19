import psycopg2
import json
import os
from dotenv import load_dotenv

# Carga las variables del archivo .env
load_dotenv()


class ConexionPostgres:

    def __init__(self):
        self.server = os.environ.get("server_name")
        self.port = os.environ.get("port", "5432")
        self.database_name = os.environ.get("database_name")
        self.user = os.environ.get("user")
        self.password = os.environ.get("password")

        self.cnx = None
        self.cursor = None

    def crear_conexion(self):
        try:
            self.cnx = psycopg2.connect(
                host=self.server,
                port=self.port,
                dbname=self.database_name,
                user=self.user,
                password=self.password
            )
            self.cursor = self.cnx.cursor()
            print(f"conectado al servidor {self.server}")
            return self.cnx
        except UnicodeDecodeError:
            # PostgreSQL rechazó la conexión, pero su mensaje en español
            # no se puede leer como UTF-8. Normalmente es contraseña,
            # puerto o nombre de base de datos incorrectos.
            print(f"error al conectarse al servidor {self.server}")
            print("Revisa usuario, contraseña, puerto y nombre de la base de datos")
            self.cnx = None
            self.cursor = None
            return None
        except psycopg2.Error as e:
            print(f"error al conectarse al servidor {self.server}")
            print(e)
            self.cnx = None
            self.cursor = None
            return None

    def ejecutar_consulta(self, sql, parametros=None):
        try:
            # Verificar conexión
            if self.cnx is None:
                # Intento conectarme
                if self.crear_conexion() is None:
                    return json.dumps(
                        {
                            "estado": False,
                            "mensaje": "No fue posible establecer la conexión"
                        },
                        ensure_ascii=False
                    )

            # Ejecutar consulta
            if parametros:
                self.cursor.execute(sql, parametros)
            else:
                self.cursor.execute(sql)

            # Identificar operación
            tipo = sql.strip().split()[0].upper()

            # SELECT
            if tipo == "SELECT":
                columnas = []
                for columna in self.cursor.description:
                    columnas.append(columna[0])

                # Obtener registros
                registros = self.cursor.fetchall()

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

                    ensure_ascii=False  # Para caracteres latinoamericanos
                )

            # INSERT
            elif tipo == "INSERT":
                filas = self.cursor.rowcount
                self.cnx.commit()
                return json.dumps(
                    {
                        "estado": True,
                        "tipo": "INSERT",
                        "mensaje": "Registro insertado correctamente",
                        "filas_afectadas": filas
                    },
                    ensure_ascii=False
                )

            # UPDATE
            elif tipo == "UPDATE":
                filas = self.cursor.rowcount
                self.cnx.commit()
                return json.dumps(
                    {
                        "estado": True,
                        "tipo": "UPDATE",
                        "mensaje": "Registro actualizado correctamente",
                        "filas_afectadas": filas
                    },
                    ensure_ascii=False
                )

            # DELETE
            elif tipo == "DELETE":
                filas = self.cursor.rowcount
                self.cnx.commit()
                return json.dumps(
                    {
                        "estado": True,
                        "tipo": "DELETE",
                        "mensaje": "Registro eliminado correctamente",
                        "filas_afectadas": filas
                    },
                    ensure_ascii=False
                )

            # OTRAS OPERACIONES
            else:
                filas = self.cursor.rowcount
                self.cnx.commit()
                return json.dumps(
                    {
                        "estado": True,
                        "tipo": tipo,
                        "mensaje": "Consulta ejecutada correctamente",
                        "filas_afectadas": filas
                    },
                    ensure_ascii=False
                )

        # ERROR DE INTEGRIDAD
        except psycopg2.IntegrityError as e:
            if self.cnx:
                self.cnx.rollback()  # Deshace los movimientos
            return json.dumps(
                {
                    "estado": False,
                    "tipo": "IntegrityError",
                    "mensaje": "Violación de integridad en la base de datos",
                    "error": str(e)
                },
                ensure_ascii=False
            )

        # ERROR DE PROGRAMACIÓN SQL
        except psycopg2.ProgrammingError as e:
            if self.cnx:
                self.cnx.rollback()
            return json.dumps(
                {
                    "estado": False,
                    "tipo": "ProgrammingError",
                    "mensaje": "Error en la consulta SQL",
                    "error": str(e)
                },
                ensure_ascii=False
            )

        # ERROR GENERAL
        except psycopg2.Error as e:
            if self.cnx:
                self.cnx.rollback()
            return json.dumps(
                {
                    "estado": False,
                    "tipo": "DatabaseError",
                    "mensaje": "Error en la base de datos",
                    "error": str(e)
                },
                ensure_ascii=False
            )

        # ERROR DE PYTHON
        except Exception as e:
            if self.cnx:
                self.cnx.rollback()
            return json.dumps(
                {
                    "estado": False,
                    "tipo": "Error",
                    "mensaje": "Error inesperado",
                    "error": str(e)
                },
                ensure_ascii=False
            )

    # Método cerrar conexión
    def cerrar_conexion(self):
        try:
            if self.cursor:
                self.cursor.close()
                self.cursor = None
            if self.cnx:
                self.cnx.close()
                self.cnx = None

            print(f"se ha cerrado la conexion con el servidor {self.server}")
            return True
        except psycopg2.Error as e:
            print("error al desconectarse del servidor de base de datos")
            print(e)
            return False


def main():
    cnn = ConexionPostgres()
    cnn.crear_conexion()
    sql = """
            SELECT 
            C.company_name, O.order_id, P.product_name,OD.quantity AS cantidad,OD.unit_price AS precio,
            OD.discount AS descuento,
            (OD.unit_price * OD.quantity * (1 - OD.discount)) AS subtotal
            FROM customers C
            INNER JOIN orders O ON C.customer_id = O.customer_id
            INNER JOIN order_details OD ON O.order_id = OD.order_id
            INNER JOIN products P ON OD.product_id = P.product_id
            where O.order_id = %(order_id)s
        """
    parametros = {"order_id" : 10248}
    result = cnn.ejecutar_consulta(sql, parametros)
    result = json.loads(result)
    cnn.cerrar_conexion()
    print(result)
    for r in result["registros"]:
      print(r)



    """# 1. Conexión
    print("--- 1. CONEXION ---")
    if cnn.crear_conexion() is None:
        return

    # 2. Crear tabla de prueba
    print("--- 2. CREATE ---")
    print(cnn.ejecutar_consulta(
        "CREATE TABLE IF NOT EXISTS prueba (id INT PRIMARY KEY, nombre VARCHAR(50), precio NUMERIC(10,2))"
    ))

    # 3. INSERT con parámetros
    print("--- 3. INSERT ---")
    print(cnn.ejecutar_consulta(
        "INSERT INTO prueba (id, nombre, precio) VALUES (%s, %s, %s)",
        (1, "Café", 25.50)
    ))
    print(cnn.ejecutar_consulta(
        "INSERT INTO prueba (id, nombre, precio) VALUES (%s, %s, %s)",
        (2, "Té", 18.00)
    ))

    # 4. SELECT
    print("--- 4. SELECT ---")
    resultado = cnn.ejecutar_consulta("SELECT * FROM prueba ORDER BY id")
    datos = json.loads(resultado)
    if datos["estado"]:
        for registro in datos["registros"]:
            print(registro)
    else:
        print(resultado)

    # 5. UPDATE
    print("--- 5. UPDATE ---")
    print(cnn.ejecutar_consulta(
        "UPDATE prueba SET precio = %s WHERE id = %s",
        (30.00, 1)
    ))

    # 6. DELETE
    print("--- 6. DELETE ---")
    print(cnn.ejecutar_consulta(
        "DELETE FROM prueba WHERE id = %s",
        (2,)
    ))

    # 7. Error de integridad (id duplicado)
    print("--- 7. ERROR DE INTEGRIDAD ---")
    print(cnn.ejecutar_consulta(
        "INSERT INTO prueba (id, nombre, precio) VALUES (%s, %s, %s)",
        (1, "Repetido", 10)
    ))

    # 8. Error de programación (tabla que no existe)
    print("--- 8. ERROR DE PROGRAMACION ---")
    print(cnn.ejecutar_consulta("SELECT * FROM tabla_que_no_existe"))

    # 9. Comprobar que la conexión sigue funcionando después de los errores
    print("--- 9. SELECT FINAL ---")
    print(cnn.ejecutar_consulta("SELECT * FROM prueba"))

    # 10. Limpiar y cerrar
    print("--- 10. LIMPIEZA ---")
    print(cnn.ejecutar_consulta("DROP TABLE prueba"))
    cnn.cerrar_conexion()"""


if __name__ == '__main__':
    main()