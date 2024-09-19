# Regular expression to match BEM followed by 3 digits, optionally followed by a letter
import re


BEM_PATTERN = r"(BEM\s(\d{3}[A-Z]?))"


def get_bem_url(text: str) -> str:
    bem = re.search(BEM_PATTERN, text)
    if not bem:
        raise ValueError(f"No BEM number found in text: {text}")
    return f"https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/{bem.group(2)}.pdf"


def replace_bem_with_link(text: str) -> str:
    return re.sub(
        BEM_PATTERN,
        r'<a href="https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/\2.pdf">\1</a>',
        text,
    )