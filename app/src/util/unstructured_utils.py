import json
import pprint
import re
import tempfile

import requests
from unstructured.partition.pdf import partition_pdf


# Build a tree from the JSON returned by Unstructured
def get_tree_of_elements(unstructured_json):
    elements_by_id = {item["element_id"]: item for item in unstructured_json}

    # Add children_ids
    for element_id in elements_by_id:
        if parent_id := elements_by_id[element_id]["metadata"].get("parent_id"):
            if "children_ids" in elements_by_id[parent_id]:
                elements_by_id[parent_id]["children_ids"].append(element_id)
            else:
                elements_by_id[parent_id]["children_ids"] = [element_id]

    def build_tree(elements_by_id, element_ids):
        tree = []

        for element_id in element_ids:
            element = elements_by_id[element_id]
            if children_ids := element.get("children_ids"):
                element["children"] = build_tree(elements_by_id, children_ids)
            else:
                element["children"] = []

            tree.append(element)

        return tree

    root_element_ids = [
        element_id
        for element_id in elements_by_id
        if elements_by_id[element_id]["metadata"].get("parent_id") == None
    ]
    return build_tree(elements_by_id, root_element_ids)


# Return a Markdown nested list of items in the tree
def get_tree_as_markdown(tree, indent=0):
    txt = ""
    for item in tree:
        txt += ("    " * indent) + " - [" + item["type"] + "] " + item["text"] + "\n"
        txt += get_tree_as_markdown(item["children"], indent + 1)
    return txt


def display_tree(tree):
    print(get_tree_as_markdown(tree))


def get_json_from_file(filepath):
    elements = partition_pdf(filepath, strategy="fast")
    return [element.to_dict() for element in elements]


def get_file_from_url(url):
    response = requests.get(url)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(response.content)
    return temp_file.name


def get_json_from_url(url):
    temp_file_path = get_file_from_url(url)
    return get_json_from_file(temp_file_path)
