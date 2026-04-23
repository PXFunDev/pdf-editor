"""PDF merging module using pypdf."""

from pathlib import Path

from pypdf import PdfWriter


def merge_pdfs(pdf_paths: list[str], output_path: str) -> str:
    """Merge multiple PDF files into a single output file.

    Args:
        pdf_paths: Ordered list of paths to input PDF files.
        output_path: Full path (including filename) for the merged PDF.

    Returns:
        Absolute path to the merged PDF file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = PdfWriter()
    for path in pdf_paths:
        writer.append(str(path))

    with open(output_path, "wb") as f:
        writer.write(f)

    return str(output_path)


def merge_folder(input_dir: str, output_path: str) -> str:
    """Merge all PDF files found in a directory into a single output file.

    Files are merged in alphabetical order of their filenames.

    Args:
        input_dir: Directory containing PDF files to merge.
        output_path: Full path (including filename) for the merged PDF.

    Returns:
        Absolute path to the merged PDF file.
    """
    input_dir = Path(input_dir)
    pdf_files = sorted(input_dir.glob("*.pdf")) + sorted(input_dir.glob("*.PDF"))

    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found in: {input_dir}")

    return merge_pdfs([str(p) for p in pdf_files], output_path)
