
def test_jarvislive_mro():
    import main

    # Check that methods moved to mixins no longer exist directly in JarvisLive.__dict__
    moved_methods = [
        '_listen_audio',
        '_send_realtime',
        '_receive_audio',
        '_play_audio',
        '_relay_phone_audio',
        '_execute_tool'
    ]

    for method in moved_methods:
        assert method not in main.JarvisLive.__dict__, f"{method} must not be in JarvisLive.__dict__"
        assert hasattr(main.JarvisLive, method), f"{method} must resolve via MRO"
