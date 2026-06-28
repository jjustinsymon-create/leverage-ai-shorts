#!/usr/bin/env python3
"""
Leverage AI — Daily Faceless Short Generator
Cost: $0/month forever
Stack: Gemini Flash API (free) + Edge-TTS (free) + Pexels API (free) + MoviePy (free) + YouTube API (free)
Runs automatically every day via GitHub Actions (free)
"""

import os, sys, json, asyncio, requests, textwrap
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import edge_tts
import google.generativeai as genai
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip, ColorClip,
    CompositeVideoClip, concatenate_videoclips
)
from moviepy.video.fx.all import crop as mpy_crop
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# ── CONFIG ────────────────────────────────────────────────────────────────────
CHANNEL = "Leverage AI"
TAGLINE = "Work less. Build more."
W, H = 1080, 1920   # 9:16 vertical
FPS   = 30

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_KEY = os.environ["PEXELS_API_KEY"]
YT_CREDS   = os.environ["YOUTUBE_TOKEN"]

# Load topic list and pick today's
with open("topics.json") as f:
    TOPICS = json.load(f)
day   = datetime.utcnow().timetuple().tm_yday
TOPIC = TOPICS[(day - 1) % len(TOPICS)]

# Temp file paths
AUDIO   = "/tmp/voice.mp3"
FOOTAGE = "/tmp/footage.mp4"
OUTPUT  = "/tmp/short.mp4"


# ── STEP 1: GENERATE SCRIPT ───────────────────────────────────────────────────
def make_script(topic: str) -> str:
    """Use Google Gemini Flash (free tier) to generate a 60-second script."""
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""Write a 60-second YouTube Shorts script for the Leverage AI channel.

Topic: {topic}
Channel niche: Practical AI tips for freelancers and solopreneurs.

