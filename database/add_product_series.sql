-- Create product_series table
CREATE TABLE IF NOT EXISTS product_series (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add series_id column to products table
ALTER TABLE products
ADD COLUMN series_id INT NULL AFTER manufacturer_id,
ADD CONSTRAINT fk_products_series
    FOREIGN KEY (series_id) REFERENCES product_series(id)
    ON DELETE SET NULL;

-- Create index on series_id
CREATE INDEX idx_series_id ON products(series_id);

-- Insert sample product series
INSERT INTO product_series (name, is_active) VALUES
('BT21', TRUE),
('TINY TAN', TRUE),
('Character Series', TRUE);

-- Optional: Migrate existing series data from string to FK
-- This will create series entries from existing string values and link products
-- UPDATE products p
-- LEFT JOIN product_series ps ON p.series = ps.name
-- SET p.series_id = ps.id
-- WHERE p.series IS NOT NULL AND p.series != '';

-- After migration, you can optionally drop the old series column:
-- ALTER TABLE products DROP COLUMN series;
