# -*- coding: utf-8 -*-
import os
from datetime import datetime

from scrapy.extensions.httpcache import FilesystemCacheStorage
from scrapy.http.request import Request
from scrapy.spiders import Spider

# For debugging and development
crawl_log = open(
    f"crawl_log-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.txt", "w", encoding="utf-8"
)


class FolderBasedFSCacheStorage(FilesystemCacheStorage):
    "Save files using a readable directory structure"

    def _get_request_path(self, spider: Spider, request: Request) -> str:
        global crawl_log
        crawl_log.write(f"{request.url}\n")
        assert hasattr(spider, "common_url_prefix")
        key = request.url.replace(spider.common_url_prefix, "pages/").replace(":", "_")
        folders = key.split("/")
        return os.path.join(self.cachedir, spider.name, *folders)
