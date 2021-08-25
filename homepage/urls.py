from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.generic.base import TemplateView

from . import views

urlpatterns = [
    path("", views.all_ongoing, name="site-home"),
    re_path(r"^author/(?P<author_slug>[\w-]+)/$", views.author_series, name="author-series"),
    path("series/", views.all_series, name="site-series"),
    path("oneshots/", views.all_oneshots, name="site-oneshots"),
    path("nsfw/", views.all_nsfw, name="site-nsfw"),
    path("latest_chapters/", views.all_chapters, name="site-chapters"),
    path("admin_home/", views.admin_home, name="admin_home"),
    path("about/", views.about, name="site-about"),
    path("robots.txt", TemplateView.as_view(template_name="homepage/robots.txt", content_type="text/plain")),
    path("random/", views.random, name="site-main-series-random"),
]

# Importer is not included in the repo and is distributed using a different license
try:
    from homepage.mangadex_importer import view_callback
    urlpatterns.append(path("mangadex/", view_callback, name="mangadex_importer"),)
except ImportError:
    pass