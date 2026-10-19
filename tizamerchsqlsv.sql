/* =========================================================
   SIW TIZAMERCH · Control de inventarios
   Script para Microsoft SQL Server 2012 o superior (incluye Express)
   ---------------------------------------------------------
   Ejecútalo completo en SSMS (F5) estando conectado a "master".
   El bloque 1 BORRA la base Tizamerch si ya existe y la crea de nuevo.

   Cambios respecto al esquema original:
    * Usuarios.Contrasena guarda un hash bcrypt (60 caracteres), nunca texto plano.
    * Productos y Proveedores tienen columna Estado para "Dar de baja" sin borrar
      historial (borrar físicamente rompería las llaves foráneas de los movimientos).
    * Productos.Imagen_URL guarda la ruta de la miniatura subida desde el sistema.
    * MovimientosInventario enlaza cada renglón con su Entrada o Salida de origen
      y guarda la fecha y hora exactas del registro.
    * Un trigger mantiene AlertasInventario sincronizada con el stock real.

   Equivalencias PostgreSQL -> SQL Server usadas:
    GENERATED ALWAYS AS IDENTITY -> IDENTITY(1,1)
    BOOLEAN / TRUE / FALSE       -> BIT / 1 / 0
    NUMERIC(10,2)                -> DECIMAL(10,2)
    VARCHAR (con acentos)        -> NVARCHAR y textos N'...'
    CURRENT_DATE / NOW()         -> CAST(GETDATE() AS DATE) / SYSDATETIME()
    TIMESTAMP                    -> DATETIME2(0)  (en SQL Server TIMESTAMP es otra cosa)
   ========================================================= */

/* =========================================================
   1) BORRAR LA BASE ANTERIOR (SI EXISTE) Y CREARLA DE NUEVO
   ========================================================= */
USE master;
GO

IF DB_ID(N'Tizamerch') IS NOT NULL
BEGIN
    -- Cierra conexiones abiertas (SSMS, VS Code, etc.) para poder borrarla
    ALTER DATABASE Tizamerch SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE Tizamerch;
END
GO

CREATE DATABASE Tizamerch;
GO

USE Tizamerch;
GO

/* =========================================================
   2) CATÁLOGOS MAESTROS
   ========================================================= */
CREATE TABLE Categorias (
    Id_Categoria INT IDENTITY(1,1) NOT NULL,
    Nombre NVARCHAR(50) NOT NULL,
    Descripcion NVARCHAR(150) NULL,
    Estado BIT NOT NULL CONSTRAINT DF_Categorias_Estado DEFAULT 1,
    CONSTRAINT PK_Categorias PRIMARY KEY (Id_Categoria)
);

CREATE TABLE Marcas (
    Id_Marca INT IDENTITY(1,1) NOT NULL,
    Nombre NVARCHAR(50) NOT NULL,
    Descripcion NVARCHAR(150) NULL,
    Estado BIT NOT NULL CONSTRAINT DF_Marcas_Estado DEFAULT 1,
    CONSTRAINT PK_Marcas PRIMARY KEY (Id_Marca)
);

CREATE TABLE Ubicaciones (
    Id_Ubicacion INT IDENTITY(1,1) NOT NULL,
    Nombre NVARCHAR(50) NOT NULL,
    Descripcion NVARCHAR(150) NULL,
    Estado BIT NOT NULL CONSTRAINT DF_Ubicaciones_Estado DEFAULT 1,
    CONSTRAINT PK_Ubicaciones PRIMARY KEY (Id_Ubicacion)
);

