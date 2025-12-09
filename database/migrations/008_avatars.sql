-- ==========================================
-- ThunderOrders - Avatars Module Migration
-- Migration: 008_avatars.sql
-- Created: 2025-12-06
-- ==========================================

-- Table: avatar_series
-- Serie/kategorie avatarów (np. "K-pop", "Animals", "Abstract")
CREATE TABLE IF NOT EXISTS avatar_series (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    sort_order INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_slug (slug),
    INDEX idx_sort_order (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: avatars
-- Poszczególne avatary przypisane do serii
CREATE TABLE IF NOT EXISTS avatars (
    id INT AUTO_INCREMENT PRIMARY KEY,
    series_id INT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    sort_order INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (series_id) REFERENCES avatar_series(id) ON DELETE CASCADE,

    INDEX idx_series_id (series_id),
    INDEX idx_sort_order (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add avatar_id column to users table
ALTER TABLE users
ADD COLUMN avatar_id INT DEFAULT NULL,
ADD CONSTRAINT fk_users_avatar FOREIGN KEY (avatar_id) REFERENCES avatars(id) ON DELETE SET NULL;

-- Add index for avatar_id
ALTER TABLE users ADD INDEX idx_avatar_id (avatar_id);

-- ==========================================
-- Migration Complete
-- ==========================================
