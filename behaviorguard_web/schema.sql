

CREATE DATABASE IF NOT EXISTS behaviorguard1;
USE behaviorguard1;



CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(64)  NOT NULL,
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP
);



CREATE TABLE IF NOT EXISTS login_sessions (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT          NOT NULL,
    timestamp   DATETIME     DEFAULT CURRENT_TIMESTAMP,
    event_count INT          DEFAULT 0,
    risk_score  FLOAT        DEFAULT -1,
    decision    VARCHAR(20)  DEFAULT 'pending',
    ip_address  VARCHAR(50)  DEFAULT '',
    latency_ms  FLOAT        DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);



INSERT IGNORE INTO users (username, password_hash) VALUES
('ganesh', SHA2('Qwertyuiopas12@', 256)),
('pratik',   SHA2('Test@1234', 256)),
('sohel',  SHA2('Loveishappiness12@'));
