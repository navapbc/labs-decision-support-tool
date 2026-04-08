import re

BEM_PATTERN = re.compile(r"\bBEM\s+(\d{3}[A-Z]?)\b")


def extract_bem_number(text: str, prefix: str = "BEM") -> str:
    pattern = BEM_PATTERN if prefix == "BEM" else re.compile(rf"\b{re.escape(prefix)}\s+(\d{{3}}[A-Z]?)\b")
    match = pattern.search(text)
    if not match:
        raise ValueError(f"No {prefix} number found in text: {text}")
    return match.group(1)


def normalize_bem_title(title: str) -> str:
    collapsed = re.sub(r"\s+", " ", title).strip(" -:")
    if collapsed.isupper():
        return collapsed.title()
    return collapsed


def build_bem_document_name(bem_number: str, title: str, prefix: str = "BEM") -> str:
    return f"{prefix} {bem_number} — {normalize_bem_title(title)}"


def is_pdf_url(source_url: str | None) -> bool:
    return bool(source_url and ".pdf" in source_url.casefold())


def build_pdf_page_url(source_url: str | None, page_number: int | None) -> str | None:
    if not source_url:
        return None
    if page_number:
        return f"{source_url}#page={page_number}"
    return source_url
