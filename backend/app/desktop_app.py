from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ctypes
import logging
import math
import os
from pathlib import Path
import random
import sys
import threading
import tkinter as tk

from app.core.logging import configure_logging
from app.core.config import get_settings
from app.core.env_store import RuntimeEnvStore
from app.database.init import initialize_database
from app.llm.provider import LLMProvider
from app.personal_agent import PersonalWorkAgent
from app.personal_agent.settings_store import AgentPreferences, AgentSettingsStore, SkillSettingsStore
from app.voice import LocalNeuralVoiceGateway
from app.voice.model_manager import discover_voice_models, install_voice_models


logger = logging.getLogger(__name__)


def resolve_display_state(task_state: str, voice_activity: str) -> str:
    """Combine independent task and voice states for the compact status badge."""
    if voice_activity == "listening" and task_state == "confirming":
        return "confirm_listening"
    if voice_activity in {"voice_loading", "listening", "speaking", "voice_error"}:
        return voice_activity
    return task_state


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: int
    max_life: int
    size: float
    color: str


class FloatingPersonalAgent:
    """Cartoon desktop companion, voice gateway and safe Skill controller."""

    # The floating surface deliberately hugs the character.  Keeping the
    # color-key window small avoids a large invisible hit area around it.
    WIDTH = 156
    HEIGHT = 146
    TRANSPARENT = "#010203"
    BG = "#f4f8ff"
    CARD = "#ffffff"
    TEXT = "#18324a"
    MUTED = "#6b8198"
    ACCENT = "#2563eb"
    SOFT_BLUE = "#eaf3ff"
    BORDER = "#cfe0f3"
    SIDEBAR = "#edf5ff"
    STATE_COLORS = {
        "idle": "#3b82f6",
        "voice_loading": "#60a5fa",
        "listening": "#0284c7",
        "heard": "#0891b2",
        "thinking": "#2563eb",
        "working": "#1d4ed8",
        "confirming": "#f59e0b",
        "confirm_listening": "#f59e0b",
        "speaking": "#0ea5e9",
        "success": "#10b981",
        "error": "#ef4444",
        "voice_error": "#f97316",
    }

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("史蒂芬 · 个人工作 Agent")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=self.TRANSPARENT)
        try:
            self.root.wm_attributes("-transparentcolor", self.TRANSPARENT)
        except tk.TclError:
            logger.info("Transparent color is unavailable")

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{screen_width - self.WIDTH - 24}+{screen_height - self.HEIGHT - 70}")
        self.canvas = tk.Canvas(self.root, width=self.WIDTH, height=self.HEIGHT, bg=self.TRANSPARENT, bd=0, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._open_context_menu)

        self.settings_store = AgentSettingsStore()
        self.skill_settings_store = SkillSettingsStore()
        self.agent = PersonalWorkAgent(settings_store=self.settings_store, event_sink=self._agent_event)
        self.voice = LocalNeuralVoiceGateway(self.settings_store, self._voice_command, self._voice_state)

        self.state = "idle"
        self.voice_activity = "idle"
        self.state_detail = ""
        self.running = False
        self.hovered = False
        self.pressed = False
        self.dragging = False
        self.frame = 0
        self.drag_origin = (0, 0)
        self.press_screen = (0, 0)
        self.particles: list[Particle] = []
        self.settings_window: tk.Toplevel | None = None
        self.manual_chat_window: tk.Toplevel | None = None
        self.manual_chat_transcript: tk.Text | None = None
        self.manual_chat_input: tk.Text | None = None
        self._restore_manual_after_skill = False
        self.bubble: tk.Toplevel | None = None
        self.context_menu: tk.Toplevel | None = None
        self.settings_status: tk.StringVar | None = None
        self.settings_content: tk.Frame | None = None
        self.settings_canvas: tk.Canvas | None = None
        self.settings_nav_buttons: dict[str, tk.Button] = {}
        self.settings_vars: dict[str, tk.Variable] = {}
        self._needs_redraw = True

        self.root.after(250, self.voice.start)
        self._animate()

    def _voice_command(self, text: str) -> None:
        self.root.after(0, lambda: self.submit_command(text))

    def _voice_state(self, state: str, detail: str) -> None:
        self.root.after(0, lambda: self._apply_voice_state(state, detail))

    def submit_command(self, text: str) -> None:
        if self.running:
            message = "我还在处理上一个任务，请稍等。"
            if self._manual_chat_visible():
                self._append_manual_message("Agent", message)
            else:
                self._show_bubble(message)
            return
        self.running = True
        self._set_state("thinking", text)
        self._spawn_burst(20, self.STATE_COLORS["thinking"])
        threading.Thread(target=self._command_worker, args=(text,), name="agent-command", daemon=True).start()

    def _command_worker(self, text: str) -> None:
        try:
            reply = self.agent.handle(text)
        except Exception as exc:
            logger.exception("Personal agent command failed")
            self.root.after(0, lambda: self._finish_reply(f"任务失败：{exc}", "error"))
            return
        self.root.after(0, lambda: self._finish_reply(reply.text, reply.state))

    def _finish_reply(self, text: str, state: str) -> None:
        self.running = False
        self._restore_overlay()
        self._set_state(state if state in self.STATE_COLORS else "idle", text)
        self._spawn_burst(30 if state == "success" else 14, self.STATE_COLORS.get(state, self.ACCENT))
        if self._manual_chat_visible():
            self._append_manual_message("Agent", text)
        else:
            self._show_bubble(text)
        # Voice input remains available for confirmation, but replies are no
        # longer synthesized. Reopen the microphone immediately when needed.
        if state == "confirming":
            self.voice.arm()
        if state not in {"confirming", "error"}:
            self.root.after(3200, lambda: self._set_state("idle", ""))

    def _agent_event(self, event: str, payload: dict) -> None:
        self.root.after(0, lambda: self._handle_agent_event(event, payload))

    def _handle_agent_event(self, event: str, payload: dict) -> None:
        if event == "open_settings":
            self._open_settings()
        elif event == "confirmation_required":
            self._set_state("confirming", "等待确认")
        elif event == "skill_started":
            self._set_state("working", "正在执行 Skill")
            self._restore_manual_after_skill = self._manual_chat_visible()
            if self._restore_manual_after_skill and self.manual_chat_window is not None:
                self.manual_chat_window.withdraw()
            self.root.withdraw()
        elif event in {"skill_finished", "skill_failed"}:
            self._restore_overlay()
            if self._restore_manual_after_skill and self.manual_chat_window is not None and self.manual_chat_window.winfo_exists():
                self.manual_chat_window.deiconify()
                self.manual_chat_window.lift()
            self._restore_manual_after_skill = False
        elif event == "progress":
            detail = str(payload.get("message", ""))
            self.state_detail = detail
            if self.settings_status is not None:
                self.settings_status.set(detail)
            logger.info(detail)

    def _set_state(self, state: str, detail: str = "") -> None:
        self.state = state
        self.state_detail = detail
        self._needs_redraw = True
        if self.settings_status is not None:
            self.settings_status.set(detail or self._state_label())

    def _apply_voice_state(self, state: str, detail: str = "") -> None:
        """Update voice activity without destroying the current task result."""
        self.voice_activity = state
        if detail:
            self.state_detail = detail
        self._needs_redraw = True
        if self.settings_status is not None:
            self.settings_status.set(detail or self._state_label())

    def _activate_voice(self) -> None:
        if not self.settings_store.load().voice_enabled:
            self._show_bubble("语音功能已关闭，右击我可以进入设置。")
            return
        self.voice.acknowledge_and_arm()
        self._spawn_burst(18, self.STATE_COLORS["listening"])

    def _animate(self) -> None:
        self.frame += 1
        if self.particles:
            self._update_particles()
            self._needs_redraw = True
        if self._needs_redraw:
            self._draw()
            self._needs_redraw = False
        self.root.after(50, self._animate)

    def _draw(self) -> None:
        self.canvas.delete("all")
        cx, cy = self.WIDTH / 2, 64
        display_state = resolve_display_state(self.state, self.voice_activity)
        state_color = self.STATE_COLORS.get(display_state, self.ACCENT)

        for particle in self.particles:
            ratio = max(0.0, particle.life / particle.max_life)
            size = max(1.0, particle.size * ratio)
            self.canvas.create_oval(particle.x - size, particle.y - size, particle.x + size, particle.y + size, fill=particle.color, outline="")

        self._draw_poop(cx, cy)
        self._draw_status_badge(cx, state_color)

    def _draw_status_badge(self, cx: float, color: str) -> None:
        """Draw a roomy blue-white status pill with a live state indicator."""
        left, top, right, bottom = cx - 59, 113, cx + 59, 139
        radius = (bottom - top) / 2
        # Three overlapping shapes produce a clean rounded pill on every Tk
        # version.  Its constant opaque footprint also prevents text ghosting
        # when the state changes from a long label to a short one.
        self.canvas.create_rectangle(left + radius, top, right - radius, bottom, fill=self.SOFT_BLUE, outline="")
        self.canvas.create_oval(left, top, left + radius * 2, bottom, fill=self.SOFT_BLUE, outline="")
        self.canvas.create_oval(right - radius * 2, top, right, bottom, fill=self.SOFT_BLUE, outline="")
        self.canvas.create_oval(left + 12, top + 9, left + 20, top + 17, fill=color, outline="")
        self.canvas.create_text(
            cx + 6,
            (top + bottom) / 2,
            text=self._state_label(),
            font=("Microsoft YaHei UI", 8, "bold"),
            fill=self.TEXT,
        )

    def _draw_poop(self, cx: float, cy: float) -> None:
        dark = "#4a281d"
        brown = "#75402b"
        light = "#965b3a"
        shine = "#c58452"
        self.canvas.create_oval(cx - 42, cy + 5, cx + 42, cy + 40, fill=dark, outline="")
        self.canvas.create_oval(cx - 37, cy - 10, cx + 35, cy + 29, fill=brown, outline=dark, width=2)
        self.canvas.create_oval(cx - 28, cy - 29, cx + 28, cy + 10, fill=light, outline=dark, width=2)
        self.canvas.create_polygon(cx - 9, cy - 26, cx + 4, cy - 48, cx + 18, cy - 31, cx + 11, cy - 18, fill=light, outline=dark, width=2, smooth=True)
        self.canvas.create_oval(cx - 14, cy - 36, cx - 5, cy - 25, fill=shine, outline="")
        eye_y = cy - 5
        for eye_x in (cx - 15, cx + 15):
            self.canvas.create_oval(eye_x - 7, eye_y - 8, eye_x + 7, eye_y + 8, fill="#fffaf2", outline=dark, width=1)
            self.canvas.create_oval(eye_x - 2, eye_y - 2, eye_x + 3, eye_y + 4, fill="#221317", outline="")
            self.canvas.create_oval(eye_x - 1, eye_y - 2, eye_x + 1, eye_y, fill="white", outline="")
        self.canvas.create_arc(cx - 15, cy + 2, cx + 15, cy + 24, start=200, extent=140, style=tk.ARC, outline="#2a1518", width=3)
        cheek = "#d77970"
        self.canvas.create_oval(cx - 32, cy + 7, cx - 23, cy + 13, fill=cheek, outline="")
        self.canvas.create_oval(cx + 23, cy + 7, cx + 32, cy + 13, fill=cheek, outline="")

    def _state_label(self) -> str:
        labels = {
            "idle": "待命",
            "voice_loading": "加载语音模型",
            "listening": "正在聆听",
            "heard": "已听到",
            "thinking": "思考中",
            "working": "执行中",
            "confirming": "等待确认",
            "confirm_listening": "请说确认或取消",
            "speaking": "正在说话",
            "success": "已完成",
            "error": "执行出错",
            "voice_error": "语音不可用",
        }
        return labels.get(resolve_display_state(self.state, self.voice_activity), "待命")

    def _spawn_burst(self, count: int, color: str) -> None:
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(0.7, 2.3)
            life = random.randint(16, 30)
            self.particles.append(Particle(self.WIDTH / 2, 63, math.cos(angle) * speed, math.sin(angle) * speed - 0.5, life, life, random.uniform(1.5, 4.5), color))
        self._needs_redraw = True

    def _update_particles(self) -> None:
        alive: list[Particle] = []
        for particle in self.particles:
            particle.x += particle.vx
            particle.y += particle.vy
            particle.vx *= 0.985
            particle.vy += 0.025
            particle.life -= 1
            if particle.life > 0 and 12 <= particle.x <= self.WIDTH - 12 and 8 <= particle.y <= self.HEIGHT - 8:
                alive.append(particle)
        self.particles = alive[-140:]

    def _show_bubble(self, text: str) -> None:
        if self.bubble is not None:
            self.bubble.destroy()
        bubble = tk.Toplevel(self.root)
        self.bubble = bubble
        bubble.overrideredirect(True)
        bubble.attributes("-topmost", True)
        bubble.configure(bg=self.BORDER)

        visual_lines = 0
        for line in text.splitlines() or [text]:
            units = sum(2 if ord(char) > 127 else 1 for char in line)
            visual_lines += max(1, math.ceil(units / 58))
        width = 460
        height = min(380, max(142, 82 + visual_lines * 23))
        screen_width = bubble.winfo_screenwidth()
        screen_height = bubble.winfo_screenheight()
        x = max(12, min(self.root.winfo_x() - width - 16, screen_width - width - 12))
        y = max(12, min(self.root.winfo_y() + self.HEIGHT - height, screen_height - height - 52))
        bubble.geometry(f"{width}x{height}+{x}+{y}")

        card = tk.Frame(bubble, bg=self.CARD)
        card.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(card, bg=self.SOFT_BLUE, height=42)
        header.pack(fill="x")
        tk.Label(header, text="●  Agent 回复", bg=self.SOFT_BLUE, fg=self.ACCENT, font=("Microsoft YaHei UI", 9, "bold")).pack(side="left", padx=14, pady=10)
        tk.Button(header, text="×", command=bubble.destroy, bg=self.SOFT_BLUE, fg=self.MUTED, activebackground="#dbeafe", activeforeground=self.TEXT, relief="flat", bd=0, font=("Segoe UI", 13), cursor="hand2").pack(side="right", padx=10)

        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="both", expand=True, padx=(14, 8), pady=(10, 12))
        scrollbar = tk.Scrollbar(body, orient="vertical")
        message = tk.Text(
            body,
            wrap="word",
            bg=self.CARD,
            fg=self.TEXT,
            insertbackground=self.ACCENT,
            relief="flat",
            bd=0,
            font=("Microsoft YaHei UI", 10),
            spacing1=3,
            spacing3=5,
            padx=2,
            pady=2,
            yscrollcommand=scrollbar.set,
            cursor="arrow",
        )
        scrollbar.configure(command=message.yview)
        scrollbar.pack(side="right", fill="y")
        message.pack(side="left", fill="both", expand=True)
        message.insert("1.0", text)
        message.configure(state="disabled")
        bubble.bind("<Escape>", lambda _event: bubble.destroy())
        timeout = 30_000 if len(text) > 180 else 15_000
        bubble.after(timeout, lambda: bubble.destroy() if bubble.winfo_exists() else None)

    def _manual_chat_visible(self) -> bool:
        window = self.manual_chat_window
        return bool(window is not None and window.winfo_exists() and window.state() != "withdrawn")

    def _open_manual_chat(self) -> None:
        if self.manual_chat_window is not None and self.manual_chat_window.winfo_exists():
            self.manual_chat_window.deiconify()
            self._position_manual_chat(self.manual_chat_window)
            self.manual_chat_window.lift()
            self.manual_chat_window.focus_force()
            if self.manual_chat_input is not None:
                self.manual_chat_input.focus_set()
            return

        window = tk.Toplevel(self.root)
        self.manual_chat_window = window
        window.overrideredirect(True)
        window.configure(bg=self.BORDER)
        window.attributes("-topmost", True)
        self._position_manual_chat(window)

        panel = tk.Frame(window, bg=self.BG)
        panel.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(panel, bg=self.SOFT_BLUE, height=40)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="●  手动对话", bg=self.SOFT_BLUE, fg=self.ACCENT, font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=12)

        conversation = tk.Frame(panel, bg=self.CARD, highlightbackground=self.BORDER, highlightthickness=1)
        conversation.pack(fill="both", expand=True, padx=9, pady=(8, 7))
        scrollbar = tk.Scrollbar(conversation, orient="vertical")
        transcript = tk.Text(
            conversation,
            wrap="word",
            bg=self.CARD,
            fg=self.TEXT,
            relief="flat",
            bd=0,
            padx=9,
            pady=7,
            spacing1=1,
            spacing3=4,
            font=("Microsoft YaHei UI", 9),
            yscrollcommand=scrollbar.set,
            cursor="arrow",
        )
        scrollbar.configure(command=transcript.yview)
        scrollbar.pack(side="right", fill="y")
        transcript.pack(side="left", fill="both", expand=True)
        transcript.tag_configure("agent", foreground=self.ACCENT, font=("Microsoft YaHei UI", 9, "bold"))
        transcript.tag_configure("user", foreground="#047857", font=("Microsoft YaHei UI", 9, "bold"))
        transcript.configure(state="disabled")
        self.manual_chat_transcript = transcript

        composer = tk.Frame(panel, bg=self.BG)
        composer.pack(fill="x", padx=9, pady=(0, 9))
        entry_border = tk.Frame(composer, bg=self.BORDER)
        entry_border.pack(side="left", fill="both", expand=True)
        message_input = tk.Text(entry_border, height=2, wrap="word", bg="#ffffff", fg=self.TEXT, insertbackground=self.ACCENT, relief="flat", bd=0, padx=8, pady=7, font=("Microsoft YaHei UI", 9))
        message_input.pack(fill="both", expand=True, padx=1, pady=1)
        message_input.bind("<Return>", self._manual_submit_event)
        self.manual_chat_input = message_input
        tk.Button(composer, text="发送", command=self._manual_send, bg=self.ACCENT, fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff", relief="flat", bd=0, padx=14, font=("Microsoft YaHei UI", 9, "bold"), cursor="hand2").pack(side="left", padx=(7, 0), fill="y")

        def close() -> None:
            self.manual_chat_window = None
            self.manual_chat_transcript = None
            self.manual_chat_input = None
            window.destroy()

        tk.Button(header, text="×", command=close, bg=self.SOFT_BLUE, fg=self.MUTED, activebackground="#dbeafe", activeforeground=self.TEXT, relief="flat", bd=0, font=("Segoe UI", 12), cursor="hand2").pack(side="right", padx=7)
        window.bind("<Escape>", lambda _event: close())
        self._append_manual_message("Agent", "输入问题或 Skill 指令。Enter 发送，Shift+Enter 换行。")
        message_input.focus_set()

    def _position_manual_chat(self, window: tk.Toplevel) -> None:
        """Anchor the compact chat under the floating status surface when possible."""
        width, height = 380, 250
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        x = max(8, min(root_x + self.WIDTH - width, screen_width - width - 8))
        below_y = root_y + self.HEIGHT + 6
        y = below_y if below_y + height <= screen_height - 8 else root_y - height - 6
        y = max(8, min(y, screen_height - height - 8))
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _manual_submit_event(self, event: tk.Event) -> str | None:
        if event.state & 0x0001:  # Shift+Enter inserts a newline.
            return None
        self._manual_send()
        return "break"

    def _manual_send(self) -> None:
        if self.manual_chat_input is None:
            return
        text = self.manual_chat_input.get("1.0", "end-1c").strip()
        if not text:
            return
        self.manual_chat_input.delete("1.0", "end")
        self._append_manual_message("你", text)
        self.submit_command(text)

    def _append_manual_message(self, role: str, text: str) -> None:
        transcript = self.manual_chat_transcript
        if transcript is None or not transcript.winfo_exists():
            return
        transcript.configure(state="normal")
        tag = "user" if role == "你" else "agent"
        transcript.insert("end", f"{role}\n", tag)
        transcript.insert("end", f"{text.strip()}\n\n")
        transcript.configure(state="disabled")
        transcript.see("end")

    def _open_context_menu(self, event: tk.Event) -> None:
        self._close_context_menu()
        menu = tk.Toplevel(self.root)
        self.context_menu = menu
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.configure(bg=self.BORDER)
        width, height = 226, 238
        x = min(event.x_root, menu.winfo_screenwidth() - width - 12)
        y = min(event.y_root, menu.winfo_screenheight() - height - 12)
        menu.geometry(f"{width}x{height}+{max(8, x)}+{max(8, y)}")

        panel = tk.Frame(menu, bg=self.CARD)
        panel.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(panel, bg=self.SOFT_BLUE)
        header.pack(fill="x")
        tk.Label(header, text="💩", bg=self.SOFT_BLUE, fg=self.TEXT, font=("Segoe UI Emoji", 18)).pack(side="left", padx=(12, 8), pady=8)
        title = tk.Frame(header, bg=self.SOFT_BLUE)
        title.pack(side="left", pady=7)
        tk.Label(title, text="个人工作 Agent", bg=self.SOFT_BLUE, fg=self.TEXT, font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        tk.Label(title, text=f"当前状态：{self._state_label()}", bg=self.SOFT_BLUE, fg=self.MUTED, font=("Microsoft YaHei UI", 8)).pack(anchor="w")

        self._menu_button(panel, "⚙  进入设置", lambda: self._context_action(self._open_settings), accent=True)
        self._menu_button(panel, "⌨  手动对话", lambda: self._context_action(self._open_manual_chat))
        self._menu_button(panel, "🎙  开始聆听", lambda: self._context_action(self._activate_voice))
        self._menu_button(panel, "×  退出 Agent", lambda: self._context_action(self.shutdown), danger=True)
        menu.bind("<Escape>", lambda _event: self._close_context_menu())
        menu.bind("<FocusOut>", lambda _event: menu.after(120, self._close_context_if_unfocused))
        menu.focus_force()

    def _menu_button(self, parent: tk.Widget, text: str, command, accent: bool = False, danger: bool = False) -> None:
        normal = self.SOFT_BLUE if accent else self.CARD
        foreground = self.ACCENT if accent else ("#dc2626" if danger else self.TEXT)
        button = tk.Button(
            parent,
            text=text,
            command=command,
            anchor="w",
            bg=normal,
            fg=foreground,
            activebackground="#dbeafe",
            activeforeground=self.TEXT,
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            font=("Microsoft YaHei UI", 9, "bold" if accent else "normal"),
            cursor="hand2",
        )
        button.pack(fill="x", padx=6, pady=(5 if accent else 1, 0))
        button.bind("<Enter>", lambda _event: button.configure(bg="#dbeafe"))
        button.bind("<Leave>", lambda _event: button.configure(bg=normal))

    def _context_action(self, action) -> None:
        self._close_context_menu()
        action()

    def _close_context_if_unfocused(self) -> None:
        menu = self.context_menu
        if menu is not None and menu.winfo_exists() and menu.focus_displayof() is None:
            self._close_context_menu()

    def _close_context_menu(self) -> None:
        menu = self.context_menu
        self.context_menu = None
        if menu is not None and menu.winfo_exists():
            menu.destroy()

    def _open_settings(self, _event: tk.Event | None = None) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            return
        preferences = self.settings_store.load()
        runtime = get_settings()
        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("个人工作 Agent · 设置中心")
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        settings_width = min(1120, max(880, screen_width - 160))
        settings_height = min(760, max(620, screen_height - 160))
        settings_x = max(20, (window.winfo_screenwidth() - settings_width) // 2)
        settings_y = max(20, (window.winfo_screenheight() - settings_height) // 2)
        window.geometry(f"{settings_width}x{settings_height}+{settings_x}+{settings_y}")
        window.minsize(850, 580)
        window.configure(bg=self.BG)
        window.attributes("-topmost", True)
        window.lift()
        window.focus_force()

        self.settings_vars = {
            "wake_word": tk.StringVar(value=preferences.wake_word),
            "voice_enabled": tk.BooleanVar(value=preferences.voice_enabled),
            "require_confirmation": tk.BooleanVar(value=preferences.require_confirmation),
            "asr_backend": tk.StringVar(value=preferences.asr_backend),
            "renew_message": tk.StringVar(value=preferences.spark_renew_message),
            "renew_max": tk.IntVar(value=preferences.spark_renew_max_recipients),
            "renew_delay": tk.DoubleVar(value=preferences.spark_renew_delay_seconds),
            "llm_base_url": tk.StringVar(value=runtime.llm_base_url),
            "llm_api_key": tk.StringVar(value=runtime.llm_api_key),
            "llm_model": tk.StringVar(value=runtime.llm_model),
            "llm_timeout": tk.DoubleVar(value=runtime.llm_timeout_seconds),
            "ocr_backend": tk.StringVar(value=runtime.ocr_backend),
            "scan_backend": tk.StringVar(value=runtime.scan_backend),
            "scroll_settle_ms": tk.IntVar(value=runtime.scroll_settle_ms),
        }

        header = tk.Frame(window, bg=self.CARD, height=78, highlightbackground=self.BORDER, highlightthickness=1)
        header.pack(fill="x")
        tk.Label(header, text="💩", bg=self.CARD, fg=self.TEXT, font=("Segoe UI Emoji", 31)).pack(side="left", padx=(22, 12), pady=10)
        titles = tk.Frame(header, bg=self.CARD)
        titles.pack(side="left", pady=9)
        tk.Label(titles, text="个人工作 Agent · 设置中心", bg=self.CARD, fg=self.TEXT, font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
        tk.Label(titles, text="管理语音识别、大模型与可插拔 Skill", bg=self.CARD, fg=self.MUTED, font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        model_chip = "Qwen3.7 已连接" if runtime.llm_api_key else "Qwen3.7 待配置"
        tk.Label(header, text=model_chip, bg="#e8f7ef" if runtime.llm_api_key else self.SOFT_BLUE, fg="#047857" if runtime.llm_api_key else self.ACCENT, font=("Microsoft YaHei UI", 9), padx=12, pady=6).pack(side="right", padx=22)

        footer = tk.Frame(window, bg=self.CARD, height=54, highlightbackground=self.BORDER, highlightthickness=1)
        footer.pack(fill="x", side="bottom")
        self.settings_status = tk.StringVar(value="所有设置仅保存在本机")
        tk.Label(footer, textvariable=self.settings_status, bg=self.CARD, fg=self.MUTED, font=("Microsoft YaHei UI", 9)).pack(side="left", padx=20)
        tk.Button(footer, text="关闭", command=window.withdraw, bg=self.SOFT_BLUE, fg=self.TEXT, activebackground="#dbeafe", relief="flat", padx=18, pady=8, cursor="hand2").pack(side="right", padx=(8, 18), pady=9)
        tk.Button(footer, text="保存全部设置", command=self._save_all_settings, bg=self.ACCENT, fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff", relief="flat", padx=20, pady=8, font=("Microsoft YaHei UI", 9, "bold"), cursor="hand2").pack(side="right", pady=9)

        workspace = tk.Frame(window, bg=self.BG)
        workspace.pack(fill="both", expand=True)
        sidebar = tk.Frame(workspace, bg=self.SIDEBAR, width=220, highlightbackground=self.BORDER, highlightthickness=1)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="工作台", bg=self.SIDEBAR, fg=self.MUTED, font=("Microsoft YaHei UI", 8, "bold")).pack(anchor="w", padx=18, pady=(18, 7))
        self.settings_nav_buttons = {}
        self._add_settings_nav(sidebar, "overview", "⌂   总览")
        self._add_settings_nav(sidebar, "voice", "◉   语音与唤醒")
        self._add_settings_nav(sidebar, "model", "◇   模型配置")
        tk.Label(sidebar, text="SKILLS", bg=self.SIDEBAR, fg=self.MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=18, pady=(20, 7))
        for manifest in self.agent.registry.manifests():
            self._add_settings_nav(sidebar, f"skill:{manifest.id}", f"✦   {manifest.name}")
        tk.Frame(sidebar, bg=self.BORDER, height=1).pack(fill="x", padx=16, pady=(20, 12))
        tk.Button(sidebar, text="打开数据目录", command=self._open_data_directory, anchor="w", bg=self.SIDEBAR, fg=self.MUTED, activebackground="#dbeafe", activeforeground=self.TEXT, relief="flat", padx=18, pady=8, cursor="hand2").pack(fill="x")

        content_shell = tk.Frame(workspace, bg=self.BG)
        content_shell.pack(side="left", fill="both", expand=True)
        canvas = tk.Canvas(content_shell, bg=self.BG, bd=0, highlightthickness=0)
        scrollbar = tk.Scrollbar(content_shell, orient="vertical", command=canvas.yview, bg=self.CARD, troughcolor=self.BG)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        page = tk.Frame(canvas, bg=self.BG)
        page_id = canvas.create_window((0, 0), window=page, anchor="nw")
        page.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(page_id, width=event.width))
        canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"))
        self.settings_canvas = canvas
        self.settings_content = page
        self._show_settings_page("overview")
        window.protocol("WM_DELETE_WINDOW", window.withdraw)

    def _add_settings_nav(self, parent: tk.Widget, page_id: str, text: str) -> None:
        button = tk.Button(parent, text=text, command=lambda: self._show_settings_page(page_id), anchor="w", bg=self.SIDEBAR, fg=self.MUTED, activebackground="#dbeafe", activeforeground=self.TEXT, relief="flat", bd=0, padx=18, pady=10, font=("Microsoft YaHei UI", 9), cursor="hand2")
        button.pack(fill="x", padx=8, pady=1)
        self.settings_nav_buttons[page_id] = button

    def _show_settings_page(self, page_id: str) -> None:
        if self.settings_content is None:
            return
        for child in self.settings_content.winfo_children():
            child.destroy()
        for key, button in self.settings_nav_buttons.items():
            button.configure(bg="#dbeafe" if key == page_id else self.SIDEBAR, fg=self.ACCENT if key == page_id else self.MUTED)
        if page_id == "overview":
            self._build_overview_page()
        elif page_id == "voice":
            self._build_voice_page()
        elif page_id == "model":
            self._build_model_page()
        elif page_id.startswith("skill:"):
            self._build_skill_page(page_id.split(":", 1)[1])
        if self.settings_canvas is not None:
            self.settings_canvas.yview_moveto(0)

    def _page_header(self, title: str, subtitle: str) -> None:
        parent = self.settings_content
        if parent is None:
            return
        tk.Label(parent, text=title, bg=self.BG, fg=self.TEXT, font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w", padx=28, pady=(24, 3))
        tk.Label(parent, text=subtitle, bg=self.BG, fg=self.MUTED, font=("Microsoft YaHei UI", 9), wraplength=610, justify="left").pack(anchor="w", padx=28, pady=(0, 16))

    def _settings_card(self, title: str, subtitle: str = "") -> tk.Frame:
        if self.settings_content is None:
            raise RuntimeError("设置内容区域未初始化")
        card = tk.Frame(self.settings_content, bg=self.CARD, highlightbackground=self.BORDER, highlightthickness=1)
        card.pack(fill="x", padx=28, pady=(0, 14))
        tk.Label(card, text=title, bg=self.CARD, fg=self.TEXT, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=18, pady=(15, 2 if subtitle else 10))
        if subtitle:
            tk.Label(card, text=subtitle, bg=self.CARD, fg=self.MUTED, font=("Microsoft YaHei UI", 8), wraplength=720, justify="left").pack(anchor="w", padx=18, pady=(0, 9))
        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="x", padx=18, pady=(0, 16))
        return body

    def _settings_entry(self, parent: tk.Widget, label: str, variable: tk.Variable, *, secret: bool = False, hint: str = "") -> tk.Entry:
        tk.Label(parent, text=label, bg=self.CARD, fg=self.TEXT, font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(6, 4))
        entry = tk.Entry(parent, textvariable=variable, show="●" if secret else "", bg="#f7fbff", fg=self.TEXT, insertbackground=self.ACCENT, relief="solid", bd=1, highlightcolor=self.ACCENT, font=("Microsoft YaHei UI", 10))
        entry.pack(fill="x", ipady=9)
        if hint:
            tk.Label(parent, text=hint, bg=self.CARD, fg=self.MUTED, font=("Microsoft YaHei UI", 8), wraplength=720, justify="left").pack(anchor="w", pady=(4, 2))
        return entry

    def _build_overview_page(self) -> None:
        self._page_header("工作台总览", "在一个地方管理 Agent 的交互方式、语音识别、模型连接和所有 Skill。")
        status = self._settings_card("运行状态")
        items = [
            ("语音唤醒", "已开启" if bool(self.settings_vars["voice_enabled"].get()) else "已关闭", "#059669"),
            ("对话模型", str(self.settings_vars["llm_model"].get()), self.ACCENT),
            ("已安装 Skills", str(len(self.agent.registry.manifests())), "#0284c7"),
        ]
        for index, (label, value, color) in enumerate(items):
            block = tk.Frame(status, bg=self.SOFT_BLUE)
            block.pack(side="left", fill="both", expand=True, padx=(0 if index == 0 else 5, 0))
            tk.Label(block, text=label, bg=self.SOFT_BLUE, fg=self.MUTED, font=("Microsoft YaHei UI", 8)).pack(anchor="w", padx=12, pady=(10, 2))
            tk.Label(block, text=value, bg=self.SOFT_BLUE, fg=color, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=12, pady=(0, 10))

        command_card = self._settings_card("快速命令", "无需关闭设置中心即可测试路由、对话或 Skill。")
        command_var = tk.StringVar()
        row = tk.Frame(command_card, bg=self.CARD)
        row.pack(fill="x")
        command = tk.Entry(row, textvariable=command_var, bg="#f7fbff", fg=self.TEXT, insertbackground=self.ACCENT, relief="solid", bd=1, font=("Microsoft YaHei UI", 10))
        command.pack(side="left", fill="x", expand=True, ipady=9)
        tk.Button(row, text="执行命令", command=lambda: self._run_settings_command(command_var), bg=self.ACCENT, fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff", relief="flat", padx=18, pady=8, font=("Microsoft YaHei UI", 9, "bold"), cursor="hand2").pack(side="left", padx=(8, 0))
        command.bind("<Return>", lambda _event: self._run_settings_command(command_var))

        tips = self._settings_card("交互提示")
        for text in ("左击桌面图标：开始一次语音聆听", "右击桌面图标：打开手动对话或设置", "执行批量发送时：Ctrl + Shift + Q 紧急停止"):
            tk.Label(tips, text=f"•  {text}", bg=self.CARD, fg=self.TEXT, font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=3)

    def _build_voice_page(self) -> None:
        self._page_header("语音与唤醒", "SenseVoice 负责高精度中文识别；Agent 回复以文字显示，不再加载或播放语音合成。")
        models = discover_voice_models()
        state = self._settings_card("本地语音识别引擎", "模型缺失或加载失败时会自动降级到 Windows SAPI 识别，不影响手动对话。")
        asr_text = "●  SenseVoice Small INT8 已就绪" if models.asr_ready else "○  SenseVoice 模型未安装"
        tk.Label(state, text=asr_text, bg=self.CARD, fg="#047857" if models.asr_ready else "#b45309", font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w", pady=3)
        tk.Label(state, text=str(models.root), bg=self.CARD, fg=self.MUTED, font=("Microsoft YaHei UI", 8), wraplength=700, justify="left").pack(anchor="w", pady=(2, 8))
        if not models.ready:
            tk.Button(state, text="下载并安装本地识别模型", command=self._install_voice_models_from_ui, bg=self.ACCENT, fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff", relief="flat", padx=16, pady=8, font=("Microsoft YaHei UI", 9, "bold"), cursor="hand2").pack(anchor="w")

        card = self._settings_card("唤醒与识别", "SenseVoice Small INT8 + Silero VAD 会持续监听语音片段，但只在命中唤醒词后执行命令。")
        self._settings_entry(card, "唤醒词", self.settings_vars["wake_word"], hint="默认：史蒂芬。建议使用 2-4 个清晰中文音节。")
        self._settings_option(card, "语音识别引擎", self.settings_vars["asr_backend"], ("sensevoice", "sapi"))
        self._settings_check(card, "开启麦克风语音唤醒", self.settings_vars["voice_enabled"])
        self._settings_check(card, "本地桌面操作前要求确认", self.settings_vars["require_confirmation"])

    def _install_voice_models_from_ui(self) -> None:
        if self.settings_status is not None:
            self.settings_status.set("正在安装本地语音模型，请保持网络连接…")

        def report(message: str) -> None:
            self.root.after(0, lambda: self.settings_status.set(message) if self.settings_status is not None else None)

        def worker() -> None:
            try:
                install_voice_models(progress=report)
            except Exception as exc:
                self.root.after(0, lambda: self.settings_status.set(f"语音模型安装失败：{exc}") if self.settings_status is not None else None)
                return
            self.root.after(0, self._voice_models_installed)

        threading.Thread(target=worker, name="voice-model-installer", daemon=True).start()

    def _voice_models_installed(self) -> None:
        self.voice.restart()
        if self.settings_status is not None:
            self.settings_status.set("SenseVoice 与 Silero VAD 安装完成")
        self._show_settings_page("voice")

    def _build_model_page(self) -> None:
        self._page_header("模型配置", "为普通对话选择 OpenAI Chat Completions 兼容模型；Agent 工具执行仍由确定性权限层控制。")
        card = self._settings_card("Qwen / OpenAI 兼容接口", "默认使用阿里云百炼 qwen3.7-plus。API Key 仅写入本机 backend/.env。")
        self._settings_entry(card, "Base URL", self.settings_vars["llm_base_url"])
        self._settings_entry(card, "模型名称", self.settings_vars["llm_model"])
        key_entry = self._settings_entry(card, "API Key", self.settings_vars["llm_api_key"], secret=True, hint="不会写入 README 或数据库；请勿将 .env 提交到 GitHub。")
        show_key = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text="显示 API Key", variable=show_key, command=lambda: key_entry.configure(show="" if show_key.get() else "●"), bg=self.CARD, fg=self.MUTED, selectcolor=self.SOFT_BLUE, activebackground=self.CARD, activeforeground=self.TEXT, font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(5, 0))
        timeout_row = tk.Frame(card, bg=self.CARD)
        timeout_row.pack(fill="x", pady=(8, 0))
        tk.Label(timeout_row, text="请求超时（秒）", bg=self.CARD, fg=self.TEXT).pack(side="left")
        tk.Spinbox(timeout_row, from_=5, to=180, textvariable=self.settings_vars["llm_timeout"], width=8, bg="#f7fbff", fg=self.TEXT, buttonbackground=self.SOFT_BLUE, relief="solid", bd=1).pack(side="left", padx=10, ipady=4)
        configured = bool(str(self.settings_vars["llm_api_key"].get()).strip())
        state = self._settings_card("连接状态")
        tk.Label(state, text="●  API Key 已配置" if configured else "○  尚未填写 API Key", bg=self.CARD, fg="#047857" if configured else "#b45309", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        tk.Button(state, text="测试大模型连接", command=self._test_llm_connection, bg=self.ACCENT, fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff", relief="flat", padx=16, pady=7, font=("Microsoft YaHei UI", 9, "bold"), cursor="hand2").pack(anchor="w")

    def _test_llm_connection(self) -> None:
        if self.settings_status is not None:
            self.settings_status.set("正在测试大模型连接…")

        def worker() -> None:
            try:
                result = asyncio.run(self.agent.provider.complete("你是连接测试助手。", "只回复：连接成功"))
                message = "大模型连接成功" if result else "大模型未配置或未返回内容"
            except Exception as exc:
                message = f"大模型连接失败：{exc}"
            self.root.after(0, lambda: self.settings_status.set(message) if self.settings_status is not None else None)

        threading.Thread(target=worker, name="llm-connection-test", daemon=True).start()

    def _build_skill_page(self, skill_id: str) -> None:
        manifest = next((item for item in self.agent.registry.manifests() if item.id == skill_id), None)
        if manifest is None:
            return
        self._page_header(manifest.name, manifest.description)
        if skill_id == "spark_scan":
            card = self._settings_card("视觉识别", "优先使用 UIA；不可用时由 RapidOCR/OpenCV 局部视觉兜底。")
            self._settings_option(card, "扫描模式", self.settings_vars["scan_backend"], ("hybrid", "uia", "vision"))
            self._settings_option(card, "OCR 后端", self.settings_vars["ocr_backend"], ("rapid", "paddle"))
            row = tk.Frame(card, bg=self.CARD)
            row.pack(fill="x", pady=(10, 0))
            tk.Label(row, text="滚动稳定等待（毫秒）", bg=self.CARD, fg=self.TEXT).pack(side="left")
            tk.Spinbox(row, from_=100, to=2000, increment=20, textvariable=self.settings_vars["scroll_settle_ms"], width=9, bg="#f7fbff", fg=self.TEXT, buttonbackground=self.SOFT_BLUE, relief="solid", bd=1).pack(side="left", padx=10, ipady=4)
        elif skill_id == "spark_renew":
            card = self._settings_card("发送策略", "明确说出续火花指令后，将立即扫描并按这些设置顺序发送。")
            self._settings_entry(card, "消息模板", self.settings_vars["renew_message"], hint="可使用 {nickname} 插入联系人昵称；禁止换行，最长 120 字。")
            row = tk.Frame(card, bg=self.CARD)
            row.pack(fill="x", pady=(10, 0))
            tk.Label(row, text="最多发送人数", bg=self.CARD, fg=self.TEXT).pack(side="left")
            tk.Spinbox(row, from_=1, to=300, textvariable=self.settings_vars["renew_max"], width=8, bg="#f7fbff", fg=self.TEXT, buttonbackground=self.SOFT_BLUE, relief="solid", bd=1).pack(side="left", padx=(10, 26), ipady=4)
            tk.Label(row, text="逐条间隔（秒）", bg=self.CARD, fg=self.TEXT).pack(side="left")
            tk.Spinbox(row, from_=0.15, to=3.0, increment=0.05, textvariable=self.settings_vars["renew_delay"], width=8, bg="#f7fbff", fg=self.TEXT, buttonbackground=self.SOFT_BLUE, relief="solid", bd=1).pack(side="left", padx=10, ipady=4)
            safety = self._settings_card("固定安全策略", "以下保护不能在界面中关闭。")
            for text in ("明确续火花指令即开始执行，不再二次确认", "右上角消息面板 + 单次列表遍历", "固定消息编辑区输入 + 右侧箭头发送", "Ctrl + Shift + Q 紧急停止；输入失败立即中止"):
                tk.Label(safety, text=f"✓  {text}", bg=self.CARD, fg="#047857", font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=3)
        else:
            card = self._settings_card("Skill 配置")
            tk.Label(card, text=f"ID：{manifest.id}   ·   权限：{manifest.permission.name}", bg=self.CARD, fg=self.MUTED).pack(anchor="w", pady=(0, 8))
            if not manifest.settings_schema:
                tk.Label(card, text="该 Skill 暂未声明配置字段。添加 settings_schema 后，本页面会自动生成控件并持久化。", bg=self.CARD, fg=self.TEXT, wraplength=720, justify="left").pack(anchor="w", pady=(6, 0))
            saved = self.skill_settings_store.load(manifest.id)
            for field in manifest.settings_schema:
                variable_key = f"skill_custom:{manifest.id}:{field.key}"
                if variable_key not in self.settings_vars:
                    value = saved.get(field.key, field.default)
                    if field.kind == "boolean":
                        self.settings_vars[variable_key] = tk.BooleanVar(value=bool(value))
                    elif field.kind == "integer":
                        self.settings_vars[variable_key] = tk.IntVar(value=int(value))
                    elif field.kind == "number":
                        self.settings_vars[variable_key] = tk.DoubleVar(value=float(value))
                    else:
                        self.settings_vars[variable_key] = tk.StringVar(value=str(value))
                variable = self.settings_vars[variable_key]
                if field.kind == "boolean":
                    self._settings_check(card, field.label, variable)
                elif field.kind == "select" and field.options:
                    self._settings_option(card, field.label, variable, tuple(field.options))
                elif field.kind in {"integer", "number"}:
                    row = tk.Frame(card, bg=self.CARD)
                    row.pack(fill="x", pady=(7, 0))
                    tk.Label(row, text=field.label, bg=self.CARD, fg=self.TEXT).pack(side="left")
                    tk.Spinbox(row, from_=-100000, to=100000, increment=1 if field.kind == "integer" else 0.1, textvariable=variable, width=12, bg="#f7fbff", fg=self.TEXT, buttonbackground=self.SOFT_BLUE, relief="solid", bd=1).pack(side="left", padx=10, ipady=4)
                else:
                    self._settings_entry(card, field.label, variable, secret=field.kind == "password", hint=field.description)

    def _settings_check(self, parent: tk.Widget, text: str, variable: tk.Variable) -> None:
        tk.Checkbutton(parent, text=text, variable=variable, bg=self.CARD, fg=self.TEXT, selectcolor=self.SOFT_BLUE, activebackground=self.CARD, activeforeground=self.TEXT, font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=4)

    def _settings_option(self, parent: tk.Widget, label: str, variable: tk.Variable, choices: tuple[str, ...]) -> None:
        tk.Label(parent, text=label, bg=self.CARD, fg=self.TEXT, font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(7, 4))
        menu = tk.OptionMenu(parent, variable, *choices)
        menu.configure(bg="#f7fbff", fg=self.TEXT, activebackground="#dbeafe", activeforeground=self.TEXT, relief="solid", bd=1, highlightthickness=0, anchor="w")
        menu["menu"].configure(bg=self.CARD, fg=self.TEXT, activebackground="#dbeafe")
        menu.pack(fill="x", ipady=3)

    def _save_all_settings(self) -> None:
        try:
            preferences = AgentPreferences(
                wake_word=str(self.settings_vars["wake_word"].get()).strip(),
                voice_enabled=bool(self.settings_vars["voice_enabled"].get()),
                require_confirmation=bool(self.settings_vars["require_confirmation"].get()),
                asr_backend=str(self.settings_vars["asr_backend"].get()),
                spark_renew_message=str(self.settings_vars["renew_message"].get()).strip(),
                spark_renew_max_recipients=int(self.settings_vars["renew_max"].get()),
                spark_renew_delay_seconds=float(self.settings_vars["renew_delay"].get()),
            )
            base_url = str(self.settings_vars["llm_base_url"].get()).strip()
            model = str(self.settings_vars["llm_model"].get()).strip()
            if not base_url.startswith(("http://", "https://")):
                raise ValueError("模型 Base URL 必须以 http:// 或 https:// 开头。")
            if not model:
                raise ValueError("模型名称不能为空。")
            self.settings_store.save(preferences)
            RuntimeEnvStore().update(
                {
                    "LLM_BASE_URL": base_url,
                    "LLM_API_KEY": str(self.settings_vars["llm_api_key"].get()).strip(),
                    "LLM_MODEL": model,
                    "LLM_TIMEOUT_SECONDS": float(self.settings_vars["llm_timeout"].get()),
                    "OCR_BACKEND": str(self.settings_vars["ocr_backend"].get()),
                    "SCAN_BACKEND": str(self.settings_vars["scan_backend"].get()),
                    "SCROLL_SETTLE_MS": int(self.settings_vars["scroll_settle_ms"].get()),
                }
            )
            for manifest in self.agent.registry.manifests():
                values = {
                    field.key: self.settings_vars[f"skill_custom:{manifest.id}:{field.key}"].get()
                    for field in manifest.settings_schema
                    if f"skill_custom:{manifest.id}:{field.key}" in self.settings_vars
                }
                if values:
                    self.skill_settings_store.save(manifest.id, values)
        except Exception as exc:
            if self.settings_status is not None:
                self.settings_status.set(f"保存失败：{exc}")
            return
        self.agent.provider = LLMProvider()
        self.voice.restart()
        if self.settings_status is not None:
            model_state = "模型已连接" if self.agent.provider.is_configured else "模型待填写 API Key"
            self.settings_status.set(f"设置已保存 · {model_state}")
        self._show_bubble(f"设置已保存。唤醒词：{preferences.wake_word}；模型：{model}。")

    def _run_settings_command(self, variable: tk.StringVar) -> None:
        command = variable.get().strip()
        if command:
            variable.set("")
            self.submit_command(command)

    def _restore_overlay(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)

    def _on_enter(self, _event: tk.Event) -> None:
        self.hovered = True
        self._needs_redraw = True

    def _on_leave(self, _event: tk.Event) -> None:
        self.hovered = False
        self._needs_redraw = True

    def _on_press(self, event: tk.Event) -> None:
        self._close_context_menu()
        self.pressed = True
        self.dragging = False
        self.press_screen = (event.x_root, event.y_root)
        self.drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _on_drag(self, event: tk.Event) -> None:
        if not self.pressed:
            return
        if math.hypot(event.x_root - self.press_screen[0], event.y_root - self.press_screen[1]) > 5:
            self.dragging = True
            self.root.geometry(f"+{event.x_root - self.drag_origin[0]}+{event.y_root - self.drag_origin[1]}")

    def _on_release(self, _event: tk.Event) -> None:
        should_activate = self.pressed and not self.dragging
        self.pressed = False
        if should_activate:
            self._activate_voice()

    @staticmethod
    def _open_data_directory() -> None:
        from app.core.runtime import data_directory

        path = data_directory()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]

    def shutdown(self) -> None:
        self.voice.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


_mutex_handle: int | None = None


def _acquire_single_instance() -> bool:
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    _mutex_handle = kernel32.CreateMutexW(None, False, "Local\\StephenPersonalWorkAgentV1")
    return bool(_mutex_handle) and kernel32.GetLastError() != 183


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-ocr":
        configure_logging()
        from app.core.config import get_settings
        from app.vision.ocr_engine import get_ocr_engine

        image_path = Path(sys.argv[2]).resolve()
        settings = get_settings()
        blocks = get_ocr_engine(settings.ocr_lang, settings.ocr_backend).recognize(image_path)
        logger.info("OCR smoke test passed: image=%s blocks=%d", image_path, len(blocks))
        return
    if len(sys.argv) == 2 and sys.argv[1] == "--probe-uia":
        configure_logging()
        from app.desktop_agent.uia_backend import DouyinUIABackend
        from app.desktop_agent.window_locator import DouyinWindowLocator

        window = DouyinWindowLocator().find()
        snapshot = DouyinUIABackend().inspect(window)
        logger.info("UIA probe: open=%s rows=%d elapsed_ms=%d", snapshot.panel_open, len(snapshot.rows), snapshot.elapsed_ms)
        return
    if len(sys.argv) == 2 and sys.argv[1] == "--preview-settings":
        configure_logging()
        initialize_database()
        preview = FloatingPersonalAgent()
        preview.root.after(300, preview._open_settings)
        preview.run()
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--preview-settings":
        configure_logging()
        initialize_database()
        preview = FloatingPersonalAgent()

        def open_preview_page() -> None:
            preview._open_settings()
            preview._show_settings_page(sys.argv[2])

        preview.root.after(300, open_preview_page)
        preview.run()
        return
    if len(sys.argv) == 2 and sys.argv[1] == "--preview-menu":
        configure_logging()
        initialize_database()
        preview = FloatingPersonalAgent()
        preview.root.geometry(f"{preview.WIDTH}x{preview.HEIGHT}+1200+700")
        preview.root.after(500, lambda: preview.canvas.event_generate("<Button-3>", x=70, y=70))
        preview.run()
        return
    if len(sys.argv) == 2 and sys.argv[1] == "--preview-manual-chat":
        configure_logging()
        initialize_database()
        preview = FloatingPersonalAgent()
        preview.root.after(300, preview._open_manual_chat)
        preview.run()
        return
    if len(sys.argv) == 2 and sys.argv[1] == "--preview-bubble":
        configure_logging()
        initialize_database()
        preview = FloatingPersonalAgent()
        preview.root.after(
            500,
            lambda: preview._show_bubble(
                "我已经完成本次任务。这是一段用于验证长回复显示的文本：回复框现在会根据内容自动增高，"
                "内容较多时提供滚动条，并且始终限制在屏幕可见区域内，因此中文长文本、执行报告和错误详情都不会再被截断。\n\n"
                "你可以使用右上角关闭按钮，也可以按 Esc 关闭回复框。"
            ),
        )
        preview.run()
        return
    if not _acquire_single_instance():
        return
    configure_logging()
    initialize_database()
    FloatingPersonalAgent().run()


if __name__ == "__main__":
    main()
