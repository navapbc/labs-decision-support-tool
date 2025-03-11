# /// script
# dependencies = [
#   "install-playwright",
#   "playwright",
# ]
# ///
# (This comment enables `uv run` to automatically create a virtual environment)

"""
This script renders the child pages of the ImagineLA content hub
and saves them to .html files in the `pages` subdirectory.

It is intended to be run locally: the HTML files can later be added
to S3 to ingest them into a deployed environment's database.

You can either install the above dependences with pip, e.g.,
`pip install -r requirements.txt` before running with
`python scrape_content_hub.py`, or run this with
`uv run --no-project scrape_content_hub.py` to have an environment
automatically created for you.
"""

import os
import sys

from install_playwright import install
from playwright.sync_api import sync_playwright

if len(sys.argv) != 3:
    print("You need to pass the root URL and password as command line arguments.")
    print("E.g.: uv run scrape_content_hub.py <root_url> <password>")
    quit()

root_url, password = sys.argv[1:]


p = sync_playwright().start()
install(p.chromium)
browser = p.chromium.launch()

page = browser.new_page()
page.goto(root_url)

# Wait for the password field and enter credentials
password_field = page.wait_for_selector("#password", timeout=10_000)
if not password_field:
    print("Password field not found.")
    quit()
password_field.fill(password)
password_field.press("Enter")
page.wait_for_load_state("networkidle")
print("Logged in")

# Wait for the page to load by ensuring an element (e.g., an <h2> tag) is present
page.wait_for_selector("h2", timeout=10_000)

learn_more_buttons = page.locator('button:has-text("Learn more")')
content_hub_pages: dict[str, str] = {}

root_url_prefix = root_url if root_url.endswith("/") else root_url + "/"
for index in range(learn_more_buttons.count()):

    # Expand all the accordions on the page
    # so that we can click into the buttons beneath them
    # accordions = page.locator(".chakra-accordion__button")
    # for accordion_index in range(accordions.count()):
    #     accordions.nth(accordion_index).click()

    accordions = page.locator(".chakra-accordion__button[aria-expanded='false']")
    while accordions.count()>0:
        print(f"Expanding accordion {accordions.count()}")
        accordions.first.click()

    # if learn_more_buttons.nth(index).is_hidden():
    #     print(f"Skipping index={index} {learn_more_buttons.nth(index)}")
    #     continue
    try:
        with page.expect_navigation() as navigation:
            btn = learn_more_buttons.nth(index)
            parent = btn.locator("..").first
            gparent = parent.locator("..").first
            print(
                f"index={index} count={learn_more_buttons.count()} visible={btn.is_visible()} parentVis={parent.is_visible()}"
            )
            if not gparent.is_visible():
                print(gparent.inner_text())
                import pdb; pdb.set_trace()


            print(f"clicking {learn_more_buttons.nth(index)}")
            learn_more_buttons.nth(index).click(force=True)
            page.wait_for_load_state("networkidle")

        page.wait_for_selector("h2", timeout=10_000)
        page_path = page.url.removeprefix(root_url_prefix)
        print(f"Scraped page: {page_path}")

        content_hub_pages[page_path] = page.content()

        page.go_back()
        page.wait_for_load_state("networkidle")
    except Exception as e:
        print(f"Error: {e}")

# Write the files to the `pages` directory
os.makedirs("pages", exist_ok=True)

for filename, content in content_hub_pages.items():
    filepath = os.path.join("pages", f"{filename}.html")
    with open(filepath, "w", encoding="utf-8") as file:
        file.write(content)

print("HTML files generated in the 'pages' directory.")
