"""Wikipedia pageviews (Wikimedia REST API, no key): awareness level and attention trend."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean
from urllib.parse import quote

from artistscore import http
from artistscore.models import Metric, SourceResult
from artistscore.sources.base import SourceContext, SourceError

NAME = "wikipedia"
LABEL = "Wikipedia pageviews"
REQUIRES: list[str] = []


def _window(today: date) -> tuple[str, str]:
    first_of_month = today.replace(day=1)
    end = first_of_month - timedelta(days=1)
    start = date(first_of_month.year - 1, first_of_month.month, 1)
    return start.strftime("%Y%m%d00"), end.strftime("%Y%m%d00")


async def fetch(ctx: SourceContext) -> SourceResult:
    title = ctx.links.wikipedia_title
    if not title:
        return SourceResult.skipped(NAME, "no Wikipedia article linked")
    lang = "en"
    if ":" in title[:4]:
        lang, title = title.split(":", 1)
    start, end = _window(ctx.today)
    article = quote(title.strip().replace(" ", "_"), safe="")
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/"
           f"all-access/user/{article}/monthly/{start}/{end}")
    payload = await http.get_json(ctx.client, url)
    views = [float(item["views"]) for item in sorted(payload.get("items", []), key=lambda i: i["timestamp"])]
    if not views:
        raise SourceError("no pageview data for this article")
    recent = mean(views[-3:])
    metrics = [Metric("wikipedia_monthly_views", recent, NAME, "average of the last 3 full months")]
    prior = views[:-3]
    if prior and mean(prior) > 0:
        metrics.append(Metric("wikipedia_trend", recent / mean(prior) - 1, NAME,
                              "last 3 months vs the prior months, as growth"))
    return SourceResult.ok(NAME, metrics, {"url": f"https://{lang}.wikipedia.org/wiki/{article}"})
