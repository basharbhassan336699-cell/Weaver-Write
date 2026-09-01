"""
capabilities/tools/tool_youtube.py
==================================
Tool 19: fetch a YouTube video's text so the pipeline can summarize it.

Standalone and self-contained — it does NOT depend on agent_reach (whose
youtube channel file is empty and breaks its imports). Graded fallback:

  1) youtube-transcript-api   → the video's captions (light, no key)
  2) yt-dlp + ffmpeg + Whisper (Groq) → transcribe the audio, ONLY when all
     three are available (yt-dlp on PATH, ffmpeg on PATH, GROQ_API_KEY set)
  3) otherwise → ok=False, quietly (never raises)

Every third-party import (youtube_transcript_api, requests, subprocess, …) is
LAZY, inside the functions — so this module always imports cleanly even when
those packages aren't installed.
"""
from __future__ import annotations
import re
from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "youtube",
    "description": "Fetch and summarize a YouTube video by pulling its "
                   "transcript (youtube-transcript-api) or, as a fallback, "
                   "transcribing its audio via Whisper. Bridges video links to "
                   "readable text for the pipeline.",
    "triggers": ["لخّص فيديو", "رابط يوتيوب", "تفريغ فيديو", "فيديو يوتيوب",
                 "youtube", "summarize video", "video transcript", "yt"],
    "layers": [4],
}

# youtube.com/watch?v=ID | youtu.be/ID | youtube.com/shorts/ID | /embed/ID
# real ids are 11 chars; we accept 6+ so short/test ids are recognised too.
_YT_ID_RE = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|v/)"
    r"|youtu\.be/)([A-Za-z0-9_-]{6,})")
_YT_HOST_RE = re.compile(r"(?:^|\.)(?:youtube(?:-nocookie)?\.com|youtu\.be)$",
                         re.I)


def _video_id(url: str):
    """Return the 11-char video id for a YouTube URL, else None."""
    if not url:
        return None
    m = _YT_ID_RE.search(url)
    if m:
        return m.group(1)
    # bare ?v= without the strict prefix, as a last resort
    try:
        import urllib.parse
        p = urllib.parse.urlparse(url)
        if _YT_HOST_RE.search((p.netloc or "").lower()):
            qs = urllib.parse.parse_qs(p.query or "")
            v = (qs.get("v") or [""])[0]
            if re.fullmatch(r"[A-Za-z0-9_-]{6,}", v or ""):
                return v
            tail = (p.path or "").rstrip("/").split("/")[-1]
            if re.fullmatch(r"[A-Za-z0-9_-]{6,}", tail or ""):
                return tail
    except Exception:
        pass
    return None


def is_youtube_url(url: str) -> bool:
    """True when `url` is a recognisable YouTube video link."""
    return _video_id(url) is not None


