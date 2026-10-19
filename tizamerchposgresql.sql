
-- =========================================================
-- SIW TIZAMERCH · Control de inventarios
-- Script de base de datos para PostgreSQL 13 o superior
-- ---------------------------------------------------------
-- 1) Crea la base (una sola vez):   CREATE DATABASE tizamerch;
-- 2) Ejecuta este script sobre ella:
--      psql -U postgres -d tizamerch -f database.sql
--    (o ábrelo en pgAdmin > Query Tool y ejecútalo completo)
--
-- Cambios respecto al esquema original:
--  * Usuarios.Contrasena guarda un hash bcrypt (60 caracteres), nunca texto plano.
--  * Productos y Proveedores tienen columna Estado para "Dar de baja" sin borrar
--    historial (borrar físicamente rompería las llaves foráneas de los movimientos).
--  * Productos.Imagen_URL guarda la ruta de la miniatura subida desde el sistema.
--  * MovimientosInventario enlaza cada renglón con su Entrada o Salida de origen
--    y guarda la hora exacta del registro.
--  * Un trigger mantiene AlertasInventario sincronizada con el stock real.
-- =========================================================
-- =========================================================
-- ELIMINAR OBJETOS EXISTENTES (ORDEN INVERSO DE DEPENDENCIA)
-- =========================================================
DROP TABLE IF EXISTS AlertasInventario CASCADE;
DROP TABLE IF EXISTS MovimientosInventario CASCADE;
DROP TABLE IF EXISTS DetalleSalidas CASCADE;
DROP TABLE IF EXISTS Salidas CASCADE;
DROP TABLE IF EXISTS DetalleEntradas CASCADE;
DROP TABLE IF EXISTS Entradas CASCADE;
DROP TABLE IF EXISTS MotivosSalida CASCADE;
DROP TABLE IF EXISTS Usuarios CASCADE;
DROP TABLE IF EXISTS ProductosProveedores CASCADE;
DROP TABLE IF EXISTS Proveedores CASCADE;
DROP TABLE IF EXISTS Productos CASCADE;
DROP TABLE IF EXISTS Ubicaciones CASCADE;
DROP TABLE IF EXISTS Marcas CASCADE;
DROP TABLE IF EXISTS Categorias CASCADE;
DROP FUNCTION IF EXISTS fn_sincronizar_alertas() CASCADE;

-- =========================================================
-- CATÁLOGOS MAESTROS
-- =========================================================
CREATE TABLE Categorias (
    Id_Categoria INTEGER GENERATED ALWAYS AS IDENTITY,
    Nombre VARCHAR(50) NOT NULL,
    Descripcion VARCHAR(150),
    Estado BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (Id_Categoria)
);

CREATE TABLE Marcas (
    Id_Marca INTEGER GENERATED ALWAYS AS IDENTITY,
    Nombre VARCHAR(50) NOT NULL,
    Descripcion VARCHAR(150),
    Estado BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (Id_Marca)
);

CREATE TABLE Ubicaciones (
    Id_Ubicacion INTEGER GENERATED ALWAYS AS IDENTITY,
    Nombre VARCHAR(50) NOT NULL,
    Descripcion VARCHAR(150),
    Estado BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (Id_Ubicacion)
);

CREATE TABLE Productos (
    Id_Producto INTEGER GENERATED ALWAYS AS IDENTITY,
    Nombre VARCHAR(80) NOT NULL,
    Descripcion VARCHAR(200),
    Precio NUMERIC(10,2) NOT NULL,
    Stock_Actual INTEGER NOT NULL DEFAULT 0,
    Stock_Minimo INTEGER NOT NULL DEFAULT 0,
    Id_Categoria INTEGER NOT NULL,
    Id_Marca INTEGER NOT NULL,
    Id_Ubicacion INTEGER NOT NULL,
    Imagen_URL VARCHAR(255),
    Estado BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (Id_Producto),
    FOREIGN KEY (Id_Categoria) REFERENCES Categorias(Id_Categoria),
    FOREIGN KEY (Id_Marca) REFERENCES Marcas(Id_Marca),
    FOREIGN KEY (Id_Ubicacion) REFERENCES Ubicaciones(Id_Ubicacion),
    CONSTRAINT chk_Productos_Precio CHECK (Precio >= 0),
    CONSTRAINT chk_Productos_StockActual CHECK (Stock_Actual >= 0),
    CONSTRAINT chk_Productos_StockMinimo CHECK (Stock_Minimo >= 0)
);

