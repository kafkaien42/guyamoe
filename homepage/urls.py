from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.generic.base import TemplateView

from . import views

urlpatterns = [
    path("", views.all_series, name="site-home"),
    path("series/", views.all_series, name="site-series"),
    path("oneshots/", views.all_oneshots, name="site-oneshot"),
    path("latest_chapters/", views.all_chapters, name="site-chapters"),
    path("admin_home/", views.admin_home, name="admin_home"),
    path("about/", views.about, name="site-about"),
    path("robots.txt", TemplateView.as_view(template_name="homepage/robots.txt", content_type="text/plain")),
    path("random/", views.random, name="site-main-series-random"),
]
