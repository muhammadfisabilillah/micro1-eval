"""AI client multi-provider — OpenRouter + Gemini REST (Fase 2/3).

Mengirim prompt logika bisnis e-commerce ke model pilihan dan mengekstrak
angka final dari baris terakhir yang berangka (model diminta reasoning dulu,
lalu angka final — format-tata kelola: jarak jawaban terpisah dari ugutan
model mengikuti instruksi, baris metadata provider difilter).

Konfigurasi:
    - OpenRouter: OPENROUTER_API_KEY via `.env`, base https://openrouter.ai/api/v1
      (`openai` SDK, semua model slash-slug, mis. "openrouter/free")
    - Gemini    : GEMINI_API_KEY via `.env` / env var, REST generativelanguage
      (tanpa dependensi ekstra; "gemini" alias dari model env GEMINI_MODEL)

Fungsi & resep: temperature=0 (determinisme), backoff 429 exponensial,
retry lembut konten kosong/tanpa angka, AIResponse lengkap untuk arsip eval.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from openai import OpenAIError, RateLimitError as ORRateLimitError

logger = logging.getLogger(__name__)

BASE_DIR: Path = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

# ------------------------------------------------------------- konstanta
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_OPENROUTER_MODEL: str = "openrouter/free"
DEFAULT_GEMINI_MODEL: str = "gemini-3.5-flash"
# Catatan: Gemini menutup model lama untuk PENGGUNA BARU (2.0/2.5-flash sudah
# 404 / gemini-3.8-flash timeout). Teruji responsif: 3.5-flash, 3.1-flash-lite.
# Atur model lain via env GEMINI_MODEL tanpa mengubah kode.

SYSTEM_PROMPT: str = (
    "Kamu ahli logika bisnis e-commerce. Baca aturan dengan cermat, ringkaskan "
    "perhitunganmu langkah demi langkah. AKHIRI jawabanmu dengan baris terakhir "
    "yang HANYA berisi satu angka final (boleh memakai pemisah ribuan, mis. "
    "'650.000'). Tidak boleh ada teks atau satuan apa pun setelah angka tersebut."
)

# Pola angka: prioritas format ribuan penuh (1.585.000) dengan desimal koma
# opsional (1.500.364,80) agar tidak terpecah; lalu fallback angka biasa.
NUMBER_PATTERN: str = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?"
THOUSANDS_SEPARATED: re.Pattern[str] = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
METADATA_LINE: re.Pattern[str] = re.compile(
    r"^(?:user\s+safety|safety|moderation)", re.IGNORECASE
)

MAX_ATTEMPTS: int = 5
RETRY_BASE_DELAY: float = 5.0  # detik; dikali 2^(attempt-1), maksimum 60


# --------------------------------------------------------------- exceptions
class RateLimited(Exception):
    """Throttle (429/5xx) yang layak di-retry dengan backoff."""


class AIError(Exception):
    """Kegagalan non-throttle: auth, model tak ada, respons rongsok, dsb."""


# ------------------------------------------------------------------ types
@dataclass
class AIResponse:
    """Paket hasil lengkap dari satu evaluasi kasus (untuk arsip eval)."""
    raw: str
    number: Optional[float]
    attempts: int
    duration_s: float
    error: Optional[str] = None


# ----------------------------------------------------------------- parsing
def _extract_final_number(text: str) -> Optional[float]:
    """Angka terakhir dari baris berangka terakhir; skip baris metadata provider.

    Format ribuan Indonesia ('1.585.000' -> 1585000.0); desimal dipertahankan.
    """
    lines = [
        ln.strip()
        for ln in text.strip().splitlines()
        if ln.strip() and not METADATA_LINE.match(ln.strip())
    ]
    for line in reversed(lines):
        numbers = re.findall(NUMBER_PATTERN, line)
        if numbers:
            raw: str = numbers[-1]
            if THOUSANDS_SEPARATED.fullmatch(raw) or "," in raw:
                # Ribuan Indonesia: '1.585.000' / '1.500.364,80' -> 1585000 / 1500364.8
                raw = raw.replace(".", "").replace(",", ".")
            return float(raw)
    return None


# ------------------------------------------------------------- providers
def is_gemini(model: str) -> bool:
    return model == "gemini" or model.startswith("gemini")


def resolve_model(model: str) -> str:
    """Alias provider -> slug jadi: 'gemini' -> GEMINI_MODEL / default flash."""
    if model == "gemini":
        return os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    return model


def _openrouter_call(prompt: str, model: str, temperature: float) -> str:
    """Satu call OpenRouter. AssertionError/malformed naik sebagai AIError."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or api_key.startswith("sk-or-v1-GANTI"):
        raise AIError(f"OPENROUTER_API_KEY belum di-set (isi '{BASE_DIR / '.env'}').")
    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key, max_retries=0)
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except ORRateLimitError as exc:
        raise RateLimited(str(exc)) from exc
    except OpenAIError as exc:
        raise AIError(f"OpenRouter error: {exc}") from exc
    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise AIError(f"Struktur respons OpenRouter tidak terduga: {exc}") from exc


