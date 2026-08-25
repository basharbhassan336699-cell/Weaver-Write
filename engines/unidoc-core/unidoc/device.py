"""
كشف قدرات الجهاز — GPU، خادم vLLM بعيد، Tesseract.
"""

from __future__ import annotations
import os
import shutil

from .router import DeviceCapabilities


def _has_cuda_gpu() -> bool:
    """فحص وجود GPU يدعم CUDA."""
    # 1. متغير بيئة صريح
    if os.environ.get("UNIDOC_FORCE_CPU") == "1":
        return False
    if os.environ.get("UNIDOC_FORCE_GPU") == "1":
        return True

    # 2. torch إن كان مثبتاً
    try:
        import torch  # type: ignore
        return bool(torch.cuda.is_available())
    except Exception:
        pass

    # 3. nvidia-smi كبديل
    return shutil.which("nvidia-smi") is not None


def _has_tesseract() -> bool:
    """فحص وجود Tesseract OCR (fallback للأجهزة الصغيرة)."""
    if shutil.which("tesseract") is not None:
        return True
    try:
        import pytesseract  # type: ignore
        return True
    except Exception:
        return False


def detect_device() -> DeviceCapabilities:
    """
    كشف تلقائي لقدرات الجهاز الحالي.

    متغيرات البيئة المؤثرة:
      UNIDOC_FORCE_CPU=1      → تعطيل GPU
      UNIDOC_FORCE_GPU=1      → إجبار GPU
      UNIDOC_VLLM_URL=<url>   → خادم vLLM بعيد
      UNIDOC_NO_TESSERACT=1   → تعطيل Tesseract fallback
    """
    remote_url = os.environ.get("UNIDOC_VLLM_URL")

    return DeviceCapabilities(
        has_gpu=_has_cuda_gpu(),
        has_vllm_remote=bool(remote_url),
        remote_url=remote_url,
        allow_tesseract=(
            os.environ.get("UNIDOC_NO_TESSERACT") != "1" and _has_tesseract()
        ),
    )
