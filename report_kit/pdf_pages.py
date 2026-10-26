"""Contact sheet of a PDF's pages, to eyeball page breaks, clipped tables and blank pages in one image.

usage: python report_kit/pdf_pages.py <report.pdf> <out.png> [--cols 4] [--width 360] [--pages 1-12]
Needs poppler's pdftoppm and Pillow. Prints the page count.
"""
import argparse
import glob
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("out")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--width", type=int, default=360)
    ap.add_argument("--pages", default="")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["pdftoppm", "-png", "-scale-to", str(a.width)]
        if a.pages:
            first, _, last = a.pages.partition("-")
            cmd += ["-f", first, "-l", last or first]
        subprocess.run(cmd + [a.pdf, os.path.join(tmp, "p")], check=True)
        files = sorted(glob.glob(os.path.join(tmp, "p-*.png")))
        imgs = [Image.open(f).convert("RGB") for f in files]
        w = max(i.width for i in imgs)
        h = max(i.height for i in imgs)
        rows = (len(imgs) + a.cols - 1) // a.cols
        sheet = Image.new("RGB", (a.cols * (w + 8) + 8, rows * (h + 26) + 8), "white")
        d = ImageDraw.Draw(sheet)
        for k, im in enumerate(imgs):
            x, y = 8 + (k % a.cols) * (w + 8), 8 + (k // a.cols) * (h + 26)
            sheet.paste(im, (x, y + 18))
            d.rectangle([x - 1, y + 17, x + im.width, y + 18 + im.height], outline="#999999")
            d.text((x, y + 2), os.path.basename(files[k]).replace("p-", "page ").replace(".png", ""), fill="black")
        sheet.save(a.out)
    print(f"{len(imgs)} pages -> {a.out}")


if __name__ == "__main__":
    main()
