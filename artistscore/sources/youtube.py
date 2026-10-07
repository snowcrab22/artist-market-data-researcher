"""YouTube Data API v3 (free key): subscribers, channel views, engagement on the latest uploads."""

from __future__ import annotations

from artistscore import http
from artistscore.models import Metric, SourceResult
from artistscore.sources.base import SourceContext, SourceError

NAME = "youtube"
LABEL = "YouTube"
REQUIRES = ["YOUTUBE_API_KEY"]
API = "https://www.googleapis.com/youtube/v3"
RECENT_UPLOADS = 10


async def _find_channel_id(ctx: SourceContext, key: str) -> str | None:
    found = await http.get_json(ctx.client, f"{API}/search", params={
        "part": "snippet", "type": "channel", "q": ctx.name, "maxResults": 5, "key": key})
    for item in found.get("items", []):
        title = item["snippet"]["title"]
        if title.casefold() == ctx.name.casefold() and not title.endswith(" - Topic"):
            return item["id"]["channelId"]
    return None


async def fetch(ctx: SourceContext) -> SourceResult:
    key = ctx.settings.get("YOUTUBE_API_KEY")
    if not key:
        return SourceResult.skipped(NAME, "YOUTUBE_API_KEY not set")
    params = {"part": "statistics,contentDetails,snippet", "key": key}
    details: dict = {}
    if ctx.links.youtube_channel_id:
        params["id"] = ctx.links.youtube_channel_id
    elif ctx.links.youtube_handle:
        params["forHandle"] = "@" + ctx.links.youtube_handle.lstrip("@")
    else:
        channel_id = await _find_channel_id(ctx, key)
        if not channel_id:
            return SourceResult.skipped(NAME, "no YouTube channel linked and no exact-name channel found")
        params["id"] = channel_id
        details["links"] = {"youtube_channel_id": channel_id}
    items = (await http.get_json(ctx.client, f"{API}/channels", params=params)).get("items", [])
    if not items:
        raise SourceError("YouTube channel not found")
    channel = items[0]
    stats = channel["statistics"]
    details["url"] = f"https://www.youtube.com/channel/{channel['id']}"
    metrics = [Metric("youtube_views", float(stats.get("viewCount", 0)), NAME)]
    if not stats.get("hiddenSubscriberCount") and "subscriberCount" in stats:
        metrics.append(Metric("youtube_subscribers", float(stats["subscriberCount"]), NAME))

    uploads = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if uploads:
        playlist = await http.get_json(ctx.client, f"{API}/playlistItems", params={
            "part": "contentDetails", "playlistId": uploads, "maxResults": RECENT_UPLOADS, "key": key})
        video_ids = [i["contentDetails"]["videoId"] for i in playlist.get("items", [])]
        if video_ids:
            videos = await http.get_json(ctx.client, f"{API}/videos", params={
                "part": "statistics", "id": ",".join(video_ids), "key": key})
            views = interactions = 0.0
            for video in videos.get("items", []):
                s = video.get("statistics", {})
                views += float(s.get("viewCount", 0))
                interactions += float(s.get("likeCount", 0)) + float(s.get("commentCount", 0))
            if views > 0:
                metrics.append(Metric("youtube_engagement_rate", interactions / views, NAME,
                                      f"(likes + comments) ÷ views, last {len(video_ids)} uploads"))
    return SourceResult.ok(NAME, metrics, details)
