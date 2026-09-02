"""Local, offline vector embeddings via sentence-transformers.

The model (all-MiniLM-L6-v2, ~90 MB) is downloaded once to the local
HuggingFace cache and used entirely offline thereafter. No API keys, no cloud
calls, no telemetry.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from .paths import bundled_model_home

import numpy as np

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384          # all-MiniLM-L6-v2 output size
DEFAULT_BATCH_SIZE = 32

_INSTALL_HINT = (
    "sentence-transformers is required. Install it with:\n"
    "    pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
    "    pip install sentence-transformers"
)


def default_cache_dir() -> Path:
    """Where the model is kept on this machine.

    A packaged build ships the model inside it, so an engineer who has never
    run Python - and may never put this machine online - still gets a working
    search. Falling back to the HuggingFace cache keeps a source checkout
    behaving exactly as before.
    """
    override = os.environ.get("HF_HOME") or os.environ.get(
        "SENTENCE_TRANSFORMERS_HOME"
    )
    if override:
        return Path(override)
    bundled = bundled_model_home()
    if bundled is not None:
        return bundled
    return Path.home() / ".cache" / "huggingface"


class Embedder:
    """Thin wrapper around SentenceTransformer.

    The model is loaded lazily so the UI can start instantly and only pay the
    (few seconds) load cost when the engineer actually indexes or searches.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        offline: bool = False,
        device: str = "cpu",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.offline = offline
        self._model = None

    # --- model lifecycle ---------------------------------------------------
    @property
    def model(self):
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError(_INSTALL_HINT) from exc

        # A packaged build carries its own copy of the model. Point the
        # HuggingFace libraries at it before they are imported, since they
        # read this once and cache it.
        bundled = bundled_model_home()
        if bundled is not None:
            os.environ.setdefault("HF_HOME", str(bundled))

        if self.offline:
            # Hard-fail rather than silently reaching for the network.
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"

        try:
            return SentenceTransformer(self.model_name, device=self.device)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load the local model '{self.model_name}'.\n"
                f"If this is the first run, connect to the internet once and "
                f"run:  python download_model.py\n"
                f"Cache location: {default_cache_dir()}\n"
                f"Underlying error: {exc}"
            ) from exc

    def warm_up(self) -> None:
        """Force the model to load now (e.g. on a background thread)."""
        self.model.encode(["warm up"], show_progress_bar=False)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def dimension(self) -> int:
        if self._model is None:
            return EMBEDDING_DIM
        return int(self._model.get_sentence_embedding_dimension())

    # --- encoding ----------------------------------------------------------
    def encode(
        self,
        texts: Sequence[str],
        batch_size: int = DEFAULT_BATCH_SIZE,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> np.ndarray:
        """Embed a list of texts into an (n, dim) float32 array.

        Vectors are L2-normalised, so cosine similarity is a plain dot product.
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        total = len(texts)
        chunks: List[np.ndarray] = []

        for start in range(0, total, batch_size):
            batch = list(texts[start:start + batch_size])
            vectors = self.model.encode(
                batch,
                batch_size=batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            chunks.append(np.asarray(vectors, dtype=np.float32))
            if progress:
                progress(min(start + batch_size, total), total)

        return np.vstack(chunks)

    def encode_one(self, text: str) -> np.ndarray:
        """Embed a single search query into a (dim,) float32 vector."""
        return self.encode([text])[0]
