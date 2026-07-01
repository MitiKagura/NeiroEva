#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, GLib, Gdk, PangoCairo
import cairo
import math
import subprocess
import os
import sys
import signal
import random
import threading
import queue
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path.home() / "NeiroEva"
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

MAX_LOG_LINES = 250

class EvaLauncher(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="🐱 НейроЕва — Стартер")
        self.set_default_size(950, 750)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)
        self.set_decorated(True)
        self.process = None
        self.angle = 0
        self.pulse = 0
        self.animation_running = True
        self.models = []
        self.selected_model_index = 0
        self.log_queue = queue.Queue()
        self.log_lines = []
        self.log_file_path = None

        # --- Загружаем картинку Евы через Cairo ---
        self.eva_surface = None
        eva_path = os.path.join(os.path.dirname(__file__), "eva_stand.png")
        print(f"🔍 Ищем файл: {eva_path}")
        if os.path.exists(eva_path):
            try:
                self.eva_surface = cairo.ImageSurface.create_from_png(eva_path)
                print(f"✅ Ева загружена! Размер: {self.eva_surface.get_width()}x{self.eva_surface.get_height()}")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки Евы через Cairo: {e}")
        else:
            print(f"⚠️ Файл {eva_path} не найден, Ева не загружена")

        self.particles = []
        for _ in range(50):
            self.particles.append({
                'x': random.uniform(0.0, 1.0),
                'y': random.uniform(0.0, 1.0),
                'dx': random.uniform(-0.003, 0.003),
                'dy': random.uniform(-0.003, 0.003),
                'size': random.uniform(1.0, 2.8),
                'brightness': random.uniform(0.3, 1.0),
                'phase': random.uniform(0, 2 * math.pi)
            })

        self.load_css()
        self.build_ui()
        GLib.timeout_add(30, self.on_animate)
        GLib.timeout_add(100, self.update_log_display)

    def load_css(self):
        css_path = os.path.join(os.path.dirname(__file__), "eva_style.css")
        if os.path.exists(css_path):
            with open(css_path, 'r') as f:
                css = f.read()
            provider = Gtk.CssProvider()
            provider.load_from_data(css.encode('utf-8'))
            screen = Gdk.Screen.get_default()
            Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def build_ui(self):
        overlay = Gtk.Overlay()
        self.add(overlay)

        self.bg_area = Gtk.DrawingArea()
        self.bg_area.set_size_request(950, 750)
        self.bg_area.connect("draw", self.on_draw_background)
        overlay.add(self.bg_area)

        # --- Основной интерфейс (сдвинут влево) ---
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(15)
        main_box.set_margin_bottom(15)
        main_box.set_margin_start(30)
        main_box.set_margin_end(280)
        main_box.set_halign(Gtk.Align.START)
        main_box.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(main_box)

        title = Gtk.Label()
        title.set_markup("<span font='28' weight='bold' color='#f8bbd0'>🐱 НейроЕва</span>")
        title.set_margin_bottom(5)
        main_box.pack_start(title, False, False, 0)

        subtitle = Gtk.Label()
        subtitle.set_markup("<span font='14' color='#ce93d8'>✨ твой волшебный компаньон</span>")
        subtitle.set_margin_bottom(15)
        main_box.pack_start(subtitle, False, False, 0)

        # === ВЕРХНИЙ БЛОК ===
        frame = Gtk.Frame()
        frame.set_name("glow-frame")
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        main_box.pack_start(frame, False, False, 0)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_margin_top(15)
        content_box.set_margin_bottom(15)
        content_box.set_margin_start(20)
        content_box.set_margin_end(20)
        frame.add(content_box)

        # Режим
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        mode_box.set_halign(Gtk.Align.CENTER)
        content_box.pack_start(mode_box, False, False, 0)
        self.radio_local = Gtk.RadioButton.new_with_label_from_widget(None, "🚀 Локально")
        self.radio_colab = Gtk.RadioButton.new_with_label_from_widget(self.radio_local, "☁️ Colab")
        self.radio_local.set_active(True)
        self.radio_local.connect("toggled", self.on_mode_toggled)
        self.radio_colab.connect("toggled", self.on_mode_toggled)
        mode_box.pack_start(self.radio_local, False, False, 0)
        mode_box.pack_start(self.radio_colab, False, False, 0)

        # Kitty
        self.kitty_check = Gtk.CheckButton(label="📟 Логи в Kitty (tail -f)")
        self.kitty_check.set_active(False)
        self.kitty_check.set_name("kitty-check")
        content_box.pack_start(self.kitty_check, False, False, 0)

        # Кнопки
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(5)
        content_box.pack_start(btn_box, False, False, 0)
        self.start_btn = Gtk.Button(label="▶ Запустить")
        self.start_btn.set_name("start-btn")
        self.start_btn.connect("clicked", self.on_start)
        btn_box.pack_start(self.start_btn, False, False, 0)
        self.stop_btn = Gtk.Button(label="⏹ Стоп")
        self.stop_btn.set_name("stop-btn")
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", self.on_stop)
        btn_box.pack_start(self.stop_btn, False, False, 0)
        self.exit_btn = Gtk.Button(label="✕ Выход")
        self.exit_btn.set_name("exit-btn")
        self.exit_btn.connect("clicked", Gtk.main_quit)
        btn_box.pack_start(self.exit_btn, False, False, 0)

        # Модель
        model_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        model_box.set_halign(Gtk.Align.CENTER)
        content_box.pack_start(model_box, False, False, 0)

        model_label = Gtk.Label(label="Модель:")
        model_label.set_name("model-label")
        model_box.pack_start(model_label, False, False, 0)

        self.dropdown_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.dropdown_box.set_name("model-dropdown")
        model_box.pack_start(self.dropdown_box, False, False, 0)

        self.model_display = Gtk.Label()
        self.model_display.set_name("model-display")
        self.model_display.set_halign(Gtk.Align.START)
        self.model_display.set_margin_start(8)
        self.model_display.set_margin_end(8)
        self.model_display.set_margin_top(4)
        self.model_display.set_margin_bottom(4)
        self.dropdown_box.pack_start(self.model_display, True, True, 0)

        self.dropdown_btn = Gtk.Button(label="▼")
        self.dropdown_btn.set_name("dropdown-arrow")
        self.dropdown_btn.connect("clicked", self.on_dropdown_clicked)
        self.dropdown_box.pack_start(self.dropdown_btn, False, False, 0)

        self.popover = Gtk.Popover.new(self.dropdown_box)
        self.popover.set_position(Gtk.PositionType.BOTTOM)
        self.popover.set_border_width(0)
        self.popover.set_size_request(250, -1)

        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        popover_box.set_name("popover-box")
        popover_box.set_size_request(250, -1)
        self.popover.add(popover_box)

        self.model_list_store = Gtk.ListStore(str)
        self.model_tree_view = Gtk.TreeView(model=self.model_list_store)
        self.model_tree_view.set_name("model-treeview")
        self.model_tree_view.set_headers_visible(False)
        self.model_tree_view.set_enable_search(True)

        renderer = Gtk.CellRendererText()
        renderer.set_property("foreground", "white")
        renderer.set_property("xpad", 6)
        renderer.set_property("ypad", 6)
        column = Gtk.TreeViewColumn("Модель", renderer, text=0)
        self.model_tree_view.append_column(column)

        self.load_models()
        selection = self.model_tree_view.get_selection()
        selection.connect("changed", self.on_model_selected)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(150)
        scrolled.add(self.model_tree_view)
        popover_box.pack_start(scrolled, True, True, 0)

        self.refresh_model_list()
        self.set_selected_model(0)

        # Модель всегда доступна (LLM локальный)
        self.set_model_sensitive(True)

        # Статус
        self.status_label = Gtk.Label()
        self.status_label.set_markup("<span color='#b0bec5'>⏸ Остановлен</span>")
        self.status_label.set_margin_top(5)
        content_box.pack_start(self.status_label, False, False, 0)

        # === НИЖНИЙ БЛОК — ЛОГИ ===
        log_frame = Gtk.Frame()
        log_frame.set_name("log-frame")
        log_frame.set_shadow_type(Gtk.ShadowType.NONE)
        log_frame.set_label("📋 Логи")
        main_box.pack_start(log_frame, True, True, 0)

        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_scroll.set_min_content_height(200)
        log_scroll.set_max_content_height(350)
        log_scroll.set_name("log-scroll")
        log_frame.add(log_scroll)

        self.log_textview = Gtk.TextView()
        self.log_textview.set_name("log-textview")
        self.log_textview.set_editable(False)
        self.log_textview.set_cursor_visible(False)
        self.log_textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_textview.set_monospace(True)
        log_scroll.add(self.log_textview)

        footer = Gtk.Label()
        footer.set_markup("<span font='10' color='#9575cd'>🐾 сделано с любовью для Миши</span>")
        footer.set_margin_top(10)
        main_box.pack_start(footer, False, False, 0)

        self.connect("destroy", self.on_destroy)

    def set_model_sensitive(self, sensitive):
        self.dropdown_box.set_sensitive(sensitive)
        self.dropdown_btn.set_sensitive(sensitive)

    def on_mode_toggled(self, widget):
        # Модель всегда доступна (LLM локальный)
        if self.process is None:
            self.set_model_sensitive(True)
        else:
            self.set_model_sensitive(False)

    def load_models(self):
        self.models = ["qwen2.5-7b-instruct-q4_k_m.gguf"]
        if MODELS_DIR.exists():
            for f in MODELS_DIR.glob("*.gguf"):
                if f.name not in self.models:
                    self.models.append(f.name)

    def refresh_model_list(self):
        self.model_list_store.clear()
        for m in self.models:
            self.model_list_store.append([m])

    def set_selected_model(self, index):
        if 0 <= index < len(self.models):
            self.selected_model_index = index
            self.model_display.set_text(self.models[index])

    def on_model_selected(self, selection):
        model, treeiter = selection.get_selected()
        if treeiter is not None:
            path = model.get_path(treeiter)
            index = path.get_indices()[0]
            self.set_selected_model(index)
            self.popover.popdown()

    def on_dropdown_clicked(self, widget):
        self.popover.show_all()
        self.popover.popup()

    def on_draw_background(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()

        grad = cairo.RadialGradient(w/2, h/2, 50, w/2, h/2, 350)
        grad.add_color_stop_rgb(0.0, 0.15, 0.08, 0.25)
        grad.add_color_stop_rgb(0.5, 0.10, 0.05, 0.18)
        grad.add_color_stop_rgb(1.0, 0.05, 0.02, 0.08)
        cr.set_source(grad)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        cx = w/2 + 180 * math.sin(self.angle * 0.5)
        cy = h/2 + 120 * math.cos(self.angle * 0.7)
        radius = 220 + 70 * math.sin(self.pulse * 1.2)

        glow = cairo.RadialGradient(cx, cy, 30, cx, cy, radius)
        glow.add_color_stop_rgba(0.0, 0.9, 0.2, 0.6, 0.35 * (0.7 + 0.3 * math.sin(self.pulse * 0.7)))
        glow.add_color_stop_rgba(0.5, 0.7, 0.1, 0.8, 0.2 * (0.7 + 0.3 * math.cos(self.pulse * 0.5 + 1.2)))
        glow.add_color_stop_rgba(1.0, 0.2, 0.0, 0.4, 0.0)
        cr.set_source(glow)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        cx2 = w/2 - 150 * math.cos(self.angle * 0.6 + 0.8)
        cy2 = h/2 + 90 * math.sin(self.angle * 0.8 + 1.5)
        glow2 = cairo.RadialGradient(cx2, cy2, 20, cx2, cy2, 200)
        glow2.add_color_stop_rgba(0.0, 0.3, 0.1, 0.9, 0.3 * (0.6 + 0.4 * math.sin(self.pulse * 0.6 + 0.5)))
        glow2.add_color_stop_rgba(0.6, 0.5, 0.0, 0.8, 0.15 * (0.7 + 0.3 * math.cos(self.pulse * 0.4 + 2.0)))
        glow2.add_color_stop_rgba(1.0, 0.1, 0.0, 0.3, 0.0)
        cr.set_source(glow2)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        for p in self.particles:
            sx = p['x'] * w
            sy = p['y'] * h
            brightness = p['brightness'] * (0.5 + 0.5 * math.sin(self.pulse * 1.5 + p['phase']))
            cr.set_source_rgba(0.9, 0.6, 1.0, 0.5 * brightness)
            cr.arc(sx, sy, p['size'] * (0.3 + 0.7 * brightness), 0, 2 * math.pi)
            cr.fill()

        # --- Рисуем Еву ---
        if self.eva_surface is not None:
            try:
                sw = self.eva_surface.get_width()
                sh = self.eva_surface.get_height()
                target_height = 670
                scale = target_height / sh
                target_width = sw * scale
                x = w - target_width - 20
                y = (h - target_height) / 2

                cr.save()
                cr.translate(x, y)
                cr.scale(scale, scale)
                cr.set_source_surface(self.eva_surface, 0, 0)
                cr.paint()
                cr.restore()
            except Exception as e:
                print(f"⚠️ Ошибка отрисовки Евы: {e}")

    def on_animate(self):
        if not self.animation_running:
            return False
        self.angle += 0.035
        self.pulse += 0.025

        for p in self.particles:
            p['x'] += p['dx']
            p['y'] += p['dy']
            if p['x'] < 0 or p['x'] > 1:
                p['dx'] = -p['dx']
                p['x'] = max(0.0, min(1.0, p['x']))
            if p['y'] < 0 or p['y'] > 1:
                p['dy'] = -p['dy']
                p['y'] = max(0.0, min(1.0, p['y']))

        self.bg_area.queue_draw()
        return True

    def update_log_display(self):
        while not self.log_queue.empty():
            line = self.log_queue.get_nowait()
            self.log_lines.append(line)
            if len(self.log_lines) > MAX_LOG_LINES:
                self.log_lines = self.log_lines[-MAX_LOG_LINES:]

        text = "\n".join(self.log_lines)
        self.log_textview.get_buffer().set_text(text)

        adj = self.log_textview.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())
        return True

    def read_process_output(self, process, log_file):
        while True:
            line = process.stdout.readline()
            if not line:
                break
            if log_file:
                log_file.write(line)
                log_file.flush()
            self.log_queue.put(line.strip())
        process.stdout.close()
        self.log_queue.put("--- Процесс завершён ---")

    def get_selected_model(self):
        return self.models[self.selected_model_index] if self.models else ""

    def on_start(self, widget):
        if self.process:
            return

        mode = "local" if self.radio_local.get_active() else "colab"
        model_path = self.get_selected_model()

        if not model_path:
            self.status_label.set_markup("<span color='#ef9a9a'>⚠️ Выберите модель!</span>")
            return

        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self.status_label.set_markup("<span color='#ffcc80'>🔄 Запуск...</span>")
        self.set_model_sensitive(False)

        script = "main_local.py" if mode == "local" else "main.py"
        script_path = BASE_DIR / script
        if not script_path.exists():
            self.status_label.set_markup(f"<span color='#ef9a9a'>❌ {script} не найден</span>")
            self.start_btn.set_sensitive(True)
            self.stop_btn.set_sensitive(False)
            self.set_model_sensitive(True)
            return

        python_path = BASE_DIR / "evavenv" / "bin" / "python3"
        cmd = [str(python_path), str(script_path)]
        if model_path:
            full_model_path = str(MODELS_DIR / model_path)
            cmd.extend(["--model", full_model_path])
            self.log_queue.put(f"📦 Модель: {full_model_path}")

        env = os.environ.copy()
        env["http_proxy"] = "http://127.0.0.1:10809"
        env["https_proxy"] = "http://127.0.0.1:10809"

        if mode == "colab":
            env["USE_COLAB"] = "true"
            colab_url = os.getenv("COLAB_URL")
            if not colab_url:
                colab_url = "https://your-ngrok.ngrok-free.dev"  # заглушка
            env["COLAB_URL"] = colab_url
            self.log_queue.put(f"☁️ Режим Colab, URL: {colab_url}")
        else:
            env["USE_COLAB"] = "false"
            if "COLAB_URL" in env:
                del env["COLAB_URL"]
            self.log_queue.put(f"🚀 Режим Local, модель: {model_path}")

        self.log_queue.put(f"📋 Команда: {' '.join(cmd)}")

        log_filename = f"launcher_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.log_file_path = LOGS_DIR / log_filename
        log_file = open(self.log_file_path, 'w', encoding='utf-8')
        log_file.write(f"=== Запуск {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        log_file.write(f"Команда: {' '.join(cmd)}\n")
        log_file.write(f"Окружение: { {k:v for k,v in env.items() if k in ['USE_COLAB','COLAB_URL','http_proxy','https_proxy']} }\n")
        log_file.flush()

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid
        )

        thread = threading.Thread(target=self.read_process_output, args=(self.process, log_file), daemon=True)
        thread.start()

        if self.kitty_check.get_active():
            try:
                subprocess.Popen(
                    ["kitty", "--title", "NeuroEva Logs (tail)", "--hold",
                     "sh", "-c", f"tail -f {self.log_file_path}"],
                    preexec_fn=os.setsid
                )
                self.log_queue.put("📟 Kitty с логами открыт (tail -f)")
            except FileNotFoundError:
                self.log_queue.put("⚠️ Kitty не установлен, логи только в лаунчере")
        else:
            self.log_queue.put("📟 Kitty отключён, логи только в лаунчере")

        self.status_label.set_markup("<span color='#a5d6a7'>▶️ Ева запущена</span>")
        GLib.timeout_add_seconds(1, self.check_process)

    def check_process(self):
        if self.process and self.process.poll() is not None:
            self.status_label.set_markup("<span color='#ef9a9a'>⏹ Остановлен</span>")
            self.start_btn.set_sensitive(True)
            self.stop_btn.set_sensitive(False)
            self.process = None
            if self.radio_local.get_active():
                self.set_model_sensitive(True)
            self.log_queue.put("--- Процесс завершён ---")
            return False
        return True

    def on_stop(self, widget):
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except:
                pass
            self.process = None
            self.status_label.set_markup("<span color='#ef9a9a'>⏹ Остановлен</span>")
            self.start_btn.set_sensitive(True)
            self.stop_btn.set_sensitive(False)
            if self.radio_local.get_active():
                self.set_model_sensitive(True)
            self.log_queue.put("--- Остановлено пользователем ---")

    def on_destroy(self, widget):
        self.animation_running = False
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except:
                pass
        Gtk.main_quit()

def main():
    win = EvaLauncher()
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
