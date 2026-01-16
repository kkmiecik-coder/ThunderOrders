-- ============================================
-- Ankieta Testowa - Exclusive Orders & Panel Klienta
-- Uruchom w phpMyAdmin lub przez mysql CLI
-- ============================================

-- 1. Utwórz ankietę
INSERT INTO feedback_surveys (name, description, token, status, is_anonymous, allow_multiple_responses, created_by, created_at, updated_at)
VALUES (
    'Ankieta Testowa - Exclusive Orders & Panel Klienta',
    'Kompleksowa ankieta testowa obejmująca workflow zamówień Exclusive oraz funkcjonalności panelu klienta.',
    'test-exclusive-panel-2025',
    'draft',
    0,
    0,
    1,
    NOW(),
    NOW()
);

-- Pobierz ID utworzonej ankiety
SET @survey_id = LAST_INSERT_ID();

-- ============================================
-- SEKCJA 1: EXCLUSIVE ORDERS - Scenariusze testowe
-- ============================================

INSERT INTO feedback_questions (survey_id, question_type, content, options, is_required, sort_order, created_at) VALUES
(@survey_id, 'section_header', 'Sekcja 1: Exclusive Orders - Scenariusze testowe', NULL, 0, 0, NOW()),

(@survey_id, 'text', 'Wykonaj poniższe zadania i zaznacz te, które udało Ci się zrealizować:', NULL, 0, 1, NOW()),

(@survey_id, 'checkbox_list', 'Zadania do wykonania - Exclusive Orders',
    '["Otwórz link exclusive i poczekaj na countdown", "Po odblokowaniu, przejrzyj dostępne produkty", "Dodaj co najmniej 2 produkty do koszyka z różnymi ilościami", "Zmień ilość jednego produktu w koszyku", "Usuń jeden produkt z koszyka", "Wypełnij dane do wysyłki (lub wybierz zapisany adres)", "Złóż zamówienie i sprawdź potwierdzenie"]',
    1, 2, NOW()),

-- ============================================
-- SEKCJA 1: Ocena etapów workflow (skala 1-5)
-- ============================================

(@survey_id, 'section_header', 'Ocena etapów workflow Exclusive', NULL, 0, 3, NOW()),

(@survey_id, 'rating_scale', 'Strona countdown (oczekiwanie na start)', NULL, 1, 4, NOW()),
(@survey_id, 'rating_scale', 'Strona z produktami (widoczność, czytelność)', NULL, 1, 5, NOW()),
(@survey_id, 'rating_scale', 'Dodawanie do koszyka', NULL, 1, 6, NOW()),
(@survey_id, 'rating_scale', 'Podgląd koszyka', NULL, 1, 7, NOW()),
(@survey_id, 'rating_scale', 'Formularz danych wysyłki', NULL, 1, 8, NOW()),
(@survey_id, 'rating_scale', 'Potwierdzenie zamówienia', NULL, 1, 9, NOW()),

-- ============================================
-- SEKCJA 1: UI/UX Exclusive (skala 1-5)
-- ============================================

(@survey_id, 'section_header', 'UI/UX - Exclusive Orders', NULL, 0, 10, NOW()),

(@survey_id, 'rating_scale', 'Ogólny wygląd strony Exclusive', NULL, 1, 11, NOW()),
(@survey_id, 'rating_scale', 'Czytelność tekstu i cen', NULL, 1, 12, NOW()),
(@survey_id, 'rating_scale', 'Intuicyjność nawigacji', NULL, 1, 13, NOW()),
(@survey_id, 'rating_scale', 'Responsywność (jeśli testowano na telefonie)', NULL, 0, 14, NOW()),
(@survey_id, 'rating_scale', 'Animacje i przejścia', NULL, 1, 15, NOW()),
(@survey_id, 'rating_scale', 'Spójność kolorystyczna', NULL, 1, 16, NOW()),

-- ============================================
-- SEKCJA 1: Funkcjonalność Exclusive (Tak/Nie)
-- ============================================

(@survey_id, 'section_header', 'Funkcjonalność - Exclusive Orders', NULL, 0, 17, NOW()),

(@survey_id, 'yes_no', 'Czy wszystkie przyciski działały poprawnie?', NULL, 1, 18, NOW()),
(@survey_id, 'yes_no', 'Czy strona ładowała się szybko?', NULL, 1, 19, NOW()),
(@survey_id, 'yes_no_comment', 'Czy wystąpiły jakieś błędy?', NULL, 1, 20, NOW()),
(@survey_id, 'yes_no_comment', 'Czy coś było niejasne/mylące?', NULL, 1, 21, NOW()),

-- ============================================
-- SEKCJA 1: Pytania otwarte Exclusive
-- ============================================

(@survey_id, 'section_header', 'Pytania otwarte - Exclusive Orders', NULL, 0, 22, NOW()),

(@survey_id, 'textarea', 'Co Ci się najbardziej podobało w Exclusive Orders?', NULL, 0, 23, NOW()),
(@survey_id, 'textarea', 'Co byś zmienił/poprawił w Exclusive Orders?', NULL, 0, 24, NOW()),
(@survey_id, 'textarea', 'Czy czegoś brakowało w procesie zamawiania?', NULL, 0, 25, NOW()),

-- ============================================
-- SEKCJA 2: PANEL KLIENTA - Scenariusze testowe
-- ============================================

(@survey_id, 'section_header', 'Sekcja 2: Panel Klienta - Scenariusze testowe', NULL, 0, 26, NOW()),

