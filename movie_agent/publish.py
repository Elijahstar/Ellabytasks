"""Upload to YouTube, Instagram Reels and TikTok.

Every function defaults to dry-run in the CLI: it prints what it would do. Pass
--go to actually post. Credentials come from environment variables or files you
create yourself; see README.md -> Publishing.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from .models import Script


# --------------------------------------------------------------- YouTube ---

def upload_youtube(
    video: Path,
    script: Script,
    privacy: str = "private",
    srt: Path | None = None,
    chapters: Path | None = None,
    client_secret: str = "client_secret.json",
    token_file: str = "youtube_token.json",
) -> str:
    """Upload with the YouTube Data API v3 (OAuth desktop flow). Returns the video id."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    scopes = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube.force-ssl"]
    creds = Credentials.from_authorized_user_file(token_file, scopes) if Path(token_file).exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(client_secret, scopes).run_local_server(port=0)
        Path(token_file).write_text(creds.to_json())

    yt = build("youtube", "v3", credentials=creds)
    desc = script.social.youtube_description
    if chapters and chapters.exists():
        desc += "\n\nChapters:\n" + chapters.read_text()
    credits = video.parent / "image_credits_required.txt"
    credit_text = credits.read_text().strip() if credits.exists() else ""
    footer = "\n\nThis video was created with AI tools."
    if credit_text and len(desc) + len(credit_text) + len(footer) + 2 <= 5000:
        desc += "\n\n" + credit_text
    elif credit_text:
        desc += "\n\nImage credits: see the pinned comment."
        print(f"  ! The image credits don't fit in YouTube's 5000-character description.\n"
              f"    Post the text of {credits} as a comment and pin it after the upload.")
    desc += footer
    body = {
        "snippet": {
            "title": script.social.youtube_title[:100],
            "description": desc[:5000],
            "tags": script.social.tags[:30],
            "categoryId": "1",  # Film & Animation
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  uploaded {int(status.progress() * 100)}%")
    vid = resp["id"]
    if srt and srt.exists():
        yt.captions().insert(
            part="snippet",
            body={"snippet": {"videoId": vid, "language": "en", "name": "English"}},
            media_body=MediaFileUpload(str(srt)),
        ).execute()
    return vid


# -------------------------------------------------------- Instagram Reels ---

def upload_instagram_reel(video_url: str, caption: str) -> str:
    """Publish a Reel with the Instagram Graph API.

    Needs a Business/Creator account linked to a Facebook Page, plus env vars
    IG_USER_ID and IG_ACCESS_TOKEN. Instagram downloads the file itself, so
    video_url must be a public HTTPS link (S3, Cloudflare R2, Google Cloud Storage...).
    """
    user, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    base = f"https://graph.facebook.com/v21.0/{user}"
    r = requests.post(f"{base}/media", data={
        "media_type": "REELS", "video_url": video_url, "caption": caption[:2200],
        "share_to_feed": "true", "access_token": token,
    }, timeout=60)
    r.raise_for_status()
    container = r.json()["id"]
    for _ in range(60):  # wait for Instagram to process the video (up to ~10 min)
        s = requests.get(f"https://graph.facebook.com/v21.0/{container}",
                         params={"fields": "status_code", "access_token": token}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram could not process the video: {s}")
        time.sleep(10)
    r = requests.post(f"{base}/media_publish", data={"creation_id": container, "access_token": token}, timeout=60)
    r.raise_for_status()
    return r.json()["id"]


# ----------------------------------------------------------------- TikTok ---

def upload_tiktok(video: Path, caption: str, privacy: str = "SELF_ONLY") -> str:
    """Post with the TikTok Content Posting API (direct post, file upload).

    Needs env var TIKTOK_ACCESS_TOKEN with the video.publish scope. Until your
    app passes TikTok's audit, posts are forced to private (SELF_ONLY).
    """
    token = os.environ["TIKTOK_ACCESS_TOKEN"]
    size = video.stat().st_size
    if size > 64 * 1024 * 1024:
        raise RuntimeError("Single-chunk TikTok upload is limited to 64 MB; shorten or compress the clip.")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers=headers,
        json={
            "post_info": {"title": caption[:2200], "privacy_level": privacy,
                          "is_aigc": True},
            "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                            "chunk_size": size, "total_chunk_count": 1},
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()["data"]
    with open(video, "rb") as fh:
        up = requests.put(data["upload_url"], data=fh, timeout=600, headers={
            "Content-Type": "video/mp4", "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        })
    up.raise_for_status()
    return data["publish_id"]
