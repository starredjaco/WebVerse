-- Switchback: multi-database setup with least-privilege users.
-- This runs as MySQL root during first container init.

SET NAMES utf8mb4;
SET character_set_client = utf8mb4;
SET character_set_connection = utf8mb4;
SET character_set_results = utf8mb4;

CREATE DATABASE IF NOT EXISTS switchback_app   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS switchback_totp  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS switchback_mail  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS switchback_vault CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Least-privilege service accounts
CREATE USER IF NOT EXISTS 'wv_api'@'%'   IDENTIFIED WITH mysql_native_password BY 'wv_api_pass';
CREATE USER IF NOT EXISTS 'wv_mail'@'%'  IDENTIFIED WITH mysql_native_password BY 'wv_mail_pass';
CREATE USER IF NOT EXISTS 'wv_vault'@'%' IDENTIFIED WITH mysql_native_password BY 'wv_vault_pass';

-- API: can read referrals + MFA seed DB (for time-based SQLi extraction), but NOT Vault or Mail DBs.
GRANT SELECT ON switchback_app.*  TO 'wv_api'@'%';
GRANT SELECT ON switchback_totp.* TO 'wv_api'@'%';

-- Mail: can operate only on mail DB.
GRANT SELECT,INSERT,UPDATE,DELETE ON switchback_mail.* TO 'wv_mail'@'%';

-- Vault: can operate on vault DB and read MFA seed DB.
GRANT SELECT,INSERT,UPDATE,DELETE ON switchback_vault.* TO 'wv_vault'@'%';
GRANT SELECT ON switchback_totp.* TO 'wv_vault'@'%';

FLUSH PRIVILEGES;

-- App DB schema
USE switchback_app;

CREATE TABLE IF NOT EXISTS referrals (
  code VARCHAR(64) PRIMARY KEY,
  referrer_email VARCHAR(255) NOT NULL,
  points INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- TOTP DB schema (separate database on same server)
USE switchback_totp;

CREATE TABLE IF NOT EXISTS mfa_secrets (
  email VARCHAR(255) PRIMARY KEY,
  totp_secret VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Server-issued one-time MFA codes (invalidate previous by overwriting per email)
CREATE TABLE IF NOT EXISTS mfa_challenges (
  email VARCHAR(255) PRIMARY KEY,
  code CHAR(6) NOT NULL,
  created_at DATETIME NOT NULL,
  expires_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT SELECT,INSERT,UPDATE,DELETE ON switchback_totp.mfa_challenges TO 'wv_vault'@'%';
FLUSH PRIVILEGES;

-- Mail DB schema
USE switchback_mail;

CREATE TABLE IF NOT EXISTS mail_workspaces (
  id INT NOT NULL PRIMARY KEY,
  name VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS mail_users (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash CHAR(64) NOT NULL,
  workspace_id INT NOT NULL,
  FOREIGN KEY(workspace_id) REFERENCES mail_workspaces(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS mail_messages (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  mailbox_user_id INT NOT NULL,
  sender VARCHAR(255) NOT NULL,
  recipient VARCHAR(255) NOT NULL,
  subject VARCHAR(255) NOT NULL,
  body TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  folder VARCHAR(16) NOT NULL DEFAULT 'inbox',
  is_read TINYINT(1) NOT NULL DEFAULT 0,
  is_starred TINYINT(1) NOT NULL DEFAULT 0,
  FOREIGN KEY(mailbox_user_id) REFERENCES mail_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Vault DB schema
USE switchback_vault;

CREATE TABLE IF NOT EXISTS vault_users (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash CHAR(64) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'reader'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS secrets (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  owner_email VARCHAR(255) NOT NULL,
  name VARCHAR(255) NOT NULL,
  value TEXT NOT NULL,
  description TEXT,
  tags VARCHAR(255),
  expires_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  last_viewed_at DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vault_audit_events (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  actor_email VARCHAR(255) NOT NULL,
  action VARCHAR(64) NOT NULL,
  target VARCHAR(255) NOT NULL,
  ip VARCHAR(64) NOT NULL,
  created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
