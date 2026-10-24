import asyncio
import pytest
from core.audio.mixin import AudioMixin


class FakeAudioHost(AudioMixin):
    def __init__(self):
        self.out_queue = asyncio.Queue(maxsize=5)


@pytest.mark.anyio
async def test_enqueue_mic_audio_drops_oldest_on_full():
    host = FakeAudioHost()

    # Fill up queue
    for i in range(5):
        host._enqueue_mic_audio({"data": f"chunk-{i}".encode(), "seq": i})

    assert host.out_queue.full()

    # Pushing 6th chunk should drop chunk-0 and retain chunk-5 without raising QueueFull
    host._enqueue_mic_audio({"data": b"chunk-5", "seq": 5})

    items = []
    while not host.out_queue.empty():
        items.append(host.out_queue.get_nowait())

    seqs = [item["seq"] for item in items]
    assert seqs == [1, 2, 3, 4, 5]
    assert 0 not in seqs
