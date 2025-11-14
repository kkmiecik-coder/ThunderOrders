-- Migration: Add dark_mode_enabled and sidebar_collapsed columns to users table
-- Date: 2025-11-02
-- Description: Adds user preferences for dark mode and sidebar state

-- Add dark_mode_enabled column
ALTER TABLE `users`
ADD COLUMN `dark_mode_enabled` BOOLEAN DEFAULT FALSE AFTER `last_login`;

-- Add sidebar_collapsed column
ALTER TABLE `users`
ADD COLUMN `sidebar_collapsed` BOOLEAN DEFAULT FALSE AFTER `dark_mode_enabled`;

-- Update existing users to have default values
UPDATE `users` SET `dark_mode_enabled` = FALSE, `sidebar_collapsed` = FALSE WHERE `dark_mode_enabled` IS NULL;
