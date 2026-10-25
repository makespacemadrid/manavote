"""Validate proposal uploads without touching an existing proposal image."""

import logging
from pathlib import Path
import secrets


logger = logging.getLogger(__name__)


class InvalidProposalImage(ValueError):
    pass


def save_proposal_image(image, *, upload_folder, detect_image_type):
    if image is None or not image.filename:
        return None
    extension = Path(image.filename).suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png"}:
        logger.info("event=proposal_image_rejected reason_code=unsupported_extension")
        raise InvalidProposalImage("Invalid image format")

    filename = f"{secrets.token_hex(8)}{extension}"
    path = Path(upload_folder) / filename
    valid = False
    try:
        image.save(path)
        if detect_image_type(str(path)) not in {"jpeg", "png"}:
            logger.info("event=proposal_image_rejected reason_code=invalid_content")
            raise InvalidProposalImage("Invalid image format")
        valid = True
    finally:
        if not valid:
            path.unlink(missing_ok=True)
    return filename


def remove_proposal_image(filename, *, upload_folder):
    if filename:
        (Path(upload_folder) / filename).unlink(missing_ok=True)
