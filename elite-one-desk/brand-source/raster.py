import subprocess, os
from PIL import Image

OUT = 'out'
BASE_H = 350.0            # SVG user units are points at 1pt = 1px

def render(svg, height_px, dest):
    """mutool renders SVG at a DPI; 72dpi == 1 unit per pixel."""
    dpi = 72.0 * height_px / BASE_H
    subprocess.run(['mutool', 'draw', '-c', 'rgba', '-A', '8',
                    '-r', f'{dpi:.4f}', '-o', dest, svg],
                   check=True, capture_output=True)
    return Image.open(dest).convert('RGBA')

def trim(im, pad=0):
    bb = im.getbbox()
    im = im.crop(bb)
    if pad:
        c = Image.new('RGBA', (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
        c.paste(im, (pad, pad)); im = c
    return im

def save(im, stem, webp=True):
    im.save(f'{OUT}/{stem}.png', optimize=True)
    if webp:
        im.save(f'{OUT}/{stem}.webp', quality=92, method=6)

# --- emblem (the globe/plane/desk mark) -------------------------------------
for theme, src in (('', 'mark.svg'), ('-light', 'mark-light.svg')):
    master = render(src, 1400, f'{OUT}/_tmp.png')
    master = trim(master)
    for h in (512, 256, 128):
        w = round(master.width * h / master.height)
        save(master.resize((w, h), Image.LANCZOS), f'mark{theme}-{h}')

# --- full lockup ------------------------------------------------------------
for theme, src in (('', 'logo.svg'), ('-light', 'logo-light.svg')):
    master = trim(render(src, 1400, f'{OUT}/_tmp.png'))
    for h in (320, 160, 80):
        w = round(master.width * h / master.height)
        save(master.resize((w, h), Image.LANCZOS), f'logo{theme}-{h}')

# --- favicons: the emblem on the brand navy, squared ------------------------
NAVY = (21, 19, 72, 255)
mark = trim(render('mark-light.svg', 1600, f'{OUT}/_tmp.png'))
for size in (512, 180, 64, 32):
    pad = round(size * 0.08)
    inner = size - pad * 2
    scale = min(inner / mark.width, inner / mark.height)
    m = mark.resize((max(1, round(mark.width * scale)),
                     max(1, round(mark.height * scale))), Image.LANCZOS)
    canvas = Image.new('RGBA', (size, size), NAVY)
    canvas.paste(m, ((size - m.width) // 2, (size - m.height) // 2), m)
    canvas.save(f'{OUT}/favicon-{size}.png', optimize=True)
Image.open(f'{OUT}/favicon-512.png').save(
    f'{OUT}/favicon.ico', sizes=[(16, 16), (32, 32), (48, 48)])

# --- default Open Graph card ------------------------------------------------
og = Image.new('RGBA', (1200, 630), (12, 11, 43, 255))
lock = trim(render('logo-light.svg', 1400, f'{OUT}/_tmp.png'))
w = 760; h = round(lock.height * w / lock.width)
lock = lock.resize((w, h), Image.LANCZOS)
og.paste(lock, ((1200 - w) // 2, (630 - h) // 2 - 34), lock)
bar = Image.new('RGBA', (168, 5), (229, 108, 37, 255))
og.paste(bar, ((1200 - 168) // 2, (630 - h) // 2 - 34 + h + 46), bar)
og.convert('RGB').save(f'{OUT}/og-default.jpg', quality=88, optimize=True)

os.remove(f'{OUT}/_tmp.png')
for f in sorted(os.listdir(OUT)):
    print(f'{f:26} {os.path.getsize(OUT + "/" + f) / 1024:7.1f} KB')