CREATE TABLE Productos (
    Id_Producto INT IDENTITY(1,1) NOT NULL,
    Nombre NVARCHAR(80) NOT NULL,
    Descripcion NVARCHAR(200) NULL,
    Precio DECIMAL(10,2) NOT NULL,
    Stock_Actual INT NOT NULL CONSTRAINT DF_Productos_StockActual DEFAULT 0,
    Stock_Minimo INT NOT NULL CONSTRAINT DF_Productos_StockMinimo DEFAULT 0,
    Id_Categoria INT NOT NULL,
    Id_Marca INT NOT NULL,
    Id_Ubicacion INT NOT NULL,
    Imagen_URL NVARCHAR(255) NULL,
    Estado BIT NOT NULL CONSTRAINT DF_Productos_Estado DEFAULT 1,
    CONSTRAINT PK_Productos PRIMARY KEY (Id_Producto),
    CONSTRAINT FK_Productos_Categorias  FOREIGN KEY (Id_Categoria) REFERENCES Categorias(Id_Categoria),
    CONSTRAINT FK_Productos_Marcas      FOREIGN KEY (Id_Marca)     REFERENCES Marcas(Id_Marca),
    CONSTRAINT FK_Productos_Ubicaciones FOREIGN KEY (Id_Ubicacion) REFERENCES Ubicaciones(Id_Ubicacion),
    CONSTRAINT chk_Productos_Precio      CHECK (Precio >= 0),
    CONSTRAINT chk_Productos_StockActual CHECK (Stock_Actual >= 0),
    CONSTRAINT chk_Productos_StockMinimo CHECK (Stock_Minimo >= 0)
);

CREATE TABLE Proveedores (
    Id_Proveedor INT IDENTITY(1,1) NOT NULL,
    Nombre NVARCHAR(80) NOT NULL,
    Telefono NVARCHAR(20) NULL,
    Correo NVARCHAR(100) NULL,
    Estado BIT NOT NULL CONSTRAINT DF_Proveedores_Estado DEFAULT 1,
    CONSTRAINT PK_Proveedores PRIMARY KEY (Id_Proveedor)
);

CREATE TABLE ProductosProveedores (
    Id_ProductoProveedor INT IDENTITY(1,1) NOT NULL,
    Id_Producto INT NOT NULL,
    Id_Proveedor INT NOT NULL,
    CONSTRAINT PK_ProductosProveedores PRIMARY KEY (Id_ProductoProveedor),
    CONSTRAINT FK_ProductosProveedores_Productos   FOREIGN KEY (Id_Producto)  REFERENCES Productos(Id_Producto),
    CONSTRAINT FK_ProductosProveedores_Proveedores FOREIGN KEY (Id_Proveedor) REFERENCES Proveedores(Id_Proveedor),
    CONSTRAINT unique_ProductosProveedores UNIQUE (Id_Producto, Id_Proveedor)
);

/* =========================================================
   3) SEGURIDAD
   ========================================================= */
CREATE TABLE Usuarios (
    Id_Usuario INT IDENTITY(1,1) NOT NULL,
    Nombre NVARCHAR(60) NOT NULL,
    Usuario NVARCHAR(30) NOT NULL,
    Contrasena VARCHAR(100) NOT NULL,          -- hash bcrypt ($2a$/$2b$...)
    Estado BIT NOT NULL CONSTRAINT DF_Usuarios_Estado DEFAULT 1,
    CONSTRAINT PK_Usuarios PRIMARY KEY (Id_Usuario),
    CONSTRAINT unique_Usuarios_Usuario UNIQUE (Usuario)
);

/* =========================================================
   4) MOVIMIENTOS DE MERCANCÍA
   ========================================================= */
CREATE TABLE MotivosSalida (
    Id_Motivo INT IDENTITY(1,1) NOT NULL,
    Nombre NVARCHAR(50) NOT NULL,
    Descripcion NVARCHAR(150) NULL,
    CONSTRAINT PK_MotivosSalida PRIMARY KEY (Id_Motivo)
);

CREATE TABLE Entradas (
    Id_Entrada INT IDENTITY(1,1) NOT NULL,
    Fecha DATE NOT NULL CONSTRAINT DF_Entradas_Fecha DEFAULT CAST(GETDATE() AS DATE),
    Id_Proveedor INT NOT NULL,
    Id_Usuario INT NOT NULL,
    CONSTRAINT PK_Entradas PRIMARY KEY (Id_Entrada),
    CONSTRAINT FK_Entradas_Proveedores FOREIGN KEY (Id_Proveedor) REFERENCES Proveedores(Id_Proveedor),
    CONSTRAINT FK_Entradas_Usuarios    FOREIGN KEY (Id_Usuario)   REFERENCES Usuarios(Id_Usuario)
);

