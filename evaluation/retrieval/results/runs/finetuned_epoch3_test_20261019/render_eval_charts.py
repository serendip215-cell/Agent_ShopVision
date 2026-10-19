from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT
W, H = 1600, 1000
BG, PANEL, GRID, INK, MUTED = "#F3F6FA", "#FFFFFF", "#E6ECF2", "#203047", "#66758A"
NAVY, BLUE, TEAL, GOLD, CORAL, GREEN = "#203A5F", "#4C78A8", "#18A999", "#F2B544", "#E76F51", "#3A9D72"
FONT = r"C:\Windows\Fonts\segoeui.ttf"
FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"


def font(size: int, bold: bool = False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size=size)


def make_canvas(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((38, 32, W - 38, H - 32), radius=30, fill=PANEL, outline="#E2E8F0", width=2)
    draw.text((92, 70), title, font=font(38, True), fill=INK)
    draw.text((94, 126), subtitle, font=font(19), fill=MUTED)
    draw.rounded_rectangle((92, 174, W - 92, 178), radius=2, fill="#E8EEF5")
    return image, draw


def text_center(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, face, fill=INK):
    box = draw.textbbox((0, 0), text, font=face)
    draw.text((x - (box[2] - box[0]) / 2, y), text, font=face, fill=fill)


def text_right(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, face, fill=INK):
    box = draw.textbbox((0, 0), text, font=face)
    draw.text((x - (box[2] - box[0]), y), text, font=face, fill=fill)


def plot_frame(draw: ImageDraw.ImageDraw, rect, y_ticks, y_min, y_max, formatter=None, x_ticks=None):
    x0, y0, x1, y1 = rect
    for tick in y_ticks:
        py = y1 - (tick - y_min) / (y_max - y_min) * (y1 - y0)
        draw.line((x0, py, x1, py), fill=GRID, width=2)
        label = formatter(tick) if formatter else str(tick)
        text_right(draw, x0 - 16, py - 13, label, font(16), MUTED)
    draw.line((x0, y0, x0, y1), fill="#B8C4D1", width=2)
    draw.line((x0, y1, x1, y1), fill="#B8C4D1", width=2)
    if x_ticks:
        for tx, label in x_ticks:
            px = tx
            draw.line((px, y1, px, y1 + 8), fill="#98A6B5", width=2)
            text_center(draw, px, y1 + 18, label, font(16), MUTED)


def map_y(value: float, low: float, high: float, top: float, bottom: float) -> float:
    return bottom - (value - low) / (high - low) * (bottom - top)


def map_x(value: float, low: float, high: float, left: float, right: float) -> float:
    return left + (value - low) / (high - low) * (right - left)


def draw_line(draw: ImageDraw.ImageDraw, points, color: str, width=5, marker=8):
    if len(points) > 1:
        draw.line(points, fill=color, width=width, joint="curve")
    for x, y in points:
        draw.ellipse((x - marker, y - marker, x + marker, y + marker), fill=PANEL, outline=color, width=4)


def legend_item(draw, x, y, color, label):
    draw.line((x, y + 12, x + 38, y + 12), fill=color, width=5)
    draw.ellipse((x + 14, y + 6, x + 26, y + 18), fill=PANEL, outline=color, width=3)
    draw.text((x + 50, y), label, font=font(17), fill=INK)


def parse_log() -> tuple[list[dict], list[dict]]:
    train_rows, val_rows = [], []
    train_re = re.compile(
        r"Global Steps:\s*(\d+)/(\d+).*?Train Epoch:\s*(\d+).*?"
        r"Loss:\s*([0-9.]+)\s*\|\s*Image2Text Acc:\s*([0-9.]+)\s*\|\s*"
        r"Text2Image Acc:\s*([0-9.]+).*?Data Time:\s*([0-9.]+)s\s*\|\s*"
        r"Batch Time:\s*([0-9.]+)s\s*\|\s*LR:\s*([0-9.eE+-]+)"
    )
    val_re = re.compile(
        r"Validation Result \(epoch\s*(\d+)\s*@\s*(\d+) steps\).*?"
        r"Valid Loss:\s*([0-9.]+)\s*\|\s*Image2Text Acc:\s*([0-9.]+)\s*\|\s*"
        r"Text2Image Acc:\s*([0-9.]+)"
    )
    content = (SOURCE / "out_2026-10-18-12-27-38.log").read_text(encoding="utf-8").splitlines()
    for line in content:
        m = train_re.search(line)
        if m:
            step, max_steps, epoch, loss, i2t, t2i, data_time, batch_time, lr = m.groups()
            train_rows.append({"step": int(step), "max_steps": int(max_steps), "epoch": int(epoch), "loss": float(loss),
                               "i2t": float(i2t), "t2i": float(t2i), "data_time": float(data_time),
                               "batch_time": float(batch_time), "lr": float(lr)})
        m = val_re.search(line)
        if m:
            epoch, step, loss, i2t, t2i = m.groups()
            val_rows.append({"epoch": int(epoch), "step": int(step), "loss": float(loss), "i2t": float(i2t), "t2i": float(t2i)})
    if len(train_rows) < 10 or len(val_rows) < 3:
        raise RuntimeError(f"日志解析数量异常：train={len(train_rows)}, validation={len(val_rows)}")
    return train_rows, val_rows


def moving_average(values, window=9):
    values = np.asarray(values, dtype=float)
    left = (window - 1) // 2
    right = window - 1 - left
    return np.convolve(np.pad(values, (left, right), mode="edge"), np.ones(window) / window, mode="valid")


def plot_recall(baseline, tuned, n):
    labels, keys = ["R@1", "R@5", "R@10"], ["r1", "r5", "r10"]
    base = [baseline["scoreJson"][key] for key in keys]
    fine = [tuned["scoreJson"][key] for key in keys]
    image, draw = make_canvas("Top-K retrieval recall", f"Held-out test snapshot  |  {n:,} image–text pairs  |  candidate pool: {n:,}")
    rect = (210, 300, 1450, 775)
    plot_frame(draw, rect, [0, 20, 40, 60, 80, 100], 0, 100, lambda v: f"{v}%")
    x = [rect[0] + (rect[2] - rect[0]) * i / 2 for i in range(3)]
    for xx, label in zip(x, labels):
        text_center(draw, xx, 802, label, font(20, True), MUTED)
    points_b = [(xx, map_y(v, 0, 100, rect[1], rect[3])) for xx, v in zip(x, base)]
    points_f = [(xx, map_y(v, 0, 100, rect[1], rect[3])) for xx, v in zip(x, fine)]
    draw_line(draw, points_b, BLUE, 5, 9)
    draw_line(draw, points_f, TEAL, 6, 10)
    for (xx, yy), v in zip(points_b, base):
        text_center(draw, xx, yy + 17, f"{v:.1f}%", font(18, True), BLUE)
    for (xx, yy), v in zip(points_f, fine):
        text_center(draw, xx, yy - 39, f"{v:.1f}%", font(18, True), TEAL)
    legend_item(draw, 920, 220, BLUE, "Pretrained baseline")
    legend_item(draw, 1190, 220, TEAL, "Fine-tuned · epoch 3")
    image.save(ROOT / "01_recall_at_k.png", optimize=True)


def plot_gains(baseline, tuned, relative=False):
    keys = ["r1", "r5", "r10", "mean_recall"]
    labels = ["R@1", "R@5", "R@10", "Mean Recall"]
    gains = []
    for key in keys:
        b, f = baseline["scoreJson"][key], tuned["scoreJson"][key]
        gains.append((f / b - 1) * 100 if relative else f - b)
    title = "Relative improvement vs baseline" if relative else "Absolute improvement vs baseline"
    units = "% relative gain" if relative else "percentage points"
    image, draw = make_canvas(title, f"All gains use the same held-out test set  |  values shown in {units}")
    left, top, right, bottom = 350, 280, 1390, 790
    xmax = max(gains) * 1.2
    ticks = np.linspace(0, xmax, 6)
    for tick in ticks:
        x = map_x(tick, 0, xmax, left, right)
        draw.line((x, top, x, bottom), fill=GRID, width=2)
        text_center(draw, x, bottom + 20, f"{tick:.0f}", font(16), MUTED)
    colors = [CORAL, GOLD, TEAL, BLUE]
    y_positions = [330, 445, 560, 675]
    for label, gain, color, y in zip(labels, gains, colors, y_positions):
        draw.text((110, y - 18), label, font=font(21, True), fill=INK)
        end = map_x(gain, 0, xmax, left, right)
        draw.rounded_rectangle((left, y - 25, end, y + 25), radius=18, fill=color)
        draw.text((end + 18, y - 18), f"+{gain:.2f}{'%' if relative else ' pp'}", font=font(19, True), fill=color)
    draw.text((left, 850), "Improvement", font=font(16), fill=MUTED)
    image.save(ROOT / ("03_relative_gain.png" if relative else "02_absolute_gain_pp.png"), optimize=True)


def plot_validation(val_rows):
    image, draw = make_canvas("Validation trajectory", "Six validation checkpoints across three epochs  |  batch-level retrieval accuracy uses 32 in-batch candidates")
    left_rect, right_rect = (180, 320, 730, 760), (950, 320, 1470, 760)
    draw.text((180, 245), "Validation loss", font=font(23, True), fill=INK)
    draw.text((950, 245), "In-batch retrieval accuracy", font=font(23, True), fill=INK)
    plot_frame(draw, left_rect, [0.12, 0.15, 0.18, 0.21, 0.24], 0.12, 0.24, lambda v: f"{v:.2f}")
    plot_frame(draw, right_rect, [88, 90, 92, 94, 96, 98], 88, 100, lambda v: f"{v}%")
    x_min, x_max = 100, 730
    for rect in (left_rect, right_rect):
        for step in [150, 300, 450, 600, 705]:
            xx = map_x(step, x_min, x_max, rect[0], rect[2])
            draw.line((xx, rect[3], xx, rect[3] + 7), fill="#98A6B5", width=2)
            text_center(draw, xx, rect[3] + 18, str(step), font(14), MUTED)
        for step in [235, 470]:
            xx = map_x(step, x_min, x_max, rect[0], rect[2])
            draw.line((xx, rect[1], xx, rect[3]), fill="#BBC6D2", width=2)
    p_loss = [(map_x(r["step"], x_min, x_max, *left_rect[::2]), map_y(r["loss"], 0.12, 0.24, left_rect[1], left_rect[3])) for r in val_rows]
    # Explicit coordinates avoid relying on array slicing order for the second chart.
    p_loss = [(map_x(r["step"], x_min, x_max, left_rect[0], left_rect[2]), map_y(r["loss"], 0.12, 0.24, left_rect[1], left_rect[3])) for r in val_rows]
    p_i2t = [(map_x(r["step"], x_min, x_max, right_rect[0], right_rect[2]), map_y(r["i2t"], 88, 100, right_rect[1], right_rect[3])) for r in val_rows]
    p_t2i = [(map_x(r["step"], x_min, x_max, right_rect[0], right_rect[2]), map_y(r["t2i"], 88, 100, right_rect[1], right_rect[3])) for r in val_rows]
    draw_line(draw, p_loss, NAVY, 5, 8)
    draw_line(draw, p_i2t, TEAL, 5, 8)
    draw_line(draw, p_t2i, CORAL, 5, 8)
    for r, (x, y) in zip(val_rows, p_loss):
        text_center(draw, x, y - 31, f"{r['loss']:.3f}", font(14, True), NAVY)
    legend_item(draw, 1010, 840, TEAL, "Image → text")
    legend_item(draw, 1240, 840, CORAL, "Text → image")
    image.save(ROOT / "04_validation_trends.png", optimize=True)


def plot_training(train_rows):
    image, draw = make_canvas("Training convergence", "Logged every 10 optimizer steps  |  faint points show batch values; bold curves show a 9-point moving average")
    top_rect, bottom_rect = (200, 290, 1460, 580), (200, 690, 1460, 850)
    draw.text((200, 225), "Batch contrastive loss", font=font(22, True), fill=INK)
    draw.text((200, 625), "In-batch retrieval accuracy", font=font(22, True), fill=INK)
    plot_frame(draw, top_rect, [0, .15, .30, .45, .60], 0, .60, lambda v: f"{v:.2f}")
    plot_frame(draw, bottom_rect, [70, 80, 90, 100], 70, 100, lambda v: f"{v}%")
    steps = [r["step"] for r in train_rows]
    for rect in (top_rect, bottom_rect):
        for boundary in [235, 470]:
            xx = map_x(boundary, 0, 705, rect[0], rect[2])
            draw.line((xx, rect[1], xx, rect[3]), fill="#B9C5D1", width=2)
        for tick in [0, 150, 300, 450, 600, 705]:
            xx = map_x(tick, 0, 705, rect[0], rect[2])
            text_center(draw, xx, rect[3] + 12, str(tick), font(14), MUTED)
    losses = np.array([r["loss"] for r in train_rows])
    smoothed_loss = moving_average(losses)
    raw_points = [(map_x(s, 0, 705, top_rect[0], top_rect[2]), map_y(v, 0, .60, top_rect[1], top_rect[3])) for s, v in zip(steps, losses)]
    for x, y in raw_points:
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="#A9BCD0")
    draw_line(draw, [(map_x(s, 0, 705, top_rect[0], top_rect[2]), map_y(v, 0, .60, top_rect[1], top_rect[3])) for s, v in zip(steps, smoothed_loss)], NAVY, 5, 0)
    for key, color in (("i2t", TEAL), ("t2i", CORAL)):
        smooth = moving_average(np.array([r[key] for r in train_rows]))
        pts = [(map_x(s, 0, 705, bottom_rect[0], bottom_rect[2]), map_y(v, 70, 100, bottom_rect[1], bottom_rect[3])) for s, v in zip(steps, smooth)]
        draw_line(draw, pts, color, 4, 0)
    legend_item(draw, 980, 890, TEAL, "Image → text")
    legend_item(draw, 1210, 890, CORAL, "Text → image")
    image.save(ROOT / "05_training_convergence.png", optimize=True)


