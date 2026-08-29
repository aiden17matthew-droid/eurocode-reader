"""One-time model download for Eurocode Reader.

Run this ONCE while connected to the internet:

    python download_model.py

It caches all-MiniLM-L6-v2 (~90 MB) locally. After this, the app runs fully
offline - no internet, no API keys, no cloud services.
"""

from __future__ import annotations

import sys

from backend.embedder import DEFAULT_MODEL_NAME, Embedder, default_cache_dir


def main() -> int:
    print(f"Downloading '{DEFAULT_MODEL_NAME}' (~90 MB)...")
    print(f"Cache location: {default_cache_dir()}")

    try:
        embedder = Embedder(model_name=DEFAULT_MODEL_NAME)
        embedder.warm_up()
    except Exception as exc:
        print(f"\nFailed: {exc}")
        return 1

    vector = embedder.encode_one("shear resistance of bored piles")
    print(f"\nModel ready. Embedding dimension: {vector.shape[0]}")
    print("You can now disconnect from the internet - the app runs offline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
