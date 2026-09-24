"""Scrapy settings shared by every site crawl. Polite by default: obeys robots.txt and autothrottles."""
BOT_NAME = 'site_crawler'
SPIDER_MODULES = ['site_crawler.spiders']
NEWSPIDER_MODULE = 'site_crawler.spiders'

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
ROBOTSTXT_OBEY = True
AUTOTHROTTLE_ENABLED = True
CONCURRENT_REQUESTS_PER_DOMAIN = 8
DOWNLOAD_TIMEOUT = 60

# Breadth-first, so an interrupted crawl has covered the whole site shallowly rather than one corner deeply.
# Disk queues so JOBDIR can pause and resume a crawl.
DEPTH_PRIORITY = 1
SCHEDULER_DISK_QUEUE = 'scrapy.squeues.PickleFifoDiskQueue'
SCHEDULER_MEMORY_QUEUE = 'scrapy.squeues.FifoMemoryQueue'

ITEM_PIPELINES = {'site_crawler.pipelines.HtmlParquetPipeline': 300}  # needs -s HTML_DIR=...

TWISTED_REACTOR = 'twisted.internet.asyncioreactor.AsyncioSelectorReactor'
FEED_EXPORT_ENCODING = 'utf-8'
LOG_LEVEL = 'INFO'
