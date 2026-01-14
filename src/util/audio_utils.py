import numpy as np

def pcm16le_bytes(x: np.ndarray) -> bytes:
    """Convert float32 mono [-1,1] to PCM16LE bytes with clipping."""
    if x.dtype != np.float32:
        x = x.astype(np.float32, copy=False)
    # clip to [-1, 1]
    np.clip(x, -1.0, 1.0, out=x)
    # scale and cast to little-endian int16 explicitly
    i16 = (x * 32767.0).astype('<i2', copy=False)  # '<i2' = little-endian int16
    return i16.tobytes()