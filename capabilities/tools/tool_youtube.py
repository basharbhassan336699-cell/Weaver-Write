"""
capabilities/tools/tool_youtube.py
==================================
Tool 19: fetch a YouTube video's transcript (the captions YouTube itself
provides) so the pipeline can summarize it or write it out verbatim.

This is the text-transcript path ONLY — it reads the ready-made captions
via youtube-transcript-api. It does NOT download audio or run speech-to-text
(no yt-dlp, no Whisper, no API key). If a video has no captions at all, the
tool returns ok=False quietly instead of inventing content.

Intent is decided by the caller (see _detect_youtube_intent in the
orchestrator): summary | transcript | both, and whether to prefix each line
with an [MM:SS] timestamp.

Every import that touches an optional dependency is done lazily inside a
method, so importing this module never fails even when the library is
absent — the tool just degrades to ok=False.
"""
from __future__ import annotations
import re

from . import BaseTool, ToolResult

TOOL_SPEC = {
    "name": "youtube",
    "description": (
        "Fetch a YouTube video's transcript (its ready-made captions) so the "
        "pipeline can summarize it or reproduce it verbatim. Text transcript "
        "only — no audio download, no speech-to-text."
    ),
    "triggers": [
        "لخّص فيديو", "لخص فيديو", "رابط يوتيوب", "تفريغ فيديو", "فرّغ الفيديو",
        "نص الفيديو", "فيديو يوتيوب", "اكتب ما في الفيديو",
        "youtube", "youtu.be", "summarize video", "video transcript",
        "transcribe video", "yt",
    ],
    "layers": [4],
}

# youtube.com/watch?v=ID  |  youtu.be/ID  |  youtube.com/shorts/ID  |  /embed/ID
_YT_HOST = re.compile(r"(?:^|\.)(?:youtube\.com|youtu\.be)$", re.I)
_YT_ID = re.compile(r"[A-Za-z0-9_-]{11}")


def is_youtube_url(url: str) -> bool:
    """True only for a real YouTube video URL."""
    return extract_video_id(url) is not None


def extract_video_id(url: str):
    """Return the 11-char video id, or None if this isn't a YouTube video URL."""
    if not url or not isinstance(url, str):
        return None
    try:
        from urllib.parse import urlparse, parse_qs
    except Exception:
        return None
    try:
        u = urlparse(url.strip())
    except Exception:
        return None
    host = (u.netloc or "").lower().split(":")[0]
    host = host[4:] if host.startswith("www.") else host
    host = host[2:] if host.startswith("m.") else host
    if not _YT_HOST.search(host):
        return None
    # youtu.be/<id>
    if host == "youtu.be":
        cand = (u.path or "/").lstrip("/").split("/")[0]
        return cand if _YT_ID.fullmatch(cand) else None
    # youtube.com/watch?v=<id>
    if u.path == "/watch":
        v = parse_qs(u.query or "").get("v", [None])[0]
        return v if v and _YT_ID.fullmatch(v) else None
    # youtube.com/shorts/<id>  |  /embed/<id>  |  /v/<id>
    m = re.match(r"/(?:shorts|embed|v)/([A-Za-z0-9_-]{11})", u.path or "")
    return m.group(1) if m else None


def _fmt_ts(seconds: float) -> str:
    """Seconds -> [MM:SS] or [H:MM:SS]."""
    s = int(seconds or 0)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"[{h}:{m:02d}:{sec:02d}]" if h else f"[{m:02d}:{sec:02d}]"


class YouTubeTool(BaseTool):
    TOOL_SPEC = TOOL_SPEC

    async def _execute(self, inputs: dict) -> ToolResult:
        url = (inputs or {}).get("url", "")
        vid = extract_video_id(url)
        if not vid:
            return ToolResult(ok=False, error="not a YouTube video URL")

        # preferred caption languages: caller lang first, then ar, en, then any
        lang = (inputs or {}).get("lang", "ar")
        want = [lang, "ar", "en"]
        prefs, seen = [], set()
        for L in want:
            if L and L not in seen:
                prefs.append(L); seen.add(L)

        with_timing = bool((inputs or {}).get("with_timing", False))

        # ---- fetch captions (lazy import; degrades to ok=False) ----
        snippets = self._fetch_snippets(vid, prefs)
        if not snippets:
            return ToolResult(
                ok=False,
                error="no transcript available for this video "
                      "(captions may be disabled)",
            )

        if with_timing:
            lines = [f"{_fmt_ts(s['start'])} {s['text']}".strip()
                     for s in snippets if s.get("text")]
            text = "\n".join(lines)
        else:
            text = " ".join(s["text"].strip()
                            for s in snippets if s.get("text")).strip()
            text = re.sub(r"\s+", " ", text)

        if not text:
            return ToolResult(ok=False, error="transcript was empty")

        return ToolResult(ok=True, data={
            "video_id": vid,
            "url": url,
            "text": text,
            "with_timing": with_timing,
            "segments": len(snippets),
            "source": "youtube-transcript",
        })

    @staticmethod
    def _fetch_snippets(vid: str, prefs):
        """Return [{text,start,duration}] using youtube-transcript-api.

        Supports both the modern instance API (fetch/list) and the older
        classmethod API (get_transcript). Lazy import; any failure -> []."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except Exception:
            return []

        # modern API: YouTubeTranscriptApi().fetch(id, languages=[...])
        try:
            api = YouTubeTranscriptApi()
            if hasattr(api, "fetch"):
                try:
                    fetched = api.fetch(vid, languages=prefs)
                except Exception:
                    fetched = api.fetch(vid)  # any available language
                out = []
                for sn in fetched:
                    # FetchedTranscriptSnippet has .text/.start/.duration
                    out.append({
                        "text": getattr(sn, "text", "") or "",
                        "start": float(getattr(sn, "start", 0.0) or 0.0),
                        "duration": float(getattr(sn, "duration", 0.0) or 0.0),
                    })
                return out
        except Exception:
            pass

        # legacy API: YouTubeTranscriptApi.get_transcript(id, languages=[...])
        try:
            if hasattr(YouTubeTranscriptApi, "get_transcript"):
                try:
                    raw = YouTubeTranscriptApi.get_transcript(vid, languages=prefs)
                except Exception:
                    raw = YouTubeTranscriptApi.get_transcript(vid)
                return [{
                    "text": d.get("text", "") or "",
                    "start": float(d.get("start", 0.0) or 0.0),
                    "duration": float(d.get("duration", 0.0) or 0.0),
                } for d in (raw or [])]
        except Exception:
            pass

        return []


async def run(inputs: dict) -> ToolResult:
    return await YouTubeTool().run(inputs)
