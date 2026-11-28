"""Small allow-list HTML sanitizer for untrusted email bodies.

Email HTML is retained for presentation, but active content, forms, scripts,
remote stylesheets, event handlers and unsafe URL schemes are removed.
"""
from html import escape
from html.parser import HTMLParser
import re

_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "center", "cite", "code",
    "col", "colgroup", "dd", "del", "div", "dl", "dt", "em", "font", "h1",
    "h2", "h3", "h4", "hr", "i", "img", "li", "ol", "p", "pre", "s",
    "small", "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot",
    "th", "thead", "tr", "u", "ul",
}
_VOID_TAGS = {"br", "hr", "img", "col"}
_BLOCKED_CONTENT = {"script", "style", "iframe", "object", "embed", "form", "input",
                    "button", "textarea", "select", "option", "svg", "math", "video",
                    "audio", "canvas", "template"}
_GLOBAL_ATTRS = {"align", "bgcolor", "border", "cellpadding", "cellspacing", "colspan",
                 "rowspan", "width", "height", "valign", "dir", "lang", "title",
                 "alt", "class", "role"}
_STYLE_PROPERTIES = {
    "background-color", "border", "border-bottom", "border-collapse", "border-color",
    "border-left", "border-radius", "border-right", "border-spacing", "border-style",
    "border-top", "border-width", "color", "display", "font-family", "font-size",
    "font-style", "font-weight", "height", "letter-spacing", "line-height", "margin",
    "margin-bottom", "margin-left", "margin-right", "margin-top", "max-width",
    "min-width", "padding", "padding-bottom", "padding-left", "padding-right",
    "padding-top", "text-align", "text-decoration", "vertical-align", "white-space",
    "width",
}
_BAD_CSS = re.compile(r"(?:url\\s*\\(|expression\\s*\\(|javascript:|@import|behavior\\s*:|-moz-binding)", re.I)


def _safe_style(value: str) -> str:
    if _BAD_CSS.search(value) or "<" in value or ">" in value:
        return ""
    kept = []
    for declaration in value.split(";"):
        if ":" not in declaration:
            continue
        name, setting = declaration.split(":", 1)
        name, setting = name.strip().lower(), setting.strip()
        if name in _STYLE_PROPERTIES and setting and len(setting) <= 300:
            kept.append(f"{name}: {setting}")
    return "; ".join(kept)


def _safe_url(value: str, image: bool = False) -> str:
    value = value.strip()
    lowered = value.lower()
    if lowered.startswith(("https://", "http://")):
        return value[:2048]
    if not image and lowered.startswith("mailto:"):
        return value[:2048]
    # CID images are retained as references; clients without a matching inline
    # attachment simply show the supplied alt text.
    if image and lowered.startswith("cid:"):
        return value[:512]
    return ""


class _EmailHTMLSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output: list[str] = []
        self.blocked_depth = 0
        self.open_tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.blocked_depth:
            if tag in _BLOCKED_CONTENT:
                self.blocked_depth += 1
            return
        if tag in _BLOCKED_CONTENT:
            self.blocked_depth = 1
            return
        if tag not in _ALLOWED_TAGS:
            return
        safe_attrs = []
        for name, value in attrs:
            name = (name or "").lower()
            value = value or ""
            if name.startswith("on") or name in {"srcdoc", "formaction", "xlink:href"}:
                continue
            if name == "style":
                style = _safe_style(value)
                if style:
                    safe_attrs.append(("style", style))
                continue
            if tag == "a" and name == "href":
                url = _safe_url(value)
                if url:
                    safe_attrs.append(("href", url))
                    safe_attrs.append(("rel", "noopener noreferrer"))
                continue
            if tag == "img" and name == "src":
                url = _safe_url(value, image=True)
                if url:
                    safe_attrs.append(("src", url))
                    safe_attrs.append(("referrerpolicy", "no-referrer"))
                continue
            if name in _GLOBAL_ATTRS and re.fullmatch(r"[a-zA-Z0-9 _.,#%()'\"+-]{0,500}", value):
                safe_attrs.append((name, value))
        attr_text = "".join(f' {name}="{escape(value, quote=True)}"' for name, value in safe_attrs)
        self.output.append(f"<{tag}{attr_text}>")
        if tag not in _VOID_TAGS:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.blocked_depth:
            if tag in _BLOCKED_CONTENT:
                self.blocked_depth -= 1
            return
        if tag not in self._allowed_open_tags():
            return
        # Close malformed nesting safely, up to the matching open element.
        if tag in self.open_tags:
            while self.open_tags:
                current = self.open_tags.pop()
                self.output.append(f"</{current}>")
                if current == tag:
                    break

    def _allowed_open_tags(self):
        return set(self.open_tags)

    def handle_data(self, data):
        if not self.blocked_depth:
            self.output.append(escape(data, quote=False))

    def handle_entityref(self, name):
        if not self.blocked_depth:
            self.output.append(f"&{name};")

    def handle_charref(self, name):
        if not self.blocked_depth:
            self.output.append(f"&#{name};")

    def handle_comment(self, data):
        return

    def finish(self):
        while self.open_tags:
            self.output.append(f"</{self.open_tags.pop()}>")
        return "".join(self.output)


def sanitize_email_html(value: str | None) -> str:
    if not value:
        return ""
    parser = _EmailHTMLSanitizer()
    try:
        parser.feed(value[:500000])
        parser.close()
        return parser.finish()
    except Exception:
        # A malformed HTML body should never break mailbox sync or rendering.
        return ""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in _BLOCKED_CONTENT:
            self.skip_depth += 1
        elif not self.skip_depth and tag.lower() in {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "hr"}:
            self.parts.append("\\n")

    def handle_endtag(self, tag):
        if tag.lower() in _BLOCKED_CONTENT and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag.lower() in {"p", "div", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append("\\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(value[:500000])
        parser.close()
    except Exception:
        return ""
    lines = [re.sub(r"[ \\t]+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    return re.sub(r"\\n{3,}", "\\n\\n", "\\n".join(line for line in lines if line)).strip()[:200000]
