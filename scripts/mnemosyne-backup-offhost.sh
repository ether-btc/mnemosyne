#!/bin/bash
# Nightly Mnemosyne DB snapshot -> /mnt/hermes128 (off-host, independent disk).
# Capture goes through mnemosyne.dr.recovery.create_backup, which opens the
# source READ-ONLY (mode=ro) and writes a gzipped binary SQLite image.
set -uo pipefail

SRC_DB="/home/hermes-pi/.hermes/mnemosyne/data/mnemosyne.db"
DEST_DIR="/mnt/hermes128/mnemosyne-db-archive"
MOUNT_POINT="/mnt/hermes128"
# Identify the backup disk by UUID, never by device letter.
DEST_UUID="${MNEMOSYNE_BACKUP_UUID:-bceffe6e-1402-4bb6-9ac2-55102b03241c}"
KEEP="${MNEMOSYNE_BACKUP_KEEP:-14}"
STAMP="$(date +%Y%m%d_%H%M%S)"

log() { echo "[$(date '+%F %T')] $*"; }

is_mounted() {
  [ -d "$1" ] || return 1
  findmnt -rn -M "$1" >/dev/null 2>&1
}

ensure_mounted() {
  is_mounted "$MOUNT_POINT" && return 0
  log "WARN  $MOUNT_POINT not mounted — mounting by UUID $DEST_UUID"
  local dev
  dev=$(blkid -U "$DEST_UUID" 2>/dev/null || true)
  if [ -z "$dev" ]; then
    log "ERROR: no filesystem with UUID $DEST_UUID found — is the disk attached?"
    return 1
  fi
  mkdir -p "$MOUNT_POINT" 2>/dev/null || true
  if ! sudo -n mount "$dev" "$MOUNT_POINT" 2>/dev/null; then
    log "ERROR: mount $dev -> $MOUNT_POINT failed"
    return 1
  fi
  is_mounted "$MOUNT_POINT" || { log "ERROR: mount did not take"; return 1; }
  log "OK    mounted $dev at $MOUNT_POINT"
}

ensure_mounted || exit 1

root_dev=$(stat -c '%d' /)
dest_dev=$(stat -c '%d' "$DEST_DIR" 2>/dev/null || echo "")
if [ -z "$dest_dev" ]; then
  log "ERROR: $DEST_DIR not available after mounting $MOUNT_POINT — aborting"
  exit 1
fi
if [ "$dest_dev" = "$root_dev" ]; then
  log "ERROR: $DEST_DIR is on the root filesystem — refusing to treat it as a backup"
  exit 1
fi
[ -r "$SRC_DB" ] || { log "ERROR: source db unreadable: $SRC_DB"; exit 1; }

mkdir -p "$DEST_DIR"

# Capture via recovery.py (read-only source). Never open SRC_DB read-write.
export PYTHONPATH="/home/hermes-pi/mnemosyne"
export MNEMOSYNE_DATA_DIR="$(dirname "$SRC_DB")"
export DEST_DIR KEEP

backup_path=""
if ! backup_path=$(python3 - <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, "/home/hermes-pi/mnemosyne")
DEST_DIR = Path(os.environ["DEST_DIR"])
KEEP = int(os.environ["KEEP"])
from mnemosyne.dr.recovery import create_backup, rotate_backups
result = create_backup(backup_dir=DEST_DIR)
rotate_backups(backup_dir=DEST_DIR, keep=KEEP)
print(result["backup_path"])
PY
); then
  log "ERROR: backup capture failed"
  exit 1
fi
backup_path=$(printf '%s\n' "$backup_path" | tail -n 1)
if [ -z "$backup_path" ] || [ ! -f "$backup_path" ]; then
  log "ERROR: no backup artifact produced"
  exit 1
fi

# Rename fresh artifact and move its sidecar alongside.
new="$DEST_DIR/mnemosyne.db.$STAMP.db.gz"
if ! mv -f "$backup_path" "$new"; then
  log "ERROR: failed to rename artifact"
  exit 1
fi
if [ -f "${backup_path}.json" ]; then
  if ! mv -f "${backup_path}.json" "${new}.json"; then
    log "ERROR: failed to move sidecar"
    exit 1
  fi
fi

# Prune archive to newest KEEP database snapshots across formats.
find "$DEST_DIR" -maxdepth 1 -name "mnemosyne.db.*" -type f ! -name "*-wal" ! -name "*-shm" ! -name "*.json" \
  | sort -r | tail -n +$((KEEP + 1)) | xargs -r rm -f

# Remove orphaned *.json sidecars whose database file no longer exists.
for sidecar in "$DEST_DIR"/*.json; do
  [ -e "$sidecar" ] || continue
  dbfile="${sidecar%.json}"
  if [ ! -e "$dbfile" ]; then
    rm -f "$sidecar"
  fi
done

# Verification, fail closed.
verify_db="$DEST_DIR/.mnemosyne-verify-${STAMP}.db"
rm -f "$verify_db"

if ! python3 -c '
import gzip, sys
with open(sys.argv[1], "rb") as f:
    data = gzip.decompress(f.read())
if data[:16] != b"SQLite format 3\x00":
    sys.exit(1)
' "$new"; then
  log "ERROR: artifact magic mismatch — removing"
  rm -f "$new" "${new}.json" "$verify_db"
  exit 1
fi

if ! gzip -dc "$new" > "$verify_db"; then
  log "ERROR: decompress failed — removing"
  rm -f "$new" "${new}.json" "$verify_db"
  exit 1
fi

chk=$(sqlite3 "$verify_db" "PRAGMA quick_check;" 2>&1 | head -n 1)
rm -f "$verify_db"
if [ "$chk" != "ok" ]; then
  log "ERROR: quick_check failed ($chk) — removing"
  rm -f "$new" "${new}.json"
  exit 1
fi

chmod 600 "$new"
size_bytes=$(stat -c %s "$new")
size_mib=$(( size_bytes / 1048576 ))
log "OK    $(basename "$new") (${size_mib} MiB, read-only source, quick_check=ok)"

exit 0
