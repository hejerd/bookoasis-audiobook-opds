"""Generate short, original test tones; no copyrighted recordings are used.

Run with the verification environment, which needs imageio-ffmpeg and Pillow.
The plugin itself does not execute external programs.
"""
from pathlib import Path
import hashlib
import json
import subprocess

import imageio_ffmpeg
from PIL import Image, ImageDraw


def main():
    target = Path(__file__).resolve().parent / "samples"
    target.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    common = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
              "-i", "sine=frequency=440:sample_rate=44100:duration=2", "-ac", "1"]
    commands = {
        "tone.mp3": ["-codec:a", "libmp3lame", "-b:a", "64k"],
        "tone.m4a": ["-codec:a", "aac", "-b:a", "64k", "-movflags", "+faststart", "-f", "mp4"],
        "tone.m4b": ["-codec:a", "aac", "-b:a", "64k", "-movflags", "+faststart", "-f", "mp4"],
    }
    for filename, options in commands.items():
        subprocess.run(common + options + [str(target / filename)], check=True)
    cover = Image.new("RGB", (240, 240), "#173450")
    draw = ImageDraw.Draw(cover)
    draw.rectangle((30, 45, 210, 195), outline="#dce9ef", width=4)
    draw.text((60, 110), "OPDS TEST", fill="#ffffff")
    cover.save(target / "cover.jpg", quality=85)
    manifest = {
        "description": "Original 440 Hz sine tones generated for plugin verification; no speech or copyrighted media.",
        "duration_seconds": 2,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(target.iterdir()) if path.suffix in {".mp3", ".m4a", ".m4b", ".jpg"}
        },
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
