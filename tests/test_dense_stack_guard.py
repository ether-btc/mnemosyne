import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "dense-stack-guard.sh"


def make_venv(base, name, missing=(), version_map=None):
    if version_map is None:
        version_map = {"numpy": "2.4.6", "fastembed": "0.9.1", "sqlite_vec": "0.1.9"}
    venv = base / name
    (venv / "bin").mkdir(parents=True, exist_ok=True)
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n")
    stubs = base / (name + "_stubs")
    stubs.mkdir(exist_ok=True)
    for mod, ver in version_map.items():
        if mod in missing:
            continue
        (stubs / (mod + ".py")).write_text('__version__ = "%s"\n' % ver)
    python = sys.executable
    wrapper = venv / "bin" / "python"
    wrapper.write_text(
        "#!/bin/sh\nexport PYTHONPATH=%s\nexec %s -S \"$@\"\n" % (stubs, python)
    )
    wrapper.chmod(0o755)
    return venv


def base_env(tmp_path, extra=None):
    env = {
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    (tmp_path / "tmp").mkdir(exist_ok=True)
    if extra:
        env.update(extra)
    return env


def run(script_args, env):
    return subprocess.run(
        ["sh", str(SCRIPT)] + script_args,
        env=env,
        capture_output=True,
        text=True,
    )


def test_check_all_present(tmp_path):
    venv = make_venv(tmp_path, "venv")
    env = base_env(tmp_path)
    r = run(["--check", "--venv", str(venv)], env)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "RESOLVED VENV: " + str(venv) in r.stdout
    assert "OK   numpy 2.4.6" in r.stdout
    assert "OK   fastembed 0.9.1" in r.stdout
    assert "OK   sqlite_vec 0.1.9" in r.stdout


def test_check_missing_fastembed(tmp_path):
    venv = make_venv(tmp_path, "venv", missing={"fastembed"})
    env = base_env(tmp_path)
    r = run(["--check", "--venv", str(venv)], env)
    assert r.returncode != 0
    assert "MISSING fastembed" in r.stdout
    assert "ERROR: missing module(s):" in r.stdout
    assert "fastembed" in r.stdout


def test_dry_run_repair_no_exec(tmp_path):
    venv = make_venv(tmp_path, "venv", missing={"numpy", "fastembed", "sqlite_vec"})
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    log = tmp_path / "uv.log"
    uv = fakebin / "uv"
    uv.write_text('#!/bin/sh\necho "$@" >> "%s"\nexit 0\n' % log)
    uv.chmod(0o755)
    env = base_env(tmp_path, {"PATH": str(fakebin) + ":" + os.environ.get("PATH", "/usr/bin:/bin")})
    r = run(["--dry-run", "--repair", "--venv", str(venv)], env)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "uv pip install --python %s/bin/python fastembed==0.9.1 sqlite-vec==0.1.9" % venv in r.stdout
    assert "numpy==2.4.6" in r.stdout
    if log.exists():
        assert log.read_text() == ""


def test_resolution_newest_and_venv_override(tmp_path):
    root = tmp_path / "installs"
    root.mkdir()
    old_venv = root / "a" / "environments" / "x" / "venv"
    new_venv = root / "b" / "environments" / "y" / "venv"
    old_venv.mkdir(parents=True)
    new_venv.mkdir(parents=True)
    # build venv contents directly
    for v in (old_venv, new_venv):
        (v / "bin").mkdir(exist_ok=True)
        (v / "pyvenv.cfg").write_text("home = /usr/bin\n")
        stubs = v.parent / "stubs"
        stubs.mkdir(exist_ok=True)
        for mod, ver in (("numpy", "2.4.6"), ("fastembed", "0.9.1"), ("sqlite_vec", "0.1.9")):
            (stubs / (mod + ".py")).write_text('__version__ = "%s"\n' % ver)
        (v / "bin" / "python").write_text(
            "#!/bin/sh\nexport PYTHONPATH=%s\nexec %s -S \"$@\"\n" % (stubs, sys.executable)
        )
        (v / "bin" / "python").chmod(0o755)
    os.utime(str(old_venv), (1000, 1000))
    os.utime(str(new_venv), (2000, 2000))

    env = base_env(tmp_path, {"DENSE_GUARD_INSTALLS_ROOT": str(root)})
    r = run(["--check"], env)
    assert "RESOLVED VENV: " + str(new_venv) in r.stdout

    override = make_venv(tmp_path, "override")
    r2 = run(["--check", "--venv", str(override)], env)
    assert "RESOLVED VENV: " + str(override) in r2.stdout


def test_gateway_unit_resolution(tmp_path):
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    venv = make_venv(tmp_path, "unitvenv")
    (unit_dir / "app.service").write_text(
        '[Service]\nEnvironment="VENV=%s"\n' % venv
    )
    env = base_env(tmp_path, {"DENSE_GUARD_UNIT_DIRS": str(unit_dir)})
    r = run(["--check"], env)
    assert "RESOLVED VENV: " + str(venv) in r.stdout