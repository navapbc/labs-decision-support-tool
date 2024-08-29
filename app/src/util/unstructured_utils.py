from unstructured.partition.pdf import partition_pdf


def get_json_from_file(filepath):
    elements = partition_pdf(filepath, strategy="fast")
    return [element.to_dict() for element in elements]
