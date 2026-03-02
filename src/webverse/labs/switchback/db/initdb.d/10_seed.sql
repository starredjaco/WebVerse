-- Seed data (idempotent where practical).
-- Demo referral code for partner portal.

SET NAMES utf8mb4;
SET character_set_client = utf8mb4;
SET character_set_connection = utf8mb4;
SET character_set_results = utf8mb4;

USE switchback_app;
INSERT INTO referrals(code, referrer_email, points, created_at)
SELECT 'SWITCH-2026-DEMO', 'promo@marketing.switchback.local', 42, UTC_TIMESTAMP()
WHERE NOT EXISTS (SELECT 1 FROM referrals WHERE code='SWITCH-2026-DEMO');

-- Vault user's TOTP seed lives in a separate database.
USE switchback_totp;
INSERT INTO mfa_secrets(email, totp_secret)
SELECT 'vault-reader@switchback.local', 'JBSWY3DPEHPK3PXP'
WHERE NOT EXISTS (SELECT 1 FROM mfa_secrets WHERE email='vault-reader@switchback.local');

-- Mail workspaces + users + messages.
USE switchback_mail;

INSERT INTO mail_workspaces(id, name)
SELECT 1, 'Marketing' WHERE NOT EXISTS (SELECT 1 FROM mail_workspaces WHERE id=1);
INSERT INTO mail_workspaces(id, name)
SELECT 2, 'IT' WHERE NOT EXISTS (SELECT 1 FROM mail_workspaces WHERE id=2);

-- Users
INSERT INTO mail_users(email, password_hash, workspace_id)
SELECT 'demo@marketing.switchback.local', SHA2(CONCAT('mail-salt','DemoMail!2026'), 256), 1
WHERE NOT EXISTS (SELECT 1 FROM mail_users WHERE email='demo@marketing.switchback.local');

INSERT INTO mail_users(email, password_hash, workspace_id)
SELECT 'it-helpdesk@switchback.local', SHA2(CONCAT('mail-salt','HelpdeskOnly!2026'), 256), 2
WHERE NOT EXISTS (SELECT 1 FROM mail_users WHERE email='it-helpdesk@switchback.local');

-- Demo inbox hint message
INSERT INTO mail_messages(mailbox_user_id, sender, recipient, subject, body, created_at, folder, is_read, is_starred)
SELECT u.id,
       'mail-migrations@switchback.local',
       'demo@marketing.switchback.local',
       'Workspace switcher rollout: phase 2',
       'Migration update:\n\nThe new multi-workspace UI is now enabled for staging.\n\nUse the workspace switcher in the top-right during verification.\n\n— Migration Team',
       UTC_TIMESTAMP(),
       'inbox',
       0,
       0
FROM mail_users u
WHERE u.email='demo@marketing.switchback.local'
  AND NOT EXISTS (
    SELECT 1 FROM mail_messages m
    WHERE m.recipient='demo@marketing.switchback.local'
      AND m.subject='Workspace switcher rollout: phase 2'
  );

-- A normal marketing email (non-sensitive)
INSERT INTO mail_messages(mailbox_user_id, sender, recipient, subject, body, created_at, folder, is_read, is_starred)
SELECT u.id,
       'ops@switchback.local',
       'demo@marketing.switchback.local',
       'Reminder: referral attribution freeze',
       'Heads up:\n\nPartner attribution data is frozen during the rollout window. If you need verification, use the partner portal.\n',
       UTC_TIMESTAMP(),
       'inbox',
       0,
       0
FROM mail_users u
WHERE u.email='demo@marketing.switchback.local'
  AND NOT EXISTS (
    SELECT 1 FROM mail_messages m
    WHERE m.recipient='demo@marketing.switchback.local'
      AND m.subject='Reminder: referral attribution freeze'
  );

-- IT mailbox contains Vault creds
INSERT INTO mail_messages(mailbox_user_id, sender, recipient, subject, body, created_at, folder, is_read, is_starred)
SELECT u.id,
       'it-admin@switchback.local',
       'it-helpdesk@switchback.local',
       'Onboarding: Vault reader account (staging)',
       CONCAT(
         'Provisioned a low-priv Vault account for the referral team.\n\n',
         'Vault URL: http://vault.switchback.local/\n',
         'User: vault-reader@switchback.local\n',
         'Temp password: NavyVault!2026\n\n',
         'MFA is mandatory.\n'
       ),
       UTC_TIMESTAMP(),
       'inbox',
       0,
       1
FROM mail_users u
WHERE u.email='it-helpdesk@switchback.local'
  AND NOT EXISTS (
    SELECT 1 FROM mail_messages m
    WHERE m.recipient='it-helpdesk@switchback.local'
      AND m.subject='Onboarding: Vault reader account (staging)'
  );

-- Vault DB seed: low-priv vault user (password hash stored here, TOTP stored in switchback_totp).
USE switchback_vault;
INSERT INTO vault_users(email, password_hash, role)
SELECT 'vault-reader@switchback.local', SHA2(CONCAT('vault-salt','NavyVault!2026'), 256), 'reader'
WHERE NOT EXISTS (SELECT 1 FROM vault_users WHERE email='vault-reader@switchback.local');