CREATE TABLE Proveedores (
    Id_Proveedor INTEGER GENERATED ALWAYS AS IDENTITY,
    Nombre VARCHAR(80) NOT NULL,
    Telefono VARCHAR(20),
    Correo VARCHAR(100),
    Estado BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (Id_Proveedor)
);

CREATE TABLE ProductosProveedores (
    Id_ProductoProveedor INTEGER GENERATED ALWAYS AS IDENTITY,
    Id_Producto INTEGER NOT NULL,
    Id_Proveedor INTEGER NOT NULL,
    PRIMARY KEY (Id_ProductoProveedor),
    FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto),
    FOREIGN KEY (Id_Proveedor) REFERENCES Proveedores(Id_Proveedor),
    CONSTRAINT unique_ProductosProveedores UNIQUE (Id_Producto, Id_Proveedor)
);

-- =========================================================
-- SEGURIDAD
-- =========================================================
CREATE TABLE Usuarios (
    Id_Usuario INTEGER GENERATED ALWAYS AS IDENTITY,
    Nombre VARCHAR(60) NOT NULL,
    Usuario VARCHAR(30) NOT NULL,
    Contrasena VARCHAR(100) NOT NULL,          -- hash bcrypt ($2a$/$2b$...)
    Estado BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (Id_Usuario),
    CONSTRAINT unique_Usuarios_Usuario UNIQUE (Usuario)
);

-- =========================================================
-- MOVIMIENTOS DE MERCANCÍA
-- =========================================================
CREATE TABLE MotivosSalida (
    Id_Motivo INTEGER GENERATED ALWAYS AS IDENTITY,
    Nombre VARCHAR(50) NOT NULL,
    Descripcion VARCHAR(150),
    PRIMARY KEY (Id_Motivo)
);

CREATE TABLE Entradas (
    Id_Entrada INTEGER GENERATED ALWAYS AS IDENTITY,
    Fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    Id_Proveedor INTEGER NOT NULL,
    Id_Usuario INTEGER NOT NULL,
    PRIMARY KEY (Id_Entrada),
    FOREIGN KEY (Id_Proveedor) REFERENCES Proveedores(Id_Proveedor),
    FOREIGN KEY (Id_Usuario) REFERENCES Usuarios(Id_Usuario)
);

CREATE TABLE DetalleEntradas (
    Id_DetalleEntrada INTEGER GENERATED ALWAYS AS IDENTITY,
    Id_Entrada INTEGER NOT NULL,
    Id_Producto INTEGER NOT NULL,
    Cantidad INTEGER NOT NULL,
    Costo_Unitario NUMERIC(10,2) NOT NULL,
    PRIMARY KEY (Id_DetalleEntrada),
    FOREIGN KEY (Id_Entrada) REFERENCES Entradas(Id_Entrada),
    FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto),
    CONSTRAINT chk_DetalleEntradas_Cantidad CHECK (Cantidad >= 1),
    CONSTRAINT chk_DetalleEntradas_Costo CHECK (Costo_Unitario >= 0)
);

CREATE TABLE Salidas (
    Id_Salida INTEGER GENERATED ALWAYS AS IDENTITY,
    Fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    Id_Usuario INTEGER NOT NULL,
    Id_Motivo INTEGER NOT NULL,
    PRIMARY KEY (Id_Salida),
    FOREIGN KEY (Id_Usuario) REFERENCES Usuarios(Id_Usuario),
    FOREIGN KEY (Id_Motivo) REFERENCES MotivosSalida(Id_Motivo)
);

CREATE TABLE DetalleSalidas (
    Id_DetalleSalida INTEGER GENERATED ALWAYS AS IDENTITY,
    Id_Salida INTEGER NOT NULL,
    Id_Producto INTEGER NOT NULL,
    Cantidad INTEGER NOT NULL,
    PRIMARY KEY (Id_DetalleSalida),
    FOREIGN KEY (Id_Salida) REFERENCES Salidas(Id_Salida),
    FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto),
    CONSTRAINT chk_DetalleSalidas_Cantidad CHECK (Cantidad >= 1)
);

