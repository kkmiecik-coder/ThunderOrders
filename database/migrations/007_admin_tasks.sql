-- Migration 007: Admin Tasks (TODO System)
-- Date: 2025-12-03
-- Description: Dodaje tabele dla systemu zadań administracyjnych

-- Tabela główna: admin_tasks
CREATE TABLE IF NOT EXISTS admin_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    priority ENUM('low', 'medium', 'high') DEFAULT 'medium' NOT NULL,
    status ENUM('pending', 'in_progress', 'completed') DEFAULT 'pending' NOT NULL,
    parent_task_id INT,
    created_by INT NOT NULL,
    due_date DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at DATETIME,

    FOREIGN KEY (parent_task_id) REFERENCES admin_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,

    INDEX idx_status (status),
    INDEX idx_priority (priority),
    INDEX idx_parent_task (parent_task_id),
    INDEX idx_created_by (created_by),
    INDEX idx_due_date (due_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabela junction: admin_task_assignments
CREATE TABLE IF NOT EXISTS admin_task_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id INT NOT NULL,
    user_id INT NOT NULL,
    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES admin_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,

    UNIQUE KEY unique_task_user (task_id, user_id),
    INDEX idx_task_id (task_id),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
