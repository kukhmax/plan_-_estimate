"""Photo pipeline building blocks (Stage 14).

Kept outside `app.domain.services` on purpose: that package eagerly imports
application services (config, database, models). Modules here depend only on
Pillow, anyio and `app.domain.exceptions`, so tooling such as
`scripts/photo_benchmark.py` can import them without application startup code.
"""