# ── layer 1: captions via youtube-transcript-api (lazy import) ──────────────
def _fetch_transcript(video_id: str, langs):
    """Return the joined transcript text, or None. Tolerant of both the old
    (<1.0 classmethod) and new (>=1.0 instance) youtube-transcript-api APIs."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:
        return None

    def _join(segs):
        parts = []
        for s in segs or []:
            t = getattr(s, "text", None)
            if t is None and isinstance(s, dict):
                t = s.get("text", "")
            if t:
                parts.append(t)
        return " ".join(parts).strip()

    # style A — new instance API: YouTubeTranscriptApi().fetch(id, languages=…)
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=langs)
        txt = _join(getattr(fetched, "snippets", fetched))
        if txt:
            return txt
    except Exception:
        pass
    # style B — old classmethod: get_transcript(id, languages=…)
    try:
        data = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
        txt = _join(data)
        if txt:
            return txt
    except Exception:
        pass
    # style C — list then take any available transcript
    try:
        listing = YouTubeTranscriptApi.list_transcripts(video_id)
        for tr in listing:
            try:
                txt = _join(tr.fetch())
                if txt:
                    return txt
            except Exception:
                continue
    except Exception:
        pass
    return None


def _fetch_title(url: str) -> str:
    """Best-effort video title via YouTube oEmbed (stdlib only). '' on failure."""
    try:
        import urllib.request
        import urllib.parse
        import json
        o = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
            {"url": url, "format": "json"})
        req = urllib.request.Request(o, headers={"User-Agent": "WeaverWrite/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return (json.loads(r.read().decode("utf-8")) or {}).get("title", "")
    except Exception:
        return ""


# ── layer 2: audio transcription via yt-dlp + ffmpeg + Whisper (Groq) ───────
def _whisper_available():
    import os
    import shutil
    return bool(shutil.which("yt-dlp") and shutil.which("ffmpeg")
                and os.environ.get("GROQ_API_KEY"))


def _split_audio(path, tmpdir, max_bytes=24 * 1024 * 1024):
    """Split an audio file into <=~24MB chunks using ffmpeg (10-min segments).
    Returns a list of file paths; falls back to [path] on any problem."""
    import os
    import subprocess
    try:
        if os.path.getsize(path) <= max_bytes:
            return [path]
    except Exception:
        return [path]
    seg = os.path.join(tmpdir, "chunk_%03d.mp3")
    try:
        subprocess.run(["ffmpeg", "-i", path, "-f", "segment",
                        "-segment_time", "600", "-c", "copy", seg,
                        "-y", "-loglevel", "error"],
                       check=True, timeout=600)
        chunks = sorted(os.path.join(tmpdir, f) for f in os.listdir(tmpdir)
                        if f.startswith("chunk_"))
        return chunks or [path]
    except Exception:
        return [path]


def _groq_transcribe(path, key, lang):
    """Transcribe one audio file via Groq Whisper. Returns text or None."""
    try:
        import os
        import requests
        with open(path, "rb") as f:
            files = {"file": (os.path.basename(path), f, "audio/mpeg")}
            data = {"model": "whisper-large-v3"}
            if lang in ("ar", "en"):
                data["language"] = lang
            r = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files=files, data=data, timeout=300)
        if r.status_code == 200:
            return (r.json() or {}).get("text", "")
    except Exception:
        pass
    return None


def _whisper_groq(url: str, lang: str):
    """Download audio (yt-dlp) and transcribe it (Groq Whisper). None on fail."""
    if not _whisper_available():
        return None
    import os
    import shutil
    import subprocess
    import tempfile
    key = os.environ.get("GROQ_API_KEY", "")
    tmpdir = tempfile.mkdtemp(prefix="ytaud_")
    try:
        out = os.path.join(tmpdir, "audio.%(ext)s")
        subprocess.run(["yt-dlp", "-x", "--audio-format", "mp3",
                        "--audio-quality", "5", "--no-playlist", "--quiet",
                        "-o", out, url], check=True, timeout=900)
        audio = None
        for f in os.listdir(tmpdir):
            if f.lower().endswith((".mp3", ".m4a", ".webm", ".wav", ".opus")):
                audio = os.path.join(tmpdir, f)
                break
        if not audio:
            return None
        texts = []
        for ch in _split_audio(audio, tmpdir):
            t = _groq_transcribe(ch, key, lang)
            if t:
                texts.append(t)
        txt = "\n".join(texts).strip()
        return txt or None
    except Exception:
        return None
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


class YouTubeTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        url = (inputs.get("url") or "").strip()
        lang = (inputs.get("lang") or "ar").strip() or "ar"
        if not url:
            return ToolResult(ok=False, error="url is required")
        vid = _video_id(url)
        if not vid:
            return ToolResult(ok=False, error="not a youtube url")

        title = _fetch_title(url)

        # 1) captions (light, no key)
        try:
            langs = []
            for L in (lang, "ar", "en"):
                if L and L not in langs:
                    langs.append(L)
            txt = _fetch_transcript(vid, langs)
            if txt and txt.strip():
                return ToolResult(ok=True, data={
                    "text": txt.strip(), "title": title,
                    "source": "youtube-transcript", "url": url})
        except Exception:
            pass

        # 2) audio → Whisper (Groq), only if yt-dlp + ffmpeg + GROQ_API_KEY
        try:
            txt = _whisper_groq(url, lang)
            if txt and txt.strip():
                return ToolResult(ok=True, data={
                    "text": txt.strip(), "title": title,
                    "source": "whisper-groq", "url": url})
        except Exception:
            pass

        # 3) quiet failure — never raise
        return ToolResult(ok=False, error="no transcript or audio available")


async def run(inputs: dict) -> ToolResult:
    return await YouTubeTool().run(inputs)
