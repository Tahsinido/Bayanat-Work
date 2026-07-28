# Docker Deployment

::: warning Beta
Docker Compose deployment is still in beta. For production environments, [native installation](/deployment/installation) is recommended.
:::

## Prerequisites

- Docker Engine with the Compose v2 plugin (`docker compose`, not the legacy `docker-compose` binary)
- `.env.docker` file configured (see [Configuration](/deployment/configuration))

## Quick Start

```bash
docker compose --env-file .env.docker up -d
```

This starts PostgreSQL, Redis, the Flask app, NGINX, and Celery.

::: tip
The `--env-file .env.docker` flag is required so Compose can substitute `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`, and `${REDIS_PASSWORD}` placeholders in `docker-compose.yml`. Without it, those services boot with empty credentials and the Flask container fails to connect.
:::

## First Admin User

The entrypoint creates an `admin` user automatically on the first startup
(when the database has no schema yet) and prints a one-time random
password to the container logs. Retrieve it with:

```bash
docker compose --env-file .env.docker logs bayanat | grep -A4 "Generated password"
```

Sign in at the Bayanat URL with `admin` and the printed password. The
setup wizard runs after first login. Change the admin password from your
account settings afterwards.

If the auto-bootstrap was missed or the admin account was deleted, run
the CLI directly:

```bash
docker compose --env-file .env.docker exec bayanat uv run flask install -u admin
```

It generates a fresh password and prints it. If an admin already exists
the command exits without changing anything.

## Development

```bash
docker compose -f docker-compose-dev.yml up
```

## Testing

```bash
docker compose -f docker-compose-test.yml up
```

## Troubleshooting

### `exec /usr/local/bin/docker-entrypoint.sh: operation not permitted`

This affects `postgres`, `redis`, or any other service, and means the
kernel refused to execute a script that's already in the image with
otherwise-correct permissions. It is a host issue, not a Bayanat/image
issue — `docker-compose.yml` runs these services `read_only` with
`no-new-privileges` and non-root `user:` accounts, so it's more exposed to
host-level exec restrictions than a default container.

Run the read-only diagnostic script from the Docker host (not inside a
container):

```bash
sudo bash scripts/diagnose-docker-permissions.sh /home/bayanat/bayanat
```

It checks, roughly in order of likelihood:

1. **`noexec` on the mount backing Docker's data-root** (or the project
   directory, `/home`, or `/tmp`). This is the most common cause: if
   `/var/lib/docker` (or a relocated `data-root`) lives on a filesystem
   mounted `noexec` — common on hardened servers — every container's
   entrypoint fails exactly like this, regardless of image. Fix by
   moving Docker's `data-root` to a mount without `noexec`, or removing
   the flag from the relevant `/etc/fstab` line and remounting.
2. **AppArmor denials** around the time the containers started
   (`dmesg`/`journalctl -k`). Ubuntu applies an AppArmor profile to
   containers by default; a stale or broken profile after an OS/Docker
   upgrade can deny the exec.
3. **Stale containers** created under an older version of
   `docker-compose.yml`. `docker compose down && docker compose
   --env-file .env.docker up -d` recreates them cleanly.
4. **Named volume mount options/ownership** (`postgres_data`,
   `redis_data`) if their backing storage is also affected by (1).

The script only reads state (daemon info, mounts, `dmesg`/journal,
`docker inspect`) — it changes nothing. Fixes for `noexec` mounts and
AppArmor profiles require host-level changes (editing `/etc/fstab`,
remounting, or relocating Docker's `data-root`) and should be applied
manually with root privileges after confirming the diagnosis.
