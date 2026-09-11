"""Abstract interfaces. Concrete implementations live in ``adapters/``.

Nothing outside this component may import from ``adapters/`` - only
``app/backend/main.py``, the single composition root.
"""
