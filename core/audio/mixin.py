import asyncio
import re
import traceback

import time
from datetime import datetime
import sounddevice as sd
import numpy as np
from google.genai import types
from core import audio_devices

# Import constants and helpers from their real source
from core.audio.constants import (
    RECEIVE_SAMPLE_RATE, SEND_SAMPLE_RATE, CHUNK_SIZE, CHANNELS,
    _TAIL_MARGIN, _VIS_HOP, _CURSOR_SLACK, _FIRST_SOUND, _REPEAT_MIN,
    SLEEP_VOICE_COMMANDS
)
from core.audio.utils import _pcm_level, _pcm_visemes, _is_repeat_chunk, _clean_transcript
from core.wake_word import WakeWordDetector
from core.audio.constants import JarvisState
from memory.config_manager import get_input_device, get_output_device

class AudioMixin:

    def _wake_available(self) -> bool:
        """Try to start wake-word detection; fall back to ALWAYS-AWAKE if it can't.

        Wake-word mode puts JARVIS to sleep with the mic gated until the local
        detector hears "Hey Jarvis". If the detector cannot start (the model file
        is missing, openwakeword is not installed) nothing can ever wake it, and
        JARVIS sits at "waiting for wake word" forever while the user talks to
        it. So when the detector is unusable, wake-word mode is switched off for
        this run only (the saved preference is untouched, so it comes back by
        itself once the model is installed) and JARVIS stays awake.
        """
        try:
            ok = bool(self._ensure_wake_detector())
        except Exception as e:
            print(f"[Wake] detector start failed: {e}")
            ok = False
        if ok:
            return True
        if self._wake_enabled:
            self._wake_enabled = False
            self.state = JarvisState.AWAKE
            self._awake = True
            print("[Wake] Wake word unavailable - staying awake (push-to-talk / always-on).")
            try:
                self.ui.write_log(
                    "SYS: Wake word is not set up (model missing), so I stay awake and "
                    "listen all the time. Install it in Settings > Wake Word to use 'Hey Jarvis'."
                )
            except Exception:
                pass
        return False
    def _ensure_wake_detector(self) -> bool:
        """Load the detector once (model loads on first start). Idempotent."""
        if self._wake_detector is None:
            self._wake_detector = WakeWordDetector(
                on_detect=self._on_wake_detected,
                logger=lambda m: print(f"[Wake] {m}"),
                notify=lambda m: self.ui.write_log(f"SYS: {m}"),
            )
        if not self._wake_detector.ready:
            return self._wake_detector.start()
        return True

    def _enqueue_mic_audio(self, msg: dict) -> None:
        if self.out_queue is None:
            return
        if self.out_queue.full():
            try:
                self.out_queue.get_nowait()
            except Exception:
                pass
        try:
            self.out_queue.put_nowait(msg)
        except asyncio.QueueFull:
            try:
                self.out_queue.get_nowait()
                self.out_queue.put_nowait(msg)
            except Exception:
                pass

    async def _send_realtime(self):
        half_full_start: float | None = None
        warned_congestion = False
        while True:
            if self.out_queue is not None:
                max_s = getattr(self.out_queue, "maxsize", 200) or 200
                q_size = self.out_queue.qsize()
                if q_size > max_s // 2:
                    now = time.monotonic()
                    if half_full_start is None:
                        half_full_start = now
                    elif (now - half_full_start) >= 3.0:
                        if not warned_congestion:
                            warned_congestion = True
                            if hasattr(self, "ui") and hasattr(self.ui, "write_log"):
                                self.ui.write_log("SYS: Weak connection — audio delayed")
                            print("[Audio] ⚠️ Weak connection — audio delayed")
                    while self.out_queue.qsize() > 10:
                        try:
                            self.out_queue.get_nowait()
                        except Exception:
                            break
                else:
                    half_full_start = None
                    warned_congestion = False

            msg = await self.out_queue.get()
            try:
                await asyncio.wait_for(
                    self.session.send_realtime_input(
                        audio=types.Blob(
                            data=msg["data"],
                            mime_type=msg.get("mime_type", "audio/pcm"),
                        )
                    ),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                pass
            except Exception:
                raise

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            # ── Wake-word gate ───────────────────────────────────────────────
            # While asleep, the mic audio NEVER goes to Gemini (nothing is
            # streamed, so JARVIS can't respond to speech not addressed to it and
            # nothing leaves the machine). Frames are instead handed to the local
            # detector, which runs its model in ITS OWN thread — the cost here is
            # only a queue push, so the audio path is never slowed. When wake word
            # is off (default) or we're awake, this is a single boolean check.
            if self._wake_enabled and not self._awake:
                det = self._wake_detector
                if det is None:
                    try:
                        self._ensure_wake_detector()
                        det = self._wake_detector
                    except Exception:
                        pass
                if det is not None:
                    det.feed(indata)
                return
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking

            # ── Barge-in ─────────────────────────────────────────────────────
            # While JARVIS talks the mic is not streamed, but it is still worth
            # listening to locally: if the user starts speaking, cut the answer
            # short the way a person would stop when interrupted.
            #
            # The whole difficulty is echo — on speakers the mic hears JARVIS.
            # So the test is not "is the mic loud" but "is the mic louder than
            # the echo of what we are playing right now", sustained long enough
            # that a cough or a keystroke cannot trigger it.
            if jarvis_speaking:
                lvl = _pcm_level(indata)
                try:
                    is_speech = self._echo.is_user_speech(indata, SEND_SAMPLE_RATE, lvl)
                except Exception:
                    is_speech = False

                if is_speech:
                    self._barge_in_consecutive += 1
                    if self._barge_in_consecutive >= 2:
                        # Section 6 disabled for Phase 2:
                        # from core.voice_auth import is_owner
                        # if not is_owner(indata, SEND_SAMPLE_RATE):
                        #     print("[Auth] ⚠️ Interruption rejected: voice does not match the owner")
                        #     self._barge_in_consecutive = 0
                        #     return


                        print("[JARVIS] 🗣️ Natural interruption detected (barge-in)")
                        self.interrupt()
                        self._barge_in_consecutive = 0
                        if not self.ui.muted and not self._phone_active:
                            data = indata.tobytes()
                            loop.call_soon_threadsafe(
                                self._enqueue_mic_audio,
                                {"data": data, "mime_type": "audio/pcm"}
                            )
                            self._recent_user_audio.append(indata.copy())
                            try:
                                self.ui.set_audio_level(lvl)
                            except Exception:
                                pass
                else:
                    self._barge_in_consecutive = 0
                return

            # ── Echo tail ────────────────────────────────────────────────────
            # The speaking flag has dropped but the speakers have not finished.
            # Sending this to the model is how an assistant hears itself, decides
            # it was addressed, and answers its own last sentence. The microphone
            # stays OPEN — the guard only drops blocks that are our own voice, so
            # replying the instant it stops still works.
            if self._tail_active():
                try:
                    if not self._echo.is_user_speech(
                            indata, SEND_SAMPLE_RATE, _pcm_level(indata)):
                        return
                    self._tail_until = 0.0      # a real voice ends the tail early
                except Exception:
                    return
            elif self._echo._hist:
                self._echo.reset()

            # ── Push-to-talk ─────────────────────────────────────────────────
            # When it is on the microphone is closed by default and the chord
            # opens it, which is the whole point: nothing leaves the machine
            # unless you are holding the key.
            if self._ptt_enabled and not self._ptt_held:
                return

            if not self.ui.muted and not self._phone_active:
                if self.out_queue is not None:
                    data = indata.tobytes()
                    loop.call_soon_threadsafe(
                        self._enqueue_mic_audio,
                        {"data": data, "mime_type": "audio/pcm"}
                    )
                self._recent_user_audio.append(indata.copy())
                # Feed the live mic level to the HUD so the waveform reacts to
                # the user's actual voice while listening. Purely cosmetic — any
                # failure here must never disturb the mic.
                try:
                    self.ui.set_audio_level(_pcm_level(indata))
                except Exception:
                    pass

        try:
            def _open_mic(dev):
                return sd.InputStream(
                    samplerate=SEND_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=CHUNK_SIZE,
                    device=dev,
                    callback=callback,
                )

            # Which microphone. resolve() returns None for "system default" and
            # for a saved device that is no longer present — so a headset
            # unplugged since the last run falls back to the built-in mic
            # instead of raising on startup and taking the session with it.
            _mic_name = get_input_device()
            _mic_dev  = audio_devices.resolve(_mic_name, "input")
            print(f"[JARVIS] 🎤 Initializing Mic... Requested: '{_mic_name or 'System Default'}', Resolved Device Index: {_mic_dev}")
            try:
                _mic_stream = _open_mic(_mic_dev)
            except Exception as _e:
                # A device the picker listed but the driver will not open right
                # now — exclusive mode, a webcam already in use, a virtual mic
                # whose source went away. Chosen hardware failing must never
                # mean the assistant cannot hear at all.
                if _mic_dev is None:
                    raise
                print(f"[JARVIS] ⚠️  Mic '{_mic_name}' failed: {_e} — using default")
                self.ui.write_log(
                    f"SYS: Microphone '{_mic_name}' unavailable — using system default."
                )
                _mic_stream = _open_mic(None)

            with _mic_stream:
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    # ── Session resumption ───────────────────────────────────
                    # The server sends this periodically. `resumable` goes false
                    # while a turn is mid-flight — replaying a handle from that
                    # moment is what the flag exists to prevent — so only
                    # resumable handles are kept. This is three lines and it is
                    # the entire fix for "every reconnect forgets everything".
                    _sru = getattr(response, "session_resumption_update", None)
                    if _sru is not None:
                        if getattr(_sru, "resumable", False) and getattr(_sru, "new_handle", None):
                            if self._resume_handle is None:
                                print("[JARVIS] 🔗 Session resumption armed")
                            self._resume_handle = _sru.new_handle

                    if response.data:
                        if self._interrupted:
                            pass  # discard: interrupted
                        else:
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            # Split into ~50 ms chunks so interrupt() stops audio within 50 ms
                            # (24000 Hz × 2 bytes/sample × 0.05 s = 2400 bytes per slice)
                            _audio_data = response.data
                            _SLICE = 2400
                            for _i in range(0, len(_audio_data), _SLICE):
                                self.audio_in_queue.put_nowait(_audio_data[_i : _i + _SLICE])

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            # A turn that involves a tool call passes through
                            # several turn_completes, and the API re-sends the
                            # tail of the transcript across them. Comparing only
                            # against the previous chunk missed that — once
                            # out_buf had been flushed and emptied, the repeat
                            # sailed straight back in, which logged the answer
                            # twice AND made the avatar mouth it twice.
                            if txt and not _is_repeat_chunk(txt, out_buf):
                                out_buf.append(txt)
                                # Hand the words to the mouth as they arrive, so
                                # the avatar can form the consonants the audio
                                # alone cannot show. Pure string work — it adds
                                # nothing measurable to the response path.
                                self._visemes.feed_text(txt)
                                # self.ui.set_emotion_from_text(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                self._last_user_speech = time.monotonic()
                                from core.activity import record_user_speech

                                record_user_speech(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            # If this turn_complete ends an interrupted response, clear the
                            # flag and preserve user's spoken words so corrections stay in context.
                            if self._interrupted:
                                self._interrupted = False
                                self._visemes.reset()
                                if not in_buf:
                                    out_buf = []
                                    continue

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                from core.confirm import resolve_from_text
                                if resolve_from_text(full_in):
                                    in_buf = []
                                    out_buf = []
                                    continue
                                self._last_out_logged = ""   # new exchange
                                self.ui.write_log(f"You: {full_in}")
                                self._session_log.append(f"User: {full_in}")
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "user",
                                        "text": full_in,
                                        "ts": datetime.now().isoformat(),
                                    }))

                                full_in_lower = full_in.lower()
                                if self._handle_voice_shutdown_request(full_in):
                                    self.ui.write_log(
                                        f"SYS: Full shutdown command '{full_in}' → Confirmation requested."
                                    )
                                    in_buf = []
                                    out_buf = []
                                    continue

                                # Explicit voice sleep trigger
                                if any(cmd in full_in_lower for cmd in SLEEP_VOICE_COMMANDS):
                                    print(f"[JARVIS] 💤 Sleep voice command detected: '{full_in}'")
                                    self.ui.write_log(f"SYS: Voice command '{full_in}' → Sleeping.")
                                    self.sleep(reason="voice command")
                                    in_buf  = []
                                    out_buf = []
                                    continue

                                # Spoken wake greetings and wake phrases
                                if any(cmd in full_in_lower for cmd in (
                                    "hello jarvis", "hey jarvis", "wake up jarvis", "okay jarvis", "ok jarvis",
                                    "wake up", "are you there jarvis", "are you there",
                                    "سائين جاڳو", "جاڳو سائين", "جاڳو", "سلام سائين", "اسلام عليڪم",
                                    "سائين حاضر آهيو", "جي سائين", "هيلو جاروس"
                                )):
                                    self._last_user_speech = time.monotonic()
                                    # self.ui.set_emotion(joy=0.8, neutral=0.2)
                                    # Removed play_wake_chime to eliminate the system beep crash
                                    if self.state == JarvisState.SLEEPING:
                                        self.wake(reason="voice greeting")
                                        in_buf  = []
                                        out_buf = []
                                        continue

                                # Voice biometric enrollment command (English, Sindhi, Urdu)
                                if any(cmd in full_in_lower for cmd in (
                                    "enroll my voice", "remember my voice", "register my voice",
                                    "منهنجو آواز ياد رکو", "آواز ياد رکو", "منهنجو آواز رڪارڊ ڪريو", "ميرا آواز ياد رکو", "آواز محفوظ ڪريو"
                                )):
                                    print(f"[JARVIS] 🎙️ Voice enrollment command: '{full_in}'")
                                    asyncio.create_task(self._do_voice_enrollment())

                                # Action kill-switch voice command
                                from actions.send_message import is_action_pending, abort_current_action
                                if is_action_pending():
                                    words = set(re.findall(r"\b\w+\b", full_in_lower))
                                    if words.intersection({"stop", "cancel", "abort"}) or any(w in full_in_lower for w in ("stop that", "cancel that", "don't send", "روڪيو", "منسوخ ڪريو")):
                                        print(f"[JARVIS] 🛑 Kill-switch voice command: '{full_in}'")
                                        abort_current_action()
                                        self.interrupt()

                                # Section 13/6 disabled for Phase 2
                                # try:
                                #     from core.voice_auth import check_speaker_status, is_enrolled, set_guest_mode
                                #     if is_enrolled() and self._recent_user_audio:
                                #         recent_chunks = list(self._recent_user_audio)[-30:]
                                #         if recent_chunks:
                                #             combined_audio = np.concatenate(recent_chunks)
                                #             is_owner_match, sim = check_speaker_status(combined_audio, SEND_SAMPLE_RATE)
                                #             if not is_owner_match:
                                #                 set_guest_mode(True)
                                #                 if not self._guest_inquiry_sent:
                                #                     self._guest_inquiry_sent = True
                                #                     inquiry_prompt = (
                                #                         "[System Notification: An unfamiliar voice spoke. Respectfully ask who is speaking and if they know Shan: "
                                #                         "'I don't recognize your voice — who am I speaking with, and do you know Shan?']"
                                #                     )
                                #                     self.plugin_say(inquiry_prompt)
                                #             else:
                                #                 set_guest_mode(False)
                                #                 if not self._owner_greeted_this_session:
                                #                     self._owner_greeted_this_session = True
                                #                     print(f"[Auth] 🔓 the owner recognized (similarity={sim:.2f}).")
                                # except Exception as e:
                                #     print(f"[Auth] Speaker check error: {e}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            # Second line of defence: even if a repeat slips
                            # into a *fresh* buffer after a flush, never log the
                            # same answer (or a tail of it) twice in a row.
                            if full_out and len(full_out) >= _REPEAT_MIN and self._last_out_logged:
                                if full_out in self._last_out_logged:
                                    full_out = ""
                            if full_out:
                                self._last_out_logged = full_out
                                self.ui.write_log(f"{self._asst_name}: {full_out}")
                                self._session_log.append(f"{self._asst_name}: {full_out}")
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "jarvis",
                                        "text": full_out,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            out_buf = []

                            if self._vision_close_pending:
                                # This turn_complete IS the vision answer — close camera + release busy flag
                                self._vision_close_pending = False
                                self._vision_busy = False
                                async def _cam_close():
                                    await asyncio.sleep(2.0)
                                    self.ui.stop_camera_stream()
                                asyncio.create_task(_cam_close())

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            from core.activity import record_tool_call, get_last_user_speech_info
                            record_tool_call()
                            last_speech_time, last_speech_txt = get_last_user_speech_info()
                            now = time.monotonic()
                            if last_speech_time is None or (now - last_speech_time) > 60.0:
                                audit_line = f"[Audit] ⚠️ UNPROMPTED TOOL CALL: {fc.name}({fc.args}) | No user speech in last 60s"
                            else:
                                elapsed = now - last_speech_time
                                audit_line = f"[Audit] Tool call: {fc.name}({fc.args}) | Preceding speech ({elapsed:.1f}s ago): \"{last_speech_txt}\""
                            print(audit_line)
                            if hasattr(self, "ui") and hasattr(self.ui, "write_log"):
                                self.ui.write_log(audit_line)
                            try:
                                import os
                                from datetime import datetime
                                os.makedirs("logs", exist_ok=True)
                                with open("logs/jarvis_activity.log", "a", encoding="utf-8") as f:
                                    f.write(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {audit_line}\n")
                            except Exception:
                                pass

                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
                        await self._flush_pending_vision()
        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        _spk_name = get_output_device()
        _spk_dev  = audio_devices.resolve(_spk_name, "output")
        if _spk_dev is not None:
            print(f"[JARVIS] 🔊 Output device: {_spk_name}")

        def _open_spk(dev):
            st = sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                device=dev,
            )
            st.start()
            return st

        try:
            stream = _open_spk(_spk_dev)
        except Exception as _e:
            # A chosen output that the host API accepts by name but refuses to
            # open (exclusive mode, wrong sample rate, device asleep) must not
            # cost the user their voice. Fall back to the default and say so.
            if _spk_dev is None:
                raise
            print(f"[JARVIS] ⚠️  Output device '{_spk_name}' failed: {_e} — using default")
            self.ui.write_log(f"SYS: Speaker '{_spk_name}' unavailable — using system default.")
            stream = _open_spk(None)

        # Ask the device how far behind the speakers actually are, rather than
        # assuming. This is what the echo tail is sized from, so a machine with a
        # large audio buffer gets a correspondingly longer guard — and one with a
        # tiny buffer is not penalised with a delay it does not need.
        try:
            lat = float(getattr(stream, "latency", 0.0) or 0.0)
            if 0.0 < lat < 1.0:
                self._out_latency = lat
            print(f"[JARVIS] 🔊 Output latency {self._out_latency*1000:.0f} ms "
                  f"→ echo tail {(self._out_latency + _TAIL_MARGIN)*1000:.0f} ms")
        except Exception:
            pass

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self.set_speaking(True)

                # Batch all immediately-available chunks into one write to reduce
                # thread-pool round-trips (was one asyncio.to_thread per 50ms slice).
                # Cap at ~200 ms so interrupt() still stops audio within ~200 ms.
                batch = bytearray(chunk)
                while len(batch) < 9600:   # 9600 bytes ≈ 200 ms at 24 kHz / 16-bit mono
                    try:
                        batch.extend(self.audio_in_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                # Drive the HUD waveform and the avatar's mouth from JARVIS's
                # own voice. The batch is up to 200 ms long, so we hand over a
                # *schedule* of 20 ms viseme frames instead of a single averaged
                # level and let the HUD play it out in step with the audio.
                try:
                    pcm = np.frombuffer(bytes(batch), dtype=np.int16)
                    hop = _VIS_HOP / RECEIVE_SAMPLE_RATE
                    frames = _pcm_visemes(pcm, sr=RECEIVE_SAMPLE_RATE)
                    # When does this batch become audible? The stream was
                    # started at launch and its callback has been pulling
                    # silence ever since, so the first bytes of a reply reach
                    # the speaker about one callback period later — NOT one
                    # buffer later. `stream.latency` reports the buffer's
                    # capacity, which is how much can be queued ahead, and on
                    # Windows that is commonly 300-500 ms. Anchoring on it put
                    # the entire schedule a buffer late; that is the half second
                    # of lag, and it grew with whatever the device reported.
                    #
                    # After the anchor nothing needs measuring: the device
                    # consumes at exactly realtime, so each batch sounds one
                    # batch-duration after the one before it. The cursor is
                    # re-anchored only when it leaves the range physically
                    # possible — behind `now` means the device drained and this
                    # batch starts a fresh stretch of speech, while further
                    # ahead than the buffer can hold means it has drifted.
                    now = time.time()
                    horizon = self._out_latency + _CURSOR_SLACK
                    if not (now <= self._play_cursor <= now + horizon):
                        self._play_cursor = now + _FIRST_SOUND
                    at = self._play_cursor
                    # Advance by the batch's own duration whether or not it
                    # yielded frames, so a block too short to analyse cannot
                    # shift everything after it out of step with the audio.
                    self._play_cursor += pcm.size / RECEIVE_SAMPLE_RATE
                    if frames:
                        frames = self._visemes.frames(frames, hop)
                        self.ui.push_visemes(frames, hop, at)
                        # Barge-in needs to know what we are playing, not just
                        # how loud: the guard subtracts this from the microphone.
                        self._out_level = max(f[0] for f in frames)
                        self._echo.note_output(pcm, RECEIVE_SAMPLE_RATE,
                                               self._out_level)
                    else:
                        lvl = _pcm_level(pcm)
                        self.ui.set_audio_level(lvl)
                        self._out_level = lvl
                        self._echo.note_output(pcm, RECEIVE_SAMPLE_RATE, lvl)
                except Exception:
                    pass

                try:
                    await asyncio.to_thread(stream.write, bytes(batch))
                except (RuntimeError, asyncio.CancelledError):
                    break   # executor shutting down — exit cleanly
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def _relay_phone_audio(self) -> None:
        """Forward phone mic PCM chunks from dashboard queue into the Gemini Live session."""
        q = self._dashboard._phone_audio_queue
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No audio for 1 s → phone mic inactive, give PC mic back
                self._phone_active = False
                continue
            self._phone_active = True   # phone is streaming — silence PC mic
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and not self.ui.muted:
                try:
                    self.out_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass
