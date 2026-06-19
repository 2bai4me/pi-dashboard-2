#!/usr/bin/env python3
"""
make_icon.py — Erstellt ein Multi-Resolution ICO fuer PI Dashboard 2.0
Verwendet PIL/Pillow (https://pillow.readthedocs.io)
"""
import os
from PIL import Image, ImageDraw, ImageFont

# ── Konfiguration ───────────────────────────────────────────────────
PROJECT_DIR = r"D:\Entwicklung\PI-Dashboard 2"
OUTPUT_DIR = os.path.join(PROJECT_DIR, "assets")
OUTPUT_ICO = os.path.join(OUTPUT_DIR, "pi-dashboard-icon.ico")
OUTPUT_SVG = os.path.join(OUTPUT_DIR, "pi-dashboard-icon.svg")
SIZES = [16, 32, 48, 64, 128, 256]

# Hermes-Theme-Farben
COLOR_BG_TOP   = (14, 18, 23)    # #0e1217
COLOR_BG_BOT   = (28, 35, 51)    # #1c2333
COLOR_BORDER   = (48, 54, 61)    # #30363d
COLOR_PI       = (88, 166, 255)  # #58a6ff
COLOR_BADGE    = (210, 153, 34)  # #d29922
COLOR_DARK     = (14, 18, 23)    # #0e1217
COLOR_PULSE    = (210, 153, 34)  # #d29922
COLOR_ACCENT   = (46, 160, 67)   # #2ea043 (gruen)
COLOR_DANGER   = (248, 81, 73)   # #f85149 (rot)
COLOR_MUTED    = (33, 38, 45)    # #21262d


def lerp_color(c1, c2, t):
    """Linear-interpolation zwischen 2 RGB-Farben"""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def fill_gradient(img, top_color, bot_color):
    """Vertikaler Gradient"""
    w, h = img.size
    for y in range(h):
        t = y / max(1, h - 1)
        color = lerp_color(top_color, bot_color, t)
        for x in range(w):
            img.putpixel((x, y), color)


