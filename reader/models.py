import os
from datetime import datetime, timezone
from random import randint
import hashlib
from typing import List

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django_extensions.db.fields import AutoSlugField

MANGADEX = "MD"
SCRAPING_SOURCES = ((MANGADEX, "MangaDex"),)


class HitCount(models.Model):
    content = GenericForeignKey("content_type", "object_id")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    hits = models.PositiveIntegerField(("Hits"), default=0)


class Person(models.Model):
    name = models.CharField(max_length=200)
    slug = AutoSlugField(null=True, default=None, unique=True, db_index=True, editable=True, populate_from='name')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"/author/{self.slug}/"


class Group(models.Model):
    name = models.CharField(max_length=200)
    scrapping_uuids = models.CharField(max_length=400, null=True, help_text='External source uuids as a comma separated list of uuids (example: "123e4567-e89b-12d3-a456-426614174000" or "123e4567-e89b-12d3-a456-426614174000,123e4567-e89b-12d3-a456-426614174001"), ordering does not matter.')

    def __str__(self):
        return self.name

    def get_parsed_scrapping_uuids(self):
        if self.scrapping_uuids:
            return [uuid.strip() for uuid in str(self.scrapping_uuids).split(',')]
        return None


class Series(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(unique=True, max_length=200)
    author = models.ForeignKey(
        Person,
        blank=False,
        null=True,
        on_delete=models.SET_NULL,
        related_name="series_author",
    )
    artist = models.ForeignKey(
        Person,
        blank=False,
        null=True,
        on_delete=models.SET_NULL,
        related_name="series_artist",
    )
    synopsis = models.TextField(blank=True, null=True)
    alternative_titles = models.TextField(blank=True, null=True)
    next_release_page = models.BooleanField(default=False)
    next_release_time = models.DateTimeField(
        default=None, blank=True, null=True, db_index=True
    )
    next_release_html = models.TextField(blank=True, null=True)
    indexed = models.BooleanField(default=False)
    preferred_sort = models.CharField(max_length=200, blank=True, null=True)
    scraping_enabled = models.BooleanField(default=False)
    scraping_source = models.CharField(
        max_length=2, choices=SCRAPING_SOURCES, default=MANGADEX
    )
    scraping_identifiers = models.TextField(blank=True, null=True)
    scraping_uuid = models.CharField(max_length=200, blank=True, null=True)
    is_oneshot = models.BooleanField(default=False)
    is_nsfw = models.BooleanField(default=False)
    discord_role_id = models.CharField(max_length=200, blank=True, null=True, help_text='To find the role id, enter \\@TheRole on discord. Only enter numbers (e.g. <@&1234567890> => 1234567890)')
    uploadable_to_tumblr = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"/read/manga/{self.slug}/"

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "series"


def new_volume_folder(instance):
    return os.path.join(
        "manga",
        instance.series.slug,
        "volume_covers",
        str(instance.volume_number),
    )


def new_volume_path_file_name(instance, filename):
    _, ext = os.path.splitext(filename)
    new_filename = str(randint(10000, 99999)) + ext
    return os.path.join(
        new_volume_folder(instance),
        new_filename,
    )


class Volume(models.Model):
    volume_number = models.PositiveIntegerField(blank=False, null=False, db_index=True)
    series = models.ForeignKey(
        Series, blank=False, null=False, on_delete=models.CASCADE
    )
    volume_cover = models.ImageField(blank=True, upload_to=new_volume_path_file_name)

    class Meta:
        unique_together = (
            "volume_number",
            "series",
        )


class Chapter(models.Model):
    series = models.ForeignKey(Series, on_delete=models.CASCADE)
    title = models.CharField(max_length=200, blank=True)
    chapter_number = models.FloatField(blank=False, null=False, db_index=True)
    folder = models.CharField(max_length=255, blank=True, null=True)
    volume = models.PositiveSmallIntegerField(
        blank=True, null=True, default=None, db_index=True
    )
    group = models.ForeignKey(Group, null=True, on_delete=models.PROTECT)
    uploaded_on = models.DateTimeField(
        default=None, blank=True, null=True, db_index=True
    )
    updated_on = models.DateTimeField(
        default=None, blank=True, null=True, db_index=True
    )
    version = models.PositiveSmallIntegerField(blank=True, null=True, default=None)
    preferred_sort = models.CharField(max_length=200, blank=True, null=True)
    scraper_hash = models.CharField(max_length=36, blank=True)
    is_public = models.BooleanField(default=False)

    def clean_chapter_number(self):
        return (
            str(int(self.chapter_number))
            if self.chapter_number % 1 == 0
            else str(self.chapter_number)
        )

    def clean_title(self):
        if self.title:
            return f"Chapter {self.clean_chapter_number()} - {self.title}"
        else:
            return f"Chapter {self.clean_chapter_number()}"

    def slug_chapter_number(self):
        return self.clean_chapter_number().replace(".", "-")

    def get_chapter_time(self):
        upload_date = self.uploaded_on
        upload_time = (
            datetime.utcnow().replace(tzinfo=timezone.utc) - upload_date
        ).total_seconds()
        days = int(upload_time // (24 * 3600))
        upload_time = upload_time % (24 * 3600)
        hours = int(upload_time // 3600)
        upload_time %= 3600
        minutes = int(upload_time // 60)
        upload_time %= 60
        seconds = int(upload_time)
        if days == 0 and hours == 0 and minutes == 0:
            upload_date = f"{seconds} second{'s' if seconds != 1 else ''} ago"
        elif days == 0 and hours == 0:
            upload_date = f"{minutes} min{'s' if minutes != 1 else ''} ago"
        elif days == 0:
            upload_date = f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif days < 7:
            upload_date = f"{days} day{'s' if days != 1 else ''} ago"
        else:
            upload_date = upload_date.strftime("%Y-%m-%d")
        return upload_date

    def __str__(self):
        return f"{self.chapter_number} - {self.title} | {self.group}"

    def get_absolute_url(self):
        return f"/read/manga/{self.series.slug}/{Chapter.slug_chapter_number(self)}/1/"

    def get_private_absolute_url(self):
        return f"{self.get_absolute_url()}?showprivate={hashlib.md5(self.clean_title().encode()).hexdigest()}"

    def first_page_absolute_url(self):
        chapter_folder_path = self.chapter_path_relative_to_media_root()
        # Use this if our png are not optimized enough and it is eating up our bandwidth
        # chapter_folder_path = os.path.join(
        #     "manga", series_slug, "chapters", chapter.folder, str(chapter.group.id) + "_shrunk"
        # )

        query_string = "" if not self.version else f"?v{self.version}"
        filenames = sorted(
            [
                filename + query_string
                for filename in os.listdir(self.chapter_local_path())
            ]
        )
        if filenames:
            return settings.MEDIA_URL + os.path.join(chapter_folder_path, filenames[0])
        # Return something if there are no page
        return "/static/img/bg_box_blur_smol.jpg"
    
    def image_paths(self) -> List[str]:
        chapter_folder_path = self.chapter_local_path()
        return list(sorted(
            [
                os.path.join(chapter_folder_path, filename) for filename in os.listdir(chapter_folder_path)
            ]
        ))

    def chapter_path_relative_to_media_root(self) -> str:
        return os.path.join("manga", self.series.slug, "chapters", self.folder, str(self.group.id))

    def chapter_local_path(self) -> str:
        return os.path.join(settings.MEDIA_ROOT, self.chapter_path_relative_to_media_root())

    class Meta:
        ordering = ("chapter_number",)
        unique_together = (
            "chapter_number",
            "series",
            "group",
        )


class ChapterIndex(models.Model):
    word = models.CharField(max_length=48, db_index=True)
    chapter_and_pages = models.TextField()
    series = models.ForeignKey(Series, on_delete=models.CASCADE)

    def __str__(self):
        return self.word

    class Meta:
        unique_together = (
            "word",
            "series",
        )
