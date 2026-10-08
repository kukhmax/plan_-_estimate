"""Documents / PDF (Stage 15).

Data -> template -> PDF. A template receives a ready view model and formats it; it never calculates (sums, quantities and
order come from the Stage 10 estimate snapshots and the Stage 14I report read model). Client-facing documents are Polish:
every label lives in `locales/pl.json`. The PDF is rendered by WeasyPrint in a separate, resource-limited process
(`renderer.py`); templates can reach no network and no file outside the bundled fonts and the document's own assets.
"""
