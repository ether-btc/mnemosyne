#!/bin/sh
# dense-stack-guard.sh
# Resolve the venv that owns the dense stack (numpy/fastembed/sqlite_vec)
# and verify or repair it.
#
# WHY: dense recall works only because numpy 2.4.6 / fastembed 0.9.1 /
# sqlite-vec 0.1.9 were hand-installed into the pm committed gateway venv.
# That venv is rebuilt from workspace/pyproject.toml + uv.lock on every
# hermes update / pm reprovision, which drops the three packages; the agent
# then silently returns to FTS-only recall (embeddings.available() is False
# at import: no error, just worse answers). This guard checks the resolved
# venv before that degradation and can repair the missing pieces.
#
# VENV resolution order (first match wins):
#   a) --venv PATH (must exist and contain pyvenv.cfg)
#   b) Gateway unit runtime: search $DENSE_GUARD_UNIT_DIRS (colon-separated
#      override; default space-separated list of systemd unit dirs) for
#      *.service/*.unit files; per file (sorted by name, dirs in listed
#      order) extract the first VENV= value (Environment="VENV=/path" or
#      bare VENV=/path); use it if its pyvenv.cfg exists.
#   c) Fallback: newest $DENSE_GUARD_INSTALLS_ROOT/*/environments/*/venv
#      (default root $HOME/.hermes/installs) whose pyvenv.cfg exists,
#      ordered by venv directory mtime newest first.
#
# Manual recovery on a host without uv:
#   $VENV/bin/python -m ensurepip    (only if pip is missing)
#   $VENV/bin/python -m pip install numpy==2.4.6 fastembed==0.9.1 sqlite-vec==0.1.9
#
set -u

usage() {
    echo "Usage: $0 [--venv PATH] [--dry-run] [--check|--repair]" >&2
}

VENV=""
venv_arg=""
dry_run=0
check=0
repair=0

while [ $# -gt 0 ]; do
    case "$1" in
        --venv)
            if [ $# -lt 2 ]; then
                usage
                exit 2
            fi
            venv_arg="$2"
            shift 2
            ;;
        --venv=*)
            venv_arg="${1#--venv=}"
            shift
            ;;
        --dry-run)
            dry_run=1
            shift
            ;;
        --check)
            check=1
            shift
            ;;
        --repair)
            repair=1
            shift
            ;;
        *)
            echo "Unknown flag: $1" >&2
            usage
            exit 2
            ;;
    esac
done

if [ "$check" -eq 1 ] && [ "$repair" -eq 1 ]; then
    echo "ERROR: --check and --repair are mutually exclusive" >&2
    exit 2
fi

if [ "$check" -eq 0 ] && [ "$repair" -eq 0 ]; then
    check=1
fi

# --- VENV resolution ---
if [ -n "$venv_arg" ]; then
    # (a) --venv wins
    if [ ! -f "$venv_arg/pyvenv.cfg" ]; then
        echo "ERROR: --venv path does not exist or lacks pyvenv.cfg: $venv_arg" >&2
        exit 2
    fi
    VENV="$venv_arg"
