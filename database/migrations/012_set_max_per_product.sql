-- Migration 012: Add set_max_per_product column to exclusive_sections
-- This field stores the maximum number of each product that can be sold in total (global limit)

ALTER TABLE exclusive_sections
ADD COLUMN set_max_per_product INT NULL DEFAULT NULL AFTER set_max_sets;