CREATE TABLE MovimientosInventario (
    Id_Movimiento INTEGER GENERATED ALWAYS AS IDENTITY,
    Id_Producto INTEGER NOT NULL,
    Tipo_Movimiento VARCHAR(20) NOT NULL,
    Cantidad INTEGER NOT NULL,
    Fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    Id_Usuario INTEGER NOT NULL,
    Id_Entrada INTEGER,                         -- origen si es ENTRADA
    Id_Salida INTEGER,                          -- origen si es SALIDA
    Registrado_En TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (Id_Movimiento),
    FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto),
    FOREIGN KEY (Id_Usuario) REFERENCES Usuarios(Id_Usuario),
    FOREIGN KEY (Id_Entrada) REFERENCES Entradas(Id_Entrada),
    FOREIGN KEY (Id_Salida) REFERENCES Salidas(Id_Salida),
    CONSTRAINT chk_Movimientos_Tipo CHECK (Tipo_Movimiento IN ('ENTRADA','SALIDA','AJUSTE')),
    CONSTRAINT chk_Movimientos_Cantidad CHECK (Cantidad >= 1)
);

CREATE TABLE AlertasInventario (
    Id_Alerta INTEGER GENERATED ALWAYS AS IDENTITY,
    Id_Producto INTEGER NOT NULL,
    Tipo_Alerta VARCHAR(20) NOT NULL,
    Fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    Estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    PRIMARY KEY (Id_Alerta),
    FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto),
    CONSTRAINT chk_Alertas_Tipo CHECK (Tipo_Alerta IN ('AGOTADO','STOCK_MINIMO')),
    CONSTRAINT chk_Alertas_Estado CHECK (Estado IN ('PENDIENTE','ATENDIDA'))
);

-- Índices para las consultas del panel y del historial
CREATE INDEX idx_Movimientos_Fecha    ON MovimientosInventario (Fecha);
CREATE INDEX idx_Movimientos_Producto ON MovimientosInventario (Id_Producto);
CREATE INDEX idx_Entradas_Fecha       ON Entradas (Fecha);
CREATE INDEX idx_Salidas_Fecha        ON Salidas (Fecha);
CREATE INDEX idx_Alertas_Pendientes   ON AlertasInventario (Id_Producto) WHERE Estado = 'PENDIENTE';

-- =========================================================
-- ALERTAS AUTOMÁTICAS DE STOCK
-- Cada vez que cambia el stock, el mínimo o el estado de un producto:
--   * stock = 0               -> alerta AGOTADO pendiente
--   * stock <= stock mínimo   -> alerta STOCK_MINIMO pendiente
--   * stock recuperado / baja -> las alertas pendientes pasan a ATENDIDA
-- =========================================================
CREATE OR REPLACE FUNCTION fn_sincronizar_alertas() RETURNS TRIGGER AS $$
DECLARE
    v_tipo VARCHAR(20);
BEGIN
    IF NOT NEW.Estado THEN
        v_tipo := NULL;
    ELSIF NEW.Stock_Actual = 0 THEN
        v_tipo := 'AGOTADO';
    ELSIF NEW.Stock_Actual <= NEW.Stock_Minimo THEN
        v_tipo := 'STOCK_MINIMO';
    ELSE
        v_tipo := NULL;
    END IF;

    UPDATE AlertasInventario
       SET Estado = 'ATENDIDA'
     WHERE Id_Producto = NEW.Id_Producto
       AND Estado = 'PENDIENTE'
       AND (v_tipo IS NULL OR Tipo_Alerta <> v_tipo);

    IF v_tipo IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM AlertasInventario
         WHERE Id_Producto = NEW.Id_Producto
           AND Estado = 'PENDIENTE'
           AND Tipo_Alerta = v_tipo
    ) THEN
        INSERT INTO AlertasInventario (Id_Producto, Tipo_Alerta, Fecha)
        VALUES (NEW.Id_Producto, v_tipo, CURRENT_DATE);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_Productos_Alertas
AFTER INSERT OR UPDATE OF Stock_Actual, Stock_Minimo, Estado ON Productos
FOR EACH ROW EXECUTE FUNCTION fn_sincronizar_alertas();

