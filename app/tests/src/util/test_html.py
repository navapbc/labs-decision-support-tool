from src.util.html import get_text_from_html


def test_get_text_from_html():
    html = """<html><body>
<p>Hello, world!</p>
<p>This is some HTML.</p></body></html>"""
    assert get_text_from_html(html) == "\n\nHello, world!\n\n\nThis is some HTML."
