from core.greeting import pick_greeting


def test_greeting_time_awareness_and_no_consecutive_repeats():
    # Morning (hour 9)
    g1 = pick_greeting(9, "Shan Ali")
    assert "Shan Ali" in g1
    assert any(w in g1.lower() for w in ("morning", "ready", "here"))

    # Pick again immediately: should not repeat the same line
    g2 = pick_greeting(9, "Shan Ali")
    assert g2 != g1

    # Afternoon (hour 14)
    g3 = pick_greeting(14, "Shan Ali")
    assert any(w in g3.lower() for w in ("afternoon", "service", "here"))

    # Night (hour 23)
    g4 = pick_greeting(23, "")
    assert "sir" in g4.lower()
