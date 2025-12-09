-- Migration: 009_exclusive_pages
-- Description: Tabele dla stron ekskluzywnych zamówień (pre-order)
-- Date: 2025-12-08

-- ============================================
-- Tabela: exclusive_pages
-- Strona ekskluzywna - formularz zamówień pre-order
-- ============================================

CREATE TABLE IF NOT EXISTS exclusive_pages (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Podstawowe informacje
    name VARCHAR(200) NOT NULL,
    description TEXT,
    token VARCHAR(100) UNIQUE NOT NULL,

    -- Status
    status ENUM('draft', 'scheduled', 'active', 'paused', 'ended') DEFAULT 'draft' NOT NULL,

    -- Daty sprzedaży
    starts_at DATETIME,                  -- NULL = brak zaplanowanej daty
    ends_at DATETIME,                    -- NULL = bez daty końca (ręczne zakończenie)

    -- Stopka (zawsze na dole strony)
    footer_content TEXT,

    -- Metadane
    created_by INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign Keys
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,

    -- Indexes
    INDEX idx_token (token),
    INDEX idx_status (status),
    INDEX idx_starts_at (starts_at),
    INDEX idx_ends_at (ends_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================
-- Tabela: exclusive_sections
-- Sekcje strony ekskluzywnej (Page Builder)
-- ============================================

CREATE TABLE IF NOT EXISTS exclusive_sections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    exclusive_page_id INT NOT NULL,

    -- Typ sekcji
    section_type ENUM('heading', 'paragraph', 'product', 'set') NOT NULL,
    sort_order INT DEFAULT 0,

    -- Dla heading i paragraph
    content TEXT,

    -- Dla product
    product_id INT,
    min_quantity INT,                    -- NULL = brak minimum
    max_quantity INT,                    -- NULL = brak maksimum

    -- Dla set
    set_name VARCHAR(200),
    set_min_sets INT DEFAULT 1,          -- Min. kompletnych setów
    set_max_sets INT,                    -- NULL = brak maksimum

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Foreign Keys
    FOREIGN KEY (exclusive_page_id) REFERENCES exclusive_pages(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,

    -- Indexes
    INDEX idx_exclusive_page_id (exclusive_page_id),
    INDEX idx_section_type (section_type),
    INDEX idx_sort_order (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================
-- Tabela: exclusive_set_items
-- Elementy setu - produkty wchodzące w skład setu
-- ============================================

CREATE TABLE IF NOT EXISTS exclusive_set_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    section_id INT NOT NULL,
    product_id INT NOT NULL,

    quantity_per_set INT DEFAULT 1,      -- Ile sztuk tego produktu w jednym secie
    sort_order INT DEFAULT 0,

    -- Foreign Keys
    FOREIGN KEY (section_id) REFERENCES exclusive_sections(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,

    -- Indexes
    INDEX idx_section_id (section_id),
    INDEX idx_product_id (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================
-- Komentarz
-- ============================================
-- Statusy exclusive_pages:
--   draft     - Strona w budowie (niepubliczna)
--   scheduled - Zaplanowana, czeka na datę startu (pokazuje countdown)
--   active    - Sprzedaż aktywna (można zamawiać)
--   paused    - Sprzedaż wstrzymana tymczasowo
--   ended     - Sprzedaż zakończona
--
-- Typy exclusive_sections:
--   heading   - Nagłówek H2
--   paragraph - Paragraf tekstu
--   product   - Pojedynczy produkt z min/max ilością
--   set       - Set produktów (komplet, np. karty wszystkich członków zespołu)
