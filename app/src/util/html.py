from html.parser import HTMLParser


def get_text_from_html(html: str) -> str:
    html_parser = HTMLParser()
    text = []
    html_parser.handle_data = lambda data: text.append(data)  # type: ignore
    html_parser.feed(html)
    return "\n".join(text)
