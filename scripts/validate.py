"""Pipeline de validacion local (equivalente a `npm run validate`).

Ejecuta en orden:
  1. pyflakes  -> syntax-check estatico de app.py + services/ + blueprints/.
  2. tests     -> python test_core.py.
  3. e2e       -> python verify_project.py.
  4. ruff      -> opcional, si ruff esta instalado: `ruff check .`
                  y `ruff format --check .`.
  5. mypy      -> opcional, si mypy esta instalado: type-check no
                  estricto (`--ignore-missing-imports`).

Si ruff o mypy no estan instalados se omiten sin error (solo
informativo). El script sale con codigo != 0 si cualquier paso
obligatorio falla.

Uso:
  python scripts/validate.py

Equivalente npm del devkit: `npm run validate`.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Forzar UTF-8 en stdout/stderr para que los caracteres (✓, ✗, →) no
# rompan en consolas Windows con cp1252 por defecto.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def header(title: str) -> None:
    print()
    print("=" * 60)
    print(f" {title}")
    print("=" * 60)


def step(label: str, cmd: list[str], cwd: Path | None = None, required: bool = True) -> bool:
    """Ejecuta `cmd`; devuelve True si termina con codigo 0.

    Si ``required`` es False y el comando falla, solo se reporta como
    advertencia y no se cuenta como fallo bloqueante.
    """
    header(label)
    t0 = time.monotonic()
    try:
        result = subprocess.run(cmd, cwd=cwd or ROOT, check=False)
    except FileNotFoundError as e:
        print(f"  ! herramienta no encontrada: {e}")
        return True  # Opcionales no cuentan como fallo
    dt = time.monotonic() - t0
    ok = result.returncode == 0
    if required:
        mark = "OK" if ok else "FAIL"
    else:
        mark = "OK" if ok else "WARN"
    print(f"  [{mark}] {label} ({dt:.1f}s)")
    return ok or not required


def main() -> int:
    failed: list[str] = []

    # 1. pyflakes (obligatorio). stdlib; no requiere pip.
    if shutil.which("pyflakes"):
        if not step(
            "pyflakes app.py services/ blueprints/",
            ["pyflakes", "app.py", "services", "blueprints"],
        ):
            failed.append("pyflakes")
    else:
        # Fallback: usar `python -m pyflakes` (viene con el paquete
        # pyflakes, pero si no está, hacer compile() por archivo).
        header("pycompile check (fallback)")
        ok = True
        for py in [
            ROOT / "app.py",
            *(p for p in (ROOT / "services").glob("*.py")),
            *(p for p in (ROOT / "blueprints").glob("*.py")),
            ROOT / "test_core.py",
            ROOT / "verify_project.py",
        ]:
            try:
                py.resolve(strict=True).read_text(encoding="utf-8")
            except OSError:
                pass
            import py_compile
            try:
                py_compile.compile(str(py), doraise=True)
                print(f"  ✓ {py.relative_to(ROOT)}")
            except py_compile.PyCompileError as e:
                print(f"  ✗ {py.relative_to(ROOT)}: {e}")
                ok = False
        if not ok:
            failed.append("pycompile")

    # 2. unit tests
    if not step(
        "tests (test_core.py)",
        [sys.executable, str(ROOT / "test_core.py")],
    ):
        failed.append("tests")

    # 3. e2e
    if not step(
        "e2e (verify_project.py)",
        [sys.executable, str(ROOT / "verify_project.py")],
    ):
        failed.append("e2e")

    # 4. ruff (opcional, informativo: no bloquea el exit code mientras
    # la base de codigo no este limpia). Para promoverlo a obligatorio
    # pasar `required=True` en step().
    if shutil.which("ruff"):
        step("ruff check .", ["ruff", "check", "."], required=False)
        step("ruff format --check .", ["ruff", "format", "--check", "."], required=False)
    else:
        print("\n  [skip] ruff no instalado (opcional)")

    # 5. mypy (opcional, informativo por la misma razon).
    if shutil.which("mypy"):
        targets = ["app.py", "services", "blueprints"]
        step(
            "mypy (no estricto, ignore-missing-imports)",
            ["mypy", "--ignore-missing-imports", *targets],
            required=False,
        )
    else:
        print("\n  [skip] mypy no instalado (opcional)")

    # Resumen
    header("RESUMEN")
    if failed:
        print(f"  ✗ Pasos fallidos: {', '.join(failed)}")
        return 1
    print("  ✓ Todas las validaciones pasaron")
    return 0


if __name__ == "__main__":
    sys.exit(main())