(@survey_id, 'text', 'Wykonaj poniższe zadania w panelu klienta i zaznacz te, które udało Ci się zrealizować:', NULL, 0, 27, NOW()),

(@survey_id, 'checkbox_list', 'Zadania do wykonania - Panel Klienta',
    '["Zaloguj się do panelu klienta", "Przejrzyj dashboard - sprawdź statystyki i ostatnie zamówienia", "Przejdź do historii zamówień i zobacz szczegóły jednego zamówienia", "Dodaj nowy adres wysyłkowy", "Edytuj istniejący adres wysyłkowy", "Ustaw adres jako domyślny", "Dodaj nową metodę płatności", "Przejrzyj ustawienia konta", "Zmień motyw (light/dark mode)", "Wyloguj się i zaloguj ponownie"]',
    1, 28, NOW()),

-- ============================================
-- SEKCJA 2: Ocena poszczególnych stron (skala 1-5)
-- ============================================

(@survey_id, 'section_header', 'Ocena stron Panelu Klienta', NULL, 0, 29, NOW()),

(@survey_id, 'rating_scale', 'Dashboard (strona główna panelu)', NULL, 1, 30, NOW()),
(@survey_id, 'rating_scale', 'Lista zamówień', NULL, 1, 31, NOW()),
(@survey_id, 'rating_scale', 'Szczegóły zamówienia', NULL, 1, 32, NOW()),
(@survey_id, 'rating_scale', 'Adresy wysyłkowe', NULL, 1, 33, NOW()),
(@survey_id, 'rating_scale', 'Metody płatności', NULL, 1, 34, NOW()),
(@survey_id, 'rating_scale', 'Ustawienia konta', NULL, 1, 35, NOW()),

-- ============================================
-- SEKCJA 2: Nawigacja i UX (skala 1-5)
-- ============================================

(@survey_id, 'section_header', 'Nawigacja i UX - Panel Klienta', NULL, 0, 36, NOW()),

(@survey_id, 'rating_scale', 'Sidebar - czytelność i organizacja', NULL, 1, 37, NOW()),
(@survey_id, 'rating_scale', 'Łatwość znalezienia potrzebnych funkcji', NULL, 1, 38, NOW()),
(@survey_id, 'rating_scale', 'Przejścia między stronami', NULL, 1, 39, NOW()),
(@survey_id, 'rating_scale', 'Komunikaty sukcesu/błędów', NULL, 1, 40, NOW()),
(@survey_id, 'rating_scale', 'Formularze (dodawanie/edycja)', NULL, 1, 41, NOW()),

-- ============================================
-- SEKCJA 2: Funkcjonalność Panel Klienta (Tak/Nie)
-- ============================================

(@survey_id, 'section_header', 'Funkcjonalność - Panel Klienta', NULL, 0, 42, NOW()),

(@survey_id, 'yes_no', 'Czy wszystkie dane wyświetlają się poprawnie?', NULL, 1, 43, NOW()),
(@survey_id, 'yes_no', 'Czy zapisywanie zmian działa prawidłowo?', NULL, 1, 44, NOW()),
(@survey_id, 'yes_no', 'Czy usuwanie elementów działa prawidłowo?', NULL, 1, 45, NOW()),
(@survey_id, 'yes_no_comment', 'Czy wystąpiły jakieś błędy w panelu klienta?', NULL, 1, 46, NOW()),

-- ============================================
-- SEKCJA 2: Pytania otwarte Panel Klienta
-- ============================================

(@survey_id, 'section_header', 'Pytania otwarte - Panel Klienta', NULL, 0, 47, NOW()),

(@survey_id, 'textarea', 'Której funkcji panelu używałbyś najczęściej?', NULL, 0, 48, NOW()),
(@survey_id, 'textarea', 'Co jest najbardziej intuicyjne w panelu?', NULL, 0, 49, NOW()),
(@survey_id, 'textarea', 'Co sprawiło trudność lub było mylące?', NULL, 0, 50, NOW()),
(@survey_id, 'textarea', 'Czego brakuje w panelu klienta?', NULL, 0, 51, NOW()),

-- ============================================
-- SEKCJA 3: OCENA OGÓLNA
-- ============================================

(@survey_id, 'section_header', 'Sekcja 3: Ocena ogólna', NULL, 0, 52, NOW()),

(@survey_id, 'rating_10', 'Ogólna ocena doświadczenia z całą aplikacją (1-10)', NULL, 1, 53, NOW()),

(@survey_id, 'multiple_choice', 'Czy poleciłbyś ten system innym?',
    '["Tak, zdecydowanie", "Raczej tak", "Może", "Raczej nie", "Nie"]',
    1, 54, NOW()),

(@survey_id, 'textarea', 'Dodatkowe uwagi i sugestie (opcjonalne)', NULL, 0, 55, NOW());

-- ============================================
-- WYŚWIETL PODSUMOWANIE
-- ============================================

SELECT
    s.id AS survey_id,
    s.name AS survey_name,
    s.token AS survey_token,
    s.status,
    COUNT(q.id) AS questions_count
FROM feedback_surveys s
LEFT JOIN feedback_questions q ON q.survey_id = s.id
WHERE s.id = @survey_id
GROUP BY s.id;

-- Link do ankiety będzie:
-- https://thunderorders.cloud/feedback/test-exclusive-panel-2025
-- (po aktywacji ankiety)
