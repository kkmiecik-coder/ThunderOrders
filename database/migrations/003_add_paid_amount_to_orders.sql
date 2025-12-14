-- Migration: Add paid_amount column to orders table
-- Date: 2024-12-14
-- Description: Adds paid_amount field to track customer payments

-- Add paid_amount column with default 0.00
ALTER TABLE orders
ADD COLUMN paid_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00
AFTER total_amount;

-- Update comment
ALTER TABLE orders
MODIFY COLUMN paid_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00
COMMENT 'Amount paid by customer';
