"""
番茄钟桌面应用 - Pomodoro Timer
A full-featured desktop Pomodoro timer built with Python + Tkinter.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import time
import json
import os
from datetime import datetime
import winsound
import threading

# ── Constants ────────────────────────────────────────────────────────
COLORS = {
    "bg": "#0f1a12",           # 深墨绿 - background
    "card": "#16261b",         # 深林色 - card surface
    "card_alt": "#1c3022",     # 浅林色 - hover/alt
    "primary": "#99bf8e",      # 灰绿 (主色) - buttons, active accent
    "primary_hover": "#7da672",
    "secondary": "#d1e3c9",    # 浅灰绿 - short break mode
    "secondary_hover": "#b4c8b4",
    "accent": "#8cb48c",       # 中灰绿 - long break mode
    "accent_hover": "#6e9a6e",
    "text": "#e5fede",         # 雾白绿 - primary text
    "text_dim": "#7a9a7a",     # 暗绿 - secondary text
    "text_bright": "#f0ffea",  # 亮雾白 - bright text
    "border": "#2a4030",       # 墨绿边框
    "success": "#99bf8e",
    "warning": "#d4b872",      # 暖金 - from paper tones
}

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_LARGE = ("Segoe UI", 56, "bold")
FONT_MEDIUM = ("Segoe UI", 14)
FONT_SMALL = ("Segoe UI", 9)

DEFAULT_WORK = 25
DEFAULT_SHORT_BREAK = 5
DEFAULT_LONG_BREAK = 15
LONG_BREAK_INTERVAL = 4  # every N pomodoros


class PomodoroApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("番茄钟 - Pomodoro Timer")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(False, False)

        # Window icon (use a simple text-based icon with tkinter)
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        # Center the window
        self._center_window(420, 580)

        # ── State ────────────────────────────────────────────────
        self.modes = {
            "pomodoro":    {"label": "🎋 专注", "duration": DEFAULT_WORK * 60,       "color": COLORS["primary"],   "type": "work"},
            "short_break": {"label": "🌱 短休", "duration": DEFAULT_SHORT_BREAK * 60, "color": COLORS["secondary"], "type": "break"},
            "long_break":  {"label": "🌳 长休", "duration": DEFAULT_LONG_BREAK * 60,  "color": COLORS["accent"],    "type": "break"},
        }
        self.current_mode = "pomodoro"
        self.time_left = self.modes[self.current_mode]["duration"]
        self.is_running = False
        self.completed_pomodoros = 0
        self.timer_job = None
        self.auto_start = tk.BooleanVar(value=False)

        self._base_dir = os.path.dirname(os.path.abspath(__file__))
        self.settings_file = os.path.join(self._base_dir, "pomodoro_settings.json")
        self._load_settings()

        # ── Build UI ────────────────────────────────────────────
        self._build_ui()
        self._update_display()

        # ── Keyboard shortcuts ──────────────────────────────────
        self.root.bind("<space>", lambda e: self.toggle_start())
        self.root.bind("<r>", lambda e: self.reset())
        self.root.bind("<Escape>", lambda e: self.reset())

        # ── Main loop ───────────────────────────────────────────
        self.root.mainloop()

    # ── Window ─────────────────────────────────────────────────────
    def _center_window(self, w, h):
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        x = (ws - w) // 2
        y = (hs - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _center_toplevel(self, toplevel, w, h):
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        x = (ws - w) // 2
        y = (hs - h) // 2
        toplevel.geometry(f"{w}x{h}+{x}+{y}")

    # ── Settings ──────────────────────────────────────────────────
    def _read_json(self, path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _load_settings(self):
        data = self._read_json(self.settings_file)
        self.modes["pomodoro"]["duration"] = data.get("work", DEFAULT_WORK * 60)
        self.modes["short_break"]["duration"] = data.get("short_break", DEFAULT_SHORT_BREAK * 60)
        self.modes["long_break"]["duration"] = data.get("long_break", DEFAULT_LONG_BREAK * 60)
        self.completed_pomodoros = data.get("completed", 0)

    def _save_settings(self):
        data = {
            "work": self.modes["pomodoro"]["duration"],
            "short_break": self.modes["short_break"]["duration"],
            "long_break": self.modes["long_break"]["duration"],
            "completed": self.completed_pomodoros,
        }
        try:
            with open(self.settings_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ── UI Building ───────────────────────────────────────────────
    def _build_ui(self):
        # Main container with padding
        self.main_frame = tk.Frame(self.root, bg=COLORS["bg"])
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Title ────────────────────────────────────────────
        title_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        title_frame.pack(fill="x", pady=(0, 8))

        tk.Label(
            title_frame,
            text="🍅 番茄钟",
            font=("Segoe UI", 18, "bold"),
            bg=COLORS["bg"],
            fg=COLORS["text_bright"],
        ).pack(side="left")

        # Settings button
        self._btn_cog = tk.Button(
            title_frame,
            text="⚙",
            font=("Segoe UI", 14),
            bg=COLORS["bg"],
            fg=COLORS["text_dim"],
            bd=0,
            activebackground=COLORS["bg"],
            activeforeground=COLORS["text"],
            cursor="hand2",
            command=self._show_settings,
        )
        self._btn_cog.pack(side="right")

        # Stats
        self.lbl_stats = tk.Label(
            title_frame,
            text="",
            font=FONT_SMALL,
            bg=COLORS["bg"],
            fg=COLORS["text_dim"],
        )
        self.lbl_stats.pack(side="right", padx=(0, 10))

        # ── Mode Tabs ─────────────────────────────────────────
        self.tab_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        self.tab_frame.pack(fill="x", pady=(0, 14))

        self.tab_btns = {}
        for mode_key in ["pomodoro", "short_break", "long_break"]:
            mode = self.modes[mode_key]
            btn = tk.Button(
                self.tab_frame,
                text=mode["label"],
                font=FONT_BOLD,
                bg=COLORS["card"] if mode_key != self.current_mode else mode["color"],
                fg=COLORS["text"],
                bd=0,
                padx=14,
                pady=6,
                cursor="hand2",
                activebackground=mode["color"],
                activeforeground=COLORS["text_bright"],
                command=lambda k=mode_key: self.switch_mode(k),
            )
            btn.pack(side="left", padx=(0, 6))
            self.tab_btns[mode_key] = btn

        # ── Timer Canvas (circular) ──────────────────────────
        self.canvas_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        self.canvas_frame.pack(pady=(4, 4))

        self.canvas_size = 260
        self.canvas = tk.Canvas(
            self.canvas_frame,
            width=self.canvas_size,
            height=self.canvas_size,
            bg=COLORS["bg"],
            highlightthickness=0,
        )
        self.canvas.pack()

        # Timer text on canvas
        self.timer_text_id = self.canvas.create_text(
            self.canvas_size // 2,
            self.canvas_size // 2 - 10,
            text="25:00",
            font=FONT_LARGE,
            fill=COLORS["text_bright"],
            anchor="center",
        )
        self.status_text_id = self.canvas.create_text(
            self.canvas_size // 2,
            self.canvas_size // 2 + 38,
            text="点击开始",
            font=FONT_SMALL,
            fill=COLORS["text_dim"],
            anchor="center",
        )

        # ── Controls ─────────────────────────────────────────
        self.ctrl_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        self.ctrl_frame.pack(pady=(10, 6))

        self.btn_start = tk.Button(
            self.ctrl_frame,
            text="▶ 开始",
            font=FONT_BOLD,
            bg=COLORS["primary"],
            fg=COLORS["text_bright"],
            bd=0,
            padx=32,
            pady=8,
            cursor="hand2",
            activebackground=COLORS["primary_hover"],
            activeforeground=COLORS["text_bright"],
            command=self.toggle_start,
        )
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_reset = tk.Button(
            self.ctrl_frame,
            text="↺",
            font=("Segoe UI", 14),
            bg=COLORS["card"],
            fg=COLORS["text"],
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            activebackground=COLORS["card_alt"],
            activeforeground=COLORS["text_bright"],
            command=self.reset,
        )
        self.btn_reset.pack(side="left")

        # ── Auto-start toggle ────────────────────────────────
        auto_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        auto_frame.pack(fill="x", pady=(4, 0))

        tk.Checkbutton(
            auto_frame,
            text="自动开始下一个",
            variable=self.auto_start,
            font=FONT_SMALL,
            bg=COLORS["bg"],
            fg=COLORS["text_dim"],
            selectcolor=COLORS["card"],
            activebackground=COLORS["bg"],
            activeforeground=COLORS["text"],
            bd=0,
            cursor="hand2",
        ).pack(side="left")

        # ── Session Log ─────────────────────────────────────
        sep = tk.Frame(self.main_frame, bg=COLORS["border"], height=1)
        sep.pack(fill="x", pady=(14, 8))

        log_header = tk.Frame(self.main_frame, bg=COLORS["bg"])
        log_header.pack(fill="x")

        tk.Label(
            log_header,
            text="📋 今日记录",
            font=FONT_BOLD,
            bg=COLORS["bg"],
            fg=COLORS["text"],
        ).pack(side="left")

        self.lbl_today_count = tk.Label(
            log_header,
            text="0 个番茄",
            font=FONT_SMALL,
            bg=COLORS["bg"],
            fg=COLORS["text_dim"],
        )
        self.lbl_today_count.pack(side="right")

        # Log list
        list_frame = tk.Frame(self.main_frame, bg=COLORS["bg"])
        list_frame.pack(fill="both", expand=True, pady=(6, 0))

        self.log_listbox = tk.Listbox(
            list_frame,
            height=4,
            bg=COLORS["card"],
            fg=COLORS["text"],
            bd=0,
            highlightthickness=0,
            font=FONT_SMALL,
            selectbackground=COLORS["card_alt"],
            selectforeground=COLORS["text"],
            activestyle="none",
        )
        self.log_listbox.pack(fill="both", expand=True, side="left")

        scrollbar = tk.Scrollbar(list_frame, bg=COLORS["card"], troughcolor=COLORS["bg"])
        scrollbar.pack(side="right", fill="y")
        self.log_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.log_listbox.yview)

        # ── Key Hint ─────────────────────────────────────────
        tk.Label(
            self.main_frame,
            text="空格: 开始/暂停  |  R: 重置",
            font=("Segoe UI", 8),
            bg=COLORS["bg"],
            fg=COLORS["text_dim"],
        ).pack(fill="x", pady=(8, 0))

        # ── Load today's log ────────────────────────────────
        self._load_today_log()
        self._update_stats()

    # ── Canvas Drawing ─────────────────────────────────────────────
    def _draw_progress(self, progress):
        cx = cy = self.canvas_size // 2
        radius = 105
        width = 8

        # Background circle (created once)
        if not self.canvas.find_withtag("progress_bg"):
            self.canvas.create_oval(
                cx - radius, cy - radius,
                cx + radius, cy + radius,
                outline=COLORS["border"],
                width=width,
                tags="progress_bg",
            )

        color = self.modes[self.current_mode]["color"]
        arc_items = self.canvas.find_withtag("progress_arc")

        if progress > 0:
            extent = -360 * progress
            if arc_items:
                self.canvas.itemconfig(arc_items[0], extent=extent, outline=color)
            else:
                self.canvas.create_arc(
                    cx - radius, cy - radius,
                    cx + radius, cy + radius,
                    start=90,
                    extent=extent,
                    outline=color,
                    width=width,
                    style="arc",
                    tags="progress_arc",
                )
        elif arc_items:
            self.canvas.delete("progress_arc")

    def _update_display(self):
        total = self.modes[self.current_mode]["duration"]
        remaining = self.time_left
        progress = 1 - (remaining / total) if total > 0 else 0

        mins = int(remaining // 60)
        secs = int(remaining % 60)
        time_str = f"{mins:02d}:{secs:02d}"

        self.canvas.itemconfig(self.timer_text_id, text=time_str)
        self._draw_progress(progress)

        # Update window title
        if self.is_running:
            self.root.title(f"{time_str} - 番茄钟")
        else:
            self.root.title("番茄钟 - Pomodoro Timer")

    def _update_stats(self):
        self.lbl_stats.config(text=f"✅ {self.completed_pomodoros}")
        self.lbl_today_count.config(text=f"{self.completed_pomodoros} 个番茄")

    # ── Mode Switching ─────────────────────────────────────────────
    def _cancel_timer(self):
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None

    def switch_mode(self, mode_key):
        if self.is_running and mode_key != self.current_mode:
            return  # Don't switch while running

        self.current_mode = mode_key
        mode = self.modes[mode_key]
        self.time_left = mode["duration"]

        self._cancel_timer()
        self.is_running = False

        # Update tab button styles
        for key, btn in self.tab_btns.items():
            m = self.modes[key]
            btn.config(bg=COLORS["card"] if key != mode_key else m["color"])

        # Update button
        self.btn_start.config(text="▶ 开始", bg=mode["color"])
        self.canvas.itemconfig(self.status_text_id, text="点击开始")

        self._update_display()

    # ── Timer Control ──────────────────────────────────────────────
    def toggle_start(self):
        if self.is_running:
            self._pause()
        else:
            self._start()

    def _start(self):
        if self.time_left <= 0:
            return
        self.is_running = True
        mode = self.modes[self.current_mode]
        self.btn_start.config(text="⏸ 暂停", bg=mode["color"])
        self.canvas.itemconfig(self.status_text_id, text="专注中..." if self.modes[self.current_mode]["type"] == "work" else "休息中...")
        self._tick()

    def _pause(self):
        self.is_running = False
        self._cancel_timer()
        mode = self.modes[self.current_mode]
        self.btn_start.config(text="▶ 继续", bg=mode["color"])
        self.canvas.itemconfig(self.status_text_id, text="已暂停")

    def reset(self):
        self._cancel_timer()
        self.is_running = False
        self.time_left = self.modes[self.current_mode]["duration"]
        mode = self.modes[self.current_mode]
        self.btn_start.config(text="▶ 开始", bg=mode["color"])
        self.canvas.itemconfig(self.status_text_id, text="点击开始")
        self._update_display()

    def _tick(self):
        if not self.is_running:
            return

        self.time_left -= 1
        self._update_display()

        if self.time_left <= 0:
            self._on_complete()
            return

        self.timer_job = self.root.after(1000, self._tick)

    def _on_complete(self):
        self.is_running = False
        mode = self.modes[self.current_mode]

        # Play sound in a separate thread
        threading.Thread(target=self._play_sound, daemon=True).start()

        # Show notification via a top-level window
        self._show_completion_popup(mode["label"])

        if self.modes[self.current_mode]["type"] == "work":
            self.completed_pomodoros += 1
            self._add_log_entry("专注完成", mode["duration"] // 60)
            self._update_stats()
            self._save_settings()

            # Determine next mode
            if self.completed_pomodoros % LONG_BREAK_INTERVAL == 0:
                next_mode = "long_break"
            else:
                next_mode = "short_break"
        else:
            next_mode = "pomodoro"

        mode = self.modes[next_mode]
        self.time_left = mode["duration"]

        # Auto-start or wait
        if self.auto_start.get():
            self.switch_mode(next_mode)
            self._start()
        else:
            self.switch_mode(next_mode)

    # ── Notifications ──────────────────────────────────────────────
    def _play_sound(self):
        """Beep to alert user."""
        for _ in range(3):
            try:
                winsound.Beep(880, 300)
                time.sleep(0.25)
            except Exception:
                pass

    def _show_completion_popup(self, label):
        """Show a popup notification window."""
        popup = tk.Toplevel(self.root)
        popup.title("⏰ 时间到！")
        popup.configure(bg=COLORS["bg"])
        popup.resizable(False, False)

        self._center_toplevel(popup, 320, 160)

        popup.transient(self.root)
        popup.grab_set()

        frame = tk.Frame(popup, bg=COLORS["bg"], padx=24, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text="🔔",
            font=("Segoe UI", 32),
            bg=COLORS["bg"],
        ).pack(pady=(0, 8))

        tk.Label(
            frame,
            text=f"{label} 时间到！",
            font=FONT_BOLD,
            bg=COLORS["bg"],
            fg=COLORS["text_bright"],
        ).pack()

        color = self.modes[self.current_mode]["color"]
        tk.Button(
            frame,
            text="知道了",
            font=FONT_BOLD,
            bg=color,
            fg=COLORS["text_bright"],
            bd=0,
            padx=24,
            pady=6,
            cursor="hand2",
            activebackground=color,
            command=popup.destroy,
        ).pack(pady=(12, 0))

        # Auto-close after 5 seconds
        popup.after(5000, lambda: popup.destroy() if popup.winfo_exists() else None)

        popup.focus_set()
        popup.bind("<Return>", lambda e: popup.destroy())
        popup.bind("<Escape>", lambda e: popup.destroy())

    # ── Session Log ────────────────────────────────────────────────
    def _log_path(self):
        return os.path.join(self._base_dir, "pomodoro_log.json")

    def _load_today_log(self):
        self.log_listbox.delete(0, tk.END)
        today = datetime.now().strftime("%Y-%m-%d")
        data = self._read_json(self._log_path())
        for entry in data.get(today, []):
            self.log_listbox.insert(tk.END, entry)

    def _add_log_entry(self, label, minutes):
        now = datetime.now().strftime("%H:%M")
        entry = f"{now}  {label} ({minutes}分钟)"

        self.log_listbox.insert(0, entry)
        # Keep max 50 entries in view
        while self.log_listbox.size() > 50:
            self.log_listbox.delete(tk.END)

        # Persist
        today = datetime.now().strftime("%Y-%m-%d")
        data = self._read_json(self._log_path())

        if today not in data:
            data[today] = []
        data[today].insert(0, entry)
        # Keep max 100 per day
        data[today] = data[today][:100]

        try:
            with open(self._log_path(), "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── Settings Dialog ────────────────────────────────────────────
    def _show_settings(self):
        """Show settings dialog to customize timer durations."""
        dialog = tk.Toplevel(self.root)
        dialog.title("设置")
        dialog.configure(bg=COLORS["bg"])
        dialog.resizable(False, False)

        self._center_toplevel(dialog, 320, 260)

        dialog.transient(self.root)
        dialog.grab_set()

        frame = tk.Frame(dialog, bg=COLORS["bg"], padx=20, pady=16)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text="⏱ 计时设置",
            font=FONT_BOLD,
            bg=COLORS["bg"],
            fg=COLORS["text_bright"],
        ).pack(anchor="w", pady=(0, 12))

        settings_labels = {
            "pomodoro": "专注时间 (分钟)",
            "short_break": "短休息 (分钟)",
            "long_break": "长休息 (分钟)",
        }
        fields = [(settings_labels[key], key) for key in self.modes]

        entries = {}
        for label, key in fields:
            row = tk.Frame(frame, bg=COLORS["bg"])
            row.pack(fill="x", pady=4)

            tk.Label(
                row,
                text=label,
                font=FONT_SMALL,
                bg=COLORS["bg"],
                fg=COLORS["text"],
                width=14,
                anchor="w",
            ).pack(side="left")

            var = tk.StringVar(value=str(self.modes[key]["duration"] // 60))
            entry = tk.Entry(
                row,
                textvariable=var,
                font=FONT,
                bg=COLORS["card"],
                fg=COLORS["text"],
                bd=0,
                insertbackground=COLORS["text"],
                width=6,
                justify="center",
            )
            entry.pack(side="left", padx=(0, 4))
            entries[key] = var

        # Buttons
        btn_frame = tk.Frame(frame, bg=COLORS["bg"])
        btn_frame.pack(fill="x", pady=(16, 0))

        def save():
            try:
                for key, var in entries.items():
                    val = int(var.get())
                    if val < 1 or val > 120:
                        raise ValueError
                    self.modes[key]["duration"] = val * 60

                if self.current_mode in self.modes:
                    self.time_left = self.modes[self.current_mode]["duration"]
                    self._update_display()

                self._save_settings()
                dialog.destroy()
                messagebox.showinfo("提示", "设置已保存！", parent=self.root)
            except ValueError:
                messagebox.showerror("错误", "请输入 1-120 之间的整数", parent=dialog)

        tk.Button(
            btn_frame,
            text="保存",
            font=FONT_BOLD,
            bg=COLORS["primary"],
            fg=COLORS["text_bright"],
            bd=0,
            padx=20,
            pady=6,
            cursor="hand2",
            activebackground=COLORS["primary_hover"],
            command=save,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame,
            text="取消",
            font=FONT_BOLD,
            bg=COLORS["card"],
            fg=COLORS["text"],
            bd=0,
            padx=20,
            pady=6,
            cursor="hand2",
            activebackground=COLORS["card_alt"],
            command=dialog.destroy,
        ).pack(side="left")

        dialog.focus_set()
        dialog.bind("<Escape>", lambda e: dialog.destroy())


if __name__ == "__main__":
    PomodoroApp()
