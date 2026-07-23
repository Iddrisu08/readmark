"""
ReadMark — URL Utilities
Normalize URLs to strip tracking params so the same article
is recognized regardless of how the user got to it.
"""

from urllib.parse import urlparse, parse_qs, urlencode

TRACKING_PARAMS = {
    # UTM
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    # Social / share tracking
    "fbclid", "gclid", "gclsrc", "dclid", "gbraid", "wbraid",
    "twclid", "ttclid", "igshid", "s", "si",
    "mc_cid", "mc_eid",
    # Analytics / misc
    "ref", "ref_src", "ref_url", "referer", "source", "src",
    "campaign", "medium",
    "_ga", "_gl", "_hsenc", "_hsmi", "_ke",
    "trk", "trkcampaign", "sc_campaign", "sc_channel", "sc_content",
    "mkt_tok", "mkwid",
    "pk_campaign", "pk_kwd", "pk_source", "pk_medium",
    "hsa_cam", "hsa_grp", "hsa_mt", "hsa_src", "hsa_ad", "hsa_acc",
    "hsa_net", "hsa_ver", "hsa_la", "hsa_ol", "hsa_kw", "hsa_tgt",
    # Reddit / HN / misc
    "share", "context", "st", "sh",
    # Newsletter / email
    "email", "e", "ck_subscriber_id",
    # General noise
    "amp", "__twitter_impression", "from", "via",
}


def normalize_url(url: str) -> str:
    """
    Normalize a URL by stripping tracking parameters, www prefix,
    trailing slashes, and fragments.
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url)

        # Normalize hostname
        hostname = parsed.hostname or ""
        if hostname.startswith("www."):
            hostname = hostname[4:]

        # Normalize path (strip trailing slash)
        path = parsed.path.rstrip("/") or "/"

        # Strip tracking params
        query_params = parse_qs(parsed.query, keep_blank_values=False)
        clean_params = {
            k: v for k, v in query_params.items()
            if k.lower() not in TRACKING_PARAMS
        }
        clean_query = urlencode(clean_params, doseq=True) if clean_params else ""

        # Reconstruct (no fragment)
        scheme = parsed.scheme or "https"
        port_str = ""
        if parsed.port and parsed.port not in (80, 443):
            port_str = f":{parsed.port}"

        normalized = f"{scheme}://{hostname}{port_str}{path}"
        if clean_query:
            normalized += f"?{clean_query}"

        return normalized
    except Exception:
        return url
