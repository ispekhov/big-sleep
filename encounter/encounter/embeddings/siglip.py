"""SigLIP image embedder (production backend).

Requires ``transformers`` + ``torch`` and downloads model weights on first use,
so it is imported lazily and only constructed when explicitly configured.
DINOv2 can be wired in the same way as a second descriptor for ensembling.
"""

from __future__ import annotations

import io

import numpy as np

from ..config import get_settings


class SiglipEmbedder:
    name = "siglip"

    def __init__(self) -> None:
        import torch  # type: ignore
        from transformers import AutoModel, AutoProcessor  # type: ignore

        settings = get_settings()
        self._torch = torch
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._processor = AutoProcessor.from_pretrained(settings.siglip_model)
        self._model = AutoModel.from_pretrained(settings.siglip_model).to(
            self._device
        )
        self._model.eval()
        self.dim = int(self._model.config.vision_config.hidden_size)

    def embed(self, image_bytes: bytes) -> np.ndarray:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        inputs = self._processor(images=img, return_tensors="pt").to(self._device)
        with self._torch.no_grad():
            feats = self._model.get_image_features(**inputs)
        vec = feats[0].cpu().numpy().astype(np.float32)
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec
