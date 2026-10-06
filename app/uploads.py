"""Validate and re-encode images; never serve uploaded executable formats."""
import secrets
import warnings
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 30_000_000


def store_image(file):
    if not file or not file.filename:
        return ''
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(file.stream) as original:
                if original.format not in {'JPEG', 'PNG', 'WEBP', 'GIF'}:
                    raise ValueError('image_format')
                original.load()
                image = ImageOps.exif_transpose(original)
                image.thumbnail((3200, 3200))
                image = image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
                name = secrets.token_hex(20) + '.webp'
                destination = Path(current_app.config['UPLOAD_FOLDER']) / name
                image.save(destination, 'WEBP', quality=88)
                return '/uploads/' + name
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('image_invalid') from exc
