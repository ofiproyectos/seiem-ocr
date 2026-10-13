CREATE DATABASE IF NOT EXISTS seiem_filiacion
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS seiem_filiacion.solicitudes (
  id VARCHAR(36) NOT NULL PRIMARY KEY,
  folio VARCHAR(40) NULL UNIQUE,
  estado VARCHAR(30) NOT NULL DEFAULT 'borrador',
  curp VARCHAR(18) NULL,
  nombre_completo VARCHAR(220) NULL,
  correo_electronico VARCHAR(180) NULL,
  datos JSON NOT NULL,
  extracciones JSON NOT NULL,
  notas_operador TEXT NULL,
  revisado_por VARCHAR(80) NULL,
  revisado_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  INDEX idx_solicitudes_estado (estado),
  INDEX idx_solicitudes_curp (curp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS seiem_filiacion.codigos_postales (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  cp VARCHAR(5) NOT NULL,
  asentamiento VARCHAR(160) NOT NULL,
  tipo_asentamiento VARCHAR(80) NULL,
  municipio VARCHAR(120) NOT NULL,
  estado VARCHAR(120) NOT NULL,
  ciudad VARCHAR(120) NULL,
  INDEX idx_codigos_postales_cp (cp),
  INDEX idx_codigos_postales_cp_asentamiento (cp, asentamiento)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
