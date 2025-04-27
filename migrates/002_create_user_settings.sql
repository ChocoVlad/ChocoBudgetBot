CREATE TABLE IF NOT EXISTS user_settings (
    user_id BIGINT PRIMARY KEY,
    base VARCHAR(10),
    amount DOUBLE PRECISION DEFAULT 1.0,
    selected TEXT NOT NULL DEFAULT '[]',
    msg_id BIGINT,
    message_sent_at TIMESTAMP,
    chat_id BIGINT
);
