"""
This script renders the child pages of the ImagineLA content hub
and saves them to .html files in the `pages` subdirectory.
"""

# Python script to export all Contentful content entries as JSON (fixed version)
import os
import sys

import contentful
from rich_text_renderer import RichTextRenderer

ENVIRONMENT_ID = "master"  # Default environment ID
PAGES_DIR = os.path.join("src", "ingestion", "imagine_la", "pages")


def main() -> None:
    # 0. Instantiate the Contentful client
    space_id = os.getenv("CONTENT_HUB_SPACE_ID", None)
    access_token = os.getenv("CONTENT_HUB_ACCESS_TOKEN", None)

    if space_id is None:
        print("Please set the CONTENT_HUB_SPACE_ID environment variable.")
        sys.exit(1)

    if access_token is None:
        print("Please set the CONTENT_HUB_ACCESS_TOKEN environment variable.")
        sys.exit(1)

    client = contentful.Client(
        space_id=space_id, access_token=access_token, environment=ENVIRONMENT_ID
    )

    # 1. Get all of the benefit programs covered
    benefit_programs = []
    offset = 0
    limit = 1000  # Contentful max pagination limit
    while True:
        entries = client.entries({"content_type": "benefit", "limit": limit, "skip": offset})

        for entry in entries:
            fields = entry.fields()

            # Some stray entries may not have the required fields
            # E.g., "Introduction" -- they aren't benefit programs
            # even though they're listed as such, so can be ignored
            # Others end in "test" (heuristic, not confirmed with Imagine LA)
            if fields.get("faq", None) is None or fields["route"].endswith("test"):
                continue

            benefit_program = {
                "name": fields["name"],
                "route": fields["route"],
                "description": fields["description"],
                "faq": fields["faq"],
            }
            benefit_programs.append(benefit_program)

        offset += limit

        if len(entries) < limit:
            break

    # 2. For each benefit program, render its FAQs
    html_renderer = RichTextRenderer()
    for benefit_program in benefit_programs:
        rendered_faqs = []
        for faq in benefit_program["faq"]:
            fields = faq.fields()
            rendered_faq = {
                "question": faq.fields()["question"],
                "answer": html_renderer.render(faq.fields()["answer"]),
            }
            rendered_faqs.append(rendered_faq)

        benefit_program["rendered_faq"] = rendered_faqs

    # 3. Save the rendered FAQs to an HTML file
    os.makedirs(PAGES_DIR, exist_ok=True)
    for benefit_program in benefit_programs:
        filepath = os.path.join(PAGES_DIR, benefit_program["route"] + ".html")
        with open(filepath, "w", encoding="utf-8") as file:
            file.write(f"<h1>{benefit_program['name']}</h1>\n")
            file.write(f"<p>{benefit_program['description']}</p>\n\n")
            for faq in benefit_program["rendered_faq"]:
                file.write(f"<h2>{faq['question']}</h2>\n")
                file.write(f"{faq['answer']}\n\n")

    print("HTML files generated in the 'pages' directory.")


if __name__ == "__main__":
    main()
