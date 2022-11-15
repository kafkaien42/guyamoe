from django.contrib.syndication.views import Feed
from django.core.cache import cache
from django.shortcuts import reverse
from django.utils.feedgenerator import DefaultFeed
from django.conf import settings


from reader.models import Chapter, Series


class CorrectMimeTypeFeed(DefaultFeed):
    content_type = "application/xml; charset=utf-8"


class AllChaptersFeed(Feed):
    feed_type = CorrectMimeTypeFeed
    link = "/latest_chapters/"
    title = settings.BRANDING_NAME
    description = "Latest chapter updates"

    description_template = 'rss_feed.html'

    def items(self):
        return Chapter.objects.filter(is_public=True).order_by("-uploaded_on")

    def item_title(self, item):
        return f"{item.series.name} - {item.clean_title()}"

    def item_link(self, item):
        return item.get_absolute_url()

    def item_pubdate(self, item):
        return item.uploaded_on


class SeriesChaptersFeed(Feed):
    feed_type = CorrectMimeTypeFeed
    title = "Series Chapter updates"
    description = "Latest chapter updates"
    description_template = 'rss_feed.html'

    def get_object(self, request, series_slug):
        return Series.objects.get(slug=series_slug)

    def title(self, obj):
        return obj.name

    def link(self, obj):
        return obj.get_absolute_url()

    def item_title(self, obj):
        return f"{obj.series.name} - {obj.clean_title()}"

    def item_link(self, obj):
        return obj.get_absolute_url()

    def items(self, obj):
        return Chapter.objects.filter(series=obj, is_public=True).order_by("-uploaded_on")

    def item_pubdate(self, item):
        return item.uploaded_on