CREATE TABLE DetalleEntradas (
    Id_DetalleEntrada INT IDENTITY(1,1) NOT NULL,
    Id_Entrada INT NOT NULL,
    Id_Producto INT NOT NULL,
    Cantidad INT NOT NULL,
    Costo_Unitario DECIMAL(10,2) NOT NULL,
    CONSTRAINT PK_DetalleEntradas PRIMARY KEY (Id_DetalleEntrada),
    CONSTRAINT FK_DetalleEntradas_Entradas  FOREIGN KEY (Id_Entrada)  REFERENCES Entradas(Id_Entrada),
    CONSTRAINT FK_DetalleEntradas_Productos FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto),
    CONSTRAINT chk_DetalleEntradas_Cantidad CHECK (Cantidad >= 1),
    CONSTRAINT chk_DetalleEntradas_Costo    CHECK (Costo_Unitario >= 0)
);

CREATE TABLE Salidas (
    Id_Salida INT IDENTITY(1,1) NOT NULL,
    Fecha DATE NOT NULL CONSTRAINT DF_Salidas_Fecha DEFAULT CAST(GETDATE() AS DATE),
    Id_Usuario INT NOT NULL,
    Id_Motivo INT NOT NULL,
    CONSTRAINT PK_Salidas PRIMARY KEY (Id_Salida),
    CONSTRAINT FK_Salidas_Usuarios      FOREIGN KEY (Id_Usuario) REFERENCES Usuarios(Id_Usuario),
    CONSTRAINT FK_Salidas_MotivosSalida FOREIGN KEY (Id_Motivo)  REFERENCES MotivosSalida(Id_Motivo)
);

CREATE TABLE DetalleSalidas (
    Id_DetalleSalida INT IDENTITY(1,1) NOT NULL,
    Id_Salida INT NOT NULL,
    Id_Producto INT NOT NULL,
    Cantidad INT NOT NULL,
    CONSTRAINT PK_DetalleSalidas PRIMARY KEY (Id_DetalleSalida),
    CONSTRAINT FK_DetalleSalidas_Salidas   FOREIGN KEY (Id_Salida)   REFERENCES Salidas(Id_Salida),
    CONSTRAINT FK_DetalleSalidas_Productos FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto),
    CONSTRAINT chk_DetalleSalidas_Cantidad CHECK (Cantidad >= 1)
);

CREATE TABLE MovimientosInventario (
    Id_Movimiento INT IDENTITY(1,1) NOT NULL,
    Id_Producto INT NOT NULL,
    Tipo_Movimiento VARCHAR(20) NOT NULL,
    Cantidad INT NOT NULL,
    Fecha DATE NOT NULL CONSTRAINT DF_Movimientos_Fecha DEFAULT CAST(GETDATE() AS DATE),
    Id_Usuario INT NOT NULL,
    Id_Entrada INT NULL,                        -- origen si es ENTRADA
    Id_Salida INT NULL,                         -- origen si es SALIDA
    Registrado_En DATETIME2(0) NOT NULL CONSTRAINT DF_Movimientos_Registrado DEFAULT SYSDATETIME(),
    CONSTRAINT PK_MovimientosInventario PRIMARY KEY (Id_Movimiento),
    CONSTRAINT FK_Movimientos_Productos FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto),
    CONSTRAINT FK_Movimientos_Usuarios  FOREIGN KEY (Id_Usuario)  REFERENCES Usuarios(Id_Usuario),
    CONSTRAINT FK_Movimientos_Entradas  FOREIGN KEY (Id_Entrada)  REFERENCES Entradas(Id_Entrada),
    CONSTRAINT FK_Movimientos_Salidas   FOREIGN KEY (Id_Salida)   REFERENCES Salidas(Id_Salida),
    CONSTRAINT chk_Movimientos_Tipo     CHECK (Tipo_Movimiento IN ('ENTRADA','SALIDA','AJUSTE')),
    CONSTRAINT chk_Movimientos_Cantidad CHECK (Cantidad >= 1)
);

