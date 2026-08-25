"""
office-core — Office document engine.
Vendored libraries live in vendored/; tools add it to sys.path at runtime.
"""
import os
import sys

_VENDORED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendored")
if os.path.isdir(_VENDORED) and _VENDORED not in sys.path:
    sys.path.insert(0, _VENDORED)
