"""Lightweight initializer for the GIFTs package.

Original code imported all product modules (METAR, SWA, TAF, TCA, VAA) eagerly.
Optional modules may have extra third-party dependencies (e.g. `skyfield` for SWA).
We now import each module lazily, tolerating missing optional dependencies so that
core METAR encoding/decoding works in minimal environments.
"""

# flake8: noqa F401
try:
    # Provides Encoder class composing metarDecoder/metarEncoder
    from . import METAR as METAR
except ImportError:  # pragma: no cover
    # METAR functionality unavailable (optional dependency chain missing)
    pass

OPTIONAL_MODULES = ["SWA", "TAF", "TCA", "VAA"]
for _name in OPTIONAL_MODULES:
    try:
        globals()[_name] = __import__(
            f"{__package__}.{_name}", fromlist=[_name])
    except ImportError:  # pragma: no cover
        pass

try:
    from .common import bulletin as bulletin
except ImportError:  # pragma: no cover
    # Bulletin module optional
    pass
