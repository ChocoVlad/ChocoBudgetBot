CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    base TEXT,
    amount REAL DEFAULT 1.0,
    selected TEXT NOT NULL DEFAULT '[]',
    msg_id INTEGER,
    message_sent_at DATETIME
);
