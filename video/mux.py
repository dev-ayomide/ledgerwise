"""Combine the screen recording with the narration at the recorded scene start times."""

import glob
import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
meta = json.loads((HERE / "starts.json").read_text())
raw = sorted(glob.glob(str(HERE / "raw" / "*.webm")))[-1]
keys = list(meta["starts"])
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", raw]
for k in keys:
    cmd += ["-i", str(HERE / "audio" / f"{k}.wav")]
filters, labels = [], []
for i, k in enumerate(keys, start=1):
    ms = int(meta["starts"][k] * 1000)
    filters.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
    labels.append(f"[a{i}]")
filters.append("".join(labels) + f"amix=inputs={len(keys)}:normalize=0,volume=1.6[aout]")
out = HERE / "ledgerwise-demo.mp4"
cmd += [
    "-filter_complex", ";".join(filters),
    "-map", "0:v", "-map", "[aout]",
    "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p",
    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30",
    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
dur = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)]).decode().strip()
print("wrote", out, "duration", dur, "s")
