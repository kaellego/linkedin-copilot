"""Small helpers for keeping credentials and personal data out of logs/artifacts."""

import re
from urllib.parse import urlsplit, urlunsplit


_EMAIL_RE = re.compile(r"\b[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)")
_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|senha|token|secret|api[_-]?key|authorization)\b\s*[:=]\s*([^\s,;]+)"
)
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def sanitize_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if parts.scheme and parts.netloc:
            host = parts.hostname or ""
            if parts.port:
                host = f"{host}:{parts.port}"
            return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except (TypeError, ValueError):
        pass
    return "[url omitida]"


def sanitize_text(value: object, limit: int = 1200) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = _URL_RE.sub(lambda match: sanitize_url(match.group(0)), text)
    text = _EMAIL_RE.sub("[email ocultado]", text)
    text = _PHONE_RE.sub("[telefone ocultado]", text)
    text = _SECRET_RE.sub(lambda match: f"{match.group(1)}=[ocultado]", text)
    return text[:limit]


def sanitize_html(html: str) -> str:
    """Remove valores de controles, scripts e tokens de query dos snapshots."""
    html = re.sub(r"(?is)<script\b[^>]*>.*?</script\s*>", "<script>[removido]</script>", html)
    html = re.sub(r"(?is)<textarea\b([^>]*)>.*?</textarea\s*>", r"<textarea\1></textarea>", html)
    html = re.sub(r"(?is)(<input\b[^>]*?)\svalue\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", r"\1", html)
    html = re.sub(r"(?i)\s(?:checked|selected|aria-checked|aria-selected)\s*(?:=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?", "", html)
    html = re.sub(
        r"(?is)(<[^>]+\b(?:href|src)\s*=\s*)(\"|')([^\"']+)(\2)",
        lambda match: match.group(1) + match.group(2) + sanitize_url(match.group(3)) + match.group(4)
        if match.group(3).startswith(("http://", "https://")) else match.group(0),
        html,
    )
    html = _EMAIL_RE.sub("[email ocultado]", html)
    html = _PHONE_RE.sub("[telefone ocultado]", html)
    return html
