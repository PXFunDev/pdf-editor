# pdf-editor

PDF ファイルを JPEG / PNG 画像に変換したり、PDF を分割・結合できる GUI アプリケーションです。

---

## フォルダ構成

```
pdf-editor/
├── gui/
│   ├── main.py          # GUI エントリーポイント (Flet)
│   └── assets/          # アイコン・画像ファイル格納フォルダ
├── src/
│   ├── __init__.py
│   ├── pdf_to_img.py    # PDF → JPEG / PNG 変換
│   ├── pdf_split.py     # PDF 分割
│   └── pdf_merge.py     # PDF 結合
├── input/               # 入力ファイル置き場
├── output/              # 出力ファイル置き場
├── requirements.txt
└── README.md
```

---

## セットアップ

### 必要環境
- Python 3.10 以上

### 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

---

## 起動方法

```bash
python gui/main.py
```

---

## 機能

### 1. PDF → 画像 タブ
- **ファイル** モード: 単一の PDF ファイルを選択して変換
- **フォルダ** モード: 指定フォルダ内の全 PDF を一括変換
- 出力フォーマット: **JPEG** / **PNG**
- 解像度: 72 / 150 / 300 DPI
- 変換結果は `output/` フォルダに保存されます

### 2. PDF 分割 タブ
- **全ページ**: 1 ページごとに個別 PDF として分割
- **ページ範囲指定**: `1-3, 5, 7-9` のようにカンマ区切りで範囲を指定
- 分割結果は `output/` フォルダに保存されます

### 3. PDF 結合 タブ
- **ファイル選択**: 複数の PDF を個別に追加して順番通りに結合
- **フォルダ内すべて**: 指定フォルダ内の全 PDF をファイル名順に結合
- 出力ファイル名を指定可能（デフォルト: `merged.pdf`）
- 結合結果は `output/` フォルダに保存されます

---

## 依存ライブラリ

| パッケージ  | 用途 |
|------------|------|
| [flet](https://flet.dev/) | GUI フレームワーク |
| [pymupdf](https://pymupdf.readthedocs.io/) | PDF → 画像変換 |
| [pypdf](https://pypdf.readthedocs.io/) | PDF 分割・結合 |

---

## ライセンス

[LICENSE](LICENSE) を参照してください。