-- Migration: Add shipping address and pickup point fields to orders table
-- Date: 2025-12-14
-- Description: Adds fields for delivery address, pickup point, and tracking in the new 3-column layout

-- Add shipping address fields (Adres dostawy)
ALTER TABLE orders
    ADD COLUMN shipping_name VARCHAR(200) NULL COMMENT 'Imię i nazwisko odbiorcy',
    ADD COLUMN shipping_address VARCHAR(500) NULL COMMENT 'Adres (ulica, numer)',
    ADD COLUMN shipping_postal_code VARCHAR(10) NULL COMMENT 'Kod pocztowy',
    ADD COLUMN shipping_city VARCHAR(100) NULL COMMENT 'Miejscowość',
    ADD COLUMN shipping_voivodeship VARCHAR(50) NULL COMMENT 'Województwo',
    ADD COLUMN shipping_country VARCHAR(100) NULL DEFAULT 'Polska' COMMENT 'Kraj';

-- Add pickup point fields (Odbiór w punkcie)
ALTER TABLE orders
    ADD COLUMN pickup_courier VARCHAR(100) NULL COMMENT 'Nazwa kuriera (InPost, DPD, etc.)',
    ADD COLUMN pickup_point_id VARCHAR(50) NULL COMMENT 'ID punktu odbioru (np. WAW123A)',
    ADD COLUMN pickup_address VARCHAR(500) NULL COMMENT 'Adres punktu odbioru',
    ADD COLUMN pickup_postal_code VARCHAR(10) NULL COMMENT 'Kod pocztowy punktu',
    ADD COLUMN pickup_city VARCHAR(100) NULL COMMENT 'Miasto punktu';

-- Add indexes for frequently searched columns
CREATE INDEX idx_orders_shipping_postal_code ON orders(shipping_postal_code);
CREATE INDEX idx_orders_shipping_city ON orders(shipping_city);
CREATE INDEX idx_orders_pickup_courier ON orders(pickup_courier);
CREATE INDEX idx_orders_pickup_point_id ON orders(pickup_point_id);

-- Rollback script (run this to undo migration):
-- ALTER TABLE orders
--     DROP COLUMN shipping_name,
--     DROP COLUMN shipping_address,
--     DROP COLUMN shipping_postal_code,
--     DROP COLUMN shipping_city,
--     DROP COLUMN shipping_voivodeship,
--     DROP COLUMN shipping_country,
--     DROP COLUMN pickup_courier,
--     DROP COLUMN pickup_point_id,
--     DROP COLUMN pickup_address,
--     DROP COLUMN pickup_postal_code,
--     DROP COLUMN pickup_city;
-- DROP INDEX idx_orders_shipping_postal_code ON orders;
-- DROP INDEX idx_orders_shipping_city ON orders;
-- DROP INDEX idx_orders_pickup_courier ON orders;
-- DROP INDEX idx_orders_pickup_point_id ON orders;