def plot_epoch_end(val_rows):
    final = {}
    for row in val_rows:
        final[row["epoch"]] = row
    rows = [final[k] for k in sorted(final)]
    image, draw = make_canvas("Epoch-end validation", "Final checkpoint in each epoch  |  accuracy is batch-level, not full-pool test Recall@K")
    left_rect, right_rect = (210, 335, 730, 760), (950, 335, 1460, 760)
    draw.text((210, 255), "Validation loss", font=font(23, True), fill=INK)
    draw.text((950, 255), "Mean bidirectional accuracy", font=font(23, True), fill=INK)
    plot_frame(draw, left_rect, [0, .05, .10, .15, .20, .25], 0, .25, lambda v: f"{v:.2f}")
    plot_frame(draw, right_rect, [88, 90, 92, 94, 96, 98, 100], 88, 100, lambda v: f"{v}%")
    x1 = [map_x(i, 1, 3, left_rect[0], left_rect[2]) for i in [1, 2, 3]]
    x2 = [map_x(i, 1, 3, right_rect[0], right_rect[2]) for i in [1, 2, 3]]
    p1 = [(x, map_y(r["loss"], 0, .25, left_rect[1], left_rect[3])) for x, r in zip(x1, rows)]
    avg = [(r["i2t"] + r["t2i"]) / 2 for r in rows]
    p2 = [(x, map_y(v, 88, 100, right_rect[1], right_rect[3])) for x, v in zip(x2, avg)]
    draw_line(draw, p1, NAVY, 6, 10)
    draw_line(draw, p2, TEAL, 6, 10)
    for i, (x, r) in enumerate(zip(x1, rows), 1):
        text_center(draw, x, left_rect[3] + 24, f"Epoch {i}", font(17, True), MUTED)
        text_center(draw, x, p1[i - 1][1] - 38, f"{r['loss']:.3f}", font(18, True), NAVY)
    for i, (x, v) in enumerate(zip(x2, avg), 1):
        text_center(draw, x, right_rect[3] + 24, f"Epoch {i}", font(17, True), MUTED)
        text_center(draw, x, p2[i - 1][1] - 38, f"{v:.2f}%", font(18, True), TEAL)
    image.save(ROOT / "06_epoch_end_validation.png", optimize=True)


