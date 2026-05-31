"""
Test tesserocr OCR on data/pics/B1 images.
Outputs one .txt file per image into data/ocr_output/B1/.
"""

from pathlib import Path
import tesserocr
from PIL import Image

TESSDATA = "/opt/homebrew/share/tessdata/"
LANG = "deu+chi_sim"
INPUT_DIR = Path(__file__).parent.parent / "data" / "pics" / "B1"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "ocr_output" / "B1"


def ocr_image(image_path: Path, api: tesserocr.PyTessBaseAPI) -> str:
    img = Image.open(image_path)
    api.SetImage(img)
    return api.GetUTF8Text()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    images = sorted(INPUT_DIR.glob("*.png"))
    if not images:
        print(f"No PNG files found in {INPUT_DIR}")
        return

    print(f"Processing {len(images)} images with lang={LANG} ...")

    with tesserocr.PyTessBaseAPI(path=TESSDATA, lang=LANG) as api:
        for img_path in images:
            text = ocr_image(img_path, api)
            out_path = OUTPUT_DIR / (img_path.stem + ".txt")
            out_path.write_text(text, encoding="utf-8")
            line_count = text.count("\n")
            print(f"  {img_path.name} -> {out_path.name}  ({line_count} lines)")

    print(f"\nDone. Output in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
