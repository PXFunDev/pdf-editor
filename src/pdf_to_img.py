"""PDF to image conversion module using PyMuPDF (fitz)."""

import fitz  # PyMuPDF
from pathlib import Path


def pdf_to_images(
    pdf_path: str,
    output_dir: str,
    fmt: str = "jpeg",
    dpi: int = 150,
) -> list[str]:
    """Convert each page of a PDF file to an image.

    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Directory where converted images will be saved.
        fmt: Output image format, either ``"jpeg"`` or ``"png"``.
        dpi: Resolution in dots per inch (default 150).

    Returns:
        List of absolute paths to the generated image files.
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ext = "jpg" if fmt.lower() == "jpeg" else "png"
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)

    output_files: list[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=matrix)
            out_file = output_dir / f"{pdf_path.stem}_page_{page_num + 1:03d}.{ext}"
            pix.save(str(out_file))
            output_files.append(str(out_file))

    return output_files


def convert_folder(
    input_dir: str,
    output_dir: str,
    fmt: str = "jpeg",
    dpi: int = 150,
) -> dict[str, list[str] | str]:
    """Convert all PDF files in a folder to images.

    Args:
        input_dir: Directory containing PDF files.
        output_dir: Directory where converted images will be saved.
        fmt: Output image format, either ``"jpeg"`` or ``"png"``.
        dpi: Resolution in dots per inch (default 150).

    Returns:
        Dictionary mapping each PDF path to a list of generated image
        paths (on success) or an error message string (on failure).
    """
    input_dir = Path(input_dir)
    results: dict[str, list[str] | str] = {}

    pdf_files = sorted(input_dir.glob("*.pdf")) + sorted(input_dir.glob("*.PDF"))

    for pdf_file in pdf_files:
        try:
            files = pdf_to_images(str(pdf_file), output_dir, fmt, dpi)
            results[str(pdf_file)] = files
        except Exception as exc:
            results[str(pdf_file)] = str(exc)

    return results