def plot_lr_runtime(train_rows):
    image, draw = make_canvas("Learning-rate & runtime diagnostics", "Training log averages  |  per-step timing is from the completed run, not a fresh benchmark")
    left_rect, right_rect = (200, 330, 735, 760), (950, 330, 1460, 760)
    draw.text((200, 255), "Cosine learning-rate schedule", font=font(22, True), fill=INK)
    draw.text((950, 255), "Data loading vs. remaining step time", font=font(22, True), fill=INK)
    max_lr = max(r["lr"] for r in train_rows) * 1.1
    plot_frame(draw, left_rect, np.linspace(0, max_lr, 6), 0, max_lr, lambda v: f"{v*1e5:.1f}×10⁻⁵")
    plot_frame(draw, right_rect, [0, .08, .16, .24, .32, .40], 0, .40, lambda v: f"{v:.2f}s")
    for rect in (left_rect, right_rect):
        for tick in [0, 150, 300, 450, 600, 705]:
            xx = map_x(tick, 0, 705, rect[0], rect[2])
            text_center(draw, xx, rect[3] + 22, str(tick), font(14), MUTED)
        for boundary in [235, 470]:
            xx = map_x(boundary, 0, 705, rect[0], rect[2])
            draw.line((xx, rect[1], xx, rect[3]), fill="#B9C5D1", width=2)
    steps = [r["step"] for r in train_rows]
    p_lr = [(map_x(s, 0, 705, left_rect[0], left_rect[2]), map_y(r["lr"], 0, max_lr, left_rect[1], left_rect[3])) for s, r in zip(steps, train_rows)]
    p_data = [(map_x(s, 0, 705, right_rect[0], right_rect[2]), map_y(r["data_time"], 0, .40, right_rect[1], right_rect[3])) for s, r in zip(steps, train_rows)]
    p_work = [(map_x(s, 0, 705, right_rect[0], right_rect[2]), map_y(max(0, r["batch_time"] - r["data_time"]), 0, .40, right_rect[1], right_rect[3])) for s, r in zip(steps, train_rows)]
    draw_line(draw, p_lr, GOLD, 4, 0)
    draw_line(draw, p_data, BLUE, 4, 0)
    draw_line(draw, p_work, TEAL, 4, 0)
    legend_item(draw, 980, 835, BLUE, "Data loading")
    legend_item(draw, 1210, 835, TEAL, "Compute + other overhead")
    image.save(ROOT / "07_lr_and_runtime.png", optimize=True)


