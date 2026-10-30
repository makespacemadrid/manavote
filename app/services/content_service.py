"""The supported, inert subset of member-authored Markdown."""

import bleach
import markdown


def render_member_markdown(text):
    if not text:
        return ""
    return bleach.clean(
        markdown.markdown(str(text), extensions=["nl2br"]),
        tags={"p", "br", "strong", "em", "a", "ul", "ol", "li", "blockquote",
              "code", "pre", "h2", "h3", "h4", "hr"},
        attributes={"a": ["href", "title"]},
        protocols={"http", "https", "mailto"},
        strip=True,
    )
