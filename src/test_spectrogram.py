# spectro_live.py
import math
import sys
import signal
import time
from collections import deque

import numpy as np
import sounddevice as sd
from scipy.signal import get_window
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.console import Console
from rich.columns import Columns
from shutil import get_terminal_size

console = Console()

# ===== Config (speech preset) =====
FS = 16_000                    # sampling rate
WIN_MS = 25                    # window length in ms
HOP_MS = 10                    # hop length in ms
NFFT = 512                     # FFT size
FMIN = 50                      # Hz
FMAX = 8_000                   # Hz (Nyquist @ 16k is 8k)
DB_MIN = -80.0                 # display floor
DB_MAX = 0.0                   # display ceiling
CHANNELS = 1
DTYPE = "float32"

# ===== Derived =====
WIN_SAMPLES = int(round(WIN_MS * 1e-3 * FS))   # 400
HOP_SAMPLES = int(round(HOP_MS * 1e-3 * FS))   # 160
assert WIN_SAMPLES <= NFFT, "NFFT must be >= window length"

hann = get_window("hann", WIN_SAMPLES, fftbins=True).astype(np.float32)
win_norm = np.sum(hann)  # for rough dBFS reference

freqs = np.fft.rfftfreq(NFFT, d=1.0/FS)  # 0..Nyquist
# Limit to 50..8000 Hz
lo = int(np.ceil(FMIN / (FS / NFFT)))
hi = int(np.floor(FMAX / (FS / NFFT)))
lo = max(lo, 0)
hi = min(hi, len(freqs) - 1)
freq_slice = slice(lo, hi + 1)
freqs_view = freqs[freq_slice]

# Ring buffer to hold the last window of audio
buf = deque(maxlen=WIN_SAMPLES)

# Hop scheduler
samples_since_proc = 0

# Graceful exit
stop_flag = False
def handle_sigint(sig, frame):
    global stop_flag
    stop_flag = True
signal.signal(signal.SIGINT, handle_sigint)

def dbfs(x, eps=1e-12):
    # magnitude to dB relative to full-scale ~1.0 (window energy affects absolute level)
    return 20.0 * np.log10(np.maximum(x, eps))

def group_bins(values, freqs_hz, target_cols):
    """
    Group the per-bin values (dB) into ~target_cols display columns,
    returning per-group mean dB and (f_low, f_high) labels.
    """
    n = len(values)
    cols = max(8, min(target_cols, n))  # clamp reasonable range
    # chunk size in bins
    chunk = int(math.ceil(n / cols))
    grouped_vals = []
    labels = []
    # Bin spacing (Hz)
    if len(freqs_hz) > 1:
        delta = float(freqs_hz[1] - freqs_hz[0])
    else:
        delta = FS / float(NFFT)
    prev_hi_int = None
    for i in range(0, n, chunk):
        j = min(i + chunk, n)
        v = float(np.mean(values[i:j]))
        # Use bin edges (± half-bin) then clamp
        lo_edge = float(freqs_hz[i]) - 0.5 * delta
        hi_edge = float(freqs_hz[j - 1]) + 0.5 * delta
        lo_edge = max(lo_edge, FMIN)
        hi_edge = min(hi_edge, FMAX)
        # Display as contiguous integers with no gaps
        lo_int = int(round(lo_edge))
        if prev_hi_int is not None and lo_int <= prev_hi_int:
            lo_int = prev_hi_int + 1
        hi_int = int(round(hi_edge))
        if hi_int < lo_int:
            hi_int = lo_int
        labels.append((lo_int, hi_int))
        grouped_vals.append(v)
        prev_hi_int = hi_int
    return np.array(grouped_vals, dtype=np.float32), labels

