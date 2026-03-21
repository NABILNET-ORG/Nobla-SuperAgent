"""Shared fixtures for voice pipeline tests."""
import struct
import pytest


@pytest.fixture
def silence_pcm_16khz() -> bytes:
    """1 second of silence as PCM 16-bit 16kHz mono."""
    return b"\x00\x00" * 16000


@pytest.fixture
def sine_wave_pcm_16khz() -> bytes:
    """1 second of 440Hz sine wave as PCM 16-bit 16kHz mono."""
    import math
    samples = []
    for i in range(16000):
        sample = int(32767 * math.sin(2 * math.pi * 440 * i / 16000))
        samples.append(struct.pack("<h", sample))
    return b"".join(samples)
