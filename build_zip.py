"""
Build dist/SmartDent.zip, the folder to submit for TM471.

    python build_zip.py

Only the items in INCLUDE go in. Private or bulky files are always left out:
the dataset (data/), .venv, the database and uploads (instance/), .env, caches,
old backups (_restyle_tmp) and dist itself. The zip unpacks into one SmartDent/ folder.
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "dist" / "SmartDent.zip"

INCLUDE = ["app", "ml", "scripts", "tests", "notebooks", "docs", "samples", "models/best.pt",
           "run.py", "requirements.txt", "start.bat", "start.sh", "start.command", "README.md",
           ".env.example", ".gitignore", "pytest.ini", "build_zip.py"]
SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", "instance", "uploads", "data", "_restyle_tmp", "dist",
             ".ipynb_checkpoints"}
SKIP_FILES = {".env", "secret_key", "kaggle.json"}
SKIP_SUFFIXES = {".db", ".pyc", ".sqlite", ".sqlite3"}
EXECUTABLE = {"start.sh", "start.command"}     # keep the "run me" permission for Mac and Linux


def files_to_pack():
    for item in INCLUDE:
        path = ROOT / item
        if not path.exists():
            raise SystemExit(f"Missing: {item}")
        for f in ([path] if path.is_file() else sorted(path.rglob("*"))):
            rel = f.relative_to(ROOT)
            if f.is_file() and not SKIP_DIRS.intersection(rel.parts[:-1]) \
                    and f.name not in SKIP_FILES and f.suffix not in SKIP_SUFFIXES:
                yield f, rel


def main():
    OUT.parent.mkdir(exist_ok=True)
    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f, rel in files_to_pack():
            info = zipfile.ZipInfo.from_file(f, Path("SmartDent") / rel)
            mode = 0o755 if rel.as_posix() in EXECUTABLE else 0o644
            info.external_attr = (0o100000 | mode) << 16          # regular file + permissions
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, f.read_bytes())
            count += 1
    print(f"Wrote {OUT.relative_to(ROOT)}: {count} files, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
