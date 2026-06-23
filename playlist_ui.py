import os
import tkinter as tk
from tkinter import ttk

from playlist_store import read_track_metadata
from window_chrome import (
    apply_tk_dpi_scaling,
    resolve_sharp_ui_font,
    scaled_minsize,
    scaled_window_geometry,
    schedule_cursor_dark_titlebar,
    schedule_allow_drop,
)


class PlaylistWindow:
    _AUDIO_EXTS = {'.wav', '.flac', '.ogg', '.mp3', '.m4a', '.aac', '.wma', '.opus'}
    _UI_FONT = ('Microsoft YaHei UI', 11)
    _HOVER_PREVIEW_MS = 500

    # Cursor Dark (cedricverlinden/cursor-dark) workbench tokens
    _CURSOR_DARK = {
        'bg': '#141414',
        'surface': '#1a1a1a',
        'surface_alt': '#292929',
        'fg': '#E8E8E8',
        'fg_muted': '#D0D0D0',
        'fg_dim': '#9A9A9A',
        'select_bg': '#2A2A2A',
        'select_fg': '#FFFFFF',
        'border': '#2A2A2A',
        'focus_ring': '#505050',
        'accent': '#4c9df3',
        'accent_soft': '#88C0D0',
        'error': '#bf616a',
        'drop_queue_bg': '#243028',
        'drop_queue_fg': '#B8D4C8',
        'drop_reorder_bg': '#2A2A2A',
        'drop_reorder_fg': '#E8E8E8',
        'trash_bg': '#1a1a1a',
        'trash_fg': '#D0D0D0',
        'trash_hover_bg': '#3a2020',
        'trash_active_bg': '#8b3a3a',
        'ghost_bg': '#333333',
        'ghost_fg': '#FFFFFF',
        'scrollbar': '#404040',
        'scrollbar_trough': '#141414',
        'btn_primary_bg': '#333333',
        'btn_primary_hover': '#3C3C3C',
        'btn_primary_fg': '#F0F0F0',
        'btn_secondary_bg': '#252526',
        'btn_secondary_hover': '#2D2D2D',
        'btn_secondary_fg': '#C8C8C8',
    }

    def __init__(self, master, player):
        self.master = master
        self.player = player
        self.store = player.playlist_store
        self.win = None
        self._manual_list = None
        self._album_list = None
        self._artist_list = None
        self._track_list = None
        self._trash = None
        self._manual_ids = []
        self._album_ids = []
        self._artist_ids = []
        self._display_pl_id = None
        self._track_header = None
        self._drag = {
            'active': False, 'kind': None, 'index': None, 'pl_id': None,
            'moved': False, 'handled': False, 'previewed': False,
            'label_text': None, 'track': None, 'display_before': None,
            'hover_pl_id': None, 'hint_state': None, 'ghost_text': None,
        }
        self._press_xy = (0, 0)
        self._hover_preview_after_id = None
        self._drag_ghost = None
        self._ghost_label = None
        self._listbox_default_bg = {}
        self._theme = self._CURSOR_DARK
        self._active_font = self._UI_FONT
        self._last_win_dpi = None
        self._win_move_offset = None

    def _current_font(self):
        return self._active_font

    def _refresh_ui_font(self, widget=None):
        target = widget or self.win
        if target is not None and target.winfo_exists():
            self._active_font = resolve_sharp_ui_font(target, 'Microsoft YaHei UI', 11)
        else:
            self._active_font = self._UI_FONT

    def _on_win_dpi_map(self, _event=None):
        if self.win is None or not self.win.winfo_exists():
            return
        try:
            dpi = self.win.winfo_fpixels('1i')
        except tk.TclError:
            return
        if dpi == self._last_win_dpi:
            return
        self._last_win_dpi = dpi
        apply_tk_dpi_scaling(self.win)
        self._refresh_ui_font(self.win)
        self._apply_fonts_to_widgets()

    def _on_win_unmap(self, event=None):
        if not self._is_open():
            return
        if event is not None and event.widget is not self.win:
            return
        try:
            if self.win.state() == 'iconic':
                self._on_close()
        except tk.TclError:
            pass

    def close_if_open(self):
        if self.win is not None and self.win.winfo_exists():
            self._on_close()

    def _is_open(self):
        try:
            return self.win is not None and self.win.winfo_exists()
        except tk.TclError:
            return False

    def _widget_alive(self, widget):
        try:
            return widget is not None and widget.winfo_exists()
        except tk.TclError:
            return False

    def _bind_window_drag(self, widget):
        widget.bind('<ButtonPress-1>', self._on_window_drag_press, add='+')

    def _on_window_drag_press(self, event):
        if self._drag.get('active') or self._drag.get('moved'):
            return
        w = event.widget
        if not isinstance(w, (tk.Label, ttk.Label)):
            return
        if w is self._trash:
            return
        if not self._is_open():
            return
        self._win_move_offset = (
            event.x_root - self.win.winfo_rootx(),
            event.y_root - self.win.winfo_rooty(),
        )

    def _move_window_by_drag(self, event):
        if self._win_move_offset is None or not self._is_open():
            return
        try:
            ox, oy = self._win_move_offset
            self.win.geometry(f'+{event.x_root - ox}+{event.y_root - oy}')
        except tk.TclError:
            self._clear_win_move()

    def _clear_win_move(self):
        self._win_move_offset = None

    def _apply_fonts_to_widgets(self):
        font = self._current_font()
        for lb in (self._manual_list, self._album_list, self._artist_list, self._track_list):
            if self._widget_alive(lb):
                try:
                    lb.config(font=font)
                except tk.TclError:
                    pass
        if self._widget_alive(self._trash):
            try:
                self._trash.config(font=font)
            except tk.TclError:
                pass
        if self._widget_alive(self._ghost_label):
            try:
                self._ghost_label.config(font=font)
            except tk.TclError:
                pass
        if self._is_open():
            try:
                style = ttk.Style(self.win)
                style.configure('TLabel', font=font)
            except tk.TclError:
                pass

    def _apply_cursor_theme(self):
        t = self._theme
        self.win.configure(bg=t['bg'])
        style = ttk.Style(self.win)
        style.theme_use('clam')
        style.configure('.', background=t['bg'], foreground=t['fg'])
        style.configure('TFrame', background=t['bg'])
        style.configure('TPanedwindow', background=t['bg'])
        style.configure(
            'TLabel', background=t['bg'], foreground=t['fg_muted'],
            font=self._current_font(),
        )
        style.configure(
            'Vertical.TScrollbar',
            background=t['surface_alt'],
            troughcolor=t['scrollbar_trough'],
            bordercolor=t['border'],
            arrowcolor=t['fg_muted'],
            darkcolor=t['border'],
            lightcolor=t['border'],
        )
        style.map(
            'Vertical.TScrollbar',
            background=[('active', t['scrollbar']), ('pressed', t['surface_alt'])],
        )
        style.configure('TSeparator', background=t['border'])

    def _make_dialog_button(self, parent, text, command, *, primary=False):
        t = self._theme
        if primary:
            bg, fg, hover = t['btn_primary_bg'], t['btn_primary_fg'], t['btn_primary_hover']
        else:
            bg, fg, hover = t['btn_secondary_bg'], t['btn_secondary_fg'], t['btn_secondary_hover']
        btn = tk.Button(
            parent, text=text, command=command,
            bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
            relief=tk.FLAT, borderwidth=0, padx=14, pady=6,
            font=self._current_font(), cursor='hand2',
        )
        btn.bind('<Enter>', lambda e: btn.config(bg=hover))
        btn.bind('<Leave>', lambda e: btn.config(bg=bg))
        return btn

    def _ask_string(self, title, prompt, initial=''):
        if self.win is None or not self.win.winfo_exists():
            return None
        t = self._theme
        result = {'value': None}

        dlg = tk.Toplevel(self.win)
        dlg.title(title)
        dlg.transient(self.win)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(bg=t['bg'])
        schedule_cursor_dark_titlebar(
            dlg, caption=t['bg'], text=t['fg_muted'], border=t['border'])

        frame = tk.Frame(dlg, bg=t['bg'], padx=16, pady=14)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame, text=prompt, bg=t['bg'], fg=t['fg'],
            font=self._current_font(), anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 8))

        entry = tk.Entry(
            frame, bg=t['surface'], fg=t['fg'],
            insertbackground=t['fg'],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=t['border'],
            highlightcolor=t['focus_ring'],
            font=self._current_font(),
        )
        entry.pack(fill=tk.X, ipady=4)
        if initial:
            entry.insert(0, initial)
        entry.focus_set()
        entry.select_range(0, tk.END)

        btn_row = tk.Frame(frame, bg=t['bg'])
        btn_row.pack(fill=tk.X, pady=(14, 0))

        def _submit():
            val = entry.get().strip()
            if val:
                result['value'] = val
            dlg.destroy()

        def _cancel(_event=None):
            dlg.destroy()

        self._make_dialog_button(btn_row, '创建', _submit, primary=True).pack(
            side=tk.RIGHT, padx=(8, 0))
        self._make_dialog_button(btn_row, '取消', _cancel).pack(side=tk.RIGHT)

        entry.bind('<Return>', lambda e: _submit())
        entry.bind('<Escape>', _cancel)
        dlg.bind('<Escape>', _cancel)
        dlg.protocol('WM_DELETE_WINDOW', _cancel)

        dlg.update_idletasks()
        pw = self.win.winfo_rootx() + (self.win.winfo_width() - dlg.winfo_width()) // 2
        ph = self.win.winfo_rooty() + (self.win.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f'+{max(0, pw)}+{max(0, ph)}')
        dlg.wait_window()
        return result['value']

    def _listbox_kwargs(self):
        t = self._theme
        return dict(
            exportselection=False,
            selectmode=tk.SINGLE,
            activestyle='none',
            bg=t['surface'],
            fg=t['fg'],
            selectbackground=t['select_bg'],
            selectforeground=t['select_fg'],
            highlightbackground=t['border'],
            highlightcolor=t['focus_ring'],
            highlightthickness=1,
            relief=tk.FLAT,
            borderwidth=0,
            font=self._current_font(),
        )

    def open(self):
        if self.win is not None and self.win.winfo_exists():
            self.win.lift()
            self.win.focus_force()
            self.refresh()
            return
        self.store.ensure_queue_playlist()
        t = self._theme
        self.win = tk.Toplevel(self.master)
        self.win.withdraw()
        self.win.title('歌单管理')
        self.win.configure(bg=t['bg'])
        self.win.protocol('WM_DELETE_WINDOW', self._on_close)
        apply_tk_dpi_scaling(self.win)
        self.win.geometry(scaled_window_geometry(self.win, 920, 520))
        self.win.minsize(*scaled_minsize(self.win, 760, 420))
        self._refresh_ui_font(self.win)
        self._apply_cursor_theme()
        self.win.bind('<Map>', self._on_win_dpi_map, add='+')
        self.win.bind('<Unmap>', self._on_win_unmap, add='+')

        outer = ttk.Frame(self.win, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)

        paned = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        self._album_list = self._make_pl_column(paned, '专辑', 'album', weight=1)
        self._artist_list = self._make_pl_column(paned, '歌手', 'artist', weight=1)
        self._manual_list = self._make_pl_column(paned, '自建歌单', 'manual', weight=1)
        right = ttk.Frame(paned)
        paned.add(right, weight=3)
        hdr = ttk.Label(right, text='当前列表')
        hdr.pack(anchor=tk.W)
        self._bind_window_drag(hdr)
        self._track_header = ttk.Label(right, text='')
        self._track_header.pack(anchor=tk.W)
        self._bind_window_drag(self._track_header)
        tr_wrap = ttk.Frame(right)
        tr_wrap.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        tr_scroll = ttk.Scrollbar(tr_wrap)
        tr_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._track_list = tk.Listbox(tr_wrap, yscrollcommand=tr_scroll.set, **self._listbox_kwargs())
        self._track_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tr_scroll.config(command=self._track_list.yview)
        self._bind_track_drag(self._track_list)
        self._track_list.bind('<Double-Button-1>', self._play_selected_track)
        self._setup_track_file_drop(tr_wrap)

        trash_frame = ttk.Frame(outer)
        trash_frame.pack(fill=tk.X, pady=(8, 0))
        self._trash = tk.Label(
            trash_frame,
            text='🗑  拖到此处删除歌单或歌曲',
            anchor=tk.CENTER,
            relief=tk.GROOVE,
            bg=t['trash_bg'],
            fg=t['trash_fg'],
            padx=12,
            pady=10,
            font=self._current_font(),
            highlightbackground=t['border'],
            highlightcolor=t['focus_ring'],
            highlightthickness=1,
        )
        self._trash.pack(fill=tk.X)
        self._trash_default = (t['trash_bg'], t['trash_fg'], '🗑  拖到此处删除歌单或歌曲')
        self._trash.bind('<Enter>', lambda e: self._set_trash_highlight(True, hover_only=True))
        self._trash.bind('<Leave>', lambda e: self._set_trash_highlight(False, hover_only=True))

        self.win.bind('<B1-Motion>', self._win_drag_motion, add='+')
        self.win.bind('<ButtonRelease-1>', self._win_drag_release, add='+')

        self.refresh()
        self.win.update_idletasks()
        schedule_cursor_dark_titlebar(
            self.win,
            caption=t['bg'],
            text=t['fg_muted'],
            border=t['border'],
        )
        schedule_allow_drop(self.win)
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def _make_pl_column(self, paned, title, column_kind, weight=1):
        col = ttk.Frame(paned)
        paned.add(col, weight=weight)
        hint = '播放列表在首行 · 双击空白处新建' if column_kind == 'manual' else '自动生成'
        hdr = ttk.Label(col, text=f'{title}  ·  {hint}')
        hdr.pack(anchor=tk.W)
        self._bind_window_drag(hdr)
        box = ttk.Frame(col)
        box.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        scroll = ttk.Scrollbar(box)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        lb = tk.Listbox(box, yscrollcommand=scroll.set, **self._listbox_kwargs())
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=lb.yview)
        lb.bind('<<ListboxSelect>>', lambda e, k=column_kind: self._on_playlist_select(k))
        if column_kind == 'manual':
            lb.bind('<Double-Button-1>', self._on_manual_double_click)
        else:
            lb.bind('<Double-Button-1>', lambda e, k=column_kind: self._play_playlist_column(k))
        self._bind_playlist_drag(lb, column_kind)
        return lb

    def _bind_playlist_drag(self, lb, column_kind):
        lb.bind('<ButtonPress-1>', lambda e: self._playlist_press(e, lb, column_kind), add='+')
        lb.bind('<B1-Motion>', self._playlist_motion, add='+')
        lb.bind('<ButtonRelease-1>', lambda e: self._playlist_release(e, lb, column_kind), add='+')

    def _bind_track_drag(self, lb):
        lb.bind('<ButtonPress-1>', self._track_press, add='+')
        lb.bind('<B1-Motion>', self._track_motion, add='+')
        lb.bind('<ButtonRelease-1>', self._track_release, add='+')

    def _setup_track_file_drop(self, widget):
        # Guard: only register windnd hooks once per Toplevel window lifetime.
        if getattr(self, '_track_drop_hooked', False):
            return
        self._track_drop_hooked = True

        def _on_files(raw_paths):
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
            self._import_files_to_current(paths)

        try:
            import windnd
            windnd.hook_dropfiles(widget, func=_on_files)
            windnd.hook_dropfiles(self._track_list, func=_on_files)
        except Exception:
            pass

    def _queue_id(self):
        return self.store.ensure_queue_playlist()['id']

    def _display_playlist(self):
        if not self._display_pl_id:
            return self.store.get_queue_playlist()
        return self.store.get_playlist(self._display_pl_id)

    def _is_editable_display(self):
        pl = self._display_playlist()
        return pl is not None and pl.get('kind') in ('manual', 'queue')

    def _update_track_header(self):
        if self._track_header is None:
            return
        pl = self._display_playlist()
        if not pl:
            self._track_header.config(text='')
            return
        name = pl.get('name', '')
        q = self.store.get_queue_playlist()
        active_id = self.store.data.get('active_playlist_id')
        playing = '  ● 正在播放' if pl['id'] == active_id and active_id == q['id'] else ''
        if pl.get('kind') in ('manual', 'queue'):
            self._track_header.config(
                text=f'「{name}」{playing}  ·  拖动排序 · 双击播放 · 拖入添加 · 拖到回收站删除')
        elif pl.get('kind') in ('album', 'artist'):
            self._track_header.config(
                text=f'「{name}」  ·  双击歌曲载入播放列表并播放 · 拖到回收站移除重复文件')
        else:
            self._track_header.config(
                text=f'「{name}」  ·  双击歌曲载入播放列表并播放')

    def _set_display_pl_id(self, pl_id):
        if not self._is_open():
            self._display_pl_id = pl_id
            return False
        if not pl_id or pl_id == self._display_pl_id:
            return False
        self._display_pl_id = pl_id
        self._refresh_tracks()
        self._update_track_header()
        return True

    def _focus_display_pl(self, pl_id):
        self._display_pl_id = pl_id
        if not self._is_open():
            return
        self._select_playlist_id(pl_id)
        self._refresh_tracks()
        self._update_track_header()

    def _load_queue_and_play(self, source_pl_id, track_index=0):
        q = self.store.replace_queue_from(source_pl_id)
        self.store.set_active(q['id'], track_index)
        self.player.set_current_track_from_playlist(start_play=True)

    def _import_files_to_current(self, paths):
        pl = self._display_playlist() or self.store.get_queue_playlist()
        files = [
            p.strip().strip('"').strip("'") for p in paths
            if os.path.splitext(p)[1].lower() in self._AUDIO_EXTS and os.path.isfile(p.strip().strip('"').strip("'"))]
        if not files:
            return
        if pl.get('kind') == 'manual':
            self.store.add_tracks_to_playlist(pl['id'], files, sync_albums=True)
        else:
            for fp in files:
                self.store.add_to_queue(fp)
            if pl.get('kind') != 'queue':
                self._focus_display_pl(self._queue_id())
        self.refresh()

    def _on_close(self):
        self._clear_win_move()
        self._clear_drag_visuals()
        if self.win is not None:
            self.win.destroy()
        self.win = None
        self._drag_ghost = None
        self._ghost_label = None
        self._track_drop_hooked = False

    def _active_mark(self, pl_id):
        return '  ●' if pl_id == self.store.data.get('active_playlist_id') else ''

    def _refresh_active_marks(self):
        self._fill_playlist_column(
            self._manual_list, self._manual_ids,
            [self.store.ensure_queue_playlist()] + self.store.list_manual_playlists())
        self._fill_playlist_column(
            self._album_list, self._album_ids, self.store.list_album_playlists())
        self._fill_playlist_column(
            self._artist_list, self._artist_ids, self.store.list_artist_playlists())
        if self._display_pl_id:
            self._select_playlist_id(self._display_pl_id)

    def refresh(self):
        if self.win is None or not self.win.winfo_exists():
            return
        if not self._display_pl_id:
            self._display_pl_id = self._queue_id()
        self._fill_playlist_column(
            self._manual_list, self._manual_ids,
            [self.store.ensure_queue_playlist()] + self.store.list_manual_playlists())
        self._fill_playlist_column(
            self._album_list, self._album_ids, self.store.list_album_playlists())
        self._fill_playlist_column(
            self._artist_list, self._artist_ids, self.store.list_artist_playlists())
        self._select_playlist_id(self._display_pl_id)
        self._refresh_tracks()
        self._update_track_header()

    def _fill_playlist_column(self, lb, id_list, playlists):
        id_list.clear()
        lb.delete(0, tk.END)
        active_id = self.store.data.get('active_playlist_id')
        for pl in playlists:
            id_list.append(pl['id'])
            name = pl.get('name', '')
            if pl.get('kind') == 'queue':
                mark = '  ●' if pl['id'] == active_id else ''
                lb.insert(tk.END, f'▶ {name}{mark}')
            else:
                lb.insert(tk.END, name)

    def _playlist_id_at(self, column_kind, index):
        ids = {'manual': self._manual_ids, 'album': self._album_ids, 'artist': self._artist_ids}.get(column_kind, [])
        if 0 <= index < len(ids):
            return ids[index]
        return None

    def _current_playlist(self):
        return self._display_playlist()

    def _select_playlist_id(self, pl_id):
        if not self._is_open():
            return
        for lb, ids in (
            (self._manual_list, self._manual_ids),
            (self._album_list, self._album_ids),
            (self._artist_list, self._artist_ids),
        ):
            if not self._widget_alive(lb):
                continue
            if pl_id in ids:
                idx = ids.index(pl_id)
                try:
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(idx)
                    lb.see(idx)
                except tk.TclError:
                    pass
                return

    def _on_playlist_select(self, column_kind):
        lb = {'manual': self._manual_list, 'album': self._album_list, 'artist': self._artist_list}[column_kind]
        sel = lb.curselection()
        if not sel:
            return
        pl_id = self._playlist_id_at(column_kind, int(sel[0]))
        if not pl_id:
            return
        self._set_display_pl_id(pl_id)

    def _paths_with_duplicate_identity(self, tracks):
        counts = {}
        for t in tracks:
            key = (
                int(t.get('disc_num') or 0),
                int(t.get('track_num') or 0),
                (t.get('title') or '').strip().casefold(),
            )
            counts[key] = counts.get(key, 0) + 1
        dup_keys = {k for k, n in counts.items() if n > 1}
        if not dup_keys:
            return set()
        paths = set()
        for t in tracks:
            key = (
                int(t.get('disc_num') or 0),
                int(t.get('track_num') or 0),
                (t.get('title') or '').strip().casefold(),
            )
            if key in dup_keys:
                path = t.get('path')
                if path:
                    paths.add(path)
        return paths

    def _refresh_tracks(self):
        if self._track_list is None:
            return
        self._track_list.delete(0, tk.END)
        pl = self._display_playlist()
        if not pl:
            return
        q = self.store.get_queue_playlist()
        active_id = self.store.data.get('active_playlist_id')
        playing_idx = self.store.get_track_index() if active_id == q['id'] and pl['id'] == q['id'] else -1
        dup_paths = set()
        if pl.get('kind') in ('album', 'artist'):
            dup_paths = self._paths_with_duplicate_identity(pl.get('tracks', []))
        for i, t in enumerate(pl.get('tracks', [])):
            num = t.get('track_num') or 0
            prefix = f'{num:02d}. ' if num else ''
            title = t.get('title') or '未知曲目'
            artist = t.get('artist') or ''
            line = f'{prefix}{title}'
            if artist:
                line += f' — {artist}'
            path = t.get('path') or ''
            if path in dup_paths:
                line += f' · {os.path.basename(path)}'
            if path and not os.path.isfile(path):
                line = f'⚠ {line}'
            if i == playing_idx:
                line = f'▶ {line}'
            self._track_list.insert(tk.END, line)

    def _on_manual_double_click(self, event):
        lb = self._manual_list
        size = lb.size()
        if size == 0:
            self._create_playlist()
            return
        # Check if the click landed below the last item (empty space).
        last_bbox = lb.bbox(size - 1)
        if last_bbox is not None:
            item_bottom = last_bbox[1] + last_bbox[3]  # y + height
            if event.y > item_bottom + 2:
                self._create_playlist()
                return
        idx = lb.nearest(event.y)
        if idx < 0 or idx >= size:
            self._create_playlist()
            return
        pl_id = self._playlist_id_at('manual', idx)
        pl = self.store.get_playlist(pl_id)
        if pl and pl.get('kind') == 'queue':
            if pl.get('tracks'):
                self._load_queue_and_play(pl_id, 0)
            return
        self._play_playlist_column('manual')

    def _create_playlist(self):
        if self.win is None or not self.win.winfo_exists():
            return
        name = self._ask_string('新建歌单', '歌单名称：')
        if not name:
            return
        pl = self.store.create_playlist(name, kind='manual')
        self.refresh()
        self._set_display_pl_id(pl['id'])
        self._select_playlist_id(pl['id'])

    def _over_trash(self, event):
        if self._trash is None:
            return False
        x, y = self._trash.winfo_rootx(), self._trash.winfo_rooty()
        w, h = self._trash.winfo_width(), self._trash.winfo_height()
        return x <= event.x_root <= x + w and y <= event.y_root <= y + h

    def _cancel_hover_preview_timer(self):
        if self._hover_preview_after_id is not None and self.win is not None:
            try:
                self.win.after_cancel(self._hover_preview_after_id)
            except tk.TclError:
                pass
        self._hover_preview_after_id = None

    def _schedule_hover_preview(self, pl_id):
        if pl_id == self._display_pl_id:
            self._cancel_hover_preview_timer()
            return
        if self._hover_preview_after_id is not None and self._drag.get('hover_pl_id') == pl_id:
            return
        self._cancel_hover_preview_timer()
        if self.win is None or not self.win.winfo_exists():
            return
        self._hover_preview_after_id = self.win.after(
            self._HOVER_PREVIEW_MS, lambda pid=pl_id: self._apply_hover_preview(pid))

    def _apply_hover_preview(self, pl_id):
        self._hover_preview_after_id = None
        if not self._drag.get('active') or not self._drag.get('moved'):
            return
        if self._drag.get('kind') != 'track':
            return
        if self._drag.get('hover_pl_id') != pl_id:
            return
        if self._set_display_pl_id(pl_id):
            self._drag['previewed'] = True

    def _reset_drag(self):
        previewed = self._drag.get('previewed')
        restore_id = self._drag.get('display_before')
        self._clear_drag_visuals()
        self._drag = {
            'active': False, 'kind': None, 'index': None,
            'pl_id': None, 'moved': False, 'handled': False, 'previewed': False,
            'label_text': None, 'track': None, 'display_before': None,
            'hover_pl_id': None, 'hint_state': None, 'ghost_text': None,
        }
        if previewed and restore_id:
            self._focus_display_pl(restore_id)

    def _playlist_at_event(self, event):
        for column_kind, lb, ids in (
            ('manual', self._manual_list, self._manual_ids),
            ('album', self._album_list, self._album_ids),
            ('artist', self._artist_list, self._artist_ids),
        ):
            if lb is not None and self._point_in_widget(event, lb):
                local_y = event.y_root - lb.winfo_rooty()
                idx = lb.nearest(local_y)
                if 0 <= idx < len(ids):
                    return ids[idx], column_kind, lb, idx
        return None, None, None, None

    def _point_in_widget(self, event, widget):
        if widget is None:
            return False
        x, y = widget.winfo_rootx(), widget.winfo_rooty()
        w, h = widget.winfo_width(), widget.winfo_height()
        return x <= event.x_root <= x + w and y <= event.y_root <= y + h

    def _drag_item_text(self):
        cached = self._drag.get('label_text')
        if cached:
            return cached
        kind = self._drag.get('kind')
        idx = self._drag.get('index')
        if kind == 'playlist':
            col = self._drag.get('column')
            lb = {'manual': self._manual_list, 'album': self._album_list, 'artist': self._artist_list}.get(col)
            if lb and idx is not None and 0 <= idx < lb.size():
                return lb.get(idx).strip()
        elif kind == 'track' and self._track_list and idx is not None:
            if 0 <= idx < self._track_list.size():
                return self._track_list.get(idx).strip()
        return '拖动中…'

    def _ensure_drag_ghost(self):
        if self._drag_ghost is not None and self._drag_ghost.winfo_exists():
            return
        t = self._theme
        self._drag_ghost = tk.Toplevel(self.win)
        self._drag_ghost.configure(bg=t['ghost_bg'])
        self._drag_ghost.overrideredirect(True)
        self._drag_ghost.attributes('-topmost', True)
        try:
            self._drag_ghost.attributes('-alpha', 0.92)
        except tk.TclError:
            pass
        self._ghost_label = tk.Label(
            self._drag_ghost,
            text='',
            bg=t['ghost_bg'],
            fg=t['ghost_fg'],
            font=self._current_font(),
            padx=10,
            pady=5,
            relief=tk.FLAT,
            borderwidth=0,
        )
        self._ghost_label.pack()

    def _move_drag_ghost(self, event):
        if self._drag_ghost is None or self._ghost_label is None:
            return
        text = self._drag.get('ghost_text')
        if text is None:
            text = self._drag_item_text()
            if len(text) > 48:
                text = text[:45] + '…'
            self._drag['ghost_text'] = text
        self._ghost_label.config(text=text)
        self._drag_ghost.geometry(f'+{event.x_root + 14}+{event.y_root + 10}')
        self._drag_ghost.deiconify()

    def _hide_drag_ghost(self):
        if self._drag_ghost is not None and self._drag_ghost.winfo_exists():
            self._drag_ghost.withdraw()

    def _set_trash_highlight(self, active, hover_only=False):
        if self._trash is None:
            return
        t = self._theme
        if self._drag.get('moved') and active:
            self._trash.config(bg=t['trash_active_bg'], fg='#ffffff', text='🗑  松开以删除')
        elif hover_only and active and not self._drag.get('moved'):
            self._trash.config(bg=t['trash_hover_bg'], fg='#eeeeee', text=self._trash_default[2])
        else:
            bg, fg, txt = self._trash_default
            self._trash.config(bg=bg, fg=fg, text=txt)

    def _remember_listbox_colors(self, lb):
        if lb not in self._listbox_default_bg:
            try:
                self._listbox_default_bg[lb] = lb.cget('bg')
            except tk.TclError:
                self._listbox_default_bg[lb] = self._theme['surface']

    def _clear_listbox_hints(self, lb):
        if lb is None:
            return
        self._remember_listbox_colors(lb)
        default_bg = self._listbox_default_bg.get(lb, self._theme['surface'])
        for i in range(lb.size()):
            try:
                lb.itemconfig(i, bg=default_bg, fg=lb.cget('fg'))
            except tk.TclError:
                pass

    def _highlight_listbox_row(self, lb, index, bg, fg=None):
        if lb is None or index is None or index < 0 or index >= lb.size():
            return
        self._remember_listbox_colors(lb)
        self._clear_listbox_hints(lb)
        kwargs = {'bg': bg}
        if fg:
            kwargs['fg'] = fg
        lb.itemconfig(index, **kwargs)

    def _dim_drag_source(self, lb, index):
        if lb is None or index is None or index < 0 or index >= lb.size():
            return
        self._remember_listbox_colors(lb)
        try:
            lb.itemconfig(index, fg=self._theme['fg_dim'])
        except tk.TclError:
            pass

    def _update_drop_hints(self, event):
        if self._drag.get('kind') != 'track':
            return

        t = self._theme
        pl_id, _col, lb, idx = self._playlist_at_event(event)
        track_to_idx = None
        pl = self._display_playlist()
        if pl and pl.get('kind') in ('manual', 'queue') and self._point_in_widget(event, self._track_list):
            size = self._track_list.size()
            if size > 0:
                track_to_idx = max(0, min(self._track_list.nearest(event.y), size - 1))

        hint_state = (pl_id, idx, track_to_idx)
        if hint_state == self._drag.get('hint_state'):
            if pl_id is not None:
                self._drag['hover_pl_id'] = pl_id
                self._schedule_hover_preview(pl_id)
            else:
                self._drag['hover_pl_id'] = None
                self._cancel_hover_preview_timer()
            return
        self._drag['hint_state'] = hint_state

        for list_lb in (self._manual_list, self._album_list, self._artist_list, self._track_list):
            self._clear_listbox_hints(list_lb)

        if pl_id is not None:
            self._highlight_listbox_row(lb, idx, t['drop_queue_bg'], t['drop_queue_fg'])
            self._drag['hover_pl_id'] = pl_id
            self._schedule_hover_preview(pl_id)
        else:
            self._drag['hover_pl_id'] = None
            self._cancel_hover_preview_timer()

        if track_to_idx is not None:
            self._highlight_listbox_row(
                self._track_list, track_to_idx, t['drop_reorder_bg'], t['drop_reorder_fg'])

    def _dim_drag_source_once(self):
        kind = self._drag.get('kind')
        idx = self._drag.get('index')
        if kind == 'playlist':
            col = self._drag.get('column')
            lb = {'manual': self._manual_list, 'album': self._album_list, 'artist': self._artist_list}.get(col)
            self._dim_drag_source(lb, idx)
        elif kind == 'track' and self._drag.get('pl_id') == self._display_pl_id:
            self._dim_drag_source(self._track_list, idx)

    def _update_drag_visuals(self, event):
        if not self._drag.get('moved'):
            return
        self._ensure_drag_ghost()
        self._move_drag_ghost(event)
        if self.win:
            self.win.config(cursor='hand2')
        self._set_trash_highlight(self._over_trash(event))
        self._update_drop_hints(event)

    def _clear_drag_visuals(self):
        self._cancel_hover_preview_timer()
        self._hide_drag_ghost()
        self._set_trash_highlight(False)
        if self.win and self.win.winfo_exists():
            self.win.config(cursor='')
        for lb in (self._manual_list, self._album_list, self._artist_list, self._track_list):
            self._clear_listbox_hints(lb)

    def _begin_drag_motion(self, event):
        if not self._drag.get('active') or self._drag.get('handled'):
            return
        dx = abs(event.x_root - self._press_xy[0])
        dy = abs(event.y_root - self._press_xy[1])
        if dx + dy > 6:
            if not self._drag.get('moved'):
                self._drag['moved'] = True
                self._dim_drag_source_once()
            self._update_drag_visuals(event)

    def _win_drag_motion(self, event):
        if self._win_move_offset is not None and not self._drag.get('moved'):
            self._move_window_by_drag(event)
            return
        if not self._drag.get('active'):
            return
        self._begin_drag_motion(event)

    def _win_drag_release(self, event):
        self._clear_win_move()
        if not self._drag.get('active') or not self._drag.get('moved') or self._drag.get('handled'):
            return
        if self._drag.get('kind') == 'track':
            self._track_release(event)
        elif self._drag.get('kind') == 'playlist':
            self._playlist_release(event, None, self._drag.get('column'))

    def _playlist_press(self, event, lb, column_kind):
        idx = lb.nearest(event.y)
        if idx < 0 or idx >= lb.size():
            self._reset_drag()
            return
        pl_id = self._playlist_id_at(column_kind, idx)
        if not pl_id:
            self._reset_drag()
            return
        self._press_xy = (event.x_root, event.y_root)
        self._drag = {
            'active': True, 'kind': 'playlist', 'index': idx,
            'pl_id': pl_id, 'moved': False, 'handled': False, 'previewed': False,
            'column': column_kind,
        }

    def _playlist_motion(self, event):
        self._begin_drag_motion(event)

    def _playlist_release(self, event, lb, column_kind):
        if not self._drag.get('active') or self._drag.get('kind') != 'playlist':
            return
        if self._drag.get('handled'):
            return
        if not self._drag.get('moved'):
            self._reset_drag()
            return
        self._drag['handled'] = True
        if self._over_trash(event):
            pl_id = self._drag.get('pl_id')
            pl = self.store.get_playlist(pl_id)
            if pl and pl.get('kind') in ('queue', 'album', 'manual'):
                self.store.delete_playlist(pl_id)
                if self._display_pl_id == pl_id:
                    self._display_pl_id = None
                self.refresh()
            # artist playlists: cannot be deleted manually (auto-managed)
        self._reset_drag()

    def _track_press(self, event):
        lb = self._track_list
        idx = lb.nearest(event.y)
        if idx < 0 or idx >= lb.size():
            self._reset_drag()
            return
        pl = self._display_playlist()
        if not pl:
            self._reset_drag()
            return
        track = self.store.track_at(pl['id'], idx)
        self._press_xy = (event.x_root, event.y_root)
        self._drag = {
            'active': True, 'kind': 'track', 'index': idx,
            'pl_id': pl['id'], 'moved': False, 'handled': False, 'previewed': False,
            'display_before': self._display_pl_id,
            'label_text': lb.get(idx).strip(),
            'track': dict(track) if track else None,
        }

    def _track_drop_index(self, event):
        if not self._point_in_widget(event, self._track_list):
            return None
        size = self._track_list.size()
        if size <= 0:
            return 0
        return max(0, min(self._track_list.nearest(event.y), size - 1))

    def _track_motion(self, event):
        self._begin_drag_motion(event)

    def _track_release(self, event):
        if not self._drag.get('active') or self._drag.get('kind') != 'track':
            return
        if self._drag.get('handled'):
            return
        if not self._drag.get('moved'):
            self._reset_drag()
            return
        self._drag['handled'] = True

        pl_id = self._drag['pl_id']
        from_idx = self._drag['index']
        pl = self.store.get_playlist(pl_id)
        track = self._drag.get('track') or (self.store.track_at(pl_id, from_idx) if pl else None)

        if self._over_trash(event):
            if pl and pl.get('kind') in ('manual', 'queue'):
                self.store.remove_track(pl_id, from_idx)
                self.refresh()
            # album / artist: individual tracks cannot be deleted;
            # delete the whole playlist by dragging the playlist row to trash.
            self._reset_drag()
            return

        to_idx = self._track_drop_index(event)
        if to_idx is not None and track:
            display_pl = self._display_playlist()
            if display_pl and display_pl.get('kind') in ('manual', 'queue'):
                target_id = display_pl['id']
                if self.store.move_track_to_playlist(pl_id, from_idx, target_id, to_idx):
                    self.refresh()
                    self._focus_display_pl(target_id)
                    if self._track_list.size() > 0:
                        sel = min(to_idx, self._track_list.size() - 1)
                        self._track_list.selection_set(sel)
                self._reset_drag()
                return

        tgt_id, _col, _lb, _idx = self._playlist_at_event(event)
        if track and tgt_id:
            tgt_pl = self.store.get_playlist(tgt_id)
            if tgt_pl and tgt_pl.get('kind') in ('manual', 'queue'):
                append_idx = len(tgt_pl.get('tracks', []))
                if self.store.move_track_to_playlist(pl_id, from_idx, tgt_id, append_idx):
                    self.refresh()
                    self._focus_display_pl(tgt_id)
                self._reset_drag()
                return

        self._reset_drag()

    def _play_selected_track(self, event=None):
        pl = self._display_playlist()
        if not pl or not pl.get('tracks'):
            return
        if event is not None:
            idx = self._track_list.nearest(event.y)
            idx = max(0, min(idx, len(pl['tracks']) - 1))
        else:
            sel = self._track_list.curselection()
            idx = int(sel[0]) if sel else 0
        q = self.store.get_queue_playlist()
        if pl['id'] != q['id']:
            self.store.replace_queue_from(pl['id'])
        self.store.set_active(q['id'], idx)
        self.player.set_current_track_from_playlist(start_play=True)

    def _play_playlist_column(self, column_kind):
        lb = {'manual': self._manual_list, 'album': self._album_list, 'artist': self._artist_list}[column_kind]
        sel = lb.curselection()
        if not sel:
            return
        pl_id = self._playlist_id_at(column_kind, int(sel[0]))
        pl = self.store.get_playlist(pl_id)
        if not pl or not pl.get('tracks'):
            return
        self._load_queue_and_play(pl_id, 0)
