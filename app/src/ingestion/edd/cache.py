# -*- coding: utf-8 -*-
"""
Adapted from https://github.com/scrapy-plugins/scrapy-splash/tree/master/scrapy_splash

To handle "splash" Request meta key correctly when HTTP cache is enabled
Scrapy needs a custom caching backed.

See https://github.com/scrapy/scrapy/issues/900 for more info.
"""
from __future__ import absolute_import

import os

from scrapy.extensions.httpcache import FilesystemCacheStorage

# Create file
# crawl_log = open(f"crawl_log-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.txt", "w")


class SplashAwareFSCacheStorage(FilesystemCacheStorage):
    def _get_request_path(self, spider, request):
        # global crawl_log
        # crawl_log.write(f"{request.url}\n")
        key = request.url.replace("https://edd.ca.gov/en/", "edd/").replace(":", "_")
        folders = key.split("/")
        return os.path.join(self.cachedir, spider.name, *folders)
