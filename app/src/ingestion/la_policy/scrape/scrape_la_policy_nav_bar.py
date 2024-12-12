# /// script
# dependencies = [
#   "install-playwright",
#   "playwright",
# ]
# ///
# (This comment enables `uv run` to automatically create a virtual environment)

"""
This script expands the navigation bar's TOC in order to get a list of pages to scrape
and saves the html file, required for Scrapy to process.

This is intended to be run locally.

You can either install the above dependences with pip, e.g.,
`pip install -r requirements.txt` before running with
`python scrape_la_policy_nav_bar.py`, or run this with
`uv run --no-project scrape_la_policy_nav_bar.py` to have an environment
automatically created for you.
"""

from install_playwright import install
from playwright.sync_api import Locator, sync_playwright


p = sync_playwright().start()
install(p.chromium)
browser = p.chromium.launch()

page = browser.new_page()
base_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster"
page.goto(f"{base_url}/index.htm")

# Wait for the page to load by ensuring an element (e.g., an <h2> tag) is present
page.wait_for_load_state("domcontentloaded")
page.wait_for_selector("a.toc")
page.click("a.toc")
page.wait_for_selector('li.book:has-text("Programs")')

# Helper functions for debugging


def html(locator: Locator):
    return locator.evaluate("el => el.outerHTML")


def write_html(filename="la_policy.html"):
    with open(filename, "w", encoding="utf-8") as file:
        file.write(page.content())
    print("Saved to", filename)


def expand_nav_item(li: Locator):
    data_itemkey = li.get_attribute("data-itemkey")
    print(f"Clicking {li.text_content()!r} ({data_itemkey})")
    li.click()
    page.locator(f'ul.child[data-child="{data_itemkey}"]:not(hidden)').wait_for()

    children = page.locator(f'ul.child[data-child="{data_itemkey}"] > li.book')
    print(f"  has {children.count()} children:", children.all_text_contents())
    for index in range(children.count()):
        child = children.nth(index)
        href = child.locator("a").first.get_attribute("href")
        if href == "#":
            expand_nav_item(child)
        else:
            print(index, "Found URL to scrape:", href)


try:
    programs = page.locator('li.book:has-text("Programs")')
    expand_nav_item(programs)
    write_html("la_policy_nav_bar.html")
except Exception as e:
    write_html("exception.html")
    raise e
