-- Migration: Add order_shipments table (without foreign keys for compatibility)
-- Created: 2025-12-14
-- Description: Allows multiple shipments per order with tracking

-- Create order_shipments table
CREATE TABLE IF NOT EXISTS order_shipments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    tracking_number VARCHAR(100) NOT NULL,
    courier VARCHAR(50) NOT NULL,
    notes VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by INT,

    INDEX idx_order_id (order_id),
    INDEX idx_tracking_number (tracking_number),
    INDEX idx_courier (courier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
