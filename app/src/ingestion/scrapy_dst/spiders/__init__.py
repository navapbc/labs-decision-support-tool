# This package will contain the spiders of your Scrapy project
#
# Please refer to the documentation for information on how to create and manage
# your spiders.

import os
import sys

app_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
print(f"(Bootstrapping for Scrapy: Adding DST's app folder to sys.path:{app_folder})")
sys.path.append(app_folder)