def render_bars(group_db, labels, height, width):
    """
    Render a vertical bar chart as text with given number of rows (height).
    The width is the number of columns (len(group_db)).
    """
    # Normalize to 0..1 within DB_MIN..DB_MAX
    norm = np.clip((group_db - DB_MIN) / (DB_MAX - DB_MIN), 0.0, 1.0)
    # Map to 0..height
    levels = (norm * height).astype(int)

    lines = []
    for row in range(height, 0, -1):
        line_chars = []
        for lvl in levels:
            ch = "█" if lvl >= row else " "
            line_chars.append(ch)
        lines.append("".join(line_chars))
    # Add a simple frequency axis line
    # Show multiple evenly spaced frequency labels
    if labels:
        f_start = labels[0][0]
        f_end = labels[-1][1]
        # Estimate label length (e.g., "8000 Hz")
        sample_label = f"{f_end} Hz"
        label_len = len(sample_label)
        # Choose ticks based on width so labels do not collide
        ideal_ticks = min(12, max(4, width // (label_len + 6)))
        num_ticks = max(4, ideal_ticks)
        # Compute tick positions and raw labels
        tick_positions = [int(round(i * (width - 1) / (num_ticks - 1))) for i in range(num_ticks)]
        tick_labels = [f"{int(round(f_start + i * (f_end - f_start) / (num_ticks - 1)))} Hz" for i in range(num_ticks)]
        # Tick marks line
        axis_line = [" "] * width
        for pos in tick_positions:
            axis_line[pos] = "|"
        lines.append("".join(axis_line))
        # Label line with collision avoidance
        label_line = [" "] * width
        last_end = -1
        for i, (pos, label) in enumerate(zip(tick_positions, tick_labels)):
            if i == num_ticks - 1:
                # Force the last one to the right edge
                start = width - len(label)
            else:
                # Center the label on pos
                start = pos - len(label) // 2
                if start < 0:
                    start = 0
                if start + len(label) > width:
                    start = width - len(label)
            # Skip if this would overlap the previous label
            if start <= last_end:
                continue
            for j, ch in enumerate(label):
                idx = start + j
                if 0 <= idx < width:
                    label_line[idx] = ch
            last_end = start + len(label) - 1
        lines.append("".join(label_line))
    return "\n".join(lines)

def make_tables(group_db, labels, max_rows_per_col=32):
    """
    Build multiple numeric tables of grouped bands and their dB levels,
    arranged side-by-side in columns to cover all bands.
    """
    n = len(group_db)
    base_rows = max(1, max_rows_per_col)
    num_cols = int(math.ceil(n / base_rows))
    if n > base_rows * 3:
        num_cols = max(4, num_cols)
        rows = int(math.ceil(n / num_cols))
        rows = min(rows, base_rows)
    else:
        rows = base_rows
    tables = []
    for c in range(num_cols):
        table = Table(show_header=True, header_style="bold")
        table.add_column("Band")
        table.add_column("Freq Range (Hz)", justify="right")
        table.add_column("Level (dBFS)", justify="right")
        start_idx = c * rows
        end_idx = min((c + 1) * rows, n)
        for i in range(start_idx, end_idx):
            f_lo, f_hi = labels[i]
            band_name = f"B{i+1}"
            table.add_row(
                band_name,
                f"{f_lo}-{f_hi}",
                f"{group_db[i]:6.1f}"
            )
        tables.append(table)
    return Columns(tables, equal=True, expand=True)

def build_layout(graph_text, table_obj):
    layout = Layout()
    layout.split(Layout(name="top", ratio=2), Layout(name="bottom", ratio=3))
    layout["top"].update(Panel(graph_text, title="Realtime Spectrum 50-8000 Hz", border_style="cyan"))
    layout["bottom"].update(Panel(table_obj, title="Numeric Levels (grouped bins)", border_style="cyan"))
    return layout

def process_frame(x):
    """
    x: 1D float32 array of length WIN_SAMPLES (most recent window)
    Returns grouped dB values and labels plus a pre-rendered graph string.
    """
    # Apply Hann window and zero-pad to NFFT
    w = hann * x[:WIN_SAMPLES]
    X = np.fft.rfft(w, n=NFFT)
    # Magnitude
    mag = np.abs(X)
    # Slice to desired range
    mag = mag[freq_slice]
    # Convert to dBFS. Normalize roughly by window energy so 0 dBFS ~ full-scale tone.
    # Add small factor to relate to RMS across window.
    mag_db = dbfs(mag / (win_norm / 2.0 + 1e-12))

    # Determine display width and height
    term = get_terminal_size((100, 30))
    # Leave margins for panels; estimate graph width as ~min(term.columns-6, 120)
    graph_cols = max(40, term.columns - 8)
    graph_rows = max(8, min(term.lines // 3, 14))
    # Heuristic for table rows per column based on remaining height.
    # Leave ~8 lines for panel borders, titles, and spacing.
    table_rows = max(24, term.lines - graph_rows - 8)

    grouped_db, labels = group_bins(mag_db, freqs_view, graph_cols)
    graph_text = render_bars(grouped_db, labels, height=graph_rows, width=len(grouped_db))
    return grouped_db, labels, graph_text, table_rows

def main():
    console.print("[bold]Mic realtime spectrogram (binned) - Ctrl+C to quit[/bold]")
    # Pre-fill buffer with zeros so we can process ASAP
    for _ in range(WIN_SAMPLES):
        buf.append(0.0)

    def audio_cb(indata, frames, time_info, status):
        if status:
            # Non-fatal, print once in a while
            pass
        # Mono
        x = indata[:, 0]
        for s in x:
            buf.append(float(s))

    with sd.InputStream(
        channels=CHANNELS,
        callback=audio_cb,
        samplerate=FS,
        dtype=DTYPE,
        blocksize=HOP_SAMPLES,   # drive ~10 ms hops
        latency="low"
    ):
        # Live render loop
        with Live(auto_refresh=False, console=console) as live:
            while not stop_flag:
                # Process every hop
                if len(buf) >= WIN_SAMPLES:
                    windowed = np.frombuffer(np.array(buf, dtype=np.float32), dtype=np.float32, count=WIN_SAMPLES)
                    grouped_db, labels, graph_text, table_rows = process_frame(windowed)
                    table = make_tables(grouped_db, labels, max_rows_per_col=table_rows)
                    layout = build_layout(graph_text, table)
                    live.update(layout, refresh=True)
                # Small sleep to avoid 100% CPU; ~hop rate
                time.sleep(HOP_MS / 1000.0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass