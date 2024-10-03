# Scrapy settings for edd project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "edd"

SPIDER_MODULES = ["edd.spiders"]
NEWSPIDER_MODULE = "edd.spiders"


# Crawl responsibly by identifying yourself (and your website) on the user-agent
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0"

LOG_LEVEL = "INFO"
DEPTH_STATS_VERBOSE = True

# Obey robots.txt rules
ROBOTSTXT_OBEY = False
# True

# Configure maximum concurrent requests performed by Scrapy (default: 16)
#CONCURRENT_REQUESTS = 32

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
#DOWNLOAD_DELAY = 3
# The download delay setting will honor only one of:
#CONCURRENT_REQUESTS_PER_DOMAIN = 16
#CONCURRENT_REQUESTS_PER_IP = 16

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "edd.middlewares.EddSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
DOWNLOADER_MIDDLEWARES = {
#    "edd.middlewares.EddDownloaderMiddleware": 543,

    # YL: https://www.quora.com/Can-you-make-Scrapy-keep-all-the-HTML-it-downloads
    # To make Scrapy keep all the HTML it downloads, you can use the HttpCompressionMiddleware and set the COMPRESS_RESPONSE setting to False in your Scrapy project.
    # Scrapy will now keep the full HTML content of the downloaded pages in your project's data files, rather than discarding it after the data extraction is complete.
    'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 543,
}

COMPRESS_RESPONSE = False

# YL: https://stackoverflow.com/a/10897298
# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
# YL: https://jerrynsh.com/5-useful-tips-while-working-with-python-scrapy/#tldr
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 0
# YL: https://stackoverflow.com/questions/51085665/mocking-the-requests-for-testing-in-scrapy-spider
# YL: Relative to the .scrapy/ directory
HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
# YL: https://doc.scrapy.org/en/latest/topics/downloader-middleware.html#module-scrapy.downloadermiddlewares.httpcache
# YL: https://stackoverflow.com/questions/51432471/how-to-set-same-cache-folder-for-different-spiders-now-scrapy-creates-subfolder
HTTPCACHE_STORAGE = "edd.cache.SplashAwareFSCacheStorage"

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "edd.pipelines.EddPipeline": 300,
#}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Set settings whose default value is deprecated to a future-proof value
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
