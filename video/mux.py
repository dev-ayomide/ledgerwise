"""Combine the screen recording with the narration at the recorded scene start times."""

import glob
import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
meta = json.loads((HERE / "starts.json").read_text())
raw = str(HERE / "silent.mp4")
keys = list(meta["starts"])
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", raw]
for k in keys:
    cmd += ["-i", str(HERE / "audio" / f"{k}.wav")]
filters, labels = [], []
for i, k in enumerate(keys, start=1):
    start = meta["starts"][k]
    if start < 0:  # the first frame arrived after the scene began: drop that much audio
        filters.append(f"[{i}:a]atrim=start={-start:.3f},asetpts=PTS-STARTPTS[a{i}]")
    else:
        ms = int(start * 1000)
        filters.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
    labels.append(f"[a{i}]")
filters.append("".join(labels) + f"amix=inputs={len(keys)}:normalize=0,volume=1.3,alimiter=limit=0.9[aout]")
out = HERE / "ledgerwise-demo.mp4"
cmd += [
    "-filter_complex", ";".join(filters),
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "copy",
    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out),
]
subprocess.run(cmd, check=True)
dur = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)]).decode().strip()
print("wrote", out, "duration", dur, "s")
