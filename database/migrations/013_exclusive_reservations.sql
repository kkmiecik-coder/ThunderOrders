-- Migration: Add exclusive_reservations table for product reservation system
-- Date: 2025-12-09
-- Description: Creates table to track product reservations on exclusive pages with 10-minute timer

CREATE TABLE exclusive_reservations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL COMMENT 'UUID for session identification',
    exclusive_page_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    reserved_at BIGINT NOT NULL COMMENT 'UNIX timestamp (seconds) when first product was reserved',
    expires_at BIGINT NOT NULL COMMENT 'UNIX timestamp (seconds) when reservation expires',
    extended BOOLEAN DEFAULT FALSE COMMENT 'Whether reservation was extended (+2 minutes)',
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at BIGINT DEFAULT (UNIX_TIMESTAMP()),

    FOREIGN KEY (exclusive_page_id) REFERENCES exclusive_pages(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,

    INDEX idx_session (session_id),
    INDEX idx_page_product (exclusive_page_id, product_id),
    INDEX idx_expires (expires_at),
    UNIQUE KEY unique_session_product (session_id, product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
