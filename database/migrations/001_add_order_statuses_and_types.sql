-- =============================================
-- Migration: Add order_statuses and order_types tables
-- Date: 2025-12-13
-- Description: Replace ENUM with separate tables for better management
-- =============================================

-- Create order_statuses table
CREATE TABLE IF NOT EXISTS `order_statuses` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `slug` VARCHAR(50) UNIQUE NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `badge_class` VARCHAR(50),  -- CSS class for badge (e.g. 'badge-success')
    `sort_order` INT DEFAULT 0,
    `is_active` BOOLEAN DEFAULT TRUE,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX `idx_slug` (`slug`),
    INDEX `idx_sort_order` (`sort_order`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create order_types table
CREATE TABLE IF NOT EXISTS `order_types` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `slug` VARCHAR(50) UNIQUE NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `prefix` VARCHAR(5) NOT NULL,  -- For order number generation (PO, OH, EX)
    `badge_class` VARCHAR(50),  -- CSS class for type badge
    `sort_order` INT DEFAULT 0,
    `is_active` BOOLEAN DEFAULT TRUE,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX `idx_slug` (`slug`),
    INDEX `idx_prefix` (`prefix`),
    INDEX `idx_sort_order` (`sort_order`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default order statuses
INSERT INTO `order_statuses` (`slug`, `name`, `badge_class`, `sort_order`) VALUES
('nowe', 'Nowe', 'badge-info', 1),
('oczekujace', 'Oczekujące', 'badge-orange', 2),
('dostarczone_proxy', 'Dostarczone do Proxy', 'badge-purple', 3),
('w_drodze_polska', 'W drodze do Polski', 'badge-purple', 4),
('urzad_celny', 'Urząd Celny', 'badge-warning', 5),
('dostarczone_gom', 'Dostarczone do GOM', 'badge-purple', 6),
('do_pakowania', 'Do Pakowania', 'badge-warning', 7),
('spakowane', 'Spakowane', 'badge-purple', 8),
('wyslane', 'Wysłane', 'badge-purple', 9),
('dostarczone', 'Dostarczone', 'badge-success', 10),
('anulowane', 'Anulowane', 'badge-gray', 11),
('do_zwrotu', 'Do Zwrotu', 'badge-warning', 12),
('zwrocone', 'Zwrócone', 'badge-error', 13),
('czesciowo_zwrocone', 'Częściowo Zwrócone', 'badge-warning', 14);

-- Insert default order types
INSERT INTO `order_types` (`slug`, `name`, `prefix`, `badge_class`, `sort_order`) VALUES
('pre_order', 'Pre-order', 'PO', 'type-pre-order', 1),
('on_hand', 'On-hand', 'OH', 'type-on-hand', 2),
('exclusive', 'Exclusive', 'EX', 'type-exclusive', 3);

-- Add order_type column to orders table (if doesn't exist)
-- Note: This will fail if column already exists, but that's OK
ALTER TABLE `orders`
ADD COLUMN `order_type` VARCHAR(50) DEFAULT 'on_hand' AFTER `order_number`;

-- Add foreign key index for order_type (optional, for performance)
ALTER TABLE `orders`
ADD INDEX `idx_order_type` (`order_type`);

-- Update existing orders to have proper order_type based on is_exclusive flag
UPDATE `orders` SET `order_type` = 'exclusive' WHERE `is_exclusive` = TRUE;
UPDATE `orders` SET `order_type` = 'on_hand' WHERE `is_exclusive` = FALSE;