def plot_dashboard(baseline, tuned, n):
    keys, labels = ["r1", "r5", "r10"], ["R@1", "R@5", "R@10"]
    b = baseline["scoreJson"]
    f = tuned["scoreJson"]
    image, draw = make_canvas("Fine-tuned Chinese-CLIP · test summary", "Recorded evaluation snapshot · 2026-10-18 · three-epoch fine-tune")
    cards = [("TEST PAIRS", f"{n:,}", BLUE), ("BASELINE MEAN RECALL", f"{b['mean_recall']:.2f}%", NAVY),
             ("TUNED MEAN RECALL", f"{f['mean_recall']:.2f}%", TEAL),
             ("ABSOLUTE LIFT", f"+{f['mean_recall']-b['mean_recall']:.2f} pp", CORAL)]
    card_w, gap, y0, y1 = 330, 30, 235, 390
    start = 105
    for i, (label, value, color) in enumerate(cards):
        x0 = start + i * (card_w + gap)
        draw.rounded_rectangle((x0, y0, x0 + card_w, y1), radius=22, fill="#F8FAFC", outline="#E5EAF0", width=2)
        draw.text((x0 + 23, y0 + 22), label, font=font(16, True), fill=MUTED)
        draw.text((x0 + 23, y0 + 69), value, font=font(31, True), fill=color)
    rect = (260, 500, 1430, 815)
    plot_frame(draw, rect, [0, 20, 40, 60, 80, 100], 0, 100, lambda v: f"{v}%")
    xvals = [rect[0] + (rect[2] - rect[0]) * i / 3 for i in range(4)]
    bar_w = 35
    for i, key in enumerate(keys):
        x = rect[0] + (rect[2] - rect[0]) * (i + .5) / 3
        for value, color, dx in ((b[key], BLUE, -28), (f[key], TEAL, 28)):
            y = map_y(value, 0, 100, rect[1], rect[3])
            draw.rounded_rectangle((x + dx - bar_w / 2, y, x + dx + bar_w / 2, rect[3]), radius=12, fill=color)
            text_center(draw, x + dx, y - 32, f"{value:.1f}", font(16, True), color)
        text_center(draw, x, rect[3] + 20, labels[i], font(19, True), MUTED)
    legend_item(draw, 485, 875, BLUE, "Pretrained")
    legend_item(draw, 750, 875, TEAL, "Fine-tuned epoch 3")
    image.save(ROOT / "08_evaluation_dashboard.png", optimize=True)


