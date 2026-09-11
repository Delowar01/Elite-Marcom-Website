"""Turn mutool's 800-path dump into a handful of tidy, grouped SVG assets."""
import re, sys

SRC = 'logo1.svg'
NUM = re.compile(r'-?\d*\.?\d+')

def parse_paths(svg):
    out = []
    for m in re.finditer(r'<path\b([^>]*?)/>', svg, re.S):
        attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', m.group(1)))
        if 'd' in attrs:
            out.append((attrs.get('fill', '#000000'), attrs['d']))
    return out

def tokens(d):
    """Yield (command, [numbers]) for an absolute-only path string."""
    for cmd, body in re.findall(r'([MLHVCZ])([^MLHVCZ]*)', d):
        yield cmd, [float(n) for n in NUM.findall(body)]

def bbox(d):
    xs, ys, x, y = [], [], 0.0, 0.0
    for cmd, n in tokens(d):
        if cmd == 'M' or cmd == 'L':
            for i in range(0, len(n) - 1, 2):
                x, y = n[i], n[i + 1]; xs.append(x); ys.append(y)
        elif cmd == 'H':
            for v in n: x = v; xs.append(x)
        elif cmd == 'V':
            for v in n: y = v; ys.append(y)
        elif cmd == 'C':
            for i in range(0, len(n) - 5, 6):
                xs += n[i:i + 6:2]; ys += n[i + 1:i + 6:2]
                x, y = n[i + 4], n[i + 5]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)

def fmt(v):
    r = round(v)
    return str(int(r)) if abs(v - r) < 0.35 else f'{v:.1f}'.rstrip('0').rstrip('.')

def compact(d):
    """Re-emit a path with rounded numbers and no redundant separators."""
    parts = []
    for cmd, n in tokens(d):
        if cmd == 'Z':
            parts.append('Z'); continue
        s = cmd
        for i, v in enumerate(n):
            t = fmt(v)
            if i and not t.startswith('-'):
                s += ' '
            s += t
        parts.append(s)
    return ''.join(parts)

def build(paths, colours, viewbox, width, height, shift_x=0.0):
    """Merge paths by fill into one <path> each, inside a single transform group."""
    groups, order = {}, []
    for fill, d in paths:
        col = colours.get(fill.lower(), fill)
        if col == 'none':
            continue
        if col not in groups:
            groups[col] = []; order.append(col)
        groups[col].append(compact(d))
    tx = f'matrix(.1,0,0,-.1,{fmt(-shift_x * 10)},350)' if shift_x else 'matrix(.1,0,0,-.1,0,350)'
    body = '\n'.join(
        f'<path fill="{c}" d="{"".join(groups[c])}"/>' for c in order)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" '
            f'width="{width}" height="{height}" role="img">\n'
            f'<g transform="{tx}">\n{body}\n</g>\n</svg>\n')

svg = open(SRC).read()
paths = parse_paths(svg)
print(f'parsed {len(paths)} paths')

# Split emblem from wordmark on the widest empty column between them.
boxes = [bbox(d) for _, d in paths]
spans = sorted((b[0] / 10, b[2] / 10) for b in boxes)
runs = [list(spans[0])]
for a, b in spans[1:]:
    if a <= runs[-1][1] + 0.01:
        runs[-1][1] = max(runs[-1][1], b)
    else:
        runs.append([a, b])
gap, split = max((runs[i + 1][0] - runs[i][1],
                  (runs[i][1] + runs[i + 1][0]) / 2) for i in range(len(runs) - 1))
print(f'widest gap {gap:.1f}pt -> split at {split:.1f}pt')

emblem = [p for p, b in zip(paths, boxes) if b[2] / 10 <= split]
word = [p for p, b in zip(paths, boxes) if b[2] / 10 > split]
ebox = [b for b in boxes if b[2] / 10 <= split]
wbox = [b for b in boxes if b[2] / 10 > split]
print(f'emblem {len(emblem)} paths, wordmark {len(word)} paths, split at {split:.1f}pt')

NAVY, ORANGE, PEACH, WHITE = '#151348', '#e56c25', '#ffa476', '#ffffff'
# The artwork ships with its own navy/orange; map them onto the brand tokens.
DARK_BG = {'#000034': '#f8f7f4', '#ef4a00': ORANGE, '#ff9074': PEACH, '#ffffff': '#f8f7f4'}
LIGHT_BG = {'#000034': NAVY, '#ef4a00': ORANGE, '#ff9074': PEACH, '#ffffff': WHITE}
MONO_LIGHT = {c: '#f8f7f4' for c in ('#000034', '#ef4a00', '#ff9074', '#ffffff')}

W, H = 1022.08, 350
files = {
    'logo.svg':        build(paths, LIGHT_BG, f'0 0 {W} {H}', W, H),
    'logo-light.svg':  build(paths, DARK_BG,  f'0 0 {W} {H}', W, H),
    'logo-mono.svg':   build(paths, MONO_LIGHT, f'0 0 {W} {H}', W, H),
}
ew = max(b[2] for b in ebox) / 10
files['mark.svg'] = build(emblem, LIGHT_BG, f'0 0 {ew:.1f} {H}', round(ew, 1), H)
files['mark-light.svg'] = build(emblem, DARK_BG, f'0 0 {ew:.1f} {H}', round(ew, 1), H)
wx0, wx1 = min(b[0] for b in wbox) / 10, max(b[2] for b in wbox) / 10
files['wordmark-light.svg'] = build(
    word, DARK_BG, f'0 0 {wx1 - wx0:.1f} {H}', round(wx1 - wx0, 1), H, shift_x=wx0)

for name, content in files.items():
    open(name, 'w').write(content)
    print(f'{name:22} {len(content) / 1024:6.1f} KB')