else
    # (b) Gateway unit runtime
    found=0
    if [ -n "${DENSE_GUARD_UNIT_DIRS:-}" ]; then
        oldifs="$IFS"
        IFS=:
        # shellcheck disable=SC2086
        for d in $DENSE_GUARD_UNIT_DIRS; do
            [ -d "$d" ] || continue
            file_list=$(for f in "$d"/*.service "$d"/*.unit; do [ -f "$f" ] && printf '%s\n' "$f"; done | sort)
            while IFS= read -r f; do
                [ -z "$f" ] && continue
                venv_val=$(sed -n 's/.*VENV=\([^"[:space:]]*\).*/\1/p' "$f" | head -n 1)
                if [ -n "$venv_val" ] && [ -f "$venv_val/pyvenv.cfg" ]; then
                    VENV="$venv_val"
                    found=1
                    break
                fi
            done <<EOF
$file_list
EOF
            [ "$found" -eq 1 ] && break
        done
        IFS="$oldifs"
    else
        for d in /etc/systemd/system /run/systemd/system "${HOME:-}/.config/systemd/user" /etc/systemd/user; do
            [ -d "$d" ] || continue
            file_list=$(for f in "$d"/*.service "$d"/*.unit; do [ -f "$f" ] && printf '%s\n' "$f"; done | sort)
            while IFS= read -r f; do
                [ -z "$f" ] && continue
                venv_val=$(sed -n 's/.*VENV=\([^"[:space:]]*\).*/\1/p' "$f" | head -n 1)
                if [ -n "$venv_val" ] && [ -f "$venv_val/pyvenv.cfg" ]; then
                    VENV="$venv_val"
                    found=1
                    break
                fi
            done <<EOF
$file_list
EOF
            [ "$found" -eq 1 ] && break
        done
    fi

    if [ "$found" -eq 0 ]; then
        # (c) Fallback: newest installs root venv
        root="${DENSE_GUARD_INSTALLS_ROOT:-${HOME:-}/.hermes/installs}"
        best=$(find "$root" -type d -name venv -path '*/environments/*/venv' -exec test -f '{}/pyvenv.cfg' \; -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -n 1 | cut -d' ' -f2-)
        if [ -z "$best" ]; then
            echo "ERROR: no venv with pyvenv.cfg found under $root" >&2
            exit 2
        fi
        VENV="$best"
    fi
fi

echo "RESOLVED VENV: $VENV"

# --- checker temp file ---
checker=""
trap '[ -n "$checker" ] && rm -f "$checker"' EXIT
checker="${TMPDIR:-/tmp}/dense-stack-guard-checker.$$"
# Spec checker (literal): import sys; mod=sys.argv[1]; try: m=__import__(mod); except ImportError: sys.stderr.write("MISSING "+mod+"\n"); sys.exit(1); print(mod+" "+getattr(m,"__version__","?")); sys.exit(0)
cat > "$checker" <<'EOF'
import sys
mod = sys.argv[1]
try:
    m = __import__(mod)
except ImportError:
    sys.stderr.write("MISSING " + mod + "\n")
    sys.exit(1)
print(mod + " " + getattr(m, "__version__", "?"))
sys.exit(0)
EOF

# --- module checks ---
missing_numpy=0
missing_fastembed=0
missing_sqlite_vec=0
missing_list=""

for mod in numpy fastembed sqlite_vec; do
    out=$("$VENV/bin/python" "$checker" "$mod" 2>/dev/null)
    rc=$?
    if [ "$rc" -eq 0 ]; then
        printf 'OK   %s\n' "$out"
    else
        printf 'MISSING %s\n' "$mod"
        missing_list="$missing_list $mod"
        case "$mod" in
            numpy) missing_numpy=1 ;;
            fastembed) missing_fastembed=1 ;;
            sqlite_vec) missing_sqlite_vec=1 ;;
        esac
    fi
done

# comma-separated list
comma_list=""
for m in $missing_list; do
    if [ -z "$comma_list" ]; then
        comma_list="$m"
    else
        comma_list="$comma_list, $m"
    fi
done

# --- mode handling ---
if [ "$check" -eq 1 ]; then
    if [ -n "$missing_list" ]; then
        printf 'ERROR: missing module(s): %s\n' "$comma_list"
        exit 2
    fi
    exit 0
fi

# repair
if [ -z "$missing_list" ]; then
    echo "ALL PRESENT"
    exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv not found in PATH" >&2
    exit 2
fi

rc_overall=0

run_fastembed=0
run_numpy=0
if [ "$missing_fastembed" -eq 1 ] || [ "$missing_sqlite_vec" -eq 1 ]; then
    run_fastembed=1
fi
if [ "$missing_numpy" -eq 1 ]; then
    run_numpy=1
fi

if [ "$run_fastembed" -eq 1 ]; then
    if [ "$dry_run" -eq 1 ]; then
        echo "DRY-RUN: uv pip install --python $VENV/bin/python fastembed==0.9.1 sqlite-vec==0.1.9"
    else
        echo "uv pip install --python $VENV/bin/python fastembed==0.9.1 sqlite-vec==0.1.9"
        uv pip install --python "$VENV/bin/python" fastembed==0.9.1 sqlite-vec==0.1.9
        rc=$?
        if [ "$rc" -ne 0 ]; then
            rc_overall=$rc
        fi
    fi
fi

if [ "$run_numpy" -eq 1 ]; then
    if [ "$dry_run" -eq 1 ]; then
        echo "DRY-RUN: uv pip install --python $VENV/bin/python numpy==2.4.6"
    else
        echo "uv pip install --python $VENV/bin/python numpy==2.4.6"
        uv pip install --python "$VENV/bin/python" numpy==2.4.6
        rc=$?
        if [ "$rc" -ne 0 ]; then
            rc_overall=$rc
        fi
    fi
fi

exit "$rc_overall"
EOF
chmod +x /home/hermes-pi/.hermes/kanban/workspaces/t_DENSEGUARD/wt/scripts/dense-stack-guard.sh
echo done