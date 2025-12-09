-- Migration: 011_set_image_variant_groups
-- Description: Dodanie obrazka tła seta i wsparcie dla grup wariantowych w setach
-- Date: 2025-12-09

-- ============================================
-- Dodanie kolumny set_image do exclusive_sections
-- Tło seta (zamiast zdjęć pojedynczych produktów)
-- ============================================

ALTER TABLE exclusive_sections
ADD COLUMN set_image VARCHAR(500) DEFAULT NULL AFTER set_name;

-- ============================================
-- Modyfikacja exclusive_set_items dla grup wariantowych
-- Element seta może być pojedynczym produktem LUB grupą wariantową
-- ============================================

-- Zmiana product_id na nullable (bo może być variant_group zamiast product)
ALTER TABLE exclusive_set_items
MODIFY COLUMN product_id INT DEFAULT NULL;

-- Dodanie kolumny variant_group_id
ALTER TABLE exclusive_set_items
ADD COLUMN variant_group_id INT DEFAULT NULL AFTER product_id;

-- Dodanie foreign key dla variant_group_id
ALTER TABLE exclusive_set_items
ADD CONSTRAINT fk_set_item_variant_group
FOREIGN KEY (variant_group_id) REFERENCES variant_groups(id) ON DELETE CASCADE;

-- Dodanie indexu dla variant_group_id
ALTER TABLE exclusive_set_items
ADD INDEX idx_variant_group_id (variant_group_id);

-- ============================================
-- Komentarz
-- ============================================
-- set_image: Ścieżka do zdjęcia tła seta (full width, proporcjonalna wysokość)
-- variant_group_id: Opcjonalna grupa wariantowa zamiast pojedynczego produktu
-- W ExclusiveSetItem: product_id XOR variant_group_id (jeden musi być ustawiony)
