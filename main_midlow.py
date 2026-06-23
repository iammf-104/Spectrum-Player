from window_chrome import (
    apply_tk_dpi_scaling,
    enable_windows_dpi_awareness,
    scaled_minsize,
    scaled_window_geometry,
    schedule_cursor_dark_titlebar,
    schedule_allow_drop,
)

enable_windows_dpi_awareness()

import tkinter as tk
from tkinter import filedialog
import threading
import queue
from collections import deque
import numpy as np
import time
import os
import sounddevice as sd
import soundfile as sf

from playlist_store import PlaylistStore, find_file_by_name
from playlist_ui import PlaylistWindow


class SpectrumPlayer:
    def __init__(self, master):
        self.master = master
        self.master.title("Python Spectrum Player (Mid-Low Focus)")
        self.filename = None
        self.q = queue.Queue()
        self.wave_q = queue.Queue(maxsize=24)
        self._main_calls = queue.Queue()
        self.playing = False
        self.paused = False
        self.mic_active = False
        self._mic_id = 0
        self._mic_thread_handle = None
        self._playback_ending = False
        self._playback_abort = False
        self._playback_thread = None
        self._playback_id = 0
        self._handoff_until = 0.0
        self._click_after_id = None
        # smoothing parameters for visual transitions (default)
        self.smooth_alpha = 0.6
        self.smoothed_vals = None
        self.num_bars = 160  # number of visual bars
        self.bass_bias = 2.5  # >1 allocates more bars to low/mid bands
        self.gain = 0.8  # global visual gain (multiplier applied to normalized values)
        self.mid_high_gain = 1.28  # extra lift for mid-high spectrum bars
        self.max_bar_frac = 0.40     # max bar height as fraction of canvas
        self.running_peak_low = 1e-6
        self.running_peak_hi = 1e-6
        # mid-low band boundaries (Hz) — legacy attrs kept for slider side-effects
        self.f_sub_high = 70.0
        self.f_kick_high = 190.0
        self.f_punch_high = 900.0
        self.f_mid_high = 4000.0
        self.f_kick_ref = 60.0     # typical kick fundamental (Hz)
        self.kick_position = 1.0 / 8.0  # kick anchor on canvas (0..1)
        self.low_span_end = 0.30       # bass / kick region
        self.mid_log_end = 0.60        # piano + vocal mid, log-spaced (~340–3000 Hz)
        self.f_mid_lo = 340.0
        self.f_mid_log_top = 3000.0
        # running peak for adaptive normalization to keep heights visible
        self.running_peak = 1e-6
        self.peak_decay = 0.995
        self.peak_decay_low = 0.988  # low band peak falls faster -> stronger dynamics
        self.drum_f_lo = 20.0
        self.drum_f_hi = 200.0
        self.f_sub_rumble_hi = 20.0   # sub-bass rumble band top (Hz)
        self.f_sub_blend_hi = 48.0    # smooth roundness blend into kick band
        self.drum_compress_thresh = 0.48
        self.drum_compress_ratio = 2.2
        self.mid_high_compress_thresh = 0.40
        self.mid_high_compress_ratio = 4.0

        self.on_smooth_change(self.smooth_alpha)

        self.canvas_w = 800
        self.canvas_h = 300
        self.canvas = tk.Canvas(
            master, width=self.canvas_w, height=self.canvas_h,
            bg='black', highlightthickness=0, cursor='hand2')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        master.update_idletasks()
        self.canvas_w = max(100, self.canvas.winfo_width())
        self.canvas_h = max(100, self.canvas.winfo_height())
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        self.canvas.bind('<Button-1>', self._on_canvas_click)
        self.canvas.bind('<Button-3>', self._on_canvas_right_click)

        self.playlist_store = PlaylistStore()
        self.playlist_ui = PlaylistWindow(master, self)

        self.smoothed_vals = None
        self._disp_ema = None
        self.wave_blocksize = 2048
        self.wave_trail_len = 3
        self.wave_trail_colors = ("#3697FF", "#5D2323", "#311A48")  # 宝蓝, 红, 紫
        self.wave_hop = 512
        self._wave_trail = deque(maxlen=self.wave_trail_len)
        self._wave_decay_active = False
        self._wave_accept_input = True
        self._wave_decay_factor = 0.88
        self.visual_ms = 1

        self.master.after(self.visual_ms, self.update_visual)
        self.master.after(100, self.start_mic)
        self._setup_drag_drop()
        schedule_allow_drop(self.master)
        schedule_cursor_dark_titlebar(
            self.master,
            caption='#141414',
            text='#CCCCCC',
            border='#2A2A2A',
        )

    def _norm_path(self, path):
        if not path:
            return ''
        return os.path.normcase(os.path.normpath(path))

    def _track_for_filename(self):
        """Return metadata for self.filename; sync track_index when path differs."""
        if not self.filename:
            return None
        pl = self.playlist_store.get_active_playlist()
        if not pl:
            return {'title': os.path.basename(self.filename), 'artist': '', 'path': self.filename}
        want = self._norm_path(self.filename)
        idx = self.playlist_store.get_track_index()
        track = self.playlist_store.track_at(pl['id'], idx)
        if track and self._norm_path(track.get('path')) == want:
            return track
        for i, t in enumerate(pl.get('tracks', [])):
            if self._norm_path(t.get('path')) == want:
                if i != idx:
                    self.playlist_store.set_track_index(i)
                return t
        return track or {'title': os.path.basename(self.filename), 'artist': '', 'path': self.filename}

    _AUDIO_EXTS = {'.wav', '.flac', '.ogg', '.mp3', '.m4a', '.aac', '.wma', '.opus'}

    def _setup_drag_drop(self):
        def _on_drop_files(raw_paths):
            paths = []
            for raw in raw_paths:
                if isinstance(raw, bytes):
                    for enc in ('utf-8', 'gbk', 'mbcs'):
                        try:
                            paths.append(raw.decode(enc))
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        paths.append(raw.decode('utf-8', errors='ignore'))
                else:
                    paths.append(str(raw))
            self._run_on_main(lambda: self._on_files_dropped(paths))

        try:
            import windnd
            windnd.hook_dropfiles(self.master, func=_on_drop_files)
            windnd.hook_dropfiles(self.canvas, func=_on_drop_files)
        except Exception as e:
            print('Drag-drop unavailable (pip install windnd):', e)

    def _on_files_dropped(self, paths):
        files = []
        for p in paths:
            p = p.strip().strip('"').strip("'")
            if not p:
                continue
            ext = os.path.splitext(p)[1].lower()
            if ext in self._AUDIO_EXTS and os.path.isfile(p):
                files.append(p)
        if not files:
            return
        result = self.playlist_store.import_dropped_files(files)
        n = len(result.get('added', []))
        if n <= 0:
            return
        if self.playlist_ui.win is not None and self.playlist_ui.win.winfo_exists():
            self.playlist_ui.refresh()
        albums = result.get('albums') or []
        artists = result.get('artists') or []
        hint = f'已导入 {n} 首'
        if albums:
            hint += f' · {len(albums)} 张专辑'
        if artists:
            hint += f' · {len(artists)} 位歌手'
        self.master.title(hint)
        self.master.after(2500, self._restore_title_after_drop)

    def _restore_title_after_drop(self):
        if self.playing or self.filename:
            track = self._track_for_filename()
            if track:
                self._update_window_title(track)
                return
        self.master.title('Python Spectrum Player (Mid-Low Focus)')

    def _build_freq_edges(self, N, freqs):
        """Log-spaced piano/vocal mid; avoids linear cramming from 380 Hz upward."""
        f_high_c = min(20000.0, freqs[-1])
        p_kick = float(self.kick_position)
        p_low_end = float(self.low_span_end)
        p_mid_end = float(getattr(self, 'mid_log_end', 0.60))
        f_kick = float(self.f_kick_ref)
        f_floor = 0.0
        f_log_min = max(1.0, float(freqs[1]) if len(freqs) > 1 else 1.0)
        f_low_top = float(getattr(self, 'f_mid_lo', 340.0))
        f_mid_top = float(getattr(self, 'f_mid_log_top', 3000.0))

        def pos_to_freq(p):
            if p <= p_kick:
                t = max(0.0, p / p_kick)
                lf0, lf1 = np.log(f_log_min), np.log(f_kick)
                return float(np.exp(lf0 + t * (lf1 - lf0)))
            if p <= p_low_end:
                t = (p - p_kick) / (p_low_end - p_kick)
                lf0, lf1 = np.log(f_kick), np.log(f_low_top)
                return float(np.exp(lf0 + t * (lf1 - lf0)))
            if p <= p_mid_end:
                t = (p - p_low_end) / (p_mid_end - p_low_end)
                lf0, lf1 = np.log(f_low_top), np.log(f_mid_top)
                return float(np.exp(lf0 + t * (lf1 - lf0)))
            if p <= 0.78:
                t = (p - p_mid_end) / (0.78 - p_mid_end)
                lf0, lf1 = np.log(f_mid_top), np.log(min(6500.0, f_high_c))
                return float(np.exp(lf0 + t * (lf1 - lf0)))
            t = (p - 0.78) / 0.22
            return min(6500.0, f_high_c) + t * (f_high_c - min(6500.0, f_high_c))

        positions = np.linspace(0.0, 1.0, N + 1)
        edges_f = np.array([pos_to_freq(p) for p in positions], dtype=float)
        edges_f[0] = f_floor
        edges_f[-1] = f_high_c
        if not np.all(np.diff(edges_f) > 0):
            edges_f = np.linspace(f_floor, f_high_c, N + 1)
        return edges_f

    def _aggregate_bands(self, mag, freqs, edges_f, N):
        """Widen low-band windows and use peak picking so bass lines stay dense."""
        bin_hz = float(freqs[1] - freqs[0]) if len(freqs) > 1 else 10.0
        vals = []
        centers = []
        for i in range(N):
            f_lo = float(edges_f[i])
            f_hi = float(edges_f[i + 1])
            center = 0.5 * (f_lo + f_hi)
            half = max((f_hi - f_lo) * 0.5, bin_hz * 0.75)
            sub_hi = float(getattr(self, 'f_sub_rumble_hi', 20.0))
            blend_hi = float(getattr(self, 'f_sub_blend_hi', 48.0))
            if center < sub_hi:
                half = max(half, 18.0)
            elif center < blend_hi:
                half = max(half, 15.0)
            elif center < 500.0:
                half = max(half, 13.0)
            f_lo = max(freqs[0], center - half)
            f_hi = min(freqs[-1], center + half)
            if i == N - 1:
                idx = (freqs >= f_lo) & (freqs <= f_hi)
            else:
                idx = (freqs >= f_lo) & (freqs < f_hi)
            if not np.any(idx):
                vals.append(0.0)
            elif center < sub_hi:
                vals.append(float(np.mean(mag[idx])))
            elif center < 450.0:
                vals.append(float(np.max(mag[idx])))
            else:
                vals.append(float(np.mean(mag[idx])))
            centers.append(center)
        return np.array(vals, dtype=float), np.array(centers, dtype=float)

    def _band_center_hz(self, i):
        centers = getattr(self, 'band_centers', None)
        if centers is not None and i < len(centers):
            return float(centers[i])
        return None

    def _fill_sparse_bands(self, vals, centers=None):
        out = np.asarray(vals, dtype=float).copy()
        sub_hi = float(getattr(self, 'f_sub_rumble_hi', 20.0))
        for i in range(len(out)):
            if out[i] > 0.0:
                continue
            lo = max(0, i - 2)
            hi = min(len(out), i + 3)
            chunk = out[lo:hi]
            if np.any(chunk > 0.0):
                bleed = 0.79
                if centers is not None and i < len(centers) and float(centers[i]) < sub_hi:
                    bleed = 0.88
                out[i] = float(np.max(chunk)) * bleed
        return out

    def _fold_kick_energy(self, band_vals):
        """Spread sub-kick energy with Gaussian falloff for a natural bell-curve shape."""
        vals = np.asarray(band_vals, dtype=float).copy()
        n = len(vals)
        if n == 0:
            return vals
        kick_bar = int(round(n * float(self.kick_position)))
        kick_bar = max(3, min(n - 4, kick_bar))
        left_peak = float(np.max(vals[:kick_bar + 1])) if kick_bar >= 0 else 0.0
        if left_peak <= 0.0:
            return vals
        spread = max(4, int(round(n * 0.06)))
        sigma = spread * 0.50
        for b in range(kick_bar - spread, kick_bar + spread + 1):
            if 0 <= b < n:
                dist = abs(b - kick_bar)
                # Gaussian falloff → natural bell curve, no flat plateau at edges
                weight = float(np.exp(-0.5 * (dist / max(sigma, 1e-9)) ** 2))
                weight = max(0.10, weight)
                vals[b] = max(vals[b], left_peak * weight)
        rumble_end = max(2, kick_bar // 4)
        vals[:rumble_end] *= 0.65
        return vals

    def _smoothstep(self, t):
        t = max(0.0, min(1.0, float(t)))
        return t * t * (3.0 - 2.0 * t)

    def _smooth_strength(self, i, n):
        """Gradual roundness; extra smooth below 20 Hz with blend into kick band."""
        p = i / max(1, n - 1)
        low_cut = float(self.low_span_end)
        mid_cut = 0.78
        if p <= low_cut:
            base = 0.86
        elif p <= mid_cut:
            t = self._smoothstep((p - low_cut) / max(1e-6, mid_cut - low_cut))
            base = 0.86 - t * 0.28
        else:
            t = self._smoothstep((p - mid_cut) / max(1e-6, 1.0 - mid_cut))
            base = 0.66 - t * 0.19

        fc = self._band_center_hz(i)
        if fc is None:
            return base
        sub_hi = float(getattr(self, 'f_sub_rumble_hi', 20.0))
        blend_hi = float(getattr(self, 'f_sub_blend_hi', 48.0))
        if fc < sub_hi:
            return 0.95
        if fc < blend_hi:
            t = self._smoothstep((fc - sub_hi) / max(1e-6, blend_hi - sub_hi))
            return 0.95 - t * (0.95 - base)
        return base

    def _ema_alpha(self, i, n):
        p = i / max(1, n - 1)
        low_cut = float(self.low_span_end)
        mid_cut = 0.78
        if p <= low_cut:
            base = 0.50
        elif p <= mid_cut:
            t = self._smoothstep((p - low_cut) / max(1e-6, mid_cut - low_cut))
            base = 0.50 - t * 0.09
        else:
            t = self._smoothstep((p - mid_cut) / max(1e-6, 1.0 - mid_cut))
            base = 0.41 - t * 0.05

        fc = self._band_center_hz(i)
        if fc is not None and fc < float(getattr(self, 'f_sub_rumble_hi', 20.0)):
            return min(base, 0.44)
        return base

    def _fill_drum_valleys(self, display_vals, drum_bars):
        """Raise any drum bar that dips below its neighbours to prevent concavities."""
        if len(drum_bars) < 3:
            return display_vals
        vals = display_vals.copy()
        n = len(vals)
        for idx in sorted(drum_bars):
            left  = vals[idx - 1] if idx > 0     else vals[idx]
            right = vals[idx + 1] if idx < n - 1 else vals[idx]
            envelope = (left + right) * 0.5
            if vals[idx] < envelope * 0.82:
                vals[idx] = envelope * 0.82
        return vals

    def _smooth_display(self, vals, N):
        """Single-pass graded smooth so low/mid/high roundness blends seamlessly."""
        src = np.asarray(vals, dtype=float)
        n = len(src)
        if n == 0:
            return src

        light = src.copy()
        for i in range(1, n - 1):
            light[i] = src[i - 1] * 0.19 + src[i] * 0.62 + src[i + 1] * 0.19

        strong = light.copy()
        if n >= 7:
            for i in range(3, n - 3):
                strong[i] = (
                    light[i - 3] * 0.05
                    + light[i - 2] * 0.10
                    + light[i - 1] * 0.175
                    + light[i] * 0.26
                    + light[i + 1] * 0.175
                    + light[i + 2] * 0.10
                    + light[i + 3] * 0.05
                )

        out = src.copy()
        sub_hi = float(getattr(self, 'f_sub_rumble_hi', 20.0))
        blend_hi = float(getattr(self, 'f_sub_blend_hi', 48.0))
        for i in range(n):
            k = self._smooth_strength(i, n)
            fc = self._band_center_hz(i)
            if fc is not None and fc < blend_hi:
                if fc < sub_hi:
                    blend = strong[i] * 0.68 + light[i] * 0.32
                else:
                    t = self._smoothstep((fc - sub_hi) / max(1e-6, blend_hi - sub_hi))
                    sub_blend = strong[i] * 0.68 + light[i] * 0.32
                    blend = sub_blend * (1.0 - t) + strong[i] * t
                out[i] = src[i] * (1.0 - k) + blend * k
            else:
                out[i] = src[i] * (1.0 - k) + strong[i] * k

        if self._disp_ema is None or len(self._disp_ema) != n:
            self._disp_ema = out.copy()
        else:
            for i in range(n):
                a = self._ema_alpha(i, n)
                self._disp_ema[i] = a * out[i] + (1.0 - a) * self._disp_ema[i]
        return self._disp_ema.copy()

    def _wave_amplitude(self):
        # Keep ~20% of canvas height (60px at 300px tall), scale with window size.
        return self.canvas_h * 0.20

    def _wave_line_width(self):
        return 1

    def _seg_to_wave_y(self, seg):
        seg = np.asarray(seg, dtype=float)
        if seg.size == 0:
            return None
        maxabs = max(1e-9, float(np.max(np.abs(seg))))
        norm_seg = seg / maxabs
        cols = int(self.canvas_w)
        idxs = np.round(np.linspace(0, len(norm_seg) - 1, cols)).astype(int)
        idxs = np.clip(idxs, 0, len(norm_seg) - 1)
        y_center = self.canvas_h * 0.5
        wave_h = self._wave_amplitude()
        ys = y_center - norm_seg[idxs].astype(float) * wave_h
        return ys

    def _resample_wave_ys(self, ys, n):
        ys = np.asarray(ys, dtype=float)
        if ys.size == 0 or n <= 0:
            return ys
        if len(ys) == n:
            return ys.copy()
        xs = np.linspace(0.0, 1.0, len(ys))
        xn = np.linspace(0.0, 1.0, n)
        return np.interp(xn, xs, ys)

    def _wave_y_center(self):
        return self.canvas_h * 0.5

    def _drain_wave_queue(self):
        while True:
            try:
                seg = self.wave_q.get_nowait()
            except queue.Empty:
                break
            if not getattr(self, '_wave_accept_input', True):
                continue
            ys = self._seg_to_wave_y(seg)
            if ys is not None:
                self._wave_trail.append(ys)

    def _decay_wave_trail_to_zero(self):
        if not getattr(self, '_wave_decay_active', False):
            return
        center = self._wave_y_center()
        decay = float(getattr(self, '_wave_decay_factor', 0.88))
        if not self._wave_trail:
            self._finish_wave_decay()
            return
        for i in range(len(self._wave_trail)):
            ys = np.asarray(self._wave_trail[i], dtype=float)
            self._wave_trail[i] = center + (ys - center) * decay
        max_dev = 0.0
        for ys in self._wave_trail:
            for y in ys:
                max_dev = max(max_dev, abs(float(y) - center))
        if max_dev < 0.6:
            self._finish_wave_decay()

    def _finish_wave_decay(self):
        self._wave_decay_active = False
        self._wave_trail.clear()
        while True:
            try:
                self.wave_q.get_nowait()
            except queue.Empty:
                break
        self._wave_accept_input = True
        self.master.after(120, self._start_mic_if_idle)

    def _trail_color(self, index, total):
        palette = getattr(self, 'wave_trail_colors', ("#5DAEE0", "#5707078A", "#300A5783"))
        age = total - 1 - index
        if age <= 0:
            return palette[0]
        if age == 1:
            return palette[1]
        return palette[2]

    def _resample_wave_trail_width(self, new_w):
        if new_w <= 0:
            return
        resampled = deque(maxlen=self.wave_trail_len)
        for ys in self._wave_trail:
            resampled.append(self._resample_wave_ys(ys, new_w))
        self._wave_trail = resampled

    def _draw_waveform_trail(self):
        if not self._wave_trail:
            return
        n = len(self._wave_trail)
        width = self._wave_line_width()
        for i, ys in enumerate(self._wave_trail):
            color = self._trail_color(i, n)
            pts = []
            for xi, y in enumerate(ys):
                pts.extend([xi, float(y)])
            try:
                self.canvas.create_line(pts, fill=color, width=width)
            except Exception:
                pass

    def _drum_bar_indices(self, N):
        centers = getattr(self, 'band_centers', None)
        if centers is None or len(centers) != N:
            return set()
        lo = float(getattr(self, 'drum_f_lo', 20.0))
        hi = float(getattr(self, 'drum_f_hi', 200.0))
        return {i for i, fc in enumerate(centers) if lo <= float(fc) <= hi}

    def _sub_rumble_bar_indices(self, N, drum_bars):
        centers = getattr(self, 'band_centers', None)
        if centers is None or len(centers) != N:
            return set()
        sub_hi = float(getattr(self, 'f_sub_rumble_hi', 20.0))
        return {i for i, fc in enumerate(centers) if float(fc) < sub_hi and i not in drum_bars}

    def _soft_compress_height(self, h, max_frac, thresh_frac, ratio, *, drum=False):
        thresh = max_frac * float(thresh_frac)
        ratio = max(1.5, float(ratio))
        if h <= thresh:
            return max(0.0, h)
        headroom = max(max_frac - thresh, 1e-9)
        if drum:
            t = (h - thresh) / max(headroom * ratio, 1e-9)
            return min(max_frac, thresh + headroom * (1.0 - np.exp(-t)))
        return min(max_frac, thresh + (h - thresh) / ratio)

    def _is_mid_high_bar(self, i, N, drum_bars):
        if i in drum_bars:
            return False
        centers = getattr(self, 'band_centers', None)
        if centers is not None and len(centers) == N:
            return float(centers[i]) > float(self.drum_f_hi)
        low_end = max(4, int(round(N * float(self.low_span_end))))
        return i >= low_end

    def _map_bar_height(self, h, gain, max_frac, is_drum, is_mid_high, is_sub_rumble=False):
        raw = float(h) * gain
        if is_sub_rumble:
            return self._soft_compress_height(
                raw, max_frac, 0.52, 2.4, drum=True)
        if is_drum:
            return self._soft_compress_height(
                raw, max_frac, self.drum_compress_thresh, self.drum_compress_ratio, drum=True)
        if is_mid_high:
            return self._soft_compress_height(
                raw, max_frac, self.mid_high_compress_thresh, self.mid_high_compress_ratio)
        return min(max_frac, max(0.0, raw))

    def _bar_color(self, h):
        r = int(255 * h)
        g = int(80 * (1 - abs(h - 0.5) * 2))
        b = int(255 * (1 - h))
        return "#%02x%02x%02x" % (r, max(0, g), b)

    def _draw_bar(self, x0, y0, x1, y1, color, rounded=False, drum=False, sub_rumble=False):
        if y1 <= y0 + 1:
            return
        w = x1 - x0
        h = y1 - y0
        if rounded and w > 3 and h > 5:
            if h <= w * 1.15:
                self.canvas.create_oval(x0, y0, x1, y1, fill=color, outline='')
            else:
                r = w * 0.5
                body_top = y0 + r
                body_bottom = y1 - r
                if body_bottom > body_top:
                    self.canvas.create_rectangle(x0, body_top, x1, body_bottom, fill=color, outline='')
                self.canvas.create_oval(x0, y0, x1, y0 + 2 * r, fill=color, outline='')
                self.canvas.create_oval(x0, y1 - 2 * r, x1, y1, fill=color, outline='')
        else:
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline='')

    def _init_analysis_state(self, samplerate, blocksize=4096, reset_ring=True):
        bs_changed = getattr(self, 'blocksize', None) != blocksize
        sr_changed = getattr(self, 'samplerate', None) != samplerate
        self.blocksize = blocksize
        self.samplerate = samplerate
        if not hasattr(self, '_ring') or bs_changed or sr_changed or reset_ring:
            self.window = np.hanning(blocksize)
            self._ring = np.zeros(blocksize, dtype='float32')
            self._ring_ptr = 0
            self._ring_count = 0
            self._samples_since_last = 0
            self._hop = max(1, blocksize // 4)
            self._wave_since = 0

    def _push_wave_segment(self):
        blocksize = self.blocksize
        wave_n = int(getattr(self, 'wave_blocksize', 512))
        end = self._ring_ptr
        start = (end - wave_n) % blocksize
        if self._ring_count < wave_n:
            return
        if start < end:
            wave_seg = self._ring[start:end].copy()
        else:
            wave_seg = np.concatenate((self._ring[start:], self._ring[:end]))
        try:
            self.wave_q.put_nowait(wave_seg)
        except queue.Full:
            try:
                self.wave_q.get_nowait()
                self.wave_q.put_nowait(wave_seg)
            except Exception:
                pass

    def _feed_mono_samples(self, mono, source='playback'):
        if source == 'mic':
            if not self.mic_active or self._is_actively_playing():
                return
        blocksize = self.blocksize
        wave_n = int(getattr(self, 'wave_blocksize', 512))
        wave_hop = int(getattr(self, 'wave_hop', 512))
        window = self.window
        for s in mono:
            self._ring[self._ring_ptr] = float(s)
            self._ring_ptr = (self._ring_ptr + 1) % blocksize
            if self._ring_count < blocksize:
                self._ring_count += 1
            self._samples_since_last += 1
            self._wave_since += 1
            if self._ring_count >= wave_n and self._wave_since >= wave_hop:
                self._wave_since = 0
                self._push_wave_segment()
        if self._ring_count >= blocksize and self._samples_since_last >= self._hop:
            start = self._ring_ptr % blocksize
            if start == 0:
                segment = self._ring.copy()
            else:
                segment = np.concatenate((self._ring[start:], self._ring[:start]))
            segment = segment * window
            fft = np.abs(np.fft.rfft(segment))
            if len(fft) > 0:
                fft[0] = 0.0
            try:
                self.q.put_nowait(fft)
            except Exception:
                pass
            self._samples_since_last = 0

    def _run_on_main(self, func, delay_ms=0):
        self._main_calls.put((max(0, int(delay_ms)), func))

    def _poll_main_calls(self):
        while True:
            try:
                delay_ms, func = self._main_calls.get_nowait()
            except queue.Empty:
                break
            if delay_ms <= 0:
                try:
                    func()
                except Exception as e:
                    print('UI callback error:', e)
            else:
                self.master.after(delay_ms, func)

    def _start_mic_if_idle(self):
        if self._is_actively_playing() or self.mic_active:
            return
        self.start_mic()

    def start_mic(self):
        if self.mic_active:
            return
        if self._is_actively_playing():
            return
        self._mic_id += 1
        mic_id = self._mic_id
        self.mic_active = True
        self._mic_thread_handle = threading.Thread(
            target=self._mic_thread, args=(mic_id,), daemon=True)
        self._mic_thread_handle.start()

    def stop_mic(self):
        self.mic_active = False
        thread = self._mic_thread_handle
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._mic_thread_handle = None

    def _smooth_switch_to_mic(self):
        self._playback_ending = False
        self._handoff_until = time.time() + 0.55
        self.stop_mic()
        self._wave_accept_input = False
        self._wave_decay_active = True
        while True:
            try:
                self.wave_q.get_nowait()
            except queue.Empty:
                break

    def _mark_playback_ending(self):
        self._playback_ending = True

    def _mic_thread(self, mic_id):
        blocksize = 4096
        try:
            dev = sd.query_devices(kind='input')
            samplerate = int(dev['default_samplerate'])
            self._init_analysis_state(samplerate, blocksize, reset_ring=False)

            def callback(indata, frames, time_info, status):
                if (not self.mic_active
                        or mic_id != self._mic_id
                        or self._is_actively_playing()):
                    raise sd.CallbackStop()
                mono = np.mean(indata, axis=1).astype('float32')
                mono = mono - np.mean(mono)
                self._feed_mono_samples(mono, source='mic')

            with sd.InputStream(
                    samplerate=samplerate, channels=1, dtype='float32',
                    blocksize=blocksize, callback=callback):
                while self.mic_active:
                    sd.sleep(100)
        except Exception as e:
            print('Microphone error:', e)
        finally:
            self.mic_active = False

    def _on_canvas_configure(self, event):
        new_w = max(100, int(event.width))
        new_h = max(100, int(event.height))
        if new_w != self.canvas_w:
            self._resample_wave_trail_width(new_w)
        self.canvas_w = new_w
        self.canvas_h = new_h

    def _on_canvas_click(self, event):
        if self._click_after_id is not None:
            self.master.after_cancel(self._click_after_id)
        self._click_after_id = self.master.after(280, self._handle_canvas_click)

    def _on_canvas_right_click(self, event):
        if self._click_after_id is not None:
            self.master.after_cancel(self._click_after_id)
            self._click_after_id = None
        self.playlist_ui.open()

    def _is_actively_playing(self):
        return self.playing and not self.paused

    def _update_window_title(self, track=None):
        if track is None:
            track = self._track_for_filename()
        if track is None and self.filename:
            track = {'title': os.path.basename(self.filename), 'artist': ''}
        pl = self.playlist_store.get_active_playlist()
        if track and pl:
            idx = self.playlist_store.get_track_index() + 1
            total = len(pl.get('tracks', []))
            title = track.get('title') or os.path.basename(self.filename or '')
            artist = track.get('artist') or ''
            pl_name = pl.get('name', '')
            head = f'{title} — {artist}' if artist else title
            self.master.title(f'{head}  [{idx}/{total} · {pl_name}]')
        elif self.filename:
            self.master.title(f'Mid-Low Spectrum - {self.filename}')
        else:
            self.master.title('Python Spectrum Player (Mid-Low Focus)')

    def _resolve_playback_track(self):
        pl = self.playlist_store.get_active_playlist()
        if not pl or not pl.get('tracks'):
            return False
        idx = self.playlist_store.get_track_index()
        track = self.playlist_store.track_at(pl['id'], idx)
        if not track:
            return False
        self.filename = track['path']
        self._update_window_title(track)
        return True

    def _try_relocate_track(self, path):
        """Try to find a missing file automatically, then ask the user.
        Returns the new path if resolved, or None to skip."""
        # 1. Auto-search by filename near the original location
        found = find_file_by_name(path)
        if found:
            self.playlist_store.update_track_path(path, found)
            return found

        # 2. Ask the user to manually locate the file
        filename = os.path.basename(path)
        ext = os.path.splitext(filename)[1].lower() or '.mp3'
        new_path = filedialog.askopenfilename(
            title=f'找不到文件，请手动定位：{filename}',
            initialfile=filename,
            filetypes=[
                ('音频文件', ' '.join(f'*{e}' for e in self._AUDIO_EXTS)),
                ('所有文件', '*.*'),
            ],
        )
        if new_path and os.path.isfile(new_path):
            self.playlist_store.update_track_path(path, new_path)
            # Refresh playlist UI if open
            if self.playlist_ui.win and self.playlist_ui.win.winfo_exists():
                self.playlist_ui.refresh()
            return new_path
        return None

    def set_current_track_from_playlist(self, start_play=False):
        if not self._resolve_playback_track():
            return False
        if start_play:
            self.start_play()
        return True

    def _play_next_track_or_mic(self):
        store = self.playlist_store
        if store.has_next():
            store.set_track_index(store.get_track_index() + 1)
            if self.set_current_track_from_playlist(start_play=True):
                return
        self._smooth_switch_to_mic()

    def _handle_canvas_click(self):
        self._click_after_id = None
        if self.playing:
            self.paused = not self.paused
            if self.paused:
                self.start_mic()
            else:
                self.stop_mic()
            return
        if not self.filename and not self._resolve_playback_track():
            return
        self.start_play()

    def on_smooth_change(self, val):
        try:
            v = float(val)
            v = max(0.01, min(0.99, v))
            self.smooth_release = v
            self.smooth_attack = max(0.3, v * 2)
        except Exception:
            pass

    def on_bars_change(self, val):
        try:
            n = int(float(val))
            n = max(8, min(1024, n))
            self.num_bars = n
            self.smoothed_vals = None
            self._disp_ema = None
            self.running_peak_low = 1e-6
            self.running_peak_hi = 1e-6
            self._wave_trail.clear()
            while True:
                try:
                    self.wave_q.get_nowait()
                except queue.Empty:
                    break
        except Exception:
            pass

    def on_gain_change(self, val):
        try:
            v = float(val)
            v = max(0.0, min(10.0, v))
            self.gain = v
        except Exception:
            pass

    def on_bass_change(self, val):
        try:
            v = float(val)
            v = max(1.0, min(10.0, v))
            self.bass_bias = v
            self.smoothed_vals = None
        except Exception:
            pass

    def stop_playback(self):
        self._playback_id += 1
        self._playback_abort = True
        self._playback_ending = False
        self.playing = False
        self.paused = False
        thread = self._playback_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        self._playback_thread = None

    def start_play(self):
        if not self.filename and not self._resolve_playback_track():
            return
        if self.filename:
            track = self._track_for_filename()
            if track:
                self.filename = track.get('path') or self.filename
        if not self.filename:
            return
        self.stop_playback()
        self.stop_mic()

        path = self.filename
        if not os.path.isfile(path):
            new_path = self._try_relocate_track(path)
            if new_path:
                path = new_path
                self.filename = new_path
            else:
                # File not found and user cancelled → skip to next
                self.playing = False
                self._run_on_main(self._play_next_track_or_mic)
                return

        play_id = self._playback_id
        self._playback_abort = False
        self._playback_ending = False
        self._handoff_until = 0.0
        self._wave_decay_active = False
        self._wave_accept_input = True
        self.playing = True
        self.paused = False
        self.master.after_idle(self.playlist_ui.close_if_open)
        track = self._track_for_filename()
        if track:
            self._update_window_title(track)
        self._wave_trail.clear()
        while True:
            try:
                self.wave_q.get_nowait()
            except queue.Empty:
                break
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        thread = threading.Thread(
            target=self.audio_thread, args=(play_id, path), daemon=True)
        self._playback_thread = thread
        thread.start()

    def audio_thread(self, play_id, filename):
        try:
            with sf.SoundFile(filename, 'r') as f:
                samplerate = f.samplerate
                channels = f.channels
                blocksize = 4096
                self._init_analysis_state(samplerate, blocksize, reset_ring=True)

                def callback(outdata, frames, time_info, status):
                    if not self.playing:
                        raise sd.CallbackStop()
                    if self.paused:
                        outdata[:] = 0
                        return
                    data = f.read(frames, dtype='float32', always_2d=True)
                    if len(data) == 0:
                        self._mark_playback_ending()
                        self.playing = False
                        raise sd.CallbackStop()
                    if len(data) < frames:
                        out = np.zeros((frames, channels), dtype='float32')
                        out[:len(data)] = data
                        outdata[:] = out
                        mono = np.mean(data, axis=1).astype('float32')
                        mono = mono - np.mean(mono)
                        self._feed_mono_samples(mono, source='playback')
                        self._mark_playback_ending()
                        self.playing = False
                        raise sd.CallbackStop()
                    outdata[:] = data
                    mono = np.mean(data, axis=1).astype('float32')
                    mono = mono - np.mean(mono)
                    self._feed_mono_samples(mono, source='playback')

                with sd.OutputStream(
                        samplerate=samplerate, channels=channels, callback=callback,
                        dtype='float32', blocksize=blocksize):
                    while self.playing:
                        sd.sleep(100)
        except Exception as e:
            print('Playback error:', e)
        finally:
            if play_id == self._playback_id:
                self.playing = False
                self.paused = False
                if self._playback_thread and threading.current_thread() is self._playback_thread:
                    self._playback_thread = None
                aborted = self._playback_abort
                self._playback_abort = False
                if aborted:
                    self._playback_ending = False
                    self._handoff_until = 0.0
                    self._wave_trail.clear()
                    while True:
                        try:
                            self.wave_q.get_nowait()
                        except queue.Empty:
                            break
                    self._run_on_main(self._start_mic_if_idle, delay_ms=120)
                else:
                    self._run_on_main(self._play_next_track_or_mic)

    def update_visual(self):
        self._poll_main_calls()
        latest_fft = None
        try:
            while not self.q.empty():
                latest_fft = self.q.get_nowait()
        except queue.Empty:
            pass
        self.draw_spectrum(latest_fft)
        self.master.after(int(getattr(self, 'visual_ms', 20)), self.update_visual)

    def draw_spectrum(self, fft):
        now = time.time()
        last = getattr(self, 'last_draw_time', None)
        dt = (now - last) if (last is not None and now > last) else 0.05
        self.last_draw_time = now

        self.canvas.delete('all')
        N = getattr(self, 'num_bars', 80)

        if fft is not None:
            freqs = np.fft.rfftfreq(getattr(self, 'blocksize', 4096), d=1.0 / getattr(self, 'samplerate', 44100))
            edges_f = self._build_freq_edges(N, freqs)
            mag = fft
            vals, band_centers = self._aggregate_bands(mag, freqs, edges_f, N)
            vals = self._fill_sparse_bands(vals, band_centers)
            vals = self._fold_kick_energy(vals)
            try:
                self.band_centers = band_centers
            except Exception:
                self.band_centers = None
        else:
            if self.smoothed_vals is None:
                return
            vals = None

        if vals is not None and vals.size == 0:
            return

        if vals is None:
            norm = None
        else:
            if vals.size == 0:
                return
            linear = vals
            decay = getattr(self, 'peak_decay', 0.995)
            decay_low = getattr(self, 'peak_decay_low', 0.988)
            if time.time() < getattr(self, '_handoff_until', 0):
                decay = min(decay, 0.978)
                decay_low = min(decay_low, 0.965)
            low_end = max(4, int(round(len(linear) * float(self.low_span_end))))
            low_peak = float(np.max(linear[:low_end])) if low_end > 0 else 0.0
            hi_peak = float(np.max(linear[low_end:])) if low_end < len(linear) else 0.0
            self.running_peak_low = max(low_peak, self.running_peak_low * decay_low)
            self.running_peak_hi = max(hi_peak, self.running_peak_hi * decay)
            norm = np.zeros_like(linear, dtype=float)
            if low_end > 0:
                norm[:low_end] = linear[:low_end] / max(self.running_peak_low, 1e-9)
            if low_end < len(linear):
                norm[low_end:] = linear[low_end:] / max(self.running_peak_hi, 1e-9)
            norm = np.nan_to_num(norm, nan=0.0, posinf=1.0, neginf=0.0)
            boost = getattr(self, 'visual_boost', 1.0)
            norm = np.clip(norm * boost, 0.0, 1.0)
            mid_start = low_end
            hi_gain = float(getattr(self, 'mid_high_gain', 1.18))
            if mid_start < len(norm):
                norm[mid_start:] = np.clip(norm[mid_start:] * hi_gain, 0.0, 1.0)

        if self.smoothed_vals is None and norm is not None:
            self.smoothed_vals = norm.copy()
            self.bar_vel = np.zeros_like(self.smoothed_vals)

        gravity = getattr(self, 'gravity', 1.0)
        if not hasattr(self, 'bar_vel'):
            self.bar_vel = np.zeros(getattr(self, 'num_bars', 80))

        if norm is not None:
            if len(self.smoothed_vals) != len(norm):
                self.smoothed_vals = norm.copy()
                self.bar_vel = np.zeros_like(self.smoothed_vals)
            eps = 1e-6
            low_end_phys = max(4, int(round(len(norm) * float(self.low_span_end))))
            for i in range(len(norm)):
                cur = float(norm[i])
                prev = float(self.smoothed_vals[i])
                if cur > prev + eps:
                    a = max(0.6, getattr(self, 'smooth_attack', 0.6))
                    self.smoothed_vals[i] = a * cur + (1 - a) * prev
                    self.bar_vel[i] = 0.0
                else:
                    release = max(0.12, getattr(self, 'smooth_release', 0.2))
                    if i < low_end_phys:
                        release = max(0.26, release * 1.15)
                    self.smoothed_vals[i] = prev + release * (cur - prev)
                    self.bar_vel[i] = 0.0
        else:
            in_handoff = time.time() < getattr(self, '_handoff_until', 0)
            for i in range(len(self.smoothed_vals)):
                prev = float(self.smoothed_vals[i])
                if in_handoff:
                    self.smoothed_vals[i] = prev * 0.94
                    self.bar_vel[i] = 0.0
                else:
                    self.bar_vel[i] += gravity * dt
                    fall = max(0.0, prev - self.bar_vel[i] * dt)
                    if fall <= 0.0:
                        self.smoothed_vals[i] = 0.0
                        self.bar_vel[i] = 0.0
                    else:
                        self.smoothed_vals[i] = fall

        margin_bottom = 0
        viz_h = self.canvas_h - margin_bottom
        max_frac = float(getattr(self, 'max_bar_frac', 0.40))
        bar_w = self.canvas_w / N
        display_vals = self._smooth_display(self.smoothed_vals, N)
        gain = float(getattr(self, 'gain', 1.0))
        drum_bars = self._drum_bar_indices(N)
        display_vals = self._fill_drum_valleys(display_vals, drum_bars)
        sub_rumble_bars = self._sub_rumble_bar_indices(N, drum_bars)

        self._drain_wave_queue()
        self._decay_wave_trail_to_zero()
        self._draw_waveform_trail()

        for i, h in enumerate(display_vals):
            is_drum = i in drum_bars
            is_sub = i in sub_rumble_bars
            h_vis = self._map_bar_height(
                h, gain, max_frac, is_drum, self._is_mid_high_bar(i, N, drum_bars), is_sub)
            h_color = h_vis / max_frac if max_frac > 0 else h_vis
            gap = 1.0 if (is_drum or is_sub) else 2.0
            x0 = i * bar_w
            x1 = (i + 1) * bar_w - gap
            y1 = viz_h
            y0 = viz_h - h_vis * viz_h
            color = self._bar_color(h_color)
            self._draw_bar(x0, y0, x1, y1, color, rounded=True, drum=is_drum, sub_rumble=is_sub)


if __name__ == '__main__':
    root = tk.Tk()
    apply_tk_dpi_scaling(root)
    root.geometry(scaled_window_geometry(root, 800, 300))
    root.minsize(*scaled_minsize(root, 400, 200))
    app = SpectrumPlayer(root)
    root.update_idletasks()
    app.canvas_w = max(100, app.canvas.winfo_width())
    app.canvas_h = max(100, app.canvas.winfo_height())
    root.mainloop()
