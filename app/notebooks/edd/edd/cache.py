# -*- coding: utf-8 -*-
"""
Copied from https://github.com/scrapy-plugins/scrapy-splash/tree/master/scrapy_splash

To handle "splash" Request meta key correctly when HTTP cache is enabled
Scrapy needs a custom caching backed.

See https://github.com/scrapy/scrapy/issues/900 for more info.
"""
from __future__ import absolute_import
import os
import hashlib
from datetime import datetime
import six
from scrapy.utils.python import to_bytes
from scrapy.extensions.httpcache import FilesystemCacheStorage

# -*- coding: utf-8 -*-
"""
To handle "splash" Request meta key properly a custom DupeFilter must be set.
See https://github.com/scrapy/scrapy/issues/900 for more info.
"""
from copy import deepcopy

from scrapy.dupefilters import RFPDupeFilter

from scrapy.utils.url import canonicalize_url
from scrapy.utils.request import request_fingerprint

def dict_hash(obj, start=''):
    """ Return a hash for a dict, based on its contents """
    h = hashlib.sha1(to_bytes(start))
    h.update(to_bytes(obj.__class__.__name__))
    if isinstance(obj, dict):
        for key, value in sorted(obj.items()):
            h.update(to_bytes(key))
            h.update(to_bytes(dict_hash(value)))
    elif isinstance(obj, (list, tuple)):
        for el in obj:
            h.update(to_bytes(dict_hash(el)))
    else:
        # basic types
        if isinstance(obj, bool):
            value = str(int(obj))
        elif isinstance(obj, (six.integer_types, float)):
            value = str(obj)
        elif isinstance(obj, (six.text_type, bytes)):
            value = obj
        elif obj is None:
            value = b''
        else:
            raise ValueError("Unsupported value type: %s" % obj.__class__)
        h.update(to_bytes(value))
    return h.hexdigest()


def splash_request_fingerprint(request, include_headers=None):
    """ Request fingerprint which takes 'splash' meta key into account """

    fp = request_fingerprint(request, include_headers=include_headers)
    if 'splash' not in request.meta:
        return fp

    splash_options = deepcopy(request.meta['splash'])
    args = splash_options.setdefault('args', {})

    if 'url' in args:
        args['url'] = canonicalize_url(args['url'], keep_fragments=True)

    return dict_hash(splash_options, fp)


class SplashAwareDupeFilter(RFPDupeFilter):
    """
    DupeFilter that takes 'splash' meta key in account.
    It should be used with SplashMiddleware.
    """
    def request_fingerprint(self, request):
        return splash_request_fingerprint(request)


# Create file
crawl_log = open(f"crawl_log-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.txt", "w")

class SplashAwareFSCacheStorage(FilesystemCacheStorage):
    def _get_request_path(self, spider, request):
        # key = splash_request_fingerprint(request)
        global crawl_log
        crawl_log.write(f"{request.url}\n")
        key = request.url.replace("https://edd.ca.gov/en/","edd/").replace(":", "_")
        folders = key.split("/")
        return os.path.join(self.cachedir, spider.name, *folders)
    