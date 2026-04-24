# coding: utf-8
# main.py - PDF Editor – Flet GUI entry point
# Python 3.12 / Flet 0.84.0

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, cast

import flet as ft

# Allow imports from the project root regardless of the working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pdf_merge import merge_folder, merge_pdfs
from src.pdf_split import split_by_range, split_pdf
from src.pdf_to_img import convert_folder, pdf_to_images

APP_NAME = "PDF Editor"

BASE_DIR = Path(__file__).parent.parent
INPUT_DIR = BASE_DIR / "input"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"

# SharedPreferences key prefix (他アプリと衝突しないようにユニークに) [3](https://flet.dev/docs/cookbook/client-storage/)
PREF_PREFIX = "panasss.pdf_editor."


# ── tkinter: desktop native dialogs (FilePickerを使わない) ───────────────
def _tk_choose_file(multiple: bool = False):
    """Return a single file path (str) or list[str] if multiple=True. Return None if cancelled."""
    try:
        import tkinter as _tk
        from tkinter import filedialog as _fd

        _root = _tk.Tk()
        _root.withdraw()
        if multiple:
            res = list(_fd.askopenfilenames(filetypes=[("PDF files", "*.pdf"), ("All files", "*")]))
        else:
            res = _fd.askopenfilename(filetypes=[("PDF files", "*.pdf"), ("All files", "*")])
        _root.destroy()
        return res if res else None
    except Exception:
        return None


def _tk_choose_dir():
    """Return directory path (str). Return None if cancelled."""
    try:
        import tkinter as _tk
        from tkinter import filedialog as _fd

        _root = _tk.Tk()
        _root.withdraw()
        res = _fd.askdirectory()
        _root.destroy()
        return res if res else None
    except Exception:
        return None


def _is_pdf_file(path: str) -> bool:
    p = Path(path)
    return p.is_file() and p.suffix.lower() == ".pdf"


def _ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