-- =========================================================
-- DATOS INICIALES
-- =========================================================
INSERT INTO Categorias (Nombre, Descripcion, Estado) VALUES
('Impresión 3D', 'Artículos y accesorios de tecnología 3D', TRUE),
('Insumos de Cafetería', 'Granos, tazas y suministros', TRUE);

INSERT INTO Marcas (Nombre, Descripcion, Estado) VALUES
('Tizamerch Tech', 'Marca oficial de gadgets 3D', TRUE),
('Café Selecto', 'Granos de origen certificado', TRUE);

INSERT INTO Ubicaciones (Nombre, Descripcion, Estado) VALUES
('Almacén Central', 'Bodega principal de distribución', TRUE),
('Estante Tienda', 'Exhibidor al público', TRUE);

INSERT INTO Proveedores (Nombre, Telefono, Correo) VALUES
('Filamentos y Más', '5511223344', 'contacto@filamentos.com'),
('Caficultores Asociados', '5599887766', 'ventas@caficultores.com');

-- Ambas cuentas usan la contraseña 123456, guardada como hash bcrypt.
-- Cámbiala en cuanto entres por primera vez.
-- Si insertas un usuario con contraseña en texto plano, server.js la
-- convierte a bcrypt automáticamente la próxima vez que arranque.
INSERT INTO Usuarios (Nombre, Usuario, Contrasena) VALUES
('Administrador General', 'admin',    '$2a$10$RJSsnw1WECu8JGNj.5k8/eYmtGS8ojqFKT88vuneEuYHQ9Iyf23wm'),
('Almacenista 1',         'operador', '$2a$10$RJSsnw1WECu8JGNj.5k8/eYmtGS8ojqFKT88vuneEuYHQ9Iyf23wm');

INSERT INTO MotivosSalida (Nombre, Descripcion) VALUES
('Venta a Cliente', 'Salida por comercialización'),
('Merma', 'Producto dañado o caducado');

-- Al insertar los productos, el trigger genera solo las alertas:
-- Llavero (5 de mínimo 10) -> STOCK_MINIMO, Figura (0) -> AGOTADO
INSERT INTO Productos (Nombre, Descripcion, Precio, Stock_Actual, Stock_Minimo, Id_Categoria, Id_Marca, Id_Ubicacion) VALUES
('Llavero Tizamerch 3D', 'Llavero personalizado en PLA', 45.00, 5, 10, 1, 1, 1),
('Figura Cyberpunk 3D', 'Figura decorativa con luces neón', 250.00, 0, 5, 1, 1, 2),
('Café Orgánico 1kg', 'Café de altura tostado medio', 180.00, 40, 10, 2, 2, 1);

INSERT INTO ProductosProveedores (Id_Producto, Id_Proveedor) VALUES (1, 1), (2, 1), (3, 2);

-- Historial de ejemplo: dos documentos de junio y dos de hoy (para ver el panel con datos)
INSERT INTO Entradas (Fecha, Id_Proveedor, Id_Usuario) VALUES
('2026-06-01', 1, 1),
(CURRENT_DATE, 2, 1);
INSERT INTO DetalleEntradas (Id_Entrada, Id_Producto, Cantidad, Costo_Unitario) VALUES
(1, 1, 20, 25.00),
(2, 3, 12, 95.00);

INSERT INTO Salidas (Fecha, Id_Usuario, Id_Motivo) VALUES
('2026-06-02', 2, 1),
(CURRENT_DATE, 2, 1);
INSERT INTO DetalleSalidas (Id_Salida, Id_Producto, Cantidad) VALUES
(1, 1, 15),
(2, 3, 2);

INSERT INTO MovimientosInventario (Id_Producto, Tipo_Movimiento, Cantidad, Fecha, Id_Usuario, Id_Entrada, Id_Salida, Registrado_En) VALUES
(1, 'ENTRADA', 20, '2026-06-01',  1, 1,    NULL, '2026-06-01 10:15'),
(1, 'SALIDA',  15, '2026-06-02',  2, NULL, 1,    '2026-06-02 17:40'),
(3, 'ENTRADA', 12, CURRENT_DATE,  1, 2,    NULL, NOW()),
(3, 'SALIDA',   2, CURRENT_DATE,  2, NULL, 2,    NOW());
