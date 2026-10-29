"""Printable branded QR labels with high error correction and a quiet zone."""
import qrcode
from PIL import Image, ImageDraw, ImageFont


def _font(size):
    try:
        return ImageFont.truetype('DejaVuSans-Bold.ttf', size)
    except OSError:
        return ImageFont.load_default(size=size)


def render_coin_qr(url, item_name):
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    code.add_data(url)
    code.make(fit=True)
    qr = code.make_image(fill_color='black', back_color='white').convert('RGB')
    if item_name not in {'Coke', 'Coke Zero'}:
        return qr
    color = '#d90000' if item_name == 'Coke' else '#000000'
    logo_size = int(qr.width * .14)
    logo = Image.new('RGB', (logo_size, logo_size), 'white')
    draw = ImageDraw.Draw(logo)
    draw.ellipse((3, 3, logo_size - 3, logo_size - 3), fill=color)
    draw.text((logo_size / 2, logo_size / 2), 'Coke' if item_name == 'Coke' else 'Coke\nZERO', font=_font(max(10, logo_size // 5)), fill='white', anchor='mm', align='center')
    qr.paste(logo, ((qr.width - logo_size) // 2, (qr.height - logo_size) // 2))
    title_height = 100
    label = Image.new('RGB', (qr.width, qr.height + title_height), 'white')
    ImageDraw.Draw(label).text((qr.width / 2, title_height / 2), 'COKE' if item_name == 'Coke' else 'COKE ZERO', font=_font(48), fill=color, anchor='mm')
    label.paste(qr, (0, title_height))
    return label
