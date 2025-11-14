-- ==========================================
-- ThunderOrders - Products Module Migration
-- Migration: 002_products_module.sql
-- Created: 2025-11-02
-- ==========================================

-- Table: categories
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_id INT DEFAULT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    sort_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE CASCADE,

    INDEX idx_parent_id (parent_id),
    INDEX idx_slug (slug),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: suppliers
CREATE TABLE IF NOT EXISTS suppliers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    contact_email VARCHAR(255) DEFAULT NULL,
    contact_phone VARCHAR(20) DEFAULT NULL,
    country VARCHAR(100) DEFAULT NULL,
    notes TEXT DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_name (name),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: tags
CREATE TABLE IF NOT EXISTS tags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: products
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    sku VARCHAR(100) UNIQUE DEFAULT NULL,
    ean VARCHAR(13) DEFAULT NULL,

    -- Taxonomy
    category_id INT DEFAULT NULL,
    manufacturer VARCHAR(100) DEFAULT NULL,
    series VARCHAR(100) DEFAULT NULL,

    -- Physical properties
    length DECIMAL(8, 2) DEFAULT NULL COMMENT 'Length in cm',
    width DECIMAL(8, 2) DEFAULT NULL COMMENT 'Width in cm',
    height DECIMAL(8, 2) DEFAULT NULL COMMENT 'Height in cm',
    weight DECIMAL(8, 2) DEFAULT NULL COMMENT 'Weight in kg',

    -- Pricing
    sale_price DECIMAL(10, 2) NOT NULL,
    purchase_price DECIMAL(10, 2) DEFAULT NULL,
    purchase_currency ENUM('PLN', 'KRW', 'USD') DEFAULT 'PLN',
    purchase_price_pln DECIMAL(10, 2) DEFAULT NULL COMMENT 'Converted price in PLN',
    margin DECIMAL(5, 2) DEFAULT NULL COMMENT 'Margin percentage',

    -- Stock
    quantity INT DEFAULT 0,
    supplier_id INT DEFAULT NULL,

    -- Variants
    variant_group VARCHAR(50) DEFAULT NULL COMMENT 'Grouping ID for product variants',

    -- Description
    description TEXT DEFAULT NULL,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL,

    INDEX idx_name (name),
    INDEX idx_sku (sku),
    INDEX idx_ean (ean),
    INDEX idx_category_id (category_id),
    INDEX idx_supplier_id (supplier_id),
    INDEX idx_variant_group (variant_group),
    INDEX idx_is_active (is_active),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: product_images
CREATE TABLE IF NOT EXISTS product_images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    path_original VARCHAR(500) NOT NULL,
    path_compressed VARCHAR(500) NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    sort_order INT DEFAULT 0,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,

    INDEX idx_product_id (product_id),
    INDEX idx_is_primary (is_primary),
    INDEX idx_sort_order (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: product_tags (junction table)
CREATE TABLE IF NOT EXISTS product_tags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    tag_id INT NOT NULL,

    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,

    UNIQUE KEY unique_product_tag (product_id, tag_id),
    INDEX idx_product_id (product_id),
    INDEX idx_tag_id (tag_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==========================================
-- Seed Data - Sample Categories (SKIP - already exists)
-- ==========================================
-- Categories already seeded in previous migration

-- ==========================================
-- Seed Data - Sample Tags
-- ==========================================
INSERT IGNORE INTO tags (name) VALUES
('Nowość'),
('Bestseller'),
('Promocja'),
('Limited Edition'),
('Ekskluzywne'),
('BTS'),
('BLACKPINK'),
('K-pop'),
('Anime'),
('Kawaii');

-- ==========================================
-- Seed Data - Sample Suppliers
-- ==========================================
INSERT IGNORE INTO suppliers (name, contact_email, contact_phone, country, notes, is_active) VALUES
('Korea Shop Ltd.', 'orders@koreashop.kr', '+82-2-1234-5678', 'Korea Południowa', 'Główny dostawca produktów BT21 i Line Friends', TRUE),
('Tokyo Merchandise Co.', 'contact@tokyomerch.jp', '+81-3-9876-5432', 'Japonia', 'Specjalizacja w figurkach anime', TRUE),
('China Wholesale Hub', 'sales@chinawholesale.cn', '+86-10-1111-2222', 'Chiny', 'Szeroki asortyment gadżetów po niskich cenach', TRUE);

-- ==========================================
-- Migration Complete
-- ==========================================
