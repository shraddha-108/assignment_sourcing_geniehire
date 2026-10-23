from pathlib import Path

import pymupdf
from rapidocr import RapidOCR


PDF_PATH = Path("data/ADITI_JAIN_Content_Strategist.pdf")


def main():
    engine = RapidOCR()

    document = pymupdf.open(str(PDF_PATH))

    try:
        for page_number, page in enumerate(
            document,
            start=1,
        ):
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(2, 2),
                alpha=False,
            )

            image_bytes = pixmap.tobytes("png")

            result = engine(image_bytes)

            print()
            print("=" * 80)
            print(f"PAGE {page_number}")
            print("=" * 80)

            if result.txts:
                for text, score in zip(
                    result.txts,
                    result.scores,
                ):
                    print(
                        f"{score:.2f} | {text}"
                    )

    finally:
        document.close()


if __name__ == "__main__":
    main()