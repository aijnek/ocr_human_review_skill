#!/usr/bin/env python3
"""動作確認用の合成サンプル文書 (在籍証明書のバリエーション) を samples/ に生成する。

レイアウト・文言・和暦/西暦表記をあえて変えた 3 種の PDF と、
スキャン画像を想定した PNG 1 枚を作る。
"""
from pathlib import Path

import pymupdf
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

GOTHIC = "HeiseiKakuGo-W5"
MINCHO = "HeiseiMin-W3"

W, H = A4


def sample1_classic(path: Path) -> None:
    """レイアウト1: 伝統的な中央揃えの在籍証明書 (和暦表記)。"""
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont(MINCHO, 22)
    c.drawCentredString(W / 2, H - 40 * mm, "在　籍　証　明　書")

    c.setFont(MINCHO, 12)
    y = H - 65 * mm
    lines = [
        ("氏　　名", "田中　花子"),
        ("生年月日", "平成2年5月12日"),
        ("職　　種", "保育士"),
        ("雇用形態", "正規職員（常勤）"),
        ("在籍期間", "令和2年4月1日から現在に至る"),
    ]
    for label, value in lines:
        c.drawString(45 * mm, y, f"{label}　：　{value}")
        y -= 12 * mm

    c.setFont(MINCHO, 12)
    y -= 8 * mm
    c.drawString(35 * mm, y, "上記の者は、当園に在籍していることを証明いたします。")

    y -= 25 * mm
    c.drawRightString(W - 35 * mm, y, "令和8年7月15日")
    y -= 14 * mm
    c.setFont(MINCHO, 13)
    c.drawRightString(W - 35 * mm, y, "社会福祉法人ひまわり会　ひまわり保育園")
    y -= 10 * mm
    c.drawRightString(W - 40 * mm, y, "園長　佐藤　美咲　㊞")
    y -= 10 * mm
    c.setFont(MINCHO, 10)
    c.drawRightString(W - 35 * mm, y, "東京都世田谷区桜丘1-2-3")
    c.save()


def sample2_table(path: Path) -> None:
    """レイアウト2: 表形式の勤務証明書 (西暦表記・退職済み)。"""
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont(GOTHIC, 18)
    c.drawCentredString(W / 2, H - 30 * mm, "勤務証明書")
    c.setFont(GOTHIC, 9)
    c.drawRightString(W - 25 * mm, H - 38 * mm, "証明書番号: KL-2026-0342")

    rows = [
        ("氏名", "鈴木　太郎"),
        ("生年月日", "1988年11月3日"),
        ("勤務先施設名", "さくら保育園（株式会社キッズランド運営）"),
        ("施設所在地", "神奈川県横浜市青葉区美しが丘4-5-6"),
        ("職種", "主任保育士"),
        ("雇用形態", "正規職員"),
        ("勤務期間", "2015年4月1日 〜 2023年3月31日"),
    ]
    top = H - 55 * mm
    row_h = 11 * mm
    left, right = 30 * mm, W - 30 * mm
    label_w = 45 * mm
    c.setFont(GOTHIC, 11)
    for i, (label, value) in enumerate(rows):
        y = top - i * row_h
        c.rect(left, y - row_h, right - left, row_h)
        c.line(left + label_w, y, left + label_w, y - row_h)
        c.setFillColorRGB(0.92, 0.92, 0.95)
        c.rect(left, y - row_h, label_w, row_h, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)
        c.rect(left, y - row_h, right - left, row_h)
        c.drawString(left + 3 * mm, y - row_h + 3.5 * mm, label)
        c.drawString(left + label_w + 3 * mm, y - row_h + 3.5 * mm, value)

    y = top - len(rows) * row_h - 15 * mm
    c.setFont(GOTHIC, 10.5)
    c.drawString(left, y, "上記のとおり、当社運営施設に勤務していたことを証明します。")
    y -= 15 * mm
    c.drawString(left, y, "発行日: 2026年7月1日")
    y -= 10 * mm
    c.drawString(left, y, "株式会社キッズランド　さくら保育園　施設長　高橋　健一")
    c.save()


def sample3_municipal(path: Path) -> None:
    """レイアウト3: 自治体様式風の就労証明書 (2段組・在職中)。"""
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont(GOTHIC, 16)
    c.drawString(25 * mm, H - 25 * mm, "就労証明書（保育士等キャリア確認用）")
    c.setFont(GOTHIC, 8.5)
    c.drawString(25 * mm, H - 31 * mm, "※本証明書は保育士としての就労実績を証明するものです。")

    c.setFont(GOTHIC, 10)
    boxes = [
        (25, 120, "1. 就労者情報", [
            "氏名（フリガナ）: ヤマダ アユミ",
            "氏名: 山田　あゆみ",
            "生年月日: 1995年2月28日",
        ]),
        (110, 120, "2. 就労先情報", [
            "施設名: つばさ保育園",
            "運営法人: NPO法人こども未来",
            "所在地: 大阪府吹田市山田東2-10-8",
        ]),
        (25, 120, "3. 就労状況", [
            "職種: 保育士（非常勤・パート）",
            "就労開始日: 2021年10月1日",
            "就労終了日: （在職中）",
            "週あたり勤務時間: 28時間",
        ]),
        (110, 120, "4. 証明者", [
            "発行日: 2026年8月1日",
            "法人名: NPO法人こども未来",
            "代表者: 理事長　伊藤　誠",
            "電話: 06-1234-5678",
        ]),
    ]
    y_top = H - 45 * mm
    box_h = 42 * mm
    for i, (x_mm, w_mm, title, lines) in enumerate(boxes):
        x = x_mm * mm
        y = y_top - (i // 2) * (box_h + 6 * mm)
        c.rect(x, y - box_h, w_mm * mm * 0.63, box_h)
        c.setFont(GOTHIC, 10.5)
        c.drawString(x + 2 * mm, y - 6 * mm, title)
        c.line(x, y - 8 * mm, x + w_mm * mm * 0.63, y - 8 * mm)
        c.setFont(GOTHIC, 9)
        for j, line in enumerate(lines):
            c.drawString(x + 3 * mm, y - 15 * mm - j * 6.5 * mm, line)
    c.save()


def pdf_to_png(pdf_path: Path, png_path: Path) -> None:
    with pymupdf.open(pdf_path) as doc:
        doc[0].get_pixmap(dpi=150).save(png_path)


def main() -> None:
    SAMPLES_DIR.mkdir(exist_ok=True)
    pdfmetrics.registerFont(UnicodeCIDFont(GOTHIC))
    pdfmetrics.registerFont(UnicodeCIDFont(MINCHO))

    p1 = SAMPLES_DIR / "sample1_zaiseki_himawari.pdf"
    p2 = SAMPLES_DIR / "sample2_kinmu_sakura.pdf"
    p3 = SAMPLES_DIR / "sample3_shurou_tsubasa.pdf"
    sample1_classic(p1)
    sample2_table(p2)
    sample3_municipal(p3)
    pdf_to_png(p1, SAMPLES_DIR / "sample4_zaiseki_himawari_scan.png")
    print(f"generated samples in {SAMPLES_DIR}")


if __name__ == "__main__":
    main()
