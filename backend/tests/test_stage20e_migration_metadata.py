"""Stage 20E finding F4 -- `alembic` loads only `app.models`; every table of the application must be known there, or `alembic revision --autogenerate`
proposes to DROP the ones it does not see."""
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def tables(statement: str) -> list[str]:
    code = f"{statement}\nfrom app.core.database import Base\nprint(' '.join(sorted(Base.metadata.tables)))"
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    return result.stdout.split()


def test_the_models_package_alone_knows_every_table_of_the_application():
    only_models = tables("import app.models")
    everything = tables("import app.main")
    assert only_models == everything, sorted(set(everything) - set(only_models))
    assert len(everything) >= 60
