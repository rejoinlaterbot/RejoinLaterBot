# Security Policy

Please report vulnerabilities privately to the repository's GitHub Security Advisory
form. Do not open a public issue containing tokens, database contents, encrypted
records, invite URLs, public locators, or Telegram identifiers.

The highest-priority classes are key disclosure, plaintext identifier persistence,
logs containing Telegram metadata, username reassignment, incorrect public fallback,
duplicate delivery, and failure to hard-delete completed records.

Operators should rotate a leaked bot token immediately. Rotation of data or HMAC keys
requires an explicit migration because pending ciphertext and blind indexes depend on
them. Keep all key files root-owned and mode `0600`, and never copy keys into database
backups.
