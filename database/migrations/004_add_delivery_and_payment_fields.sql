-- Migration: Add delivery method, shipping cost, and payment method fields to orders
-- Date: 2025-12-14
-- Description: Adds shipping_cost, delivery_method, payment_method columns to orders table

-- Add shipping_cost column (after paid_amount)
ALTER TABLE orders
ADD COLUMN shipping_cost DECIMAL(10, 2) NOT NULL DEFAULT 0.00
AFTER paid_amount;

-- Add delivery_method column
ALTER TABLE orders
ADD COLUMN delivery_method VARCHAR(50) NULL
AFTER shipping_cost;

-- Add payment_method column
ALTER TABLE orders
ADD COLUMN payment_method VARCHAR(50) NULL
AFTER delivery_method;
