"""Draw the Subtitle Maker logo and save icon.ico + icon.png next to this file.

Run (from the subtitle-maker folder):  uv run assets/make_icon.py

Same family as the Video Downloader logo (rounded tile, white glyph) with a
cyan->violet gradient: a screen outline with two subtitle lines at the bottom.
Geometry is on a 100x100 grid and matches the inline SVG in ui/index.html.
"""

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
S = 1024
U = S / 100

TOP_LEFT = (6, 182, 212)  # #06B6D4 cyan
BOTTOM_RIGHT = (139, 92, 246)  # #8B5CF6 violet


def u(*vals: float) -> list[float]:
    return [v * U for v in vals]


def gradient() -> Image.Image:
    img = Image.new("RGB", (S, S))
    px = img.load()
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * (S - 1))
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP_LEFT, BOTTOM_RIGHT))
    return img


def draw() -> Image.Image:
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(u(0, 0, 100, 100), radius=24 * U, fill=255)
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile.paste(gradient(), (0, 0), mask)

    d = ImageDraw.Draw(tile)
    white = (255, 255, 255, 255)
    d.rounded_rectangle(u(18, 24, 82, 76), radius=11 * U, outline=white, width=int(7 * U))  # screen
    d.rounded_rectangle(u(30, 46, 70, 53), radius=3.5 * U, fill=white)  # subtitle line 1
    d.rounded_rectangle(u(38, 57.5, 62, 64.5), radius=3.5 * U, fill=white)  # subtitle line 2
    return tile


def main() -> None:
    img = draw()
    img.resize((512, 512), Image.LANCZOS).save(HERE / "icon.png")
    img.resize((256, 256), Image.LANCZOS).save(
        HERE / "icon.ico", sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print("wrote", HERE / "icon.png", "and", HERE / "icon.ico")


if __name__ == "__main__":
    main()
