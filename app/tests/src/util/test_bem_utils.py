import pytest
from src.util.bem_util import get_bem_url, replace_bem_with_link


def test__get_bem_url():
    assert (
        get_bem_url("Please review BEM 123.")
        == "https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/123.pdf"
    )
    assert (
        get_bem_url("The policy in BEM 123A has been updated.")
        == "https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/123A.pdf"
    )
    with pytest.raises(ValueError):
        get_bem_url("This is not a valid case: BEM123.")


def test__replace_bem_with_link():
    assert (
        replace_bem_with_link("Please review BEM 123.")
        == 'Please review <a href="https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/123.pdf">BEM 123</a>.'
    )
    assert (
        replace_bem_with_link("The policy in BEM 123A has been updated.")
        == 'The policy in <a href="https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/123A.pdf">BEM 123A</a> has been updated.'
    )
    assert (
        replace_bem_with_link("Check both BEM 123 and BEM 500C.")
        == 'Check both <a href="https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/123.pdf">BEM 123</a> and <a href="https://dhhs.michigan.gov/OLMWeb/ex/BP/Public/BEM/500C.pdf">BEM 500C</a>.'
    )
    assert (
        replace_bem_with_link("There is no matching pattern here.")
        == "There is no matching pattern here."
    )
    assert (
        replace_bem_with_link("This is not a valid case: BEM123.")
        == "This is not a valid case: BEM123."
    )
