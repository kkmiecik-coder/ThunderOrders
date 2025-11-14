-- Create manufacturers table
CREATE TABLE IF NOT EXISTS manufacturers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add manufacturer_id column to products table
ALTER TABLE products
ADD COLUMN manufacturer_id INT NULL AFTER category_id,
ADD CONSTRAINT fk_products_manufacturer
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(id)
    ON DELETE SET NULL;

-- Create index on manufacturer_id
CREATE INDEX idx_manufacturer_id ON products(manufacturer_id);

-- Insert sample manufacturers
INSERT INTO manufacturers (name, is_active) VALUES
('BT21', TRUE),
('LINE FRIENDS', TRUE),
('Sanrio', TRUE);

-- Optional: Migrate existing manufacturer data from string to FK
-- This will create manufacturer entries from existing string values and link products
-- UPDATE products p
-- LEFT JOIN manufacturers m ON p.manufacturer = m.name
-- SET p.manufacturer_id = m.id
-- WHERE p.manufacturer IS NOT NULL AND p.manufacturer != '';

-- After migration, you can optionally drop the old manufacturer column:
-- ALTER TABLE products DROP COLUMN manufacturer;
