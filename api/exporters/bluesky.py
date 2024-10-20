from typing import Optional, Tuple
from atproto import Client, models, client_utils
import os
from django.conf import settings
from reader.models import Chapter, ChapterIndex, Group, Series, Volume
from PIL import Image
import io

BLUESKY_MAX_UPLOAD_BYTES = 1_000_000

def is_bluesky_supported() -> bool:
    return settings.BLUESKY_USERNAME and settings.BLUESKY_PASSWORD

def upload_thumbnail_preview(client: Client, chapter: Chapter):
    filenames = sorted(os.listdir(chapter.chapter_local_path()))
    if not filenames:
        return
    local_path_to_first_page = os.path.join(chapter.chapter_local_path(), filenames[0])
    
    try:
        img = Image.open(local_path_to_first_page)
    except:
        print(f"Failed to open chapter's first page {local_path_to_first_page}")
        return
    
    img.thumbnail((img.width, 512), Image.ANTIALIAS)
    img_byte_arr = io.BytesIO()
    img.save(
        img_byte_arr,
        "JPEG",
        quality=100,
        optimize=True,
        progressive=True,
    )
    img_byte_buff = img_byte_arr.getvalue()
    if len(img_byte_buff) > BLUESKY_MAX_UPLOAD_BYTES:
        print(f"Thumbnail image is too large for bluesky ({len(img_byte_buff)} > {BLUESKY_MAX_UPLOAD_BYTES} bytes). No thumbail.")
        return
    try:
        upload = client.upload_blob(img_byte_buff)
    except Exception as err:
        print(f"Caught exception while uploading image to bluesky: {err}")
        return
    return upload.blob

def publish_post(uri_scheme: str, chapter: Chapter) -> Optional[str]:
    if not is_bluesky_supported():
        return

    title =  f" {chapter.series.name} - Oneshot" if chapter.chapter_number == 0 and chapter.series.is_oneshot else f"{chapter.series.name} - {chapter.clean_title()}"
    root = f"{uri_scheme}://{settings.CANONICAL_ROOT_DOMAIN}"
    chapter_url = f'{root}{chapter.get_absolute_url()}'

    content = client_utils.TextBuilder().text(f'[New Release] {title} by {chapter.series.author.name}')

    if chapter.scraper_hash:
        content = content.text('\n').link("Read on MangaDex", f"https://mangadex.org/chapter/{chapter.scraper_hash}")
    content = content.text('\n').link("Read on Danke", chapter_url)
    if not chapter.series.is_oneshot:
        content = content.text('\n').link("Other chapters", f"{root}{chapter.series.get_absolute_url()}")
    
    client = Client()
    try:
        client.login(settings.BLUESKY_USERNAME, settings.BLUESKY_PASSWORD)
        thumbnail_blob = upload_thumbnail_preview(client, chapter)
        embed = None
        if thumbnail_blob:
            ext_embed = models.app.bsky.embed.external.External(title=title,
                                                            uri=chapter_url,
                                                            description="",
                                                            thumb=thumbnail_blob)
            embed = models.app.bsky.embed.external.Main(external=ext_embed)
        post = client.send_post(content, embed=embed)
    except Exception as err:
        print(f"Caught exception while publishing bluesky post: {err}")
        return
    return str(post.uri)
