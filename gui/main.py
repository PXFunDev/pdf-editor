# coding: utf-8
# main.py - PDF Editor (final layout)
# Python 3.12 / flet 0.84.0

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, cast

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

PREF_PREFIX = "panasss.pdf_editor."  # unique prefix for shared_preferences keys


# ── tkinter dialogs (FilePicker not used) ──────────────────────────────
def _tk_choose_file(multiple: bool = False):
    try:
        import tkinter as _tk
        from tkinter import filedialog as _fd

        root = _tk.Tk()
        root.withdraw()
        if multiple:
            res = list(_fd.askopenfilenames(filetypes=[("PDF files", "*.pdf"), ("All files", "*")]))
        else:
            res = _fd.askopenfilename(filetypes=[("PDF files", "*.pdf"), ("All files", "*")])
        root.destroy()
        return res if res else None
    except Exception:
        return None


def _tk_choose_dir():
    try:
        import tkinter as _tk
        from tkinter import filedialog as _fd

        root = _tk.Tk()
        root.withdraw()
        res = _fd.askdirectory()
        root.destroy()
        return res if res else None
    except Exception:
        return None


def _is_pdf_file(path: str) -> bool:
    p = Path(path)
    return p.is_file() and p.suffix.lower() == ".pdf"


def _ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def _open_folder_windows(path: str) -> None:
    os.startfile(path)


# ── OutputDirPicker (per tab) ──────────────────────────────────────────
class OutputDirPicker(ft.Row):
    """Output folder picker stored per tab via SharedPreferences."""

    def __init__(
        self,
        *,
        label: str,
        default_dir: str,
        pref_key: str,
        pref_get: Callable[[str, object], Awaitable[object]],
        pref_set: Callable[[str, object], Awaitable[None]],
        choose_dir_async: Callable[[], Awaitable[Optional[str]]],
        log: Callable[[str], None],
        open_folder: Callable[[str], None] = _open_folder_windows,
    ):
        super().__init__()
        self._label = label
        self._default_dir = default_dir
        self._pref_key = pref_key
        self._pref_get = pref_get
        self._pref_set = pref_set
        self._choose_dir_async = choose_dir_async
        self._log = log
        self._open_folder = open_folder

        self.field = ft.TextField(label=self._label, read_only=True, expand=True)
        self.btn_pick = ft.Button(content="選択", width=90)
        self.btn_open = ft.Button(content="開く", icon=ft.Icons.FOLDER_OPEN, width=90)

        self.btn_pick.on_click = self._pick
        self.btn_open.on_click = self._open

    @property
    def value(self) -> str:
        return (self.field.value or "").strip()

    async def load(self) -> None:
        v = await self._pref_get(self._pref_key, self._default_dir)
        self.field.value = str(v) if v else self._default_dir
        _ensure_dir(self.field.value)

    async def _pick(self, e: ft.Event) -> None:
        res = await self._choose_dir_async()
        if res and str(res).strip():
            folder = str(res).strip()
            self.field.value = folder
            _ensure_dir(folder)
            await self._pref_set(self._pref_key, folder)
            self.update()

    def _open(self, e: ft.Event) -> None:
        if not self.value:
            return
        try:
            self._open_folder(self.value)
        except Exception:
            self._log("⚠ フォルダを開けませんでした（権限/パスを確認してください）")