CREATE TABLE AlertasInventario (
    Id_Alerta INT IDENTITY(1,1) NOT NULL,
    Id_Producto INT NOT NULL,
    Tipo_Alerta VARCHAR(20) NOT NULL,
    Fecha DATE NOT NULL CONSTRAINT DF_Alertas_Fecha DEFAULT CAST(GETDATE() AS DATE),
    Estado VARCHAR(20) NOT NULL CONSTRAINT DF_Alertas_Estado DEFAULT 'PENDIENTE',
    CONSTRAINT PK_AlertasInventario PRIMARY KEY (Id_Alerta),
    CONSTRAINT FK_Alertas_Productos FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto),
    CONSTRAINT chk_Alertas_Tipo   CHECK (Tipo_Alerta IN ('AGOTADO','STOCK_MINIMO')),
    CONSTRAINT chk_Alertas_Estado CHECK (Estado IN ('PENDIENTE','ATENDIDA'))
);

-- Índices para las consultas del panel y del historial
CREATE INDEX idx_Movimientos_Fecha    ON MovimientosInventario (Fecha);
CREATE INDEX idx_Movimientos_Producto ON MovimientosInventario (Id_Producto);
CREATE INDEX idx_Entradas_Fecha       ON Entradas (Fecha);
CREATE INDEX idx_Salidas_Fecha        ON Salidas (Fecha);
CREATE INDEX idx_Alertas_Pendientes   ON AlertasInventario (Id_Producto) WHERE Estado = 'PENDIENTE';
GO

/* =========================================================
   5) ALERTAS AUTOMÁTICAS DE STOCK
   Cada vez que cambia el stock, el mínimo o el estado de un producto:
     * stock = 0               -> alerta AGOTADO pendiente
     * stock <= stock mínimo   -> alerta STOCK_MINIMO pendiente
     * stock recuperado / baja -> las alertas pendientes pasan a ATENDIDA
   En SQL Server el trigger se ejecuta una vez por instrucción, así que
   trabaja con todas las filas de la tabla virtual "inserted" a la vez.
   ========================================================= */
CREATE TRIGGER trg_Productos_Alertas
ON Productos
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT (UPDATE(Stock_Actual) OR UPDATE(Stock_Minimo) OR UPDATE(Estado))
        RETURN;

    DECLARE @Situacion TABLE (
        Id_Producto INT PRIMARY KEY,
        Tipo VARCHAR(20) NULL
    );

    INSERT INTO @Situacion (Id_Producto, Tipo)
    SELECT i.Id_Producto,
           CASE WHEN i.Estado = 0                    THEN NULL
                WHEN i.Stock_Actual = 0              THEN 'AGOTADO'
                WHEN i.Stock_Actual <= i.Stock_Minimo THEN 'STOCK_MINIMO'
                ELSE NULL
           END
      FROM inserted AS i;

    -- Cierra las alertas que ya no corresponden
    UPDATE a
       SET a.Estado = 'ATENDIDA'
      FROM AlertasInventario AS a
      JOIN @Situacion AS s ON s.Id_Producto = a.Id_Producto
     WHERE a.Estado = 'PENDIENTE'
       AND (s.Tipo IS NULL OR a.Tipo_Alerta <> s.Tipo);

    -- Abre la alerta nueva si no hay una igual pendiente
    INSERT INTO AlertasInventario (Id_Producto, Tipo_Alerta, Fecha)
    SELECT s.Id_Producto, s.Tipo, CAST(GETDATE() AS DATE)
      FROM @Situacion AS s
     WHERE s.Tipo IS NOT NULL
       AND NOT EXISTS (
            SELECT 1 FROM AlertasInventario AS a
             WHERE a.Id_Producto = s.Id_Producto
               AND a.Estado = 'PENDIENTE'
               AND a.Tipo_Alerta = s.Tipo
       );
END;
GO

/* =========================================================
   6) DATOS INICIALES
   ========================================================= */
INSERT INTO Categorias (Nombre, Descripcion, Estado) VALUES
(N'Impresión 3D', N'Artículos y accesorios de tecnología 3D', 1),
(N'Insumos de Cafetería', N'Granos, tazas y suministros', 1);

INSERT INTO Marcas (Nombre, Descripcion, Estado) VALUES
(N'Tizamerch Tech', N'Marca oficial de gadgets 3D', 1),
(N'Café Selecto', N'Granos de origen certificado', 1);

