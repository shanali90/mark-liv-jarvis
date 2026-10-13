import numpy as np

def test_pcm_audio_helpers():
    from core.audio.utils import _pcm_level, _pcm_visemes
    
    # Generate a 1kHz sine wave at 24kHz for 1 second
    sample_rate = 24000
    t = np.linspace(0, 1, sample_rate, False)
    sine = (np.sin(2 * np.pi * 1000 * t) * 32767).astype(np.int16)
    
    # Test _pcm_level
    level = _pcm_level(sine)
    assert 0.0 < level <= 1.0, f"Expected sane level, got {level}"
    
    # Test _pcm_visemes
    visemes = _pcm_visemes(sine, sr=sample_rate)
    new_level = visemes[0][0]
    assert len(visemes) > 0, "Expected visemes output"
    assert 0.0 < new_level <= 1.0, f"Expected sane new_level, got {new_level}"
