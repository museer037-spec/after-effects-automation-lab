
import argparse
import json
import wave
from array import array
from pathlib import Path


def detect_silence(audio_path, threshold_db=-35, min_duration=0.5):
    """Detect quiet sections in a mono or stereo PCM WAV file."""
    with wave.open(str(audio_path), "rb") as audio:
        channels = audio.getnchannels()
        sample_width = audio.getsampwidth()
        sample_rate = audio.getframerate()
        frames = audio.getnframes()

        if audio.getcomptype() != "NONE":
            raise ValueError("Use an uncompressed PCM WAV file.")

        if sample_width not in (1, 2, 3, 4):
            raise ValueError("Unsupported PCM sample width.")

        raw = audio.readframes(frames)

    if sample_width == 1:
        samples = array("B", raw)
        midpoint = 128
        peak = 128
    elif sample_width == 2:
        samples = array("h")
        samples.frombytes(raw)
        if __import__("sys").byteorder != "little":
            samples.byteswap()
        midpoint = 0
        peak = 32768
    else:
        # Convert 24-bit or 32-bit PCM into signed samples.
        step = sample_width
        values = []
        for i in range(0, len(raw), step):
            chunk = int.from_bytes(raw[i:i + step], "little", signed=False)
            sign_bit = 1 << (8 * step - 1)
            if chunk & sign_bit:
                chunk -= 1 << (8 * step)
            values.append(chunk)
        samples = values
        midpoint = 0
        peak = 1 << (8 * sample_width - 1)

    threshold = peak * (10 ** (threshold_db / 20))
    window_size = max(1, int(sample_rate * 0.02))
    quiet_windows = []
    silence_start = None

    for frame_start in range(0, len(samples), window_size * channels):
        chunk = samples[frame_start:frame_start + window_size * channels]
        if not chunk:
            break

        rms = (
            sum((sample - midpoint) ** 2 for sample in chunk)
            / len(chunk)
        ) ** 0.5

        timestamp = frame_start / (sample_rate * channels)
        is_quiet = rms < threshold

        if is_quiet and silence_start is None:
            silence_start = timestamp
        elif not is_quiet and silence_start is not None:
            end = timestamp
            if end - silence_start >= min_duration:
                quiet_windows.append({
                    "start": round(silence_start, 3),
                    "end": round(end, 3),
                    "duration": round(end - silence_start, 3)
                })
            silence_start = None

    duration = len(samples) / (sample_rate * channels)
    if silence_start is not None and duration - silence_start >= min_duration:
        quiet_windows.append({
            "start": round(silence_start, 3),
            "end": round(duration, 3),
            "duration": round(duration - silence_start, 3)
        })

    return {
        "file": str(audio_path),
        "duration": round(duration, 3),
        "threshold_db": threshold_db,
        "min_silence_duration": min_duration,
        "silences": quiet_windows
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Detect quiet sections in a PCM WAV podcast recording."
    )
    parser.add_argument("audio", help="Path to an uncompressed PCM WAV file")
    parser.add_argument("--threshold-db", type=float, default=-35)
    parser.add_argument("--min-duration", type=float, default=0.5)
    args = parser.parse_args()

    result = detect_silence(
        args.audio, args.threshold_db, args.min_duration
    )
    output = Path(args.audio).with_suffix(".silences.json")
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nResults saved to: {output}")
