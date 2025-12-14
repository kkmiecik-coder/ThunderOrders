-- Migration: Change badge_class to badge_color (HEX color picker)
-- Date: 2024-12-13
-- Description: Replace CSS class with HEX color for status/type badges

-- ==========================================
-- 1. Add new badge_color column to order_statuses
-- ==========================================
ALTER TABLE order_statuses
ADD COLUMN badge_color VARCHAR(7) DEFAULT '#6B7280' AFTER badge_class;

-- ==========================================
-- 2. Migrate existing badge_class values to HEX colors
-- ==========================================
UPDATE order_statuses
SET badge_color = CASE
    WHEN badge_class = 'badge-info' THEN '#3B82F6'      -- Blue
    WHEN badge_class = 'badge-orange' THEN '#F97316'    -- Orange
    WHEN badge_class = 'badge-purple' THEN '#9333EA'    -- Purple
    WHEN badge_class = 'badge-success' THEN '#10B981'   -- Green
    WHEN badge_class = 'badge-warning' THEN '#F59E0B'   -- Yellow
    WHEN badge_class = 'badge-error' THEN '#EF4444'     -- Red
    WHEN badge_class = 'badge-gray' THEN '#6B7280'      -- Gray
    ELSE '#6B7280'                                       -- Default Gray
END
WHERE badge_class IS NOT NULL;

-- ==========================================
-- 3. Drop old badge_class column from order_statuses
-- ==========================================
ALTER TABLE order_statuses
DROP COLUMN badge_class;

-- ==========================================
-- 4. Add new badge_color column to order_types
-- ==========================================
ALTER TABLE order_types
ADD COLUMN badge_color VARCHAR(7) DEFAULT '#6B7280' AFTER badge_class;

-- ==========================================
-- 5. Migrate existing badge_class values to HEX colors for order_types
-- ==========================================
UPDATE order_types
SET badge_color = CASE
    WHEN badge_class = 'badge-info' THEN '#3B82F6'      -- Blue
    WHEN badge_class = 'badge-orange' THEN '#F97316'    -- Orange
    WHEN badge_class = 'badge-purple' THEN '#9333EA'    -- Purple
    WHEN badge_class = 'badge-success' THEN '#10B981'   -- Green
    WHEN badge_class = 'badge-warning' THEN '#F59E0B'   -- Yellow
    WHEN badge_class = 'badge-error' THEN '#EF4444'     -- Red
    WHEN badge_class = 'badge-gray' THEN '#6B7280'      -- Gray
    ELSE '#6B7280'                                       -- Default Gray
END
WHERE badge_class IS NOT NULL;

-- ==========================================
-- 6. Drop old badge_class column from order_types
-- ==========================================
ALTER TABLE order_types
DROP COLUMN badge_class;

-- ==========================================
-- ROLLBACK (if needed)
-- ==========================================
-- ALTER TABLE order_statuses ADD COLUMN badge_class VARCHAR(50) AFTER badge_color;
-- UPDATE order_statuses SET badge_class = 'badge-info' WHERE badge_color = '#3B82F6';
-- UPDATE order_statuses SET badge_class = 'badge-orange' WHERE badge_color = '#F97316';
-- UPDATE order_statuses SET badge_class = 'badge-purple' WHERE badge_color = '#9333EA';
-- UPDATE order_statuses SET badge_class = 'badge-success' WHERE badge_color = '#10B981';
-- UPDATE order_statuses SET badge_class = 'badge-warning' WHERE badge_color = '#F59E0B';
-- UPDATE order_statuses SET badge_class = 'badge-error' WHERE badge_color = '#EF4444';
-- UPDATE order_statuses SET badge_class = 'badge-gray' WHERE badge_color = '#6B7280';
-- ALTER TABLE order_statuses DROP COLUMN badge_color;
--
-- ALTER TABLE order_types ADD COLUMN badge_class VARCHAR(50) AFTER badge_color;
-- UPDATE order_types SET badge_class = 'badge-info' WHERE badge_color = '#3B82F6';
-- UPDATE order_types SET badge_class = 'badge-orange' WHERE badge_color = '#F97316';
-- UPDATE order_types SET badge_class = 'badge-purple' WHERE badge_color = '#9333EA';
-- UPDATE order_types SET badge_class = 'badge-success' WHERE badge_color = '#10B981';
-- UPDATE order_types SET badge_class = 'badge-warning' WHERE badge_color = '#F59E0B';
-- UPDATE order_types SET badge_class = 'badge-error' WHERE badge_color = '#EF4444';
-- UPDATE order_types SET badge_class = 'badge-gray' WHERE badge_color = '#6B7280';
-- ALTER TABLE order_types DROP COLUMN badge_color;
