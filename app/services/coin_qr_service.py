"""Printable branded QR labels with high error correction and a quiet zone."""
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

_LOGO = Path(__file__).resolve().parents[2] / 'static/img/brands/coca-cola.png'


def _font(size):
    try:
        return ImageFont.truetype('DejaVuSans-Bold.ttf', size)
    except OSError:
        return ImageFont.load_default(size=size)


def qr_brand(item_name):
    name = ' '.join(str(item_name).casefold().replace('-', ' ').split())
    if name in {'coke', 'coca cola', 'cocacola'}:
        return 'coke'
    if name in {'coke zero', 'coca cola zero', 'cocacola zero'}:
        return 'zero'
    return None


def render_coin_qr(url, item_name):
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    code.add_data(url)
    code.make(fit=True)
    qr = code.make_image(fill_color='black', back_color='white').convert('RGB')
    brand = qr_brand(item_name)
    if brand is None:
        return qr
    with Image.open(_LOGO) as source:
        artwork = source.convert('RGBA')
    if brand == 'zero':
        black = Image.new('RGBA', artwork.size, 'black')
        black.putalpha(artwork.getchannel('A'))
        artwork = black
    width = int(qr.width * .22)
    height = round(width * artwork.height / artwork.width)
    artwork = artwork.resize((width, height), Image.Resampling.LANCZOS)
    padding = max(4, qr.width // 100)
    zero_height = height if brand == 'zero' else 0
    badge = Image.new('RGB', (width + padding * 2, height + zero_height + padding * 2), 'white')
    badge.paste(artwork, (padding, padding), artwork)
    if brand == 'zero':
        ImageDraw.Draw(badge).text((badge.width / 2, padding + height + zero_height / 2),
            'ZERO', font=_font(max(10, zero_height - 2)), fill='black', anchor='mm')
    qr.paste(badge, ((qr.width - badge.width) // 2, (qr.height - badge.height) // 2))
    return qr
