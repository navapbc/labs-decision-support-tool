from typing import Optional


def join_list(joining_list: Optional[list], join_txt: str = "\n") -> str:
    """
    Utility to join a list.

    Functionally equivalent to:
    "" if joining_list is None else "\n".join(joining_list)
    """
    if not joining_list:
        return ""

    return join_txt.join(joining_list)


def basic_ascii(text: str) -> str:
    # See https://www.ascii-code.com/
    return "".join([c if 32 <= ord(c) <= 126 else " " for c in text])