async def main(page: ft.Page) -> None:
    # ── Page setup ─────────────────────────────────────────────────────
    page.title = APP_NAME
    page.window.width = 920
    page.window.height = 760
    page.padding = 20
    page.theme_mode = ft.ThemeMode.LIGHT

    DEFAULT_OUTPUT_DIR.mkdir(exist_ok=True)
    INPUT_DIR.mkdir(exist_ok=True)

    # ── SharedPreferences ──────────────────────────────────────────────
    prefs = ft.SharedPreferences()

    def _k(key: str) -> str:
        return f"{PREF_PREFIX}{key}"

    async def pref_get(key: str, default: Any) -> Any:
        try:
            v = await prefs.get(_k(key))
            return default if v is None else v
        except Exception:
            return default

    async def pref_set(key: str, value: Any) -> None:
        try:
            await prefs.set(_k(key), value)
        except Exception:
            pass

    # ── Log ────────────────────────────────────────────────────────────
    log_field = ft.TextField(
        multiline=True,
        read_only=True,
        min_lines=6,
        max_lines=10,
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

    # ── Async helpers ───────────────────────────────────────────────────
    async def run_in_thread(func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    async def choose_file_async(multiple: bool = False):
        return await asyncio.to_thread(_tk_choose_file, multiple)

    async def choose_dir_async():
        return await asyncio.to_thread(_tk_choose_dir)

    # ── Busy dialog (page.open/page.close) ──────────────────────────────
    busy_text = ft.Text("処理中...", size=14)
    busy_dialog = ft.AlertDialog(
        modal=True,
        content=ft.Container(
            padding=ft.Padding.all(20),
            content=ft.Row(
                [ft.ProgressRing(), busy_text],
                spacing=16,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ),
    )

    async def show_busy(message: str) -> None:
        busy_text.value = message
        if busy_dialog not in page.overlay:
            page.overlay.append(busy_dialog)
        busy_dialog.open = True
        page.update()
        await asyncio.sleep(0)

    def hide_busy() -> None:
        busy_dialog.open = False
        if busy_dialog in page.overlay:
            page.overlay.remove(busy_dialog)
        page.update()

    # ════════════════════════════════════════════════════════════════════
    # TAB 1: PDF → 画像
    # Order: mode → input → options → output → run
    # ════════════════════════════════════════════════════════════════════
    conv_output = OutputDirPicker(
        label="出力先フォルダ（画像）",
        default_dir=str(DEFAULT_OUTPUT_DIR),
        pref_key="conv.output_dir",
        pref_get=pref_get,
        pref_set=pref_set,
        choose_dir_async=choose_dir_async,
        log=log,
    )
    await conv_output.load()

    conv_mode = ft.RadioGroup(
        value=cast(str, await pref_get("conv.mode", "file")),
        content=ft.Row(
            wrap=True,
            spacing=14,
            run_spacing=6,
            controls=[
                ft.Radio(value="file", label="ファイル"),
                ft.Radio(value="folder", label="フォルダ"),
            ],
        ),
    )

    conv_input = ft.TextField(label="入力PDF（ファイル/フォルダ）", hint_text="選択してください", expand=True)
    conv_input.value = cast(str, await pref_get("conv.last_source", ""))

    conv_format = ft.RadioGroup(
        value=cast(str, await pref_get("conv.format", "jpeg")),
        content=ft.Row(
            wrap=True,
            spacing=14,
            run_spacing=6,
            controls=[ft.Radio(value="jpeg", label="JPEG"), ft.Radio(value="png", label="PNG")],
        ),
    )

    async def conv_dpi_selected(e: ft.Event) -> None:
        await pref_set("conv.dpi", conv_dpi.value)

    conv_dpi = ft.Dropdown(
        label="解像度 (DPI)",
        options=[ft.dropdown.Option("72"), ft.dropdown.Option("150"), ft.dropdown.Option("300")],
        value=cast(str, await pref_get("conv.dpi", "150")),
        width=180,
        on_select=conv_dpi_selected,
    )

    conv_pick_btn = ft.Button(content="選択", width=90)
    conv_run_btn = ft.Button(
        content="変換実行",
        icon=ft.Icons.PLAY_ARROW,
        bgcolor=ft.Colors.BLUE_600,
        color=ft.Colors.WHITE,
        width=200,
    )

    async def conv_mode_changed(e: ft.Event) -> None:
        await pref_set("conv.mode", conv_mode.value)

    async def conv_format_changed(e: ft.Event) -> None:
        await pref_set("conv.format", conv_format.value)

    conv_mode.on_change = conv_mode_changed
    conv_format.on_change = conv_format_changed

    async def pick_conv_source(e: ft.Event) -> None:
        if conv_mode.value == "file":
            res = await choose_file_async(multiple=False)
        else:
            res = await choose_dir_async()
        if isinstance(res, str) and res:
            conv_input.value = res
            await pref_set("conv.last_source", res)
            page.update()

    async def do_convert(e: ft.Event) -> None:
        source = (conv_input.value or "").strip()
        if not source:
            log("⚠ 入力PDF（ファイル/フォルダ）を選択してください")
            return

        out_dir = conv_output.value
        if not out_dir:
            log("⚠ 出力先フォルダ（画像）を設定してください")
            return
        _ensure_dir(out_dir)

        fmt = (conv_format.value or "jpeg").lower()
        dpi = int(conv_dpi.value or "150")

        p = Path(source)
        if conv_mode.value == "file":
            if not p.exists() or not p.is_file() or p.suffix.lower() != ".pdf":
                log("⚠ 正しいPDFファイルを選択してください")
                return
        else:
            if not p.exists() or not p.is_dir():
                log("⚠ 指定されたフォルダが見つかりません")
                return

        conv_run_btn.disabled = True
        conv_pick_btn.disabled = True
        page.update()
        await show_busy("PDF → 画像 変換中...")

        try:
            if conv_mode.value == "file":
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

    tab_convert = ft.Container(
        padding=ft.Padding.all(16),
        content=ft.ListView(
            expand=True,
            spacing=16,
            controls=[
                ft.Text("PDF → JPEG / PNG に変換", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([ft.Text("変換モード:", width=90), conv_mode]),
                ft.Row([conv_input, conv_pick_btn], spacing=8),
                ft.Row(
                    [
                        ft.Column([ft.Text("出力オプション"), conv_format], expand=True),
                        ft.Column([conv_dpi], width=200),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.END,
                ),
                conv_output,
                conv_run_btn,
            ],
        ),
    )

    # ════════════════════════════════════════════════════════════════════
    # TAB 2: PDF 分割
    # Order: input → mode → output → run
    # ════════════════════════════════════════════════════════════════════
    split_output = OutputDirPicker(
        label="出力先フォルダ（分割）",
        default_dir=str(DEFAULT_OUTPUT_DIR),
        pref_key="split.output_dir",
        pref_get=pref_get,
        pref_set=pref_set,
        choose_dir_async=choose_dir_async,
        log=log,
    )
    await split_output.load()

    split_input = ft.TextField(label="入力PDFファイル", hint_text="PDFファイルを選択してください", expand=True)
    split_input.value = cast(str, await pref_get("split.last_source", ""))

    split_mode = ft.RadioGroup(
        value=cast(str, await pref_get("split.mode", "all")),
        content=ft.Row(
            wrap=True,
            spacing=14,
            run_spacing=6,
            controls=[
                ft.Radio(value="all", label="全ページ（1ページずつ）"),
                ft.Radio(value="range", label="ページ範囲指定"),
            ],
        ),
    )

    split_range = ft.TextField(label="ページ範囲（例: 1-3, 5, 7-9）", hint_text="カンマ区切り", expand=True)
    split_range.value = cast(str, await pref_get("split.range", ""))

    split_pick_btn = ft.Button(content="選択", width=90)
    split_run_btn = ft.Button(
        content="分割実行",
        icon=ft.Icons.PLAY_ARROW,
        bgcolor=ft.Colors.GREEN_600,
        color=ft.Colors.WHITE,
        width=200,
    )

    async def split_mode_changed(e: ft.Event) -> None:
        await pref_set("split.mode", split_mode.value)

    async def split_range_changed(e: ft.Event) -> None:
        await pref_set("split.range", split_range.value or "")

    split_mode.on_change = split_mode_changed
    split_range.on_change = split_range_changed

    async def pick_split_source(e: ft.Event) -> None:
        res = await choose_file_async(multiple=False)
        if isinstance(res, str) and res:
            split_input.value = res
            await pref_set("split.last_source", res)
            page.update()

    async def do_split(e: ft.Event) -> None:
        source = (split_input.value or "").strip()
        if not source or not _is_pdf_file(source):
            log("⚠ 正しいPDFファイルを選択してください")
            return

        out_dir = split_output.value
        if not out_dir:
            log("⚠ 出力先フォルダ（分割）を設定してください")
            return
        _ensure_dir(out_dir)

        split_run_btn.disabled = True
        split_pick_btn.disabled = True
        page.update()
        await show_busy("PDF 分割中...")

        try:
            if split_mode.value == "all":
                log(f"▶ 分割開始: {source}")
                files = await run_in_thread(split_pdf, source, out_dir)
                log(f"✓ 完了: {len(files)} ファイルに分割 → {out_dir}")
            else:
                rng = (split_range.value or "").strip()
                if not rng:
                    log("⚠ ページ範囲を入力してください")
                    return
                log(f"▶ 範囲分割開始: {source} / 範囲: {rng}")
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

    tab_split = ft.Container(
        padding=ft.Padding.all(16),
        content=ft.ListView(
            expand=True,
            spacing=16,
            controls=[
                ft.Text("PDF を分割", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([split_input, split_pick_btn], spacing=8),
                ft.Row([ft.Text("分割モード:", width=90), split_mode]),
                split_range,
                split_output,
                split_run_btn,
            ],
        ),
    )

    # ════════════════════════════════════════════════════════════════════
    # TAB 3: PDF 結合
    # Order: input → options → output → run
    # ════════════════════════════════════════════════════════════════════
    merge_output = OutputDirPicker(
        label="出力先フォルダ（結合）",
        default_dir=str(DEFAULT_OUTPUT_DIR),
        pref_key="merge.output_dir",
        pref_get=pref_get,
        pref_set=pref_set,
        choose_dir_async=choose_dir_async,
        log=log,
    )
    await merge_output.load()

    merge_mode = ft.RadioGroup(
        value=cast(str, await pref_get("merge.mode", "files")),
        content=ft.Row(
            wrap=True,
            spacing=14,
            run_spacing=6,
            controls=[
                ft.Radio(value="files", label="ファイル選択"),
                ft.Radio(value="folder", label="フォルダ内すべて"),
            ],
        ),
    )

    merge_folder = ft.TextField(label="入力フォルダ（フォルダ結合用）", hint_text="フォルダを選択してください", expand=True)
    merge_folder.value = cast(str, await pref_get("merge.last_folder", ""))

    merge_out_name = ft.TextField(
        label="出力ファイル名（.pdf）",
        value=cast(str, await pref_get("merge.output_name", "merged.pdf")),
        width=320,
    )

    merge_list = ft.ListView(expand=True, height=160, spacing=6)
    merge_paths: list[str] = []

    btn_pick_folder = ft.Button(content="フォルダ選択", width=110)
    btn_add_files = ft.Button(content="PDFを追加", icon=ft.Icons.ADD)
    btn_clear_files = ft.Button(content="リストをクリア", icon=ft.Icons.CLEAR_ALL)

    merge_run_btn = ft.Button(
        content="結合実行",
        icon=ft.Icons.PLAY_ARROW,
        bgcolor=ft.Colors.ORANGE_600,
        color=ft.Colors.WHITE,
        width=200,
    )

    async def merge_mode_changed(e: ft.Event) -> None:
        await pref_set("merge.mode", merge_mode.value)

    async def merge_out_name_changed(e: ft.Event) -> None:
        await pref_set("merge.output_name", merge_out_name.value or "merged.pdf")

    merge_mode.on_change = merge_mode_changed
    merge_out_name.on_change = merge_out_name_changed

    def refresh_merge_list() -> None:
        merge_list.controls.clear()

        for idx, path in enumerate(list(merge_paths)):

            def make_remove(i: int):
                def _remove(e: ft.Event) -> None:
                    if 0 <= i < len(merge_paths):
                        merge_paths.pop(i)
                        refresh_merge_list()
                return _remove

            merge_list.controls.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.PICTURE_AS_PDF, color=ft.Colors.RED_400),
                        ft.Text(Path(path).name, expand=True, size=12),
                        ft.IconButton(icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="削除", on_click=make_remove(idx)),
                    ]
                )
            )
        page.update()

    async def pick_merge_folder(e: ft.Event) -> None:
        res = await choose_dir_async()
        if isinstance(res, str) and res:
            merge_folder.value = res
            await pref_set("merge.last_folder", res)
            page.update()

    async def add_merge_files(e: ft.Event) -> None:
        res = await choose_file_async(multiple=True)
        if isinstance(res, list):
            for f in res:
                if f and f.lower().endswith(".pdf") and f not in merge_paths:
                    merge_paths.append(f)
        elif isinstance(res, str):
            if res.lower().endswith(".pdf") and res not in merge_paths:
                merge_paths.append(res)
        refresh_merge_list()

    def clear_merge_files(e: ft.Event) -> None:
        merge_paths.clear()
        refresh_merge_list()

    btn_pick_folder.on_click = pick_merge_folder
    btn_add_files.on_click = add_merge_files
    btn_clear_files.on_click = clear_merge_files

    async def do_merge(e: ft.Event) -> None:
        out_dir = merge_output.value
        if not out_dir:
            log("⚠ 出力先フォルダ（結合）を設定してください")
            return
        _ensure_dir(out_dir)

        out_name = (merge_out_name.value or "merged.pdf").strip()
        if not out_name.lower().endswith(".pdf"):
            out_name += ".pdf"
        out_path = str(Path(out_dir) / out_name)

        merge_run_btn.disabled = True
        btn_pick_folder.disabled = True
        btn_add_files.disabled = True
        btn_clear_files.disabled = True
        page.update()
        await show_busy("PDF 結合中...")

        try:
            if merge_mode.value == "files":
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
                folder = (merge_folder.value or "").strip()
                if not folder or not Path(folder).is_dir():
                    log("⚠ 正しいフォルダを選択してください")
                    return
                log(f"▶ フォルダ結合開始: {folder}")
                result = await run_in_thread(merge_folder, folder, out_path)
                log(f"✓ 完了: {result}")
        except Exception as exc:
            log(f"✗ エラー: {exc}")
        finally:
            hide_busy()
            merge_run_btn.disabled = False
            btn_pick_folder.disabled = False
            btn_add_files.disabled = False
            btn_clear_files.disabled = False
            page.update()

    merge_run_btn.on_click = do_merge

    tab_merge = ft.Container(
        padding=ft.Padding.all(16),
        content=ft.ListView(
            expand=True,
            spacing=16,
            controls=[
                ft.Text("PDF を結合", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([ft.Text("結合モード:", width=90), merge_mode]),
                ft.Row([merge_folder, btn_pick_folder], spacing=8),
                ft.Row([btn_add_files, btn_clear_files], spacing=8),
                merge_list,
                merge_out_name,
                merge_output,
                merge_run_btn,
            ],
        ),
    )

    # ── Tabs (TabBar + TabBarView) ──────────────────────────────────────
    tab_bar = ft.TabBar(
        tabs=[
            ft.Tab(label="PDF → 画像"),
            ft.Tab(label="PDF 分割"),
            ft.Tab(label="PDF 結合"),
        ]
    )
    tab_view = ft.TabBarView(expand=True, controls=[tab_convert, tab_split, tab_merge])
    tabs = ft.Tabs(expand=True, length=3, content=ft.Column([tab_bar, tab_view], expand=True))

    # ── Log (collapsed by default) ──────────────────────────────────────
    # ExpansionTile uses "expanded" to control open/close state [1](https://flet.dev/docs/controls/expansiontile/)
    log_tile = ft.ExpansionTile(
        title=ft.Row(
            [
                ft.Text("ログ", weight=ft.FontWeight.BOLD),
                ft.TextButton("クリア", on_click=clear_log),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        expanded=False,  # default hidden
        controls=[log_field],
        controls_padding=ft.Padding.only(top=8, left=4, right=4, bottom=4),
    )

    # ── Layout ─────────────────────────────────────────────────────────
    page.add(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.PICTURE_AS_PDF, size=30, color=ft.Colors.RED_500),
                        ft.Text("PDF Editor", size=26, weight=ft.FontWeight.BOLD),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(),
                tabs,
                ft.Divider(),
                log_tile,
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.run(main)