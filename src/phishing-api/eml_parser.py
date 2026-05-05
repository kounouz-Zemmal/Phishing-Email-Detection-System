"""
Parse .eml (email) files and extract features for phishing detection.
"""
import email
import re
import numpy as np
import pandas as pd
from email import policy
from email.parser import BytesParser


def parse_eml(file_bytes: bytes) -> dict:
    """
    Parse a .eml file and return a dict ready for feature engineering.
    
    Args:
        file_bytes: Raw bytes from uploaded .eml file
    
    Returns:
        dict with keys: subject, from_email, to_email, body_clean, urls, 
                       url_count, char_count, word_count, has_ip_url, html_flag
    """
    try:
        msg = BytesParser(policy=policy.default).parsebytes(file_bytes)
    except Exception as e:
        raise ValueError(f"Failed to parse EML file: {str(e)}")

    # ── Extract headers ──
    subject    = msg.get('Subject', '') or ''
    from_email = msg.get('From', '')    or ''
    to_email   = msg.get('To', '')      or ''
    reply_to   = msg.get('Reply-To', '') or ''

    # ── Extract body (prefer plain text, fall back to HTML) ──
    body_raw = ''
    html_flag = 0
    
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == 'text/plain' and not body_raw:
                body_raw = part.get_content() or ''
            elif ct == 'text/html':
                html_flag = 1
                if not body_raw:
                    raw_html = part.get_content() or ''
                    body_raw = re.sub(r'<[^>]+>', ' ', raw_html)
    else:
        ct = msg.get_content_type()
        html_flag = 1 if ct == 'text/html' else 0
        body_raw = msg.get_content() or ''
        if html_flag:
            body_raw = re.sub(r'<[^>]+>', ' ', body_raw)

    # Clean up whitespace
    body_clean = re.sub(r'\s+', ' ', body_raw).strip()

    # ── Extract URLs ──
    all_text = (body_raw or '') + ' ' + str(msg)
    urls = list(set(re.findall(r'https?://[^\s"\'<>)]+', all_text)))
    url_count = len(urls)

    # ── IP-based URL detection ──
    ip_pattern = re.compile(r'https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
    has_ip_url = int(any(ip_pattern.match(u) for u in urls))

    return {
        'subject':    subject,
        'from_email': from_email,
        'to_email':   to_email,
        'reply_to':   reply_to,
        'body_clean': body_clean,
        'urls':       str(urls),
        'url_count':  url_count,
        'char_count': len(body_clean),
        'word_count': len(body_clean.split()),
        'has_ip_url': has_ip_url,
        'html_flag':  html_flag,
    }