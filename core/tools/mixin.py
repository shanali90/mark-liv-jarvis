import asyncio
import traceback
from google.genai import types

from memory.memory_manager import update_memory, search_memory
from actions.screen_processor import _capture_camera, _capture_screen
from actions.system_monitor import get_system_status
from actions.background_monitor import add_monitor, remove_monitor, list_monitors
from core import undo as undo_stack



from core.safety.trust import get_trust_level, LEVEL_ASK
from core.audit import log_action
from selfheal.detect import safe_execute, _record_incident, _record_success
from core import confirm as confirm_gate

class ToolMixin:
    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.set_processing(True)
        self.ui.set_state("THINKING")

        action = args.get("action")
        trust_level = get_trust_level(name, action, args=args)

        if trust_level == LEVEL_ASK:
            if name == "shutdown_jarvis":
                msg = self._request_shutdown_confirmation()
                self.set_processing(False)
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return types.FunctionResponse(
                    id=fc.id, name=name, response={"result": msg}
                )

            log_action("JARVIS", "blocked_trust_ask", name, args, "BLOCKED")

            def _do_run():
                # Runs the action when confirmed by voice or UI
                if hasattr(self, "_action_registry") and self._action_registry.has(name):
                    _ctx = {"player": self.ui, "speak": getattr(self, "speak", None), "response": None, "session_memory": None}
                    success, r, dur = safe_execute(name, lambda: self._action_registry.run(name, args, _ctx))
                    log_action("JARVIS", "execute_confirmed", name, args, "SUCCESS" if success else "FAILED")
                    return str(r or "Done.")
                else:
                    log_action("JARVIS", "execute_confirmed", name, args, "SUCCESS")
                    return "Done."

            title = f"{name} {action or ''}".strip()
            msg = confirm_gate.request(f"{name}_{action}", title, str(args), _do_run)
            self.set_processing(False)
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(id=fc.id, name=name, response={"result": msg})

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "recall_memory":
                # Local file search: no network, no second model. Kept out of
                # the executor deliberately — it is a dictionary scan over a few
                # hundred short strings, and a thread hop would cost more than
                # the work itself.
                result = search_memory(args.get("query", ""), limit=8)

            elif name == "undo":
                if str(args.get("action", "")).lower().strip() == "list":
                    items = undo_stack.history()
                    result = ("Things I can undo, most recent first:\n"
                              + "\n".join(f"{i+1}. {t}" for i, t in enumerate(items))
                              ) if items else "I have not changed anything I can undo yet."
                else:
                    result = await loop.run_in_executor(None, undo_stack.undo_last)

            elif name == "screen_process":
                import time as _t_mod
                _now = _t_mod.monotonic()
                _cooldown = 4.0  # seconds — covers echo window after speaking ends
                if self._vision_busy or (_now - self._vision_last_time) < _cooldown:
                    _wait = max(0, _cooldown - (_now - self._vision_last_time))
                    print(f"[Vision] ⏳ Cooldown active ({_wait:.1f}s remaining) — ignoring duplicate call")
                    result = "Vision is still processing the previous request. I will not call this again."
                else:
                    self._vision_busy      = True
                    self._vision_last_time = _now
                    angle     = args.get("angle", "screen").lower()
                    user_text = args.get("text", "What do you see?")
                    if angle == "camera":
                        img_b, mime_t = await loop.run_in_executor(None, _capture_camera)
                        self.ui.start_camera_stream()
                        self._vision_cam_active = True
                        print(f"[Vision] 📷 Camera: {len(img_b):,} bytes")
                        _stall = "camera"
                    else:
                        img_b, mime_t = await loop.run_in_executor(None, _capture_screen)
                        print(f"[Vision] 🖥️  Screen: {len(img_b):,} bytes")
                        _stall = "screen"
                    self._pending_vision = (img_b, mime_t, user_text, angle)
                    # The image is attached to this same exchange, so there is
                    # nothing to stall for and nothing to announce. Asking for an
                    # acknowledgement here is what produced two spoken answers —
                    # the model filled that turn by answering the question from
                    # imagination, then answered it again once it could see.
                    result = (
                        f"[VISION_ACTIVE] {_stall.capitalize()} captured and attached to this "
                        f"same exchange. Do not acknowledge and do not answer yet — the image "
                        f"is arriving with this result. Reply once, from what you actually see "
                        f"in it."
                    )

            elif name == "close_camera":
                self.ui.stop_camera_stream()
                result = "Camera closed."

            elif name == "system_status":
                r = await loop.run_in_executor(None, get_system_status)
                result = str(r)
                log_action("JARVIS", "execute_static", name, args, "SUCCESS")

            elif name == "manage_monitor":
                action = args.get("action", "").lower().strip()
                topic  = args.get("topic", "").strip()
                if action == "add" and topic:
                    result = await asyncio.to_thread(add_monitor, topic)
                elif action == "remove" and topic:
                    result = await asyncio.to_thread(remove_monitor, topic)
                elif action == "list":
                    topics = await asyncio.to_thread(list_monitors)
                    result = ("Monitoring: " + ", ".join(topics)) if topics else "No topics are being monitored."
                else:
                    result = "Specify action (add/remove/list) and a topic."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                async def _do_shutdown():
                    await self._save_session_summary()
                    try:
                        from actions.browser_control import _registry
                        _registry.close_all()
                    except Exception:
                        pass
                    if self.session:
                        try:
                            await self.session.send_client_content(
                                turns={"role": "user", "parts": [{"text": "Say a brief natural goodbye to the user."}]},
                                turn_complete=True,
                            )
                        except Exception:
                            pass
                    await asyncio.sleep(1.5)
                    import os as _os
                    _os._exit(0)
                asyncio.create_task(_do_shutdown())

            elif name == "change_voice":
                req_voice = args.get("voice_name", "").strip()
                from memory.config_manager import AVAILABLE_VOICES, save_voice
                target = None
                for v in AVAILABLE_VOICES:
                    if v.lower() == req_voice.lower():
                        target = v
                        break
                if not target:
                    low = req_voice.lower()
                    if any(w in low for w in ("female", "woman", "girl")):
                        target = "Aoede"
                    else:
                        target = "Charon"
                save_voice(target)
                self.ui.write_log(f"SYS: Voice switched to {target}.")
                self._on_voice_change()
                result = f"Voice has been switched to {target}."

            elif name == "enroll_voice":
                asyncio.create_task(self._do_voice_enrollment())
                result = "Voice enrollment initiated. Please speak clearly so I can register your voice."

            elif self._action_registry.has(name):
                # file_processor: fall back to the currently-uploaded file when none is given
                if name == "file_processor" and not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                _ctx = {"player": self.ui, "speak": self.speak,
                        "response": None, "session_memory": None}

                # Execute dynamically via safe_execute
                def _run_tool():
                    return self._action_registry.run(name, args, _ctx)

                success, r, duration = await loop.run_in_executor(None, lambda: safe_execute(name, _run_tool))
                result = r or "Done."

                # Audit log
                log_action("JARVIS", "execute_dynamic", name, args, "SUCCESS" if success else "FAILED")

                # web_search: mirror results to the on-screen content panel
                if (name == "web_search" and r
                        and not r.startswith("No results")
                        and not r.startswith("Search failed")):
                    _mode  = args.get("mode", "search")
                    _query = args.get("query") or ", ".join(args.get("items", []))
                    _label = f"{_mode.upper()} — {_query[:38]}" if _query else _mode.upper()
                    self.ui.show_content(_label, r)

            else:
                if self._plugin_registry.has(name):
                    r = await loop.run_in_executor(
                        None,
                        lambda: self._plugin_registry.run(name, args, player=self.ui, session_memory=None)
                    )
                    result = r or "Done."
                else:
                    result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)
            _record_incident(name, e, args, 0.0)
            log_action("JARVIS", "execute_static", name, args, "FAILED")

        _record_success(name, 0.0)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")
        self.set_processing(False)

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")

        # A tool that declared itself NON_BLOCKING also says when its answer may
        # re-enter the conversation. Without this the model finishes whatever it
        # was saying and then reads the result out on top of it — which, for
        # something like a phone call already ringing, is exactly the noise the
        # non-blocking call was meant to avoid. Tools that declared nothing get
        # the API default and behave as they always have.
        _sched = (self._action_registry.scheduling(name)
                  or self._plugin_registry.scheduling(name))
        _extra = {"scheduling": _sched} if _sched else {}
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result},
            **_extra
        )

    def _request_shutdown_confirmation(self) -> str:
        log_action("JARVIS", "blocked_trust_ask", "shutdown_jarvis", {}, "BLOCKED")
        return confirm_gate.request(
            "shutdown_jarvis",
            "Shut down JARVIS",
            "Close the assistant and end this session.",
            self._schedule_confirmed_shutdown,
        )

    def _handle_voice_shutdown_request(self, text: str) -> bool:
        lower = str(text).lower()
        commands = (
            "shut down completely", "shutdown jarvis", "power off jarvis",
            "exit jarvis", "close jarvis", "quit jarvis",
            "سسٽم مڪمل بند ڪريو", "جاروس بند ڪريو", "پورو بند ڪريو",
        )
        if not any(command in lower for command in commands):
            return False
        print(f"[JARVIS] 🛑 Full shutdown command detected: '{text}'")
        self._request_shutdown_confirmation()
        return True

    def _schedule_confirmed_shutdown(self) -> str:
        loop = getattr(self, "_loop", None)
        if loop is None or not loop.is_running():
            raise RuntimeError("JARVIS event loop is not running")
        asyncio.run_coroutine_threadsafe(self._finish_confirmed_shutdown(), loop)
        return "JARVIS shutdown started."

    async def _finish_confirmed_shutdown(self) -> None:
        self.ui.write_log("SYS: Shutdown confirmed.")
        await self._save_session_summary()
        try:
            from actions.browser_control import _registry
            _registry.close_all()
        except Exception as e:
            self.ui.write_log(f"ERR: Could not close browser sessions: {e}")
        if self.session:
            try:
                await self.session.send_client_content(
                    turns={"role": "user", "parts": [{
                        "text": "Say a brief natural goodbye to the user."
                    }]},
                    turn_complete=True,
                )
            except Exception as e:
                self.ui.write_log(f"ERR: Could not send shutdown goodbye: {e}")
        await asyncio.sleep(1.5)
        import os
        os._exit(0)
