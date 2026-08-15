# Hetzner deployment

1. Create a current Ubuntu/Debian LTS Hetzner Cloud server and a non-root sudo user.
   Configure the firewall for inbound SSH only. Use SSH public-key authentication and
   set `PasswordAuthentication no`; do not expose PostgreSQL.
2. Install Docker Engine and the Compose plugin from Docker's official repository.
3. Clone the public repository to `/opt/rejoinlater`.
4. Create `/etc/rejoinlater/secrets` owned by `root:root`, mode `0700`. Create five
   root-owned mode-`0600` files:
   `telegram_bot_token`, `data_encryption_key`, `lookup_hmac_key`, `postgres_password`,
   and `database_url`.
5. Put independent URL-safe Base64 32-byte values in the two key files. The database
   URL uses the internal hostname, for example
   `postgresql+asyncpg://rejoinlater:<password>@postgres/rejoinlater`.
6. Set `BOT_USERNAME` if deploying under a different bot username, then run:

   ```bash
   docker compose build --pull
   docker compose up -d
   docker compose logs --tail=100 bot
   ```

The bot container runs as an unprivileged user. Compose mounts secrets read-only and
places both services on an internal network. PostgreSQL uses a persistent Docker
volume and publishes no port. Container startup runs `alembic upgrade head` before
long polling.

Create encrypted PostgreSQL backups on a separate schedule and location. Do not store
encryption keys with backups. Permanently expire backups after
`BACKUP_RETENTION_DAYS` (default 7). Test restoration and `alembic upgrade head` on a
clean database before each release.
