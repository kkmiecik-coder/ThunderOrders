-- Migration: 010_variant_group_section
-- Description: Dodaje typ sekcji 'variant_group' do exclusive_sections
-- Date: 2025-12-09

-- ============================================
-- Modyfikacja ENUM dla section_type
-- Dodajemy nowy typ: variant_group
-- ============================================

ALTER TABLE exclusive_sections
MODIFY COLUMN section_type ENUM('heading', 'paragraph', 'product', 'set', 'variant_group') NOT NULL;

-- ============================================
-- Dodanie kolumny dla variant_group
-- Przechowuje ID grupy wariantowej (z tabeli variant_groups)
-- ============================================

ALTER TABLE exclusive_sections
ADD COLUMN variant_group_id INT NULL AFTER set_max_sets,
ADD FOREIGN KEY (variant_group_id) REFERENCES variant_groups(id) ON DELETE SET NULL,
ADD INDEX idx_variant_group_id (variant_group_id);

-- ============================================
-- Komentarz
-- ============================================
-- Nowy typ sekcji: variant_group
-- Wyświetla wszystkie produkty z danej grupy wariantowej
-- Każdy produkt ma osobne min/max (domyślnie min=1 jeśli zaznaczony, 0 jeśli nie)
