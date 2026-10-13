"""
Speaker Recognition & Voice Biometrics for MARK LIV.

Extracts an acoustic voice fingerprint (MFCC mean+std embedding) to distinguish
the registered owner from background speech and third parties.
"""

from __future__ import annotations

import os
from pathlib import Path
import numpy as np
import scipy.fftpack as fftpack

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_PATH = BASE_DIR / "config" / "voice_profile.npy"
SIMILARITY_THRESHOLD = 0.72


def _hz_to_mel(hz: float | np.ndarray) -> float | np.ndarray:
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: float | np.ndarray) -> float | np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def extract_embedding(
    audio: np.ndarray,
    sr: int = 16000,
    n_mfcc: int = 20,
    n_mels: int = 40,
    n_fft: int = 512,
    hop_len: int = 160,
) -> np.ndarray:
    """Extract a 40-dimensional L2-normalized MFCC fingerprint (mean + std)."""
    if audio is None or len(audio) < n_fft:
        return np.zeros(n_mfcc * 2, dtype=np.float32)

    # Flatten and ensure float32
    audio = np.asarray(audio, dtype=np.float32).flatten()
    max_val = np.max(np.abs(audio)) if len(audio) > 0 else 0.0
    if max_val > 1.0:
        audio = audio / 32768.0

    # Pre-emphasis filter
    audio = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])

    # Framing
    num_frames = 1 + int(np.floor((len(audio) - n_fft) / hop_len))
    if num_frames < 1:
        return np.zeros(n_mfcc * 2, dtype=np.float32)

    indices = (
        np.tile(np.arange(0, n_fft), (num_frames, 1))
        + np.tile(np.arange(0, num_frames * hop_len, hop_len), (n_fft, 1)).T
    )
    frames = audio[indices] * np.hamming(n_fft)

    # Power spectrum
    mag = np.absolute(np.fft.rfft(frames, n_fft))
    pow_frames = (1.0 / n_fft) * (mag ** 2)

    # Mel filterbank
    low_mel = _hz_to_mel(0)
    high_mel = _hz_to_mel(sr / 2)
    mel_points = np.linspace(low_mel, high_mel, n_mels + 2)
    hz_points = _mel_to_hz(mel_points)
    bins = np.floor((n_fft + 1) * hz_points / sr).astype(int)

    fbank = np.zeros((n_mels, int(n_fft / 2 + 1)))
    for m in range(1, n_mels + 1):
        f_m_minus = bins[m - 1]
        f_m = bins[m]
        f_m_plus = bins[m + 1]
        for k in range(f_m_minus, f_m):
            if f_m != f_m_minus:
                fbank[m - 1, k] = (k - bins[m - 1]) / (bins[m] - bins[m - 1])
        for k in range(f_m, f_m_plus):
            if f_m_plus != f_m:
                fbank[m - 1, k] = (bins[m + 1] - k) / (bins[m + 1] - bins[m])

    filter_banks = np.dot(pow_frames, fbank.T)
    filter_banks = np.where(filter_banks <= 0, np.finfo(float).eps, filter_banks)
    filter_banks = 20.0 * np.log10(filter_banks)

    # DCT to compute MFCCs
    mfcc = fftpack.dct(filter_banks, type=2, axis=1, norm="ortho")[:, :n_mfcc]

    mean = np.mean(mfcc, axis=0)
    std = np.std(mfcc, axis=0)
    emb = np.concatenate([mean, std]).astype(np.float32)

    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


def is_enrolled() -> bool:
    """Return True if the owner's voice profile has been saved."""
    return PROFILE_PATH.exists() and PROFILE_PATH.stat().st_size > 0


def load_profile() -> np.ndarray | None:
    """Load the enrolled voice profile vector, or None if not enrolled."""
    if not is_enrolled():
        return None
    try:
        data = np.load(str(PROFILE_PATH))
        norm = np.linalg.norm(data)
        if norm > 0:
            return data / norm
        return data
    except Exception as e:
        print(f"[VoiceAuth] Failed to load voice profile: {e}")
        return None


def enroll_speaker(audio_data: np.ndarray, sample_rate: int = 16000) -> bool:
    """Extract and save the owner's voice profile from audio data."""
    try:
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        emb = extract_embedding(audio_data, sr=sample_rate)
        if np.linalg.norm(emb) == 0:
            print("[VoiceAuth] Audio was too short or silent to extract embedding.")
            return False
        # Save atomically
        tmp_path = PROFILE_PATH.with_suffix(".tmp")
        np.save(str(tmp_path), emb)
        os.replace(tmp_path, PROFILE_PATH)
        print(f"[VoiceAuth] Successfully enrolled owner voice at {PROFILE_PATH}")
        return True
    except Exception as e:
        print(f"[VoiceAuth] Error enrolling speaker: {e}")
        return False


def verify_speaker(audio_data: np.ndarray, sample_rate: int = 16000) -> float:
    """
    Compare the given audio against the owner's enrolled profile.
    Returns cosine similarity in range [-1.0, 1.0], or 1.0 if not yet enrolled.
    """
    profile = load_profile()
    if profile is None:
        return 1.0  # Not enrolled yet: soft pass

    emb = extract_embedding(audio_data, sr=sample_rate)
    if np.linalg.norm(emb) == 0:
        return 0.0

    sim = float(np.dot(profile, emb))
    return sim


def check_speaker_status(
    audio_data: np.ndarray,
    sample_rate: int = 16000,
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[bool, float]:
    """
    Returns (is_owner_matched, similarity_score).
    If not enrolled, returns (True, 1.0) so owner is never locked out before setup.
    """
    if not is_enrolled():
        return True, 1.0

    if audio_data is None or len(audio_data) < int(sample_rate * 0.4):
        return True, 1.0

    sim = verify_speaker(audio_data, sample_rate=sample_rate)
    matched = sim >= threshold
    return matched, sim


_GUEST_RESTRICTED_MODE = False


def set_guest_mode(restricted: bool) -> None:
    """Enable or disable safety-restricted mode for unknown speakers."""
    global _GUEST_RESTRICTED_MODE
    _GUEST_RESTRICTED_MODE = restricted
    if restricted:
        print("[VoiceAuth] 🔒 Restricted Guest Mode ACTIVE (sensitive actions blocked)")
    else:
        print("[VoiceAuth] 🔓 Owner Mode ACTIVE (full access granted)")


def is_guest_mode() -> bool:
    """Return True if currently in restricted guest mode."""
    return _GUEST_RESTRICTED_MODE


def is_owner(
    audio_data: np.ndarray,
    sample_rate: int = 16000,
    threshold: float = SIMILARITY_THRESHOLD,
) -> bool:
    """
    Return True if the speaker matches the owner.
    If not enrolled, returns True (soft fail so user is never locked out).
    """
    matched, sim = check_speaker_status(audio_data, sample_rate, threshold)
    if not matched:
        print(f"[VoiceAuth] ⚠️ Speaker mismatch (similarity: {sim:.2f} < {threshold})")
    return matched