INSERT INTO Ubicaciones (Nombre, Descripcion, Estado) VALUES
(N'Almacén Central', N'Bodega principal de distribución', 1),
(N'Estante Tienda', N'Exhibidor al público', 1);

INSERT INTO Proveedores (Nombre, Telefono, Correo) VALUES
(N'Filamentos y Más', N'5511223344', N'contacto@filamentos.com'),
(N'Caficultores Asociados', N'5599887766', N'ventas@caficultores.com');

-- Ambas cuentas usan la contraseña 123456, guardada como hash bcrypt.
-- Cámbiala en cuanto entres por primera vez.
INSERT INTO Usuarios (Nombre, Usuario, Contrasena) VALUES
(N'Administrador General', N'admin',    '$2a$10$RJSsnw1WECu8JGNj.5k8/eYmtGS8ojqFKT88vuneEuYHQ9Iyf23wm'),
(N'Almacenista 1',         N'operador', '$2a$10$RJSsnw1WECu8JGNj.5k8/eYmtGS8ojqFKT88vuneEuYHQ9Iyf23wm');

INSERT INTO MotivosSalida (Nombre, Descripcion) VALUES
(N'Venta a Cliente', N'Salida por comercialización'),
(N'Merma', N'Producto dañado o caducado');

-- Al insertar los productos, el trigger genera solo las alertas:
-- Llavero (5 de mínimo 10) -> STOCK_MINIMO, Figura (0) -> AGOTADO
INSERT INTO Productos (Nombre, Descripcion, Precio, Stock_Actual, Stock_Minimo, Id_Categoria, Id_Marca, Id_Ubicacion) VALUES
(N'Llavero Tizamerch 3D', N'Llavero personalizado en PLA', 45.00, 5, 10, 1, 1, 1),
(N'Figura Cyberpunk 3D', N'Figura decorativa con luces neón', 250.00, 0, 5, 1, 1, 2),
(N'Café Orgánico 1kg', N'Café de altura tostado medio', 180.00, 40, 10, 2, 2, 1);

INSERT INTO ProductosProveedores (Id_Producto, Id_Proveedor) VALUES (1, 1), (2, 1), (3, 2);

-- Historial de ejemplo: dos documentos de junio y dos de hoy (para ver el panel con datos)
INSERT INTO Entradas (Fecha, Id_Proveedor, Id_Usuario) VALUES
('2026-06-01', 1, 1),
(CAST(GETDATE() AS DATE), 2, 1);
INSERT INTO DetalleEntradas (Id_Entrada, Id_Producto, Cantidad, Costo_Unitario) VALUES
(1, 1, 20, 25.00),
(2, 3, 12, 95.00);

INSERT INTO Salidas (Fecha, Id_Usuario, Id_Motivo) VALUES
('2026-06-02', 2, 1),
(CAST(GETDATE() AS DATE), 2, 1);
INSERT INTO DetalleSalidas (Id_Salida, Id_Producto, Cantidad) VALUES
(1, 1, 15),
(2, 3, 2);

INSERT INTO MovimientosInventario (Id_Producto, Tipo_Movimiento, Cantidad, Fecha, Id_Usuario, Id_Entrada, Id_Salida, Registrado_En) VALUES
(1, 'ENTRADA', 20, '2026-06-01',            1, 1,    NULL, '2026-06-01T10:15:00'),
(1, 'SALIDA',  15, '2026-06-02',            2, NULL, 1,    '2026-06-02T17:40:00'),
(3, 'ENTRADA', 12, CAST(GETDATE() AS DATE), 1, 2,    NULL, SYSDATETIME()),
(3, 'SALIDA',   2, CAST(GETDATE() AS DATE), 2, NULL, 2,    SYSDATETIME());
GO

/* =========================================================
   7) VERIFICACIÓN RÁPIDA
   Debe mostrar 3 productos y 2 alertas pendientes.
   ========================================================= */
SELECT Id_Producto, Nombre, Stock_Actual, Stock_Minimo FROM Productos;
SELECT a.Id_Alerta, p.Nombre, a.Tipo_Alerta, a.Estado
  FROM AlertasInventario AS a
  JOIN Productos AS p ON p.Id_Producto = a.Id_Producto;
GO