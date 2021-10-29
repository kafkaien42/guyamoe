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
    from homepage.mangadex_importer import view_callback as import_callback, import_export_selection
    from homepage.mangadex_exporter import view_callback as export_callback, test_mangadex_login, export_chapter, cancel_upload_to_mangadex, link_chapter
    urlpatterns.append(path("mangadex/", import_export_selection, name="mangadex"),)
    urlpatterns.append(path("mangadex_importer/", import_callback, name="mangadex_importer"),)
    urlpatterns.append(path("mangadex_exporter/", export_callback, name="mangadex_exporter"),)
    urlpatterns.append(path("mangadex_exporter/test_mangadex_login/", test_mangadex_login, name="test_mangadex_login"),)
    urlpatterns.append(path("mangadex_exporter/cancel_upload/", cancel_upload_to_mangadex, name="cancel_upload_to_mangadex"),)
    urlpatterns.append(re_path("mangadex_exporter/export_chapter/(?P<chapter_id>[\d-]{1,9})/", export_chapter, name="upload_chapter_to_mangadex"),)
    urlpatterns.append(path("mangadex_exporter/link_chapter/<int:chapter_id>/<uuid:md_uuid>", link_chapter, name="link_chapter_to_mangadex"),)

except ImportError:
    pass