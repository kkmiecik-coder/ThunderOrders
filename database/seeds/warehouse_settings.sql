-- Warehouse Settings Seeds
-- Default values for warehouse/product management

-- SKU/EAN Settings
INSERT INTO settings (`key`, `value`, `type`, `description`) VALUES
('warehouse_sku_auto_generate', 'true', 'boolean', 'Automatyczne generowanie SKU dla nowych produktów'),
('warehouse_sku_prefix', 'TH', 'string', 'Prefix dla SKU (np. TH-PLUSH-0001)'),
('warehouse_sku_separator', '-', 'string', 'Separator w SKU'),
('warehouse_sku_number_length', '4', 'integer', 'Długość numeru w SKU (liczba cyfr)'),
('warehouse_ean_validate', 'true', 'boolean', 'Walidacja checksumu EAN-13'),
('warehouse_ean_required', 'false', 'boolean', 'Wymagaj EAN przy dodawaniu produktu');

-- Image Management
INSERT INTO settings (`key`, `value`, `type`, `description`) VALUES
('warehouse_image_max_size_mb', '10', 'integer', 'Maksymalny rozmiar pliku zdjęcia (MB)'),
('warehouse_image_max_dimension', '1600', 'integer', 'Maksymalna szerokość/wysokość zdjęcia (px)'),
('warehouse_image_quality', '85', 'integer', 'Jakość kompresji JPEG (1-100)'),
('warehouse_image_dpi', '72', 'integer', 'DPI dla zdjęć'),
('warehouse_image_max_per_product', '10', 'integer', 'Maksymalna liczba zdjęć na produkt'),
('warehouse_image_formats', 'jpg,jpeg,png,webp,gif', 'string', 'Dozwolone formaty zdjęć (CSV)');

-- Stock Management
INSERT INTO settings (`key`, `value`, `type`, `description`) VALUES
('warehouse_stock_alert_enabled', 'true', 'boolean', 'Włącz alerty niskiego stanu magazynowego'),
('warehouse_stock_alert_threshold', '5', 'integer', 'Próg ostrzeżenia o niskim stanie'),
('warehouse_stock_allow_negative', 'false', 'boolean', 'Zezwól na ujemny stan magazynowy'),
('warehouse_stock_show_out_of_stock', 'true', 'boolean', 'Pokazuj produkty wyczerpane na liście');

-- Pricing & Currency
INSERT INTO settings (`key`, `value`, `type`, `description`) VALUES
('warehouse_default_purchase_currency', 'PLN', 'string', 'Domyślna waluta zakupu (PLN/KRW/USD)'),
('warehouse_currency_source', 'nbp', 'string', 'Źródło kursów walut (nbp/exchangerate)'),
('warehouse_currency_update_frequency', '24', 'integer', 'Częstotliwość aktualizacji kursów (godziny)'),
('warehouse_currency_krw_rate', '0.0032', 'string', 'Kurs KRW → PLN'),
('warehouse_currency_usd_rate', '4.10', 'string', 'Kurs USD → PLN'),
('warehouse_currency_last_update', '2025-01-10 10:00:00', 'string', 'Ostatnia aktualizacja kursów'),
('warehouse_default_margin', '30', 'integer', 'Domyślna marża (%)'),
('warehouse_price_rounding', 'full', 'string', 'Zaokrąglenie cen (full=pełne złote, decimal=grosze)');

-- Dimensions & Weight
INSERT INTO settings (`key`, `value`, `type`, `description`) VALUES
('warehouse_dimension_unit', 'cm', 'string', 'Jednostka długości (cm/mm/inches)'),
('warehouse_weight_unit', 'kg', 'string', 'Jednostka wagi (kg/g/lbs)'),
('warehouse_dimensions_required', 'false', 'boolean', 'Wymagaj wymiarów przy dodawaniu produktu');

-- General Product Settings
INSERT INTO settings (`key`, `value`, `type`, `description`) VALUES
('warehouse_default_product_status', 'active', 'string', 'Domyślny status nowego produktu (active/inactive)'),
('warehouse_products_per_page', '20', 'integer', 'Liczba produktów na stronę');
