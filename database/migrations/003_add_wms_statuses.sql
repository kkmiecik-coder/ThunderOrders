-- Migration: Add WMS Statuses table
-- Date: 2025-12-14
-- Description: Creates wms_statuses lookup table and adds wms_status column to order_items

-- Create WMS statuses table
CREATE TABLE IF NOT EXISTS `wms_statuses` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `slug` VARCHAR(50) UNIQUE NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `badge_color` VARCHAR(7) DEFAULT '#6B7280',
    `sort_order` INT DEFAULT 0,
    `is_active` BOOLEAN DEFAULT TRUE,
    `is_default` BOOLEAN DEFAULT FALSE,
    `is_picked` BOOLEAN DEFAULT FALSE,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX `idx_slug` (`slug`),
    INDEX `idx_is_active` (`is_active`),
    INDEX `idx_is_default` (`is_default`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add wms_status column to order_items
ALTER TABLE `order_items`
ADD COLUMN `wms_status` VARCHAR(50) NULL AFTER `total`,
ADD INDEX `idx_wms_status` (`wms_status`),
ADD CONSTRAINT `fk_order_items_wms_status`
    FOREIGN KEY (`wms_status`) REFERENCES `wms_statuses`(`slug`) ON DELETE SET NULL;

-- Insert default WMS statuses
INSERT INTO `wms_statuses` (`slug`, `name`, `badge_color`, `sort_order`, `is_active`, `is_default`, `is_picked`) VALUES
('do_zebrania', 'Do zebrania', '#FF9800', 1, TRUE, TRUE, FALSE),
('zebrane', 'Zebrane', '#4CAF50', 2, TRUE, FALSE, TRUE),
('brak_na_stanie', 'Brak na stanie', '#F44336', 3, TRUE, FALSE, FALSE),
('zamowione', 'Zamówione', '#2196F3', 4, TRUE, FALSE, FALSE),
('spakowane', 'Spakowane', '#9C27B0', 5, TRUE, FALSE, TRUE);

-- Update existing order_items with default status based on picked field
UPDATE `order_items` SET `wms_status` = 'zebrane' WHERE `picked` = 1;
UPDATE `order_items` SET `wms_status` = 'do_zebrania' WHERE `picked` = 0 OR `picked` IS NULL;
