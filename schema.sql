-- Core application database structure for Cyclone Admin Matrix Tracker

CREATE TABLE IF NOT EXISTS users (
    username VARCHAR(100) PRIMARY KEY,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    approval_status VARCHAR(50) DEFAULT 'pending',
    internet_access BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) REFERENCES users(username) ON DELETE CASCADE,
    device_id VARCHAR(255) NOT NULL,
    login_count INT DEFAULT 1,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_device UNIQUE(username, device_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY,
    message TEXT NOT NULL,
    target_users VARCHAR(50) DEFAULT 'all',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed default administrator account (Password hash for: admin123)
INSERT INTO users (username, password, role, approval_status, internet_access)
VALUES ('admin', '8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918', 'admin', 'approved', TRUE)
ON CONFLICT (username) DO NOTHING;

-- Seed baseline initial operational configurations
INSERT INTO settings (key, value) VALUES 
('maintenance_mode', 'false'),
('maintenance_notice', 'System integration configuration optimization in progress.'),
('index_url', 'https://example.com'),
('custom_html', '<h1>Cyclone Distributed Node Core Active</h1>')
ON CONFLICT (key) DO NOTHING;