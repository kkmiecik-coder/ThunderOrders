-- ThunderOrders Database Schema
-- Version: 1.0
-- Date: 2025-10-31
-- Engine: MariaDB 10.6+
-- Charset: utf8mb4_unicode_ci

-- Set character set
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- =============================================
-- Table: users
-- Description: User accounts (admin, mod, client)
-- =============================================
CREATE TABLE IF NOT EXISTS `users` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `email` VARCHAR(255) UNIQUE NOT NULL,
    `password_hash` VARCHAR(255) NOT NULL,
    `first_name` VARCHAR(100) NOT NULL,
    `last_name` VARCHAR(100) NOT NULL,
    `role` ENUM('admin', 'mod', 'client') DEFAULT 'client',
    `phone` VARCHAR(20),
    `is_active` BOOLEAN DEFAULT TRUE,
    `email_verified` BOOLEAN DEFAULT FALSE,
    `email_verification_token` VARCHAR(255),
    `password_reset_token` VARCHAR(255),
    `password_reset_expires` DATETIME,
    `last_login` DATETIME,
    `dark_mode_enabled` BOOLEAN DEFAULT FALSE,
    `sidebar_collapsed` BOOLEAN DEFAULT FALSE,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX `idx_email` (`email`),
    INDEX `idx_role` (`role`),
    INDEX `idx_verification_token` (`email_verification_token`),
    INDEX `idx_reset_token` (`password_reset_token`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: categories
-- Description: Product categories (hierarchical)
-- =============================================
CREATE TABLE IF NOT EXISTS `categories` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `parent_id` INT,
    `slug` VARCHAR(100) UNIQUE NOT NULL,
    `sort_order` INT DEFAULT 0,
    `is_active` BOOLEAN DEFAULT TRUE,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (`parent_id`) REFERENCES `categories`(`id`) ON DELETE CASCADE,
    INDEX `idx_parent_id` (`parent_id`),
    INDEX `idx_slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: suppliers
-- Description: Product suppliers
-- =============================================
CREATE TABLE IF NOT EXISTS `suppliers` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(200) NOT NULL,
    `contact_email` VARCHAR(255),
    `contact_phone` VARCHAR(20),
    `country` VARCHAR(100),
    `notes` TEXT,
    `is_active` BOOLEAN DEFAULT TRUE,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX `idx_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: products
-- Description: Products catalog
-- =============================================
CREATE TABLE IF NOT EXISTS `products` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(255) NOT NULL,
    `sku` VARCHAR(100) UNIQUE,
    `ean` VARCHAR(13),

    -- Taxonomy
    `category_id` INT,
    `manufacturer` VARCHAR(100),
    `series` VARCHAR(100),

    -- Physical properties
    `length` DECIMAL(8, 2),
    `width` DECIMAL(8, 2),
    `height` DECIMAL(8, 2),
    `weight` DECIMAL(8, 2),

    -- Pricing
    `sale_price` DECIMAL(10, 2) NOT NULL,
    `purchase_price` DECIMAL(10, 2),
    `purchase_currency` ENUM('PLN', 'KRW', 'USD') DEFAULT 'PLN',
    `purchase_price_pln` DECIMAL(10, 2),
    `margin` DECIMAL(5, 2),

    -- Stock
    `quantity` INT DEFAULT 0,
    `supplier_id` INT,

    -- Variants
    `variant_group` VARCHAR(50),

    -- Description
    `description` TEXT,

    -- Status
    `is_active` BOOLEAN DEFAULT TRUE,

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (`category_id`) REFERENCES `categories`(`id`) ON DELETE SET NULL,
    FOREIGN KEY (`supplier_id`) REFERENCES `suppliers`(`id`) ON DELETE SET NULL,

    INDEX `idx_sku` (`sku`),
    INDEX `idx_ean` (`ean`),
    INDEX `idx_category_id` (`category_id`),
    INDEX `idx_variant_group` (`variant_group`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: product_images
-- Description: Product images
-- =============================================
CREATE TABLE IF NOT EXISTS `product_images` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `product_id` INT NOT NULL,
    `filename` VARCHAR(255) NOT NULL,
    `path_original` VARCHAR(500) NOT NULL,
    `path_compressed` VARCHAR(500) NOT NULL,
    `is_primary` BOOLEAN DEFAULT FALSE,
    `sort_order` INT DEFAULT 0,
    `uploaded_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (`product_id`) REFERENCES `products`(`id`) ON DELETE CASCADE,

    INDEX `idx_product_id` (`product_id`),
    INDEX `idx_is_primary` (`is_primary`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: tags
-- Description: Product tags
-- =============================================
CREATE TABLE IF NOT EXISTS `tags` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(50) UNIQUE NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: product_tags (junction table)
-- Description: Product-Tag relationship
-- =============================================
CREATE TABLE IF NOT EXISTS `product_tags` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `product_id` INT NOT NULL,
    `tag_id` INT NOT NULL,

    FOREIGN KEY (`product_id`) REFERENCES `products`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`tag_id`) REFERENCES `tags`(`id`) ON DELETE CASCADE,

    UNIQUE KEY `unique_product_tag` (`product_id`, `tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: exclusive_pages
-- Description: Exclusive order pages
-- =============================================
CREATE TABLE IF NOT EXISTS `exclusive_pages` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(200) NOT NULL,
    `token` VARCHAR(100) UNIQUE NOT NULL,
    `description` TEXT,
    `is_active` BOOLEAN DEFAULT TRUE,
    `created_by` INT NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `expires_at` DATETIME,

    FOREIGN KEY (`created_by`) REFERENCES `users`(`id`) ON DELETE RESTRICT,

    INDEX `idx_token` (`token`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: exclusive_products (junction table)
-- Description: Products on exclusive pages
-- =============================================
CREATE TABLE IF NOT EXISTS `exclusive_products` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `exclusive_page_id` INT NOT NULL,
    `product_id` INT NOT NULL,

    FOREIGN KEY (`exclusive_page_id`) REFERENCES `exclusive_pages`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`product_id`) REFERENCES `products`(`id`) ON DELETE CASCADE,

    UNIQUE KEY `unique_exclusive_product` (`exclusive_page_id`, `product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: orders
-- Description: Customer orders
-- =============================================
CREATE TABLE IF NOT EXISTS `orders` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `order_number` VARCHAR(20) UNIQUE NOT NULL,
    `user_id` INT,
    `status` ENUM(
        'nowe',
        'oczekujace',
        'dostarczone_proxy',
        'w_drodze_polska',
        'urzad_celny',
        'dostarczone_gom',
        'do_pakowania',
        'spakowane',
        'wyslane',
        'dostarczone',
        'anulowane',
        'do_zwrotu',
        'zwrocone'
    ) DEFAULT 'nowe',
    `total_amount` DECIMAL(10, 2) NOT NULL DEFAULT 0.00,

    -- Exclusive order fields
    `is_exclusive` BOOLEAN DEFAULT FALSE,
    `exclusive_page_id` INT,

    -- Guest order fields
    `is_guest_order` BOOLEAN DEFAULT FALSE,
    `guest_email` VARCHAR(255),
    `guest_name` VARCHAR(200),
    `guest_phone` VARCHAR(20),

    -- Shipping request
    `shipping_requested` BOOLEAN DEFAULT FALSE,
    `shipping_requested_at` DATETIME,

    -- Tracking
    `tracking_number` VARCHAR(100),
    `courier` VARCHAR(50),

    -- Metadata
    `notes` TEXT,
    `admin_notes` TEXT,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE SET NULL,
    FOREIGN KEY (`exclusive_page_id`) REFERENCES `exclusive_pages`(`id`) ON DELETE SET NULL,

    INDEX `idx_order_number` (`order_number`),
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_is_exclusive` (`is_exclusive`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: order_items
-- Description: Products in orders
-- =============================================
CREATE TABLE IF NOT EXISTS `order_items` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `order_id` INT NOT NULL,
    `product_id` INT NOT NULL,
    `quantity` INT NOT NULL DEFAULT 1,
    `price` DECIMAL(10, 2) NOT NULL,
    `total` DECIMAL(10, 2) NOT NULL,

    -- WMS fields
    `picked` BOOLEAN DEFAULT FALSE,
    `picked_at` DATETIME,
    `picked_by` INT,

    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (`order_id`) REFERENCES `orders`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`product_id`) REFERENCES `products`(`id`) ON DELETE RESTRICT,
    FOREIGN KEY (`picked_by`) REFERENCES `users`(`id`) ON DELETE SET NULL,

    INDEX `idx_order_id` (`order_id`),
    INDEX `idx_product_id` (`product_id`),
    INDEX `idx_picked` (`picked`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: order_comments
-- Description: Comments on orders
-- =============================================
CREATE TABLE IF NOT EXISTS `order_comments` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `order_id` INT NOT NULL,
    `user_id` INT,
    `comment` TEXT NOT NULL,
    `is_internal` BOOLEAN DEFAULT FALSE,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (`order_id`) REFERENCES `orders`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE SET NULL,

    INDEX `idx_order_id` (`order_id`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: order_refunds
-- Description: Order refunds
-- =============================================
CREATE TABLE IF NOT EXISTS `order_refunds` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `order_id` INT NOT NULL,
    `amount` DECIMAL(10, 2) NOT NULL,
    `reason` TEXT NOT NULL,
    `status` ENUM('pending', 'completed', 'cancelled') DEFAULT 'pending',
    `created_by` INT NOT NULL,
    `completed_at` DATETIME,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (`order_id`) REFERENCES `orders`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`created_by`) REFERENCES `users`(`id`) ON DELETE RESTRICT,

    INDEX `idx_order_id` (`order_id`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: order_templates
-- Description: Saved order templates
-- =============================================
CREATE TABLE IF NOT EXISTS `order_templates` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `name` VARCHAR(200) NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,

    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: order_template_items (junction table)
-- Description: Products in order templates
-- =============================================
CREATE TABLE IF NOT EXISTS `order_template_items` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `template_id` INT NOT NULL,
    `product_id` INT NOT NULL,
    `quantity` INT DEFAULT 1,

    FOREIGN KEY (`template_id`) REFERENCES `order_templates`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`product_id`) REFERENCES `products`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: activity_log
-- Description: Activity logging
-- =============================================
CREATE TABLE IF NOT EXISTS `activity_log` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT,
    `action` VARCHAR(100) NOT NULL,
    `entity_type` VARCHAR(50),
    `entity_id` INT,
    `old_value` TEXT,
    `new_value` TEXT,
    `ip_address` VARCHAR(45),
    `user_agent` VARCHAR(500),
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE SET NULL,

    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_action` (`action`),
    INDEX `idx_entity` (`entity_type`, `entity_id`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: login_attempts
-- Description: Failed login attempts tracking
-- =============================================
CREATE TABLE IF NOT EXISTS `login_attempts` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `email` VARCHAR(255) NOT NULL,
    `ip_address` VARCHAR(45) NOT NULL,
    `success` BOOLEAN DEFAULT FALSE,
    `attempted_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `locked_until` DATETIME,

    INDEX `idx_email_ip` (`email`, `ip_address`),
    INDEX `idx_attempted_at` (`attempted_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: settings
-- Description: Application settings
-- =============================================
CREATE TABLE IF NOT EXISTS `settings` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `key` VARCHAR(100) UNIQUE NOT NULL,
    `value` TEXT,
    `type` ENUM('string', 'integer', 'boolean', 'json') DEFAULT 'string',
    `description` VARCHAR(500),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `updated_by` INT,

    FOREIGN KEY (`updated_by`) REFERENCES `users`(`id`) ON DELETE SET NULL,

    INDEX `idx_key` (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: email_templates
-- Description: Email templates
-- =============================================
CREATE TABLE IF NOT EXISTS `email_templates` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) UNIQUE NOT NULL,
    `subject` VARCHAR(500) NOT NULL,
    `body_html` TEXT NOT NULL,
    `body_text` TEXT,
    `type` ENUM(
        'registration_confirmation',
        'password_reset',
        'order_confirmation',
        'order_status_change',
        'order_comment',
        'refund_notification'
    ) NOT NULL,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX `idx_type` (`type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Table: csv_imports
-- Description: CSV import history and tracking
-- =============================================
CREATE TABLE IF NOT EXISTS `csv_imports` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `filename` VARCHAR(255) NOT NULL,
    `user_id` INT NOT NULL,
    `total_rows` INT NOT NULL,
    `processed_rows` INT DEFAULT 0,
    `successful_rows` INT DEFAULT 0,
    `failed_rows` INT DEFAULT 0,
    `status` ENUM('pending', 'processing', 'completed', 'partial', 'failed') DEFAULT 'pending',
    `match_column` ENUM('id', 'sku', 'ean') DEFAULT 'sku',
    `has_headers` BOOLEAN DEFAULT TRUE,
    `column_mapping` JSON,
    `error_log` JSON,
    `temp_file_path` VARCHAR(500),
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `completed_at` DATETIME,

    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,

    INDEX `idx_user_status` (`user_id`, `status`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Enable foreign key checks
-- =============================================
SET FOREIGN_KEY_CHECKS = 1;

-- =============================================
-- Insert default data
-- =============================================

-- Default admin user (password: admin123 - CHANGE THIS!)
-- Password hash for 'admin123' using Werkzeug default method
INSERT INTO `users` (`email`, `password_hash`, `first_name`, `last_name`, `role`, `is_active`, `email_verified`)
VALUES ('admin@thunderorders.pl', 'pbkdf2:sha256:600000$defaultsalt$defaulthash', 'Admin', 'ThunderOrders', 'admin', TRUE, TRUE);

-- Default categories
INSERT INTO `categories` (`name`, `slug`, `sort_order`) VALUES
('Pluszaki', 'pluszaki', 1),
('Figurki', 'figurki', 2),
('Artykuły papiernicze', 'artykuly-papiernicze', 3),
('Akcesoria', 'akcesoria', 4);

-- Default email templates (basic structure)
INSERT INTO `email_templates` (`name`, `subject`, `body_html`, `body_text`, `type`) VALUES
('registration_confirmation', 'Witaj w ThunderOrders!', '<p>Witaj {customer_name}!</p>', 'Witaj {customer_name}!', 'registration_confirmation'),
('password_reset', 'Reset hasła - ThunderOrders', '<p>Reset hasła</p>', 'Reset hasła', 'password_reset'),
('order_confirmation', 'Potwierdzenie zamówienia {order_number}', '<p>Dziękujemy za zamówienie!</p>', 'Dziękujemy za zamówienie!', 'order_confirmation'),
('order_status_change', 'Status zamówienia {order_number}', '<p>Status zmieniony</p>', 'Status zmieniony', 'order_status_change'),
('order_comment', 'Nowy komentarz - {order_number}', '<p>Nowy komentarz</p>', 'Nowy komentarz', 'order_comment'),
('refund_notification', 'Zwrot środków - {order_number}', '<p>Zwrot</p>', 'Zwrot', 'refund_notification');

-- Default settings
INSERT INTO `settings` (`key`, `value`, `type`, `description`) VALUES
('company_name', 'ThunderOrders', 'string', 'Nazwa firmy'),
('exchange_rate_krw', '0.0032', 'string', 'Kurs KRW -> PLN'),
('exchange_rate_usd', '4.10', 'string', 'Kurs USD -> PLN'),
('exchange_rate_updated', NOW(), 'string', 'Data ostatniej aktualizacji kursów');
