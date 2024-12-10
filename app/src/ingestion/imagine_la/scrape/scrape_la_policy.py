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
import pdb
import sys

from install_playwright import install
from playwright.sync_api import Locator, sync_playwright

if len(sys.argv) != 2:
    print("You need to pass the root URL and password as command line arguments.")
    print("E.g.: uv run scrape_content_hub.py <root_url> <password>")
    quit()

base_url = "https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster"
root_url = f"{base_url}/index.htm"
# sys.argv[1]


p = sync_playwright().start()
install(p.chromium)
browser = p.chromium.launch()

page = browser.new_page()
page.goto(root_url)

# Wait for the password field and enter credentials
# password_field = page.wait_for_selector("#password", timeout=10_000)
# if not password_field:
#     print("Password field not found.")
#     quit()
# password_field.fill(password)
# password_field.press("Enter")

# Wait for the page to load by ensuring an element (e.g., an <h2> tag) is present
# page.wait_for_selector("text='When all attempts to verify'", timeout=10_000)
page.wait_for_load_state("domcontentloaded")
# page.set_default_timeout(10_000)
page.wait_for_selector("a.toc")


def html(locator: Locator):
    return locator.evaluate("el => el.outerHTML")


def write_html(filename="pdb.html"):
    filepath = os.path.join("pagesT1", filename)
    with open(filepath, "w", encoding="utf-8") as file:
        file.write(page.content())


# page.locator('a.toc').first.click()
page.click("a.toc")
page.wait_for_selector('li.book:has-text("Programs")')

# lis = page.locator('li.book a:has-text("Programs")')
# lis = page.locator('li.book.expanded.active a:has-text("Programs")')
# print(programs.evaluate("el => el.outerHTML"))


def expand_nav_item(li: Locator):
    data_itemkey = li.get_attribute("data-itemkey")
    print("Clicking", li.text_content(), li.get_attribute("data-itemid"), data_itemkey)
    li.click()
    page.locator(f'ul.child[data-child="{data_itemkey}"]:not(hidden)').wait_for()
    children = page.locator(f'ul.child[data-child="{data_itemkey}"] > li.book')  #:not(.expanded)
    print("Count", children.count(), children.all_text_contents())
    for index in range(children.count()):
        child = children.nth(index)
        print(index, child.text_content())
        href = child.locator("a").first.get_attribute("href")
        if href == "#":
            expand_nav_item(child)
            # if True or child.text_content() == ' 63-300 Application Process ':
            #     write_html()
            #     pdb.set_trace()
            print("Count", children.count(), children.all_text_contents())
        else:
            print("HREF", href)
            # print("HREF1", f"{base_url}/index.htm#t="+href)
            # print("HREF2", f'{base_url}/{href}')


try:
    programs = page.locator('li.book:has-text("Programs")')
    # page.click('li.book:has-text("Programs")')
    # data_itemkey = programs.first.get_attribute('data-itemkey')
    # page.locator(f'ul.child[data-child="{data_itemkey}"]').wait_for()
    # lis = page.locator(f'ul.child[data-child="{data_itemkey}"] li.book')
    # print("A", lis.all_text_contents())
    expand_nav_item(programs)
except Exception as e:
    write_html("exception.html")
    raise e

# page.wait_for_selector('li.book:has-text("CalFresh")')
# child = page.locator('li.book:has-text("CalFresh")')

"""
area=
general
&type=responsivehelp&ctxid=&
project=
ePolicyMaster
#t=
mergedProjects/CalFresh/CalFresh/63-300_Application_Process/63-300_Application_Process.htm

https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/
general/projects_responsive/ePolicyMaster/
mergedProjects/CalFresh/CalFresh/63-300_Application_Process/63-300_Application_Process.htm


https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/index.htm
https://epolicy.dpss.lacounty.gov/epolicy/epolicy/server/general/projects_responsive/ePolicyMaster/index.htm
#t=
'mergedProjects/CalFresh/CalFresh/63-300_Application_Process/63-300_Application_Process.htm'
#Policybc-2&rhtocid=_3_0_0_0_1
'mergedProjects/CalFresh/CalFresh/63-300_Application_Process/63-300_Application_Process.htm'
"""

write_html("done.html")
# pdb.set_trace()

# content_hub_pages: dict[str, str] = {}

# # root_url_prefix = root_url if root_url.endswith("/") else root_url + "/"
# content_hub_pages["page_path"] = page.content()

# #     page.go_back()

# # Write the files to the `pages` directory
# os.makedirs("pagesT1", exist_ok=True)

# for filename, content in content_hub_pages.items():
#     url_path = "pagesT1/" + href
#     os.makedirs(os.path.dirname(url_path), exist_ok=True)
#     with open(url_path, "w", encoding="utf-8") as file:
#         file.write(content)

print("HTML files generated in the 'pages' directory.")