Rules:
- Open with a hook in the first 3 seconds — no intro, no "hey guys", straight into the point
- One clear, specific, actionable AI tip or insight
- Short punchy sentences — conversational, no corporate language
- End exactly with: "Follow Leverage AI for one AI tip every day."
- Maximum 150 words
- Return ONLY the spoken script. Nothing else. No labels, no formatting."""

    response = model.generate_content(prompt)
    return response.text.strip()


# ── STEP 2: GENERATE VOICEOVER ────────────────────────────────────────────────
async def make_voice(script: str, path: str):
    """Edge-TTS: Microsoft neural voices, completely free, no API key needed."""
    voice = "en-US-AndrewMultilingualNeural"  # Natural male voice
    comm  = edge_tts.Communicate(script, voice, rate="+8%", pitch="+0Hz")
    await comm.save(path)


# ── STEP 3: FETCH STOCK FOOTAGE ───────────────────────────────────────────────
def fetch_footage(topic: str, path: str) -> bool:
    """Pexels API is free. Downloads portrait-orientation stock video."""
    headers = {"Authorization": PEXELS_KEY}
    queries = [
        topic[:40],
        "artificial intelligence technology",
        "productivity modern office",
        "digital technology abstract",
        "business dark background",
    ]
    for q in queries:
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": q, "orientation": "portrait", "size": "medium",
                        "per_page": 15, "min_duration": 10},
                timeout=15
            )
            if r.status_code != 200:
                continue
            videos = r.json().get("videos", [])
            for vid in videos:
                files = sorted(vid.get("video_files", []),
                               key=lambda x: x.get("width", 0), reverse=True)
                for f in files:
                    if f.get("width", 0) >= 540:
                        dl = requests.get(f["link"], stream=True, timeout=60)
                        if dl.status_code == 200:
                            with open(path, "wb") as out:
                                for chunk in dl.iter_content(8192):
                                    out.write(chunk)
                            print(f"  ✓ Downloaded footage for: {q}")
                            return True
        except Exception as e:
            print(f"  ⚠ Footage query '{q}' failed: {e}")
            continue
    return False


# ── STEP 4: BUILD VIDEO ───────────────────────────────────────────────────────
def _load_font(size: int, bold: bool = False):
    """Load DejaVu font (installed in GitHub Actions via apt)."""
    variants = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans-{'Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans-{'Bold' if bold else 'Regular'}.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in variants:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()


def _render_text_frame(text: str) -> np.ndarray:
    """Render a chunk of script text onto a transparent frame using Pillow."""
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(74, bold=True)

    lines   = textwrap.wrap(text, width=16)
    line_h  = 86
    total_h = len(lines) * line_h
    start_y = int(H * 0.42) - total_h // 2

    for i, line in enumerate(lines):
        bbox  = draw.textbbox((0, 0), line, font=font)
        tw    = bbox[2] - bbox[0]
        x     = (W - tw) // 2
        y     = start_y + i * line_h
        # Drop shadow
        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 200))
        # Main text (white)
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    return np.array(img)[:, :, :3]   # RGB only for MoviePy


def _render_branding() -> np.ndarray:
    """Render channel name + tagline at the top of the frame."""
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_big = _load_font(48, bold=True)
    font_sm  = _load_font(28, bold=False)

    # Channel name (purple-ish white)
    bb  = draw.textbbox((0, 0), CHANNEL, font=font_big)
    x   = (W - (bb[2] - bb[0])) // 2
    draw.text((x + 2, 92), CHANNEL, font=font_big, fill=(0, 0, 0, 160))
    draw.text((x, 90),     CHANNEL, font=font_big, fill=(180, 140, 255, 255))

    # Tagline
    bb2 = draw.textbbox((0, 0), TAGLINE, font=font_sm)
    x2  = (W - (bb2[2] - bb2[0])) // 2
    draw.text((x2, 148), TAGLINE, font=font_sm, fill=(200, 200, 200, 200))

    return np.array(img)[:, :, :3]


def build_video(script: str, audio_path: str, footage_path: str, output: str):
    """Assemble the final 9:16 short video."""
    audio    = AudioFileClip(audio_path)
    duration = audio.duration

    # Background footage: loop if needed, crop to 9:16, resize
    bg = VideoFileClip(footage_path, audio=False)
    if bg.duration < duration:
        reps = int(duration / bg.duration) + 2
        bg   = concatenate_videoclips([bg] * reps)
    bg = bg.subclip(0, duration)

    if (bg.w / bg.h) > (W / H):
        nw = int(bg.h * W / H)
        bg = bg.crop(x_center=bg.w / 2, width=nw)
    else:
        nh = int(bg.w * H / W)
        bg = bg.crop(y_center=bg.h / 2, height=nh)
    bg = bg.resize((W, H))

    # Dark overlay
    overlay = ColorClip((W, H), color=(0, 0, 0)).set_opacity(0.58).set_duration(duration)

    # Static branding layer
    brand = ImageClip(_render_branding()).set_duration(duration).set_position("center")

    # Timed text chunks
    words      = script.split()
    chunk_size = 7
    chunks     = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    t_per      = duration / max(len(chunks), 1)

    text_clips = []
    for i, chunk in enumerate(chunks):
        frame = _render_text_frame(chunk)
        clip  = (ImageClip(frame)
                 .set_start(i * t_per)
                 .set_duration(t_per)
                 .fadein(0.12)
                 .fadeout(0.12)
                 .set_position("center"))
        text_clips.append(clip)

    # Compose and export
    final = CompositeVideoClip([bg, overlay, brand] + text_clips, size=(W, H))
    final = final.set_audio(audio).set_duration(duration)
    final.write_videofile(
        output, fps=FPS, codec="libx264", audio_codec="aac",
        preset="ultrafast", threads=4, logger=None
    )
    print(f"  ✓ Video built: {output}")


# ── STEP 5: UPLOAD TO YOUTUBE ─────────────────────────────────────────────────
def upload_to_youtube(video_path: str, topic: str, script: str):
    """Upload to YouTube using OAuth credentials stored as GitHub Secret."""
    creds_data = json.loads(YT_CREDS)
    creds = Credentials(
        token          = creds_data.get("token"),
        refresh_token  = creds_data["refresh_token"],
        token_uri      = "https://oauth2.googleapis.com/token",
        client_id      = creds_data["client_id"],
        client_secret  = creds_data["client_secret"],
        scopes         = ["https://www.googleapis.com/auth/youtube.upload"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    yt = build("youtube", "v3", credentials=creds)

    # Auto-generate title from first sentence of script
    first_sentence = script.split(".")[0].strip()[:80]
    title = f"{first_sentence} #Shorts"

    description = (
        f"{script}\n\n"
        f"{'─' * 40}\n"
        f"{CHANNEL} — Daily AI tips for solopreneurs and freelancers.\n"
        f"One practical AI tip every day. Subscribe so you don't miss one.\n"
        f"{'─' * 40}\n"
        f"#AITips #AIProductivity #SolopreneurAI #LeverageAI #AIShorts #AITools"
    )
    tags = [
        "AI tips", "AI productivity", "solopreneur AI", "AI tools 2025",
        "freelancer AI", "Claude AI", "ChatGPT tips", "AI workflow",
        "Leverage AI", "AI automation", "AI for creators", "work smarter"
    ]

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": "28",  # Science & Technology
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        }
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4",
                            resumable=True, chunksize=4 * 1024 * 1024)
    req  = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()

    vid_id = resp["id"]
    print(f"  ✓ Uploaded: https://youtu.be/{vid_id}")
    return vid_id


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n🚀 Leverage AI Daily Short Generator")
    print(f"📌 Today's topic: {TOPIC}\n")

    print("✍️  Generating script with Gemini Flash...")
    script = make_script(TOPIC)
    print(f"   Preview: {script[:120]}...\n")

    print("🎤 Generating voiceover with Edge-TTS...")
    asyncio.run(make_voice(script, AUDIO))

    print("🎬 Fetching stock footage from Pexels...")
    if not fetch_footage(TOPIC, FOOTAGE):
        print("   Trying generic fallback...")
        fetch_footage("technology abstract", FOOTAGE)

    print("🎞️  Building video with MoviePy...")
    build_video(script, AUDIO, FOOTAGE, OUTPUT)

    print("📤 Uploading to YouTube...")
    upload_to_youtube(OUTPUT, TOPIC, script)

    print("\n✅ Done! New Short is live.\n")


if __name__ == "__main__":
    main()