def make_contact_sheet():
    files = ["01_recall_at_k.png", "02_absolute_gain_pp.png", "03_relative_gain.png", "04_validation_trends.png",
             "05_training_convergence.png", "06_epoch_end_validation.png", "07_lr_and_runtime.png", "08_evaluation_dashboard.png"]
    tw, th, caption_h = 760, 475, 45
    cols, rows = 2, 4
    sheet = Image.new("RGB", (cols * tw + 60, rows * (th + caption_h) + 70), BG)
    d = ImageDraw.Draw(sheet)
    for i, name in enumerate(files):
        chart = Image.open(ROOT / name).convert("RGB")
        chart.thumbnail((tw, th), Image.Resampling.LANCZOS)
        x = 20 + (i % cols) * (tw + 20)
        y = 20 + (i // cols) * (th + caption_h)
        sheet.paste(chart, (x, y))
        d.text((x + 8, y + th + 8), name.replace(".png", "").replace("_", " "), font=font(16, True), fill=INK)
    sheet.save(ROOT / "00_contact_sheet.png", optimize=True)


def main():
    baseline = json.loads((SOURCE / "baseline_test_score.json").read_text(encoding="utf-8"))
    tuned = json.loads((SOURCE / "finetuned_epoch3_test_score.json").read_text(encoding="utf-8"))
    manifest = json.loads((SOURCE / "run_manifest.json").read_text(encoding="utf-8"))
    train_rows, val_rows = parse_log()
    n = int(manifest["test_split"]["text_count"])
    plot_recall(baseline, tuned, n)
    plot_gains(baseline, tuned, relative=False)
    plot_gains(baseline, tuned, relative=True)
    plot_validation(val_rows)
    plot_training(train_rows)
    plot_epoch_end(val_rows)
    plot_lr_runtime(train_rows)
    plot_dashboard(baseline, tuned, n)
    make_contact_sheet()
    print(json.dumps({"training_log_points": len(train_rows), "validation_log_points": len(val_rows),
                      "test_pairs": n, "files": [p.name for p in ROOT.glob("0*.png")]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



