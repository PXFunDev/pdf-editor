"""PDF splitting module using pypdf."""

from pathlib import Path

from pypdf import PdfReader, PdfWriter


def split_pdf(pdf_path: str, output_dir: str) -> list[str]:
    """Split a PDF into individual single-page files.

    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Directory where the split pages will be saved.

    Returns:
        List of absolute paths to the generated PDF files.
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(pdf_path))
    output_files: list[str] = []

    for page_num in range(len(reader.pages)):
        writer = PdfWriter()
        writer.add_page(reader.pages[page_num])
        out_file = output_dir / f"{pdf_path.stem}_page_{page_num + 1:03d}.pdf"
        with open(out_file, "wb") as f:
            writer.write(f)
        output_files.append(str(out_file))

    return output_files


def _parse_ranges(range_str: str, total_pages: int) -> list[list[int]]:
    """Parse a range string such as ``"1-3, 5, 7-9"`` into groups of page numbers.

    Page numbers are 1-based and clamped to ``[1, total_pages]``.

    Returns:
        List of page-number lists, one list per range group.
    """
    groups: list[list[int]] = []
    for part in range_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            try:
                start = max(1, int(start_str.strip()))
                end = min(total_pages, int(end_str.strip()))
            except ValueError:
                raise ValueError(
                    f"Invalid page range format: expected numbers, got \"{part}\""
                )
            if start <= end:
                groups.append(list(range(start, end + 1)))
        else:
            try:
                page = int(part.strip())
            except ValueError:
                raise ValueError(
                    f"Invalid page number: expected a number, got \"{part}\""
                )
            if 1 <= page <= total_pages:
                groups.append([page])
    return groups


def split_by_range(pdf_path: str, output_dir: str, range_str: str) -> list[str]:
    """Split a PDF according to page-range specifications.

    Each range group produces one output PDF containing only those pages.

    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Directory where split files will be saved.
        range_str: Comma-separated page ranges, e.g. ``"1-3, 5, 7-9"``.

    Returns:
        List of absolute paths to the generated PDF files.
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    groups = _parse_ranges(range_str, total_pages)
    output_files: list[str] = []

    for group_idx, pages in enumerate(groups):
        writer = PdfWriter()
        for page_num in pages:
            writer.add_page(reader.pages[page_num - 1])
        label = f"{pages[0]}-{pages[-1]}" if len(pages) > 1 else str(pages[0])
        out_file = output_dir / f"{pdf_path.stem}_range_{group_idx + 1:03d}_p{label}.pdf"
        with open(out_file, "wb") as f:
            writer.write(f)
        output_files.append(str(out_file))

    return output_files
