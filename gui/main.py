"""PDF Editor – Flet GUI entry point."""

import sys
import threading
from pathlib import Path

import flet as ft

# Allow imports from the project root regardless of the working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pdf_merge import merge_folder, merge_pdfs
from src.pdf_split import split_by_range, split_pdf
from src.pdf_to_img import convert_folder, pdf_to_images

BASE_DIR = Path(__file__).parent.parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"


def main(page: ft.Page) -> None:
    page.title = "PDF Editor"
    page.window.width = 920
    page.window.height = 760
    page.padding = 20
    page.theme_mode = ft.ThemeMode.LIGHT

    OUTPUT_DIR.mkdir(exist_ok=True)
    INPUT_DIR.mkdir(exist_ok=True)

    # ── shared log area ────────────────────────────────────────────────
    log_field = ft.TextField(
        multiline=True,
        read_only=True,
        min_lines=6,
        max_lines=8,
        expand=True,
        text_size=12,
        border_color=ft.Colors.BLUE_GREY_200,
    )

    def log(msg: str) -> None:
        log_field.value = (log_field.value or "") + msg + "\n"
        page.update()

    def clear_log(e) -> None:
        log_field.value = ""
        page.update()

    # ── file pickers ───────────────────────────────────────────────────
    conv_file_picker = ft.FilePicker()
    conv_dir_picker = ft.FilePicker()
    split_file_picker = ft.FilePicker()
    merge_files_picker = ft.FilePicker()
    merge_dir_picker = ft.FilePicker()

    page.overlay.extend(
        [
            conv_file_picker,
            conv_dir_picker,
            split_file_picker,
            merge_files_picker,
            merge_dir_picker,
        ]
    )

    # ════════════════════════════════════════════════════════════════════
    # TAB 1 – Convert PDF → Image
    # ════════════════════════════════════════════════════════════════════
    conv_source = ft.TextField(
        label="入力ファイル / フォルダ",
        hint_text="ファイルまたはフォルダを選択してください",
        expand=True,
    )
    conv_mode = ft.RadioGroup(
        content=ft.Row(
            [
                ft.Radio(value="file", label="ファイル"),
                ft.Radio(value="folder", label="フォルダ"),
            ]
        ),
        value="file",
    )
    conv_fmt = ft.RadioGroup(
        content=ft.Row(
            [
                ft.Radio(value="jpeg", label="JPEG"),
                ft.Radio(value="png", label="PNG"),
            ]
        ),
        value="jpeg",
    )
    conv_dpi = ft.Dropdown(
        label="解像度 (DPI)",
        options=[
            ft.dropdown.Option("72"),
            ft.dropdown.Option("150"),
            ft.dropdown.Option("300"),
        ],
        value="150",
        width=160,
    )

    def _on_conv_file(e: ft.FilePickerResultEvent) -> None:
        if e.files:
            conv_source.value = e.files[0].path
            page.update()

    def _on_conv_dir(e: ft.FilePickerResultEvent) -> None:
        if e.path:
            conv_source.value = e.path
            page.update()

    conv_file_picker.on_result = _on_conv_file
    conv_dir_picker.on_result = _on_conv_dir

    def _pick_conv_source(e) -> None:
        if conv_mode.value == "file":
            conv_file_picker.pick_files(
                allowed_extensions=["pdf", "PDF"], allow_multiple=False
            )
        else:
            conv_dir_picker.get_directory_path()

    def _do_convert(e) -> None:
        source = (conv_source.value or "").strip()
        if not source:
            log("⚠ ファイルまたはフォルダを選択してください")
            return
        fmt = conv_fmt.value or "jpeg"
        dpi = int(conv_dpi.value or "150")

        def run() -> None:
            try:
                if conv_mode.value == "file":
                    log(f"▶ 変換開始: {source}")
                    files = pdf_to_images(source, str(OUTPUT_DIR), fmt, dpi)
                    log(f"✓ 完了: {len(files)} ページ → {OUTPUT_DIR}")
                else:
                    log(f"▶ フォルダ変換開始: {source}")
                    results = convert_folder(source, str(OUTPUT_DIR), fmt, dpi)
                    ok = sum(
                        len(v) for v in results.values() if isinstance(v, list)
                    )
                    ng = sum(1 for v in results.values() if isinstance(v, str))
                    log(
                        f"✓ 完了: {len(results)} ファイル / {ok} ページ変換"
                        + (f" / {ng} エラー" if ng else "")
                        + f" → {OUTPUT_DIR}"
                    )
            except Exception as exc:
                log(f"✗ エラー: {exc}")
            page.update()

        threading.Thread(target=run, daemon=True).start()

    convert_tab = ft.Tab(
        text="PDF → 画像",
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "PDF を JPEG / PNG に変換",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Row(
                        [ft.Text("変換モード:", width=90), conv_mode],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            conv_source,
                            ft.ElevatedButton("選択", on_click=_pick_conv_source),
                        ]
                    ),
                    ft.Row(
                        [
                            ft.Column(
                                [ft.Text("出力フォーマット:"), conv_fmt]
                            ),
                            ft.VerticalDivider(width=20),
                            ft.Column([conv_dpi]),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.ElevatedButton(
                        "変換実行",
                        icon=ft.Icons.IMAGE,
                        on_click=_do_convert,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.BLUE_600,
                            color=ft.Colors.WHITE,
                        ),
                        width=200,
                    ),
                ],
                spacing=16,
            ),
            padding=ft.padding.all(20),
        ),
    )

    # ════════════════════════════════════════════════════════════════════
    # TAB 2 – Split PDF
    # ════════════════════════════════════════════════════════════════════
    split_source = ft.TextField(
        label="分割するPDFファイル",
        hint_text="PDFファイルを選択してください",
        expand=True,
    )
    split_mode = ft.RadioGroup(
        content=ft.Row(
            [
                ft.Radio(value="all", label="全ページ（1ページずつ）"),
                ft.Radio(value="range", label="ページ範囲指定"),
            ]
        ),
        value="all",
    )
    split_range = ft.TextField(
        label="ページ範囲（例: 1-3, 5, 7-9）",
        hint_text="カンマ区切りで範囲を指定",
        expand=True,
    )

    def _on_split_file(e: ft.FilePickerResultEvent) -> None:
        if e.files:
            split_source.value = e.files[0].path
            page.update()

    split_file_picker.on_result = _on_split_file

    def _do_split(e) -> None:
        source = (split_source.value or "").strip()
        if not source:
            log("⚠ PDFファイルを選択してください")
            return

        def run() -> None:
            try:
                if split_mode.value == "all":
                    log(f"▶ 分割開始: {source}")
                    files = split_pdf(source, str(OUTPUT_DIR))
                    log(f"✓ 完了: {len(files)} ファイルに分割 → {OUTPUT_DIR}")
                else:
                    rng = (split_range.value or "").strip()
                    if not rng:
                        log("⚠ ページ範囲を入力してください")
                        return
                    log(f"▶ 範囲分割開始: {source}  範囲: {rng}")
                    files = split_by_range(source, str(OUTPUT_DIR), rng)
                    log(f"✓ 完了: {len(files)} ファイルに分割 → {OUTPUT_DIR}")
            except Exception as exc:
                log(f"✗ エラー: {exc}")
            page.update()

        threading.Thread(target=run, daemon=True).start()

    split_tab = ft.Tab(
        text="PDF 分割",
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("PDF を分割", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            split_source,
                            ft.ElevatedButton(
                                "選択",
                                on_click=lambda e: split_file_picker.pick_files(
                                    allowed_extensions=["pdf", "PDF"],
                                    allow_multiple=False,
                                ),
                            ),
                        ]
                    ),
                    ft.Row(
                        [ft.Text("分割モード:", width=90), split_mode],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    split_range,
                    ft.ElevatedButton(
                        "分割実行",
                        icon=ft.Icons.CALL_SPLIT,
                        on_click=_do_split,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.GREEN_600,
                            color=ft.Colors.WHITE,
                        ),
                        width=200,
                    ),
                ],
                spacing=16,
            ),
            padding=ft.padding.all(20),
        ),
    )

    # ════════════════════════════════════════════════════════════════════
    # TAB 3 – Merge PDFs
    # ════════════════════════════════════════════════════════════════════
    merge_mode = ft.RadioGroup(
        content=ft.Row(
            [
                ft.Radio(value="files", label="ファイル選択"),
                ft.Radio(value="folder", label="フォルダ内すべて"),
            ]
        ),
        value="files",
    )
    merge_dir_field = ft.TextField(
        label="PDFフォルダ",
        hint_text="フォルダを選択してください",
        expand=True,
    )
    merge_output = ft.TextField(
        label="出力ファイル名",
        value="merged.pdf",
        width=280,
    )
    merge_file_list = ft.ListView(expand=True, height=130)
    _merge_paths: list[str] = []

    def _refresh_merge_list() -> None:
        merge_file_list.controls.clear()
        for idx, path in enumerate(_merge_paths):

            def _make_remove(i: int):
                def _remove(e) -> None:
                    _merge_paths.pop(i)
                    _refresh_merge_list()

                return _remove

            merge_file_list.controls.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.PICTURE_AS_PDF, color=ft.Colors.RED_400),
                        ft.Text(Path(path).name, expand=True, size=12),
                        ft.IconButton(
                            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                            tooltip="削除",
                            on_click=_make_remove(idx),
                        ),
                    ]
                )
            )
        page.update()

    def _on_merge_files(e: ft.FilePickerResultEvent) -> None:
        if e.files:
            for f in e.files:
                if f.path not in _merge_paths:
                    _merge_paths.append(f.path)
            _refresh_merge_list()

    def _on_merge_dir(e: ft.FilePickerResultEvent) -> None:
        if e.path:
            merge_dir_field.value = e.path
            page.update()

    merge_files_picker.on_result = _on_merge_files
    merge_dir_picker.on_result = _on_merge_dir

    def _do_merge(e) -> None:
        out_name = (merge_output.value or "merged.pdf").strip()
        if not out_name.lower().endswith(".pdf"):
            out_name += ".pdf"
        out_path = str(OUTPUT_DIR / out_name)

        def run() -> None:
            try:
                if merge_mode.value == "files":
                    if not _merge_paths:
                        log("⚠ PDFファイルを追加してください")
                        return
                    log(f"▶ 結合開始: {len(_merge_paths)} ファイル")
                    result = merge_pdfs(_merge_paths, out_path)
                    log(f"✓ 完了: {result}")
                else:
                    folder = (merge_dir_field.value or "").strip()
                    if not folder:
                        log("⚠ フォルダを選択してください")
                        return
                    log(f"▶ フォルダ結合開始: {folder}")
                    result = merge_folder(folder, out_path)
                    log(f"✓ 完了: {result}")
            except Exception as exc:
                log(f"✗ エラー: {exc}")
            page.update()

        threading.Thread(target=run, daemon=True).start()

    def _clear_merge_list(e) -> None:
        _merge_paths.clear()
        _refresh_merge_list()

    merge_tab = ft.Tab(
        text="PDF 結合",
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("PDF を結合", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [ft.Text("結合モード:", width=90), merge_mode],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            merge_dir_field,
                            ft.ElevatedButton(
                                "フォルダ選択",
                                on_click=lambda e: merge_dir_picker.get_directory_path(),
                            ),
                        ]
                    ),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "PDFを追加",
                                icon=ft.Icons.ADD,
                                on_click=lambda e: merge_files_picker.pick_files(
                                    allowed_extensions=["pdf", "PDF"],
                                    allow_multiple=True,
                                ),
                            ),
                            ft.ElevatedButton(
                                "リストをクリア",
                                icon=ft.Icons.CLEAR_ALL,
                                on_click=_clear_merge_list,
                            ),
                        ]
                    ),
                    merge_file_list,
                    ft.Row([merge_output]),
                    ft.ElevatedButton(
                        "結合実行",
                        icon=ft.Icons.MERGE,
                        on_click=_do_merge,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.ORANGE_600,
                            color=ft.Colors.WHITE,
                        ),
                        width=200,
                    ),
                ],
                spacing=16,
            ),
            padding=ft.padding.all(20),
        ),
    )

    # ── main layout ────────────────────────────────────────────────────
    page.add(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.PICTURE_AS_PDF, size=32, color=ft.Colors.RED_500
                        ),
                        ft.Text(
                            "PDF Editor",
                            size=26,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(),
                ft.Tabs(
                    tabs=[convert_tab, split_tab, merge_tab],
                    expand=True,
                ),
                ft.Divider(),
                ft.Row(
                    [
                        ft.Text("ログ", weight=ft.FontWeight.BOLD),
                        ft.TextButton("クリア", on_click=clear_log),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                log_field,
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
