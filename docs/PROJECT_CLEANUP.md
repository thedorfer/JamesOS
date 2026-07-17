# Project cleanup

`scripts/project_cleanup.py` audits repository-local generated artifacts and can remove a deliberately narrow set of caches. It never runs `git clean`, accepts no arbitrary target path, and defaults to dry-run.

## Commands

```bash
python scripts/project_cleanup.py audit
python scripts/project_cleanup.py report
python scripts/project_cleanup.py clean-caches
python scripts/project_cleanup.py clean-caches --confirm
```

`audit` and `report` print structured JSON and do not write report files. `clean-caches` prints every planned deletion and its byte size. Only `--confirm` performs deletion.

## Automatic categories

Only untracked, non-symlinked known caches are automatic candidates: Python bytecode and `__pycache__`, pytest/mypy/ruff caches, coverage output, `htmlcov`, build/dist and egg-info directories, and platform tool caches such as `.dart_tool`, `.gradle`, and `.kotlin`. Tracked contents convert the whole candidate to `keep`.

Temporary/editor backups and local logs are reported conservatively. Logs should normally be moved to machine-owned storage under `~/JamesOSData`; generated reports and images require manual review because many repository assets and documentation examples are intentional.

## Protected paths

The cleaner never traverses or modifies `.git`, `.venv`, `JamesOSData`, `Profiles`, or `Secrets`. It refuses symlink cache targets, paths outside the detected Git root, tracked files, and unknown files. License, notice, contributor documentation, source modules, fixtures, and other tracked files are never automatically removed.

## Manual review

Review candidate references, Git history, packaging entry points, documentation links, runtime file loading, and deployment compatibility before removing source, wrappers, scripts, fixtures, reports, images, or documentation. An import search alone is not deletion evidence. Private deployment remnants should be inspected and migrated without copying private values into Git.

Repository cleanup removes reproducible build/cache artifacts. User evidence, reports, logs, imports, indexes, and archives belong under `JamesOSData` and must be moved or archived through a separately reviewed workflow—not this cleaner.

## Recovery

Dry-run output is the primary safeguard. If a confirmed cleanup removes a cache, recreate it by rerunning the relevant compiler, test suite, Flutter build, or coverage command. Tracked files are unaffected and can be restored through normal version-control procedures. User data is outside this tool's scope.
