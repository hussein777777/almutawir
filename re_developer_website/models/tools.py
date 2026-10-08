# -*- coding: utf-8 -*-
"""Small helpers shared by the real-estate website models."""
import re
from urllib.parse import quote_plus

_YOUTUBE_RE = re.compile(
    r'(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([\w-]{11})')
_VIMEO_RE = re.compile(r'vimeo\.com/(?:video/)?(\d+)')


def video_embed_url(url):
    """Turn a YouTube / Vimeo link into a safe embeddable URL (or False)."""
    if not url:
        return False
    match = _YOUTUBE_RE.search(url)
    if match:
        return 'https://www.youtube.com/embed/%s?rel=0' % match.group(1)
    match = _VIMEO_RE.search(url)
    if match:
        return 'https://player.vimeo.com/video/%s' % match.group(1)
    return False


def map_embed_url(query):
    """Google Maps embed URL for an address or a 'lat,long' string."""
    if not query:
        return False
    return 'https://maps.google.com/maps?q=%s&z=15&output=embed' % quote_plus(query.strip())


def whatsapp_url(number):
    digits = re.sub(r'\D', '', number or '')
    return digits and 'https://wa.me/%s' % digits or False
