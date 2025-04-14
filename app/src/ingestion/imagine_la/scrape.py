# Python script to export all Contentful content entries as JSON (fixed version)
import contentful
from rich_text_renderer import RichTextRenderer
from markdownify import markdownify
import os
import sys
from datetime import datetime

ENVIRONMENT_ID = "master"  # Default environment ID

def main():
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
        space_id=space_id,
        access_token=access_token,
        environment=ENVIRONMENT_ID
    )

    # 1. Get all of the benefit programs covered
    benefit_programs = []
    offset = 0
    limit = 1000 # Contentful max pagination limit
    while True:
        entries = client.entries({
            'content_type': "benefit",
            'limit': limit,
            'skip': offset
        })

        for entry in entries:
            fields = entry.fields()
            benefit_program = {
                "name": fields["name"],
                "description": fields["description"],
                "faq": fields["faq"] if fields.get("faq", None) else []
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
            answer_html = html_renderer.render(faq.fields()["answer"])
            answer_markdown = markdownify(answer_html)
            rendered_faq = {
                "question": faq.fields()["question"],
                "answer": answer_markdown,
            }
            rendered_faqs.append(rendered_faq)

        benefit_program["rendered_faq"] = rendered_faqs

    # 3. Save the rendered FAQs to a JSON file
    today = datetime.now().strftime("%Y%m%d")
    with open(f"content_hub{today}.md", "w", encoding="utf-8") as file:
        for benefit_program in benefit_programs:
            file.write(f"# {benefit_program['name']}\n")
            file.write(f"{benefit_program['description']}\n\n")
            for faq in benefit_program["rendered_faq"]:
                file.write(f"## {faq['question']}\n")
                file.write(f"{faq['answer']}\n\n")
            file.write("\n\n")

if __name__ == "__main__":
    main()