def _gemini_call(prompt: str, model: str, temperature: float) -> str:
    """Satu call Gemini via REST (tanpa dependensi ekstra)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key.startswith("GANTI"):
        raise AIError(f"GEMINI_API_KEY belum di-set (isi '{BASE_DIR / '.env'}').")

    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")[:300]
        except Exception:  # pragma: no cover - body tak terbaca
            detail = ""
        if exc.code in (429, 500, 503):
            raise RateLimited(f"Gemini HTTP {exc.code}") from exc
        raise AIError(f"Gemini HTTP {exc.code}: {detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        # Jaringan/timeout = transient: layak di-retry (bukan gagal permanen).
        raise RateLimited(f"Gemini jaringan: {exc}") from exc

    try:
        return "".join(
            part.get("text", "")
            for part in body["candidates"][0]["content"]["parts"]
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError(f"Struktur respons Gemini tidak terduga: {exc}") from exc


# ------------------------------------------------------------- entrypoint
def get_ai_response(
    prompt: str,
    model: str = DEFAULT_OPENROUTER_MODEL,
    temperature: float = 0.0,
) -> AIResponse:
    """Kirim prompt ke provider (OpenRouter/Gemini), balas AIResponse.

    Retry: 429/5xx backoff eksponensial; konten kosong/tanpa angka diulang
    lembut (ketahanan routing free-tier, bukan ketidakmampuan model).
    """
    resolved = resolve_model(model)
    content = ""
    error: Optional[str] = None
    attempts = 0
    start = time.perf_counter()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts = attempt
        try:
            if is_gemini(resolved):
                content = _gemini_call(prompt, resolved, temperature)
            else:
                content = _openrouter_call(prompt, resolved, temperature)
            if _extract_final_number(content) is not None:
                break  # sukses
            logger.warning(
                "Konten tanpa angka final (attempt %d/%d), ulangi...",
                attempt, MAX_ATTEMPTS,
            )
            time.sleep(1.0 * attempt)  # retry lembut, lalu lanjut attempt berikut
        except RateLimited as exc:
            if attempt == MAX_ATTEMPTS:
                error = f"429/5xx setelah {MAX_ATTEMPTS} percobaan: {exc}"
                logger.error(error)
            else:
                delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), 60.0)
                logger.warning("Rate limit (attempt %d/%d), tunda %.1fs...",
                               attempt, MAX_ATTEMPTS, delay)
                time.sleep(delay)
        except AIError as exc:
            error = str(exc)
            logger.error(error)
            break  # non-throttle: tidak layak di-retry

    duration_s = time.perf_counter() - start
    number = _extract_final_number(content)
    if number is None and error is None:
        error = "Tidak ada angka yang bisa diekstrak dari respons."

    return AIResponse(raw=content, number=number, attempts=attempts,
                      duration_s=duration_s, error=error)