def make_pi_icon(size: int) -> Image.Image:
    """Erstellt ein quadratisches Icon in der angegebenen Aufloesung.

    Design: Dashboard-Layout mit 4 Kacheln (Grid 2x2) + Pi-Symbol
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Hintergrund: vertikaler Gradient
    fill_gradient(img, COLOR_BG_TOP, COLOR_BG_BOT)

    # Outer border (subtle)
    border_w = max(1, size // 128)
    for i in range(border_w):
        draw.rectangle([i, i, size - 1 - i, size - 1 - i], outline=COLOR_BORDER)

    # ── Dashboard-Grid: 4 Kacheln ──────────────────────────────────
    if size >= 32:
        # Layout-Konstanten
        margin = max(2, size // 16)
        gap = max(1, size // 48)
        inner_w = size - 2 * margin
        inner_h = size - 2 * margin
        tile_w = (inner_w - gap) // 2
        tile_h = (inner_h - gap) // 2

        # Tile 1: oben-links — Balkendiagramm
        t1_x, t1_y = margin, margin
        draw.rectangle([t1_x, t1_y, t1_x + tile_w, t1_y + tile_h],
                        outline=COLOR_PI, width=max(1, size // 80))
        # Bars
        if size >= 48:
            bar_count = 4
            bar_area_w = tile_w * 0.75
            bar_area_h = tile_h * 0.55
            bar_w = bar_area_w / (bar_count * 1.5)
            start_x = t1_x + (tile_w - bar_area_w) / 2
            base_y = t1_y + tile_h * 0.75
            bar_heights = [0.5, 0.7, 0.4, 0.9]
            for i, h in enumerate(bar_heights):
                bx = start_x + i * (bar_w * 1.5)
                by = base_y - bar_area_h * h
                draw.rectangle([bx, by, bx + bar_w, base_y], fill=COLOR_PI)

        # Tile 2: oben-rechts — Linien-/Trend-Chart
        t2_x = margin + tile_w + gap
        t2_y = margin
        draw.rectangle([t2_x, t2_y, t2_x + tile_w, t2_y + tile_h],
                        outline=COLOR_ACCENT, width=max(1, size // 80))
        # Line chart
        if size >= 48:
            points = [(0.1, 0.7), (0.3, 0.4), (0.5, 0.6), (0.7, 0.3), (0.9, 0.5)]
            chart_w = tile_w * 0.8
            chart_h = tile_h * 0.55
            base_x = t2_x + (tile_w - chart_w) / 2
            base_y = t2_y + tile_h * 0.75
            for i in range(len(points) - 1):
                x1 = base_x + points[i][0] * chart_w
                y1 = base_y - points[i][1] * chart_h
                x2 = base_x + points[i+1][0] * chart_w
                y2 = base_y - points[i+1][1] * chart_h
                draw.line([(x1, y1), (x2, y2)], fill=COLOR_ACCENT,
                          width=max(1, size // 48))
            # Datenpunkte
            for px, py in points:
                cx = base_x + px * chart_w
                cy = base_y - py * chart_h
                r = max(1, size // 64)
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=COLOR_ACCENT)

        # Tile 3: unten-links — Donut/Pie (KPI)
        t3_x = margin
        t3_y = margin + tile_h + gap
        draw.rectangle([t3_x, t3_y, t3_x + tile_w, t3_y + tile_h],
                        outline=COLOR_BADGE, width=max(1, size // 80))
        # Donut chart
        if size >= 48:
            cx = t3_x + tile_w / 2
            cy = t3_y + tile_h / 2
            r_outer = min(tile_w, tile_h) * 0.32
            r_inner = r_outer * 0.55
            # Hintergrund-Ring (dunkel)
            draw.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
                         outline=COLOR_MUTED, width=max(2, size // 32))
            # Vordergrund-Bogen (~75%)
            # PIL kann keine Bogen, daher als 2 Linien simuliert
            # Wir nutzen Arc via pieslice
            try:
                from math import cos, sin, radians
                start_angle = -90
                end_angle = -90 + 270  # 75% von 360
                draw.pieslice([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
                              start=start_angle, end=end_angle, fill=COLOR_BADGE)
                # Innen ausschneiden (Loch)
                draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
                             fill=COLOR_BG_BOT)
            except Exception:
                pass

        # Tile 4: unten-rechts — Status-Indikator
        t4_x = margin + tile_w + gap
        t4_y = margin + tile_h + gap
        draw.rectangle([t4_x, t4_y, t4_x + tile_w, t4_y + tile_h],
                        outline=COLOR_DANGER, width=max(1, size // 80))
        # Status-Punkte (Ampel-Style)
        if size >= 48:
            cx = t4_x + tile_w / 2
            cy_start = t4_y + tile_h * 0.30
            r = min(tile_w, tile_h) * 0.12
            spacing = r * 2.5
            colors = [COLOR_ACCENT, COLOR_BADGE, COLOR_DANGER]
            for i, col in enumerate(colors):
                cy = cy_start + i * spacing
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

        # ── Pi-Symbol zentral (Overlay) ───────────────────────────
        # Wir legen das pi-Symbol als Branding ueber die Kachel-Mitte
        # Kleiner Badge-Style
        badge_size = max(tile_h, tile_w) * 0.95
        center_x = size / 2
        center_y = size / 2
        # Schatten-Ring
        shadow_r = badge_size / 2 + max(2, size // 64)
        draw.ellipse([center_x - shadow_r, center_y - shadow_r,
                      center_x + shadow_r, center_y + shadow_r],
                     fill=(0, 0, 0, 0))  # Kein Shadow, nur Substrat
        # Inner Badge (dunkel, abgerundet)
        inner_r = badge_size / 2
        draw.ellipse([center_x - inner_r, center_y - inner_r,
                      center_x + inner_r, center_y + inner_r],
                     fill=COLOR_BG_BOT, outline=COLOR_PI, width=max(1, size // 48))
        # Pi-Symbol
        try:
            pi_font_size = int(inner_r * 1.3)
            try:
                pi_font = ImageFont.truetype("seguiemj.ttf", pi_font_size)
            except OSError:
                try:
                    pi_font = ImageFont.truetype("segoeui.ttf", pi_font_size)
                except OSError:
                    pi_font = ImageFont.truetype("arial.ttf", pi_font_size)
        except Exception:
            pi_font = ImageFont.load_default()
        pi_text = "\u03c0"
        bbox = draw.textbbox((0, 0), pi_text, font=pi_font)
        try:
            tw = int(draw.textlength(pi_text, font=pi_font))
        except Exception:
            tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = center_x - tw / 2 - bbox[0]
        ty = center_y - th / 2 - bbox[1] - inner_r * 0.05
        # Italic-Look
        draw.text((tx + inner_r * 0.02, ty), pi_text, fill=COLOR_PI, font=pi_font)

    # Fallback fuer sehr kleine Icons (< 32px): nur pi-Symbol
    else:
        try:
            font_size = int(size * 0.65)
            try:
                pi_font = ImageFont.truetype("seguiemj.ttf", font_size)
            except OSError:
                pi_font = ImageFont.truetype("segoeui.ttf", font_size)
        except Exception:
            pi_font = ImageFont.load_default()
        pi_text = "\u03c0"
        bbox = draw.textbbox((0, 0), pi_text, font=pi_font)
        try:
            tw = int(draw.textlength(pi_text, font=pi_font))
        except Exception:
            tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (size - tw) // 2 - bbox[0]
        y = (size - th) // 2 - bbox[1]
        draw.text((x + 1, y), pi_text, fill=COLOR_PI, font=pi_font)

    return img


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Generiere Multi-Resolution ICO nach: {OUTPUT_ICO}")
    print(f"Aufloesungen: {SIZES}")

    images = []
    for size in SIZES:
        print(f"  - {size}x{size} ...", end=" ", flush=True)
        img = make_pi_icon(size)
        images.append(img)
        print("OK")

    # Speichere als Multi-Resolution .ico (manuell erzeugt, da PIL keine
    # echten Multi-Resolution ICOs mit verschiedenen PNG-Codecs erzeugt)
    import struct
    png_payloads = []
    for img in images:
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_payloads.append(buf.getvalue())

    # ICONDIR (6 bytes): reserved(2)=0, type(2)=1, count(2)
    # ICONDIRENTRY (16 bytes pro Eintrag)
    header_size = 6 + 16 * len(png_payloads)

    with open(OUTPUT_ICO, "wb") as f:
        # ICONDIR
        f.write(struct.pack("<HHH", 0, 1, len(png_payloads)))
        # ICONDIRENTRY[]
        offset = header_size
        for i, size in enumerate(SIZES):
            w = 0 if size >= 256 else size
            h = w
            data_size = len(png_payloads[i])
            # width(1), height(1), color_count(1), reserved(1),
            # planes(2), bit_count(2), bytes_in_res(4), image_offset(4)
            f.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, data_size, offset))
            offset += data_size
        # Image data
        for data in png_payloads:
            f.write(data)
    size_bytes = os.path.getsize(OUTPUT_ICO)
    print(f"\nFertig: {OUTPUT_ICO} ({size_bytes} bytes)")


if __name__ == "__main__":
    main()
