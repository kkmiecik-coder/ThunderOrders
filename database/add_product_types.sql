-- Create product_types table
CREATE TABLE IF NOT EXISTS product_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    slug VARCHAR(50) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_slug (slug),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add product_type_id column to products table
ALTER TABLE products
ADD COLUMN product_type_id INT NULL AFTER series_id,
ADD CONSTRAINT fk_products_product_type
    FOREIGN KEY (product_type_id) REFERENCES product_types(id)
    ON DELETE SET NULL;

-- Create index on product_type_id
CREATE INDEX idx_product_type_id ON products(product_type_id);

-- Insert product types
INSERT INTO product_types (name, slug, is_active) VALUES
('Pre-order', 'pre-order', TRUE),
('On-hand', 'on-hand', TRUE),
('Exclusive', 'exclusive', TRUE);
