#!/usr/bin/env bash
# Diagnose "exec ...docker-entrypoint.sh: operation not permitted" failures
# for Bayanat's docker-compose services (typically postgres/redis, but any
# service can be affected).
#
# This script is read-only: it inspects the Docker daemon, the host's mount
# table, AppArmor/SELinux state, and the affected images/volumes. It makes
# no changes. Run it on the Docker host itself (not inside a container),
# with sudo so it can read dmesg/journal and root-owned mount metadata:
#
#   sudo bash scripts/diagnose-docker-permissions.sh
#
# Optionally pass the docker-compose project directory (defaults to CWD):
#   sudo bash scripts/diagnose-docker-permissions.sh /home/bayanat/bayanat

set -uo pipefail

PROJECT_DIR="${1:-$PWD}"
DIVIDER="--------------------------------------------------------------------"

section() {
  echo
  echo "$DIVIDER"
  echo "## $1"
  echo "$DIVIDER"
}

have() { command -v "$1" >/dev/null 2>&1; }

section "1. Docker daemon status"
if have systemctl; then
  systemctl status docker --no-pager 2>&1 | head -n 15
else
  echo "systemctl not found (non-systemd host?)"
fi
echo
if have docker; then
  docker version 2>&1
  echo
  docker info --format \
    'DockerRootDir: {{.DockerRootDir}}
Storage Driver: {{.Driver}}
Cgroup Driver: {{.CgroupDriver}}
Security Options: {{.SecurityOptions}}
Server Version: {{.ServerVersion}}' 2>&1
else
  echo "docker CLI not found on PATH"
fi

section "2. AppArmor / SELinux status"
if have aa-status; then
  aa-status 2>&1 | head -n 30
else
  echo "aa-status not found (AppArmor tools not installed, or not Ubuntu/Debian)"
fi
echo
echo "-- Recent AppArmor denials (dmesg) --"
if have dmesg; then
  dmesg 2>/dev/null | grep -i apparmor | tail -n 40 || echo "(none found in dmesg buffer)"
else
  echo "dmesg not available"
fi
echo
echo "-- Recent AppArmor denials (journal) --"
if have journalctl; then
  journalctl -k --since "-2 days" 2>/dev/null | grep -i apparmor | tail -n 40 || echo "(none found)"
else
  echo "journalctl not available"
fi
echo
if have getenforce; then
  echo "-- SELinux --"
  getenforce 2>&1
  have sestatus && sestatus 2>&1
else
  echo "SELinux tools not present (expected on stock Ubuntu, which uses AppArmor)"
fi

section "3. noexec/nosuid mount options (the #1 cause of this error)"
echo "If the filesystem backing Docker's data-root (or the named volumes) is"
echo "mounted with 'noexec', every container's entrypoint will fail exactly"
echo "like this, for every image, regardless of image content."
echo
DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
echo "Docker root dir: $DOCKER_ROOT"
if have findmnt; then
  echo
  echo "-- Mount covering Docker root dir --"
  findmnt -T "$DOCKER_ROOT" -o TARGET,SOURCE,FSTYPE,OPTIONS 2>&1
  echo
  echo "-- Mount covering project dir ($PROJECT_DIR) --"
  findmnt -T "$PROJECT_DIR" -o TARGET,SOURCE,FSTYPE,OPTIONS 2>&1
  echo
  echo "-- Mount covering /home (Bayanat is commonly installed under /home) --"
  findmnt -T /home -o TARGET,SOURCE,FSTYPE,OPTIONS 2>&1
  echo
  echo "-- Mount covering /tmp --"
  findmnt -T /tmp -o TARGET,SOURCE,FSTYPE,OPTIONS 2>&1
else
  echo "findmnt not found; falling back to 'mount'"
  mount 2>&1 | grep -E " / | /home | /var | /tmp " || true
fi
echo
echo "-- Relevant /etc/fstab entries --"
grep -E '^\S+\s+(/|/home|/var|/tmp)\s' /etc/fstab 2>/dev/null || echo "(no matching fstab lines, or /etc/fstab unreadable)"

section "4. Named volume inspection (postgres_data / redis_data)"
if have docker; then
  for vol in postgres_data redis_data; do
    # Compose prefixes volume names with the project name, so glob-match.
    match="$(docker volume ls --format '{{.Name}}' | grep -E "(^|_)${vol}\$" | head -n1)"
    if [ -z "$match" ]; then
      echo "Volume matching '$vol' not found (has 'docker compose up' been run yet?)"
      continue
    fi
    echo "-- $match --"
    docker volume inspect "$match" 2>&1
    mountpoint="$(docker volume inspect -f '{{.Mountpoint}}' "$match" 2>/dev/null)"
    if [ -n "$mountpoint" ] && have findmnt; then
      echo "Mount options for $mountpoint:"
      findmnt -T "$mountpoint" -o TARGET,SOURCE,FSTYPE,OPTIONS 2>&1
    fi
    echo
  done
else
  echo "docker CLI not found on PATH"
fi

section "5. Entrypoint file permissions inside the images"
if have docker; then
  for img in 'postgis/postgis:16-3.5' 'redis:7.4-alpine'; do
    echo "-- $img --"
    docker run --rm --entrypoint sh "$img" -c \
      'ls -la /usr/local/bin/docker-entrypoint.sh; stat /usr/local/bin/docker-entrypoint.sh 2>/dev/null || true' \
      2>&1
    echo
  done
else
  echo "docker CLI not found on PATH"
fi

section "6. Effective security options on the failing containers"
if have docker; then
  for c in postgres redis; do
    if docker inspect "$c" >/dev/null 2>&1; then
      echo "-- $c --"
      docker inspect "$c" --format \
        'User: {{.Config.User}}
ReadonlyRootfs: {{.HostConfig.ReadonlyRootfs}}
SecurityOpt: {{.HostConfig.SecurityOpt}}
Tmpfs: {{.HostConfig.Tmpfs}}
Privileged: {{.HostConfig.Privileged}}' 2>&1
      echo
    else
      echo "Container '$c' does not exist (not created yet, or was removed)"
    fi
  done
else
  echo "docker CLI not found on PATH"
fi

section "Summary"
cat <<'EOF'
Read through sections 1-6 above. In order of likelihood for this exact
error ("exec ...docker-entrypoint.sh: operation not permitted" on ALL
containers):

  1. Section 3 shows 'noexec' in the OPTIONS column for the mount backing
     Docker's data-root, the project directory, /home, or /tmp.
     -> Move Docker's data-root (or the project) off that filesystem, or
        remount it without noexec.

  2. Section 2 shows AppArmor DENIED lines around the time you tried to
     start the containers.
     -> Note the profile name in the denial and check
        /etc/apparmor.d/ for a stale/broken docker profile; `sudo
        systemctl reload apparmor` after fixing, or temporarily set the
        profile to complain mode with `sudo aa-complain <profile>` to
        confirm AppArmor is the cause (re-enforce afterwards).

  3. Section 6 shows unexpected SecurityOpt/User combinations, or the
     containers were left over from a different compose file version.
     -> `docker compose down` then `docker compose up -d` to recreate
        with the current docker-compose.yml.

  4. Section 4 shows the named volume's Mountpoint is on a noexec/nosuid
     mount, or ownership under the volume doesn't match the container's
     'user:' directive.
     -> `docker volume rm` the affected volume (data loss for that
        volume) after backing it up, then let compose recreate it; or
        relocate Docker's data-root as in (1).

If none of the above matches, capture the full output of this script and
share it for further diagnosis.
EOF
