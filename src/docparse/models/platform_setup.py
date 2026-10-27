"""Apple Silicon runtime setup: make Paddle's model downloader work behind a corporate TLS proxy.

On macOS the PP-DocLayout / PP-OCR detectors are downloaded by paddlex at first use. Two things
differ from a plain NVIDIA box: (1) paddlex defaults its model source to Hugging Face, whose file
CDN is blocked by some corporate proxies -- ModelScope's mirror gets through, selected via
PADDLE_PDX_MODEL_SOURCE=modelscope; (2) the proxy terminates TLS with a CA that lives in the macOS
keychain but not in certifi, so `truststore` is injected to make stdlib/requests TLS trust it. Both
are idempotent no-ops once applied. Mirrors ~/repos/EEP. Only runs on darwin; elsewhere it does
nothing, so the CUDA path is untouched.
"""
from __future__ import annotations

import os
import sys

_done = False


def ensure_paddle_downloads() -> None:
    """Idempotently set the Paddle model source and inject system TLS certs (macOS only)."""
    global _done
    if _done or sys.platform != "darwin":
        return
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "modelscope")
    try:
        import truststore

        truststore.inject_into_ssl()
    except ModuleNotFoundError:
        pass  # off a proxied network the default CA bundle is fine
    _done = True
