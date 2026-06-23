"""Tint native Windows title bars to match Cursor Dark."""
import sys

if sys.platform == 'win32':
    import ctypes

    _user32 = ctypes.windll.user32
    _dwmapi = ctypes.windll.dwmapi
    _shcore = getattr(ctypes.windll, 'shcore', None)
    _gdi32 = ctypes.windll.gdi32

    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
    DWMWA_BORDER_COLOR = 34
    DWMWA_CAPTION_COLOR = 35
    DWMWA_TEXT_COLOR = 36
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_ROUND = 2
    DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
    LOGPIXELSY = 90


def enable_windows_dpi_awareness():
    """Enable per-monitor DPI awareness so Tk client text matches title-bar sharpness."""
    if sys.platform != 'win32':
        return False
    try:
        _user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        _user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        if _user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return True
    except (AttributeError, OSError):
        pass
    if _shcore is not None:
        try:
            _shcore.SetProcessDpiAwareness(2)
            return True
        except (AttributeError, OSError):
            pass
    try:
        return bool(_user32.SetProcessDPIAware())
    except (AttributeError, OSError):
        return False


def primary_monitor_dpi():
    if sys.platform != 'win32':
        return 96
    try:
        hdc = _user32.GetDC(0)
        if not hdc:
            return 96
        dpi = _gdi32.GetDeviceCaps(hdc, LOGPIXELSY)
        _user32.ReleaseDC(0, hdc)
        return int(dpi) if dpi > 0 else 96
    except (AttributeError, OSError):
        return 96


def ui_scale_factor(widget=None):
    dpi = primary_monitor_dpi()
    if widget is not None:
        try:
            widget.update_idletasks()
            measured = widget.winfo_fpixels('1i')
            if measured > 0:
                dpi = measured
        except Exception:
            pass
    return dpi / 96.0


def scale_ui(value, widget=None):
    return max(1, round(float(value) * ui_scale_factor(widget)))


def scaled_window_geometry(widget, width, height, x=None, y=None):
    w = scale_ui(width, widget)
    h = scale_ui(height, widget)
    if x is not None and y is not None:
        return f'{w}x{h}+{scale_ui(x, widget)}+{scale_ui(y, widget)}'
    return f'{w}x{h}'


def scaled_minsize(widget, min_width, min_height):
    return scale_ui(min_width, widget), scale_ui(min_height, widget)


def apply_tk_dpi_scaling(widget):
    """Sync Tk logical units with the display DPI."""
    if sys.platform != 'win32':
        return
    try:
        widget.update_idletasks()
        dpi = widget.winfo_fpixels('1i')
        if dpi <= 0:
            dpi = primary_monitor_dpi()
        target = dpi / 72.0
        current = float(widget.tk.call('tk', 'scaling'))
        if abs(current - target) > 0.05:
            widget.tk.call('tk', 'scaling', target)
    except Exception:
        pass


def resolve_sharp_ui_font(widget, family='Microsoft YaHei UI', points=11):
    """Use device-pixel font size for clear rendering at native DPI."""
    if sys.platform != 'win32':
        return (family, points)
    try:
        widget.update_idletasks()
        dpi = widget.winfo_fpixels('1i')
        if dpi <= 0:
            dpi = primary_monitor_dpi()
        scale = dpi / 96.0
        pt = 11 if scale >= 1.25 else points
        px = round(widget.winfo_fpixels(f'{pt}p'))
        px = max(px, round(pt * scale))
        return (family, -px)
    except Exception:
        return (family, points)


def _hwnd(widget):
    if sys.platform != 'win32':
        return None
    widget.update_idletasks()
    wid = widget.winfo_id()
    hwnd = _user32.GetParent(wid)
    return hwnd or wid


def _colorref(hex_color):
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return r | (g << 8) | (b << 16)


def _set_dwm_int(hwnd, attr, value):
    val = ctypes.c_int(value)
    try:
        _dwmapi.DwmSetWindowAttribute(
            hwnd, attr, ctypes.byref(val), ctypes.sizeof(val),
        )
        return True
    except OSError:
        return False


def apply_cursor_dark_titlebar(
    window,
    *,
    caption='#141414',
    text='#CCCCCC',
    border='#2A2A2A',
    rounded=True,
):
    """Keep the normal title bar; only recolor it. No-op off Windows."""
    if sys.platform != 'win32':
        return False
    hwnd = _hwnd(window)
    if not hwnd:
        return False

    _set_dwm_int(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
    _set_dwm_int(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1)
    _set_dwm_int(hwnd, DWMWA_CAPTION_COLOR, _colorref(caption))
    _set_dwm_int(hwnd, DWMWA_TEXT_COLOR, _colorref(text))
    _set_dwm_int(hwnd, DWMWA_BORDER_COLOR, _colorref(border))
    if rounded:
        _set_dwm_int(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
    return True


def schedule_cursor_dark_titlebar(window, **kwargs):
    def _apply(_event=None):
        if window.winfo_exists():
            apply_cursor_dark_titlebar(window, **kwargs)

    window.after(0, _apply)
    window.bind('<Map>', _apply, add='+')


# WM_DROPFILES = 0x0233, WM_COPYGLOBALDATA = 0x0049
_WM_DROPFILES = 0x0233
_WM_COPYGLOBALDATA = 0x0049
_MSGFLT_ALLOW = 1


def allow_drop_messages(hwnd):
    """Allow WM_DROPFILES through UIPI so drag-drop works even when elevated."""
    if sys.platform != 'win32':
        return
    try:
        _user32.ChangeWindowMessageFilterEx(hwnd, _WM_DROPFILES, _MSGFLT_ALLOW, None)
        _user32.ChangeWindowMessageFilterEx(hwnd, _WM_COPYGLOBALDATA, _MSGFLT_ALLOW, None)
    except (AttributeError, OSError):
        pass


def schedule_allow_drop(window):
    """Call allow_drop_messages once the window handle is available."""
    if sys.platform != 'win32':
        return

    def _apply(_event=None):
        if window.winfo_exists():
            hwnd = _hwnd(window)
            if hwnd:
                allow_drop_messages(hwnd)

    window.after(0, _apply)
    window.bind('<Map>', _apply, add='+')