async def main(page: ft.Page) -> None:
    # ── page setup ──────────────────────────────────────────────────────
    page.title = APP_NAME
    page.window.width = 920
    page.window.height = 760
    page.padding = 20
    page.theme_mode = ft.ThemeMode.LIGHT

    DEFAULT_OUTPUT_DIR.mkdir(exist_ok=True)
    INPUT_DIR.mkdir(exist_ok=True)

    # ── SharedPreferences（設定の永続化）───────────────────────────────
    # SharedPreferences は永続K/Vストレージを提供 [4](https://flet.dev/docs/services/sharedpreferences/)[3](https://flet.dev/docs/cookbook/client-storage/)
    prefs = ft.SharedPreferences()

    def k(key: str) -> str:
        return f"{PREF_PREFIX}{key}"

    async def pref_get(key: str, default: Any) -> Any:
        try:
            v = await prefs.get(k(key))
            return default if v is None else v
        except Exception:
            return default

    async def pref_set(key: str, value: Any) -> None:
        try:
            await prefs.set(k(key), value)
        except Exception:
            # 設定保存失敗はアプリ動作を止めない
            pass

    # ── UI: 共通ログ ───────────────────────────────────────────────────
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

    def clear_log(e: ft.Event) -> None:
        log_field.value = ""
        page.update()

    # ── 非同期ヘルパ ───────────────────────────────────────────────────
    async def run_in_thread(func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    async def choose_file_async(multiple: bool = False):
        return await asyncio.to_thread(_tk_choose_file, multiple)

    async def choose_dir_async():
        return await asyncio.to_thread(_tk_choose_dir)

    # ── 処理中プログレス（共通）────────────────────────────────────────
    # ProgressRing: 円形の進捗表示 [1](https://flet.dev/docs/controls/progressring/)
    busy_ring = ft.ProgressRing()
    busy_text = ft.Text("処理中...", size=14)
    busy_dialog = ft.AlertDialog(
        modal=True,
        content=ft.Container(
            padding=ft.Padding.all(20),
            content=ft.Row(
                [busy_ring, busy_text],
                spacing=16,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ),
    )

    async def show_busy(message: str) -> None:
        busy_text.value = message
        if busy_dialog not in page.overlay:
            page.overlay.append(busy_dialog)  # ← overlay に積む
        busy_dialog.open = True
        page.update()
        await asyncio.sleep(0)

    def hide_busy() -> None:
        busy_dialog.open = False
        if busy_dialog in page.overlay:
            page.overlay.remove(busy_dialog)  # ← 消さないと溜まる
        page.update()

    # ── 共通: 出力先フォルダ UI（全タブ共通）──────────────────────────
    output_dir_field = ft.TextField(
        label="出力先フォルダ（共通）",
        read_only=True,
        expand=True,
    )
    output_pick_btn = ft.Button(content="選択")
    output_open_btn = ft.Button(content="フォルダを開く", icon=ft.Icons.FOLDER_OPEN)

    async def pick_output_dir(e: ft.Event) -> None:
        res = await choose_dir_async()
        if isinstance(res, str) and res.strip():
            output_dir_field.value = res.strip()
            _ensure_dir(output_dir_field.value)
            await pref_set("output_dir", output_dir_field.value)
            page.update()

    def open_output_dir(e: ft.Event) -> None:
        p = output_dir_field.value
        if not p:
            return
        try:
            os.startfile(p)  # Windows前提（業務PC想定）
        except Exception:
            log("⚠ 出力先フォルダを開けませんでした（権限/パスを確認してください）")

    output_pick_btn.on_click = pick_output_dir
    output_open_btn.on_click = open_output_dir

    # ── 起動時: 設定復元 ───────────────────────────────────────────────
    output_dir_field.value = str(await pref_get("output_dir", str(DEFAULT_OUTPUT_DIR)))
    _ensure_dir(output_dir_field.value)

    # ════════════════════════════════════════════════════════════════════
    # TAB 1 – Convert PDF → Image
    # ════════════════════════════════════════════════════════════════════
    conv_input_field = ft.TextField(label="入力ファイル / フォルダ", hint_text="選択してください", expand=True)
    conv_mode_radio = ft.RadioGroup(
        content=ft.Row([ft.Radio(value="file", label="ファイル"), ft.Radio(value="folder", label="フォルダ")]),
        value=cast(str, await pref_get("conv.mode", "file")),
    )
    conv_format_radio = ft.RadioGroup(
        content=ft.Row([ft.Radio(value="jpeg", label="JPEG"), ft.Radio(value="png", label="PNG")]),
        value=cast(str, await pref_get("conv.format", "jpeg")),
    )
    async def conv_dpi_selected(e: ft.Event) -> None:
        await pref_set("conv.dpi", conv_dpi_dropdown.value)

    conv_dpi_dropdown = ft.Dropdown(
        label="解像度 (DPI)",
        options=[ft.dropdown.Option("72"), ft.dropdown.Option("150"), ft.dropdown.Option("300")],
        value=cast(str, await pref_get("conv.dpi", "150")),
        width=160,
        on_select=conv_dpi_selected,
)
    conv_input_field.value = cast(str, await pref_get("conv.last_source", ""))

    async def conv_mode_changed(e: ft.Event) -> None:
        await pref_set("conv.mode", conv_mode_radio.value)

    async def conv_format_changed(e: ft.Event) -> None:
        await pref_set("conv.format", conv_format_radio.value)

    async def conv_dpi_changed(e: ft.Event) -> None:
        await pref_set("conv.dpi", conv_dpi_dropdown.value)

    conv_mode_radio.on_change = conv_mode_changed
    conv_format_radio.on_change = conv_format_changed
    conv_dpi_dropdown.on_select = conv_dpi_changed

    conv_pick_btn = ft.Button(content="選択")
    conv_run_btn = ft.Button(
        content="変換実行",
        icon=ft.Icons.IMAGE,
        bgcolor=ft.Colors.BLUE_600,
        color=ft.Colors.WHITE,
        width=200,
    )

    async def pick_conv_source(e: ft.Event) -> None:
        if conv_mode_radio.value == "file":
            res = await choose_file_async(multiple=False)
            if isinstance(res, str):
                conv_input_field.value = res
        else:
            res = await choose_dir_async()
            if isinstance(res, str):
                conv_input_field.value = res
        await pref_set("conv.last_source", conv_input_field.value or "")
        page.update()

    async def do_convert(e: ft.Event) -> None:
        source = (conv_input_field.value or "").strip()
        if not source:
            log("⚠ ファイルまたはフォルダを選択してください")
            return

        out_dir = (output_dir_field.value or "").strip()
        if not out_dir:
            log("⚠ 出力先フォルダを設定してください")
            return
        _ensure_dir(out_dir)

        fmt = (conv_format_radio.value or "jpeg").lower()
        dpi = int(conv_dpi_dropdown.value or "150")

        p = Path(source)
        if conv_mode_radio.value == "file":
            if not p.exists() or not p.is_file():
                log("⚠ 指定されたファイルが見つかりません")
                return
            if p.suffix.lower() != ".pdf":
                log("⚠ PDFファイルを選択してください")
                return
        else:
            if not p.exists() or not p.is_dir():
                log("⚠ 指定されたフォルダが見つかりません")
                return

        # UI disable + busy
        conv_run_btn.disabled = True
        conv_pick_btn.disabled = True
        page.update()
        await show_busy("PDF → 画像 変換中...")

        try:
            if conv_mode_radio.value == "file":
                log(f"▶ 変換開始: {source}")
                files = await run_in_thread(pdf_to_images, source, out_dir, fmt, dpi)
                log(f"✓ 完了: {len(files)} ページ → {out_dir}")
            else:
                log(f"▶ フォルダ変換開始: {source}")
                results = await run_in_thread(convert_folder, source, out_dir, fmt, dpi)
                ok = sum(len(v) for v in results.values() if isinstance(v, list))
                ng = sum(1 for v in results.values() if isinstance(v, str))
                log(
                    f"✓ 完了: {len(results)} ファイル / {ok} ページ変換"
                    + (f" / {ng} エラー" if ng else "")
                    + f" → {out_dir}"
                )
        except Exception as exc:
            log(f"✗ エラー: {exc}")
        finally:
            hide_busy()
            conv_run_btn.disabled = False
            conv_pick_btn.disabled = False
            page.update()

    conv_pick_btn.on_click = pick_conv_source
    conv_run_btn.on_click = do_convert

    # 出力フォーマットが見切れない2カラム配置
    convert_content = ft.Container(
        content=ft.Column(
            [
                ft.Text("PDF を JPEG / PNG に変換", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([ft.Text("変換モード:", width=90), conv_mode_radio],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([conv_input_field, conv_pick_btn]),
                ft.Row(
                    [
                        ft.Column([ft.Text("出力フォーマット"), conv_format_radio], expand=True),
                        ft.Column([conv_dpi_dropdown], width=180),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.END,
                ),
                conv_run_btn,
            ],
            spacing=16,
        ),
        padding=ft.Padding.all(20),
    )

    # ════════════════════════════════════════════════════════════════════
    # TAB 2 – Split PDF
    # ════════════════════════════════════════════════════════════════════
    split_input_field = ft.TextField(label="分割するPDFファイル", hint_text="PDFファイルを選択してください", expand=True)
    split_mode_radio = ft.RadioGroup(
        content=ft.Row(
            [
                ft.Radio(value="all", label="全ページ（1ページずつ）"),
                ft.Radio(value="range", label="ページ範囲指定"),
            ]
        ),
        value=cast(str, await pref_get("split.mode", "all")),
    )
    split_range_field = ft.TextField(label="ページ範囲（例: 1-3, 5, 7-9）", hint_text="カンマ区切り", expand=True)

    split_input_field.value = cast(str, await pref_get("split.last_source", ""))
    split_range_field.value = cast(str, await pref_get("split.range", ""))

    async def split_mode_changed(e: ft.Event) -> None:
        await pref_set("split.mode", split_mode_radio.value)

    async def split_range_changed(e: ft.Event) -> None:
        await pref_set("split.range", split_range_field.value or "")

    split_mode_radio.on_change = split_mode_changed
    split_range_field.on_change = split_range_changed

    split_pick_btn = ft.Button(content="選択")
    split_run_btn = ft.Button(
        content="分割実行",
        icon=ft.Icons.CALL_SPLIT,
        bgcolor=ft.Colors.GREEN_600,
        color=ft.Colors.WHITE,
        width=200,
    )

    async def pick_split_source(e: ft.Event) -> None:
        res = await choose_file_async(multiple=False)
        if isinstance(res, str):
            split_input_field.value = res
            await pref_set("split.last_source", res)
            page.update()

    async def do_split(e: ft.Event) -> None:
        source = (split_input_field.value or "").strip()
        if not source:
            log("⚠ PDFファイルを選択してください")
            return
        if not _is_pdf_file(source):
            log("⚠ 正しいPDFファイルを選択してください")
            return

        out_dir = (output_dir_field.value or "").strip()
        if not out_dir:
            log("⚠ 出力先フォルダを設定してください")
            return
        _ensure_dir(out_dir)

        split_run_btn.disabled = True
        split_pick_btn.disabled = True
        page.update()
        await show_busy("PDF 分割中...")

        try:
            if split_mode_radio.value == "all":
                log(f"▶ 分割開始: {source}")
                files = await run_in_thread(split_pdf, source, out_dir)
                log(f"✓ 完了: {len(files)} ファイルに分割 → {out_dir}")
            else:
                rng = (split_range_field.value or "").strip()
                if not rng:
                    log("⚠ ページ範囲を入力してください")
                    return
                log(f"▶ 範囲分割開始: {source}  範囲: {rng}")
                files = await run_in_thread(split_by_range, source, out_dir, rng)
                log(f"✓ 完了: {len(files)} ファイルに分割 → {out_dir}")
        except Exception as exc:
            log(f"✗ エラー: {exc}")
        finally:
            hide_busy()
            split_run_btn.disabled = False
            split_pick_btn.disabled = False
            page.update()

    split_pick_btn.on_click = pick_split_source
    split_run_btn.on_click = do_split

    split_content = ft.Container(
        content=ft.Column(
            [
                ft.Text("PDF を分割", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([split_input_field, split_pick_btn]),
                ft.Row([ft.Text("分割モード:", width=90), split_mode_radio],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                split_range_field,
                split_run_btn,
            ],
            spacing=16,
        ),
        padding=ft.Padding.all(20),
    )

    # ════════════════════════════════════════════════════════════════════
    # TAB 3 – Merge PDFs
    # ════════════════════════════════════════════════════════════════════
    merge_mode_radio = ft.RadioGroup(
        content=ft.Row(
            [ft.Radio(value="files", label="ファイル選択"), ft.Radio(value="folder", label="フォルダ内すべて")]
        ),
        value=cast(str, await pref_get("merge.mode", "files")),
    )
    merge_dir_field = ft.TextField(label="PDFフォルダ（フォルダ結合用）", hint_text="フォルダを選択してください", expand=True)
    merge_output = ft.TextField(label="出力ファイル名", value=cast(str, await pref_get("merge.output_name", "merged.pdf")), width=280)
    merge_list_view = ft.ListView(expand=True, height=130)
    merge_paths: list[str] = []

    merge_dir_field.value = cast(str, await pref_get("merge.last_folder", ""))

    async def merge_mode_changed(e: ft.Event) -> None:
        await pref_set("merge.mode", merge_mode_radio.value)

    async def merge_output_changed(e: ft.Event) -> None:
        await pref_set("merge.output_name", merge_output.value or "merged.pdf")

    merge_mode_radio.on_change = merge_mode_changed
    merge_output.on_change = merge_output_changed

    merge_pick_dir_btn = ft.Button(content="フォルダ選択")
    merge_add_files_btn = ft.Button(content="PDFを追加", icon=ft.Icons.ADD)
    merge_clear_btn = ft.Button(content="リストをクリア", icon=ft.Icons.CLEAR_ALL)
    merge_run_btn = ft.Button(
        content="結合実行",
        icon=ft.Icons.MERGE,
        bgcolor=ft.Colors.ORANGE_600,
        color=ft.Colors.WHITE,
        width=200,
    )

    def refresh_merge_list() -> None:
        merge_list_view.controls.clear()

        for idx, path in enumerate(list(merge_paths)):
            def make_remove(i: int):
                def _remove(e: ft.Event) -> None:
                    if 0 <= i < len(merge_paths):
                        merge_paths.pop(i)
                        refresh_merge_list()
                return _remove

            merge_list_view.controls.append(
                ft.Row(
                    [
                        ft.Icon(cast(Any, ft.Icons).PICTURE_AS_PDF, color=ft.Colors.RED_400),
                        ft.Text(Path(path).name, expand=True, size=12),
                        ft.IconButton(
                            icon=cast(Any, ft.Icons).REMOVE_CIRCLE_OUTLINE,
                            tooltip="削除",
                            on_click=make_remove(idx),
                        ),
                    ]
                )
            )
        page.update()

    async def pick_merge_dir(e: ft.Event) -> None:
        res = await choose_dir_async()
        if isinstance(res, str):
            merge_dir_field.value = res
            await pref_set("merge.last_folder", res)
            page.update()

    async def pick_merge_files(e: ft.Event) -> None:
        res = await choose_file_async(multiple=True)
        if isinstance(res, list):
            for f in res:
                if f and f.lower().endswith(".pdf") and f not in merge_paths:
                    merge_paths.append(f)
        elif isinstance(res, str):
            if res.lower().endswith(".pdf") and res not in merge_paths:
                merge_paths.append(res)
        refresh_merge_list()

    def clear_merge_list(e: ft.Event) -> None:
        merge_paths.clear()
        refresh_merge_list()

    async def do_merge(e: ft.Event) -> None:
        out_dir = (output_dir_field.value or "").strip()
        if not out_dir:
            log("⚠ 出力先フォルダを設定してください")
            return
        _ensure_dir(out_dir)

        out_name = (merge_output.value or "merged.pdf").strip()
        if not out_name.lower().endswith(".pdf"):
            out_name += ".pdf"
        out_path = str(Path(out_dir) / out_name)

        merge_run_btn.disabled = True
        merge_pick_dir_btn.disabled = True
        merge_add_files_btn.disabled = True
        merge_clear_btn.disabled = True
        page.update()
        await show_busy("PDF 結合中...")

        try:
            if merge_mode_radio.value == "files":
                if not merge_paths:
                    log("⚠ PDFファイルを追加してください")
                    return
                bad = [p for p in merge_paths if not _is_pdf_file(p)]
                if bad:
                    log("⚠ 存在しないPDFが含まれています: " + ", ".join(Path(x).name for x in bad))
                    return

                log(f"▶ 結合開始: {len(merge_paths)} ファイル")
                result = await run_in_thread(merge_pdfs, merge_paths, out_path)
                log(f"✓ 完了: {result}")
            else:
                folder = (merge_dir_field.value or "").strip()
                if not folder:
                    log("⚠ フォルダを選択してください")
                    return
                fp = Path(folder)
                if not fp.exists() or not fp.is_dir():
                    log("⚠ 指定されたフォルダが見つかりません")
                    return

                log(f"▶ フォルダ結合開始: {folder}")
                result = await run_in_thread(merge_folder, folder, out_path)
                log(f"✓ 完了: {result}")
        except Exception as exc:
            log(f"✗ エラー: {exc}")
        finally:
            hide_busy()
            merge_run_btn.disabled = False
            merge_pick_dir_btn.disabled = False
            merge_add_files_btn.disabled = False
            merge_clear_btn.disabled = False
            page.update()

    merge_pick_dir_btn.on_click = pick_merge_dir
    merge_add_files_btn.on_click = pick_merge_files
    merge_clear_btn.on_click = clear_merge_list
    merge_run_btn.on_click = do_merge

    merge_content = ft.Container(
        content=ft.Column(
            [
                ft.Text("PDF を結合", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([ft.Text("結合モード:", width=90), merge_mode_radio],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([merge_dir_field, merge_pick_dir_btn]),
                ft.Row([merge_add_files_btn, merge_clear_btn]),
                merge_list_view,
                ft.Row([merge_output]),
                merge_run_btn,
            ],
            spacing=16,
        ),
        padding=ft.Padding.all(20),
    )

    # ── Tabs: TabBar + TabBarView（0.84互換）───────────────────────────
    tab_bar = ft.TabBar(
        tabs=[
            ft.Tab(label="PDF → 画像"),
            ft.Tab(label="PDF 分割"),
            ft.Tab(label="PDF 結合"),
        ]
    )
    tab_view = ft.TabBarView(expand=True, controls=[convert_content, split_content, merge_content])
    tabs_main = ft.Tabs(expand=True, length=3, content=ft.Column([tab_bar, tab_view], expand=True))

    # ── 共通: 出力先欄（ヘッダー直下）─────────────────────────────────
    output_row = ft.Container(
        padding=ft.Padding.only(bottom=8),
        content=ft.Column(
            [
                ft.Row([output_dir_field, output_pick_btn, output_open_btn], spacing=8),
                ft.Text("※出力先は 画像変換・分割・結合 すべてに適用されます", size=12, color=ft.Colors.BLUE_GREY_600),
            ],
            spacing=4,
        ),
    )

    # ── main layout ────────────────────────────────────────────────────
    page.add(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(cast(Any, ft.Icons).PICTURE_AS_PDF, size=32, color=ft.Colors.RED_500),
                        ft.Text("PDF Editor", size=26, weight=ft.FontWeight.BOLD),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(),
                output_row,
                tabs_main,
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
    ft.run(main)  
    # app() は 0.80+ で非推奨 [7](https://magenta-magenta.com/2024/07/26/post-1792/)[8](https://flet.dev/docs/)
