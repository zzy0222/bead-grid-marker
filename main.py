from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageTk


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class GridDetectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AxisGrid:
    lines: list[int]
    cell_size: float


@dataclass(frozen=True)
class Grid:
    x: AxisGrid
    y: AxisGrid


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise GridDetectionError(f"无法读取图片：{path}")
    return image


def write_image(path: Path, image: np.ndarray) -> None:
    ext = path.suffix.lower()
    params: list[int] = []
    if ext in {".jpg", ".jpeg"}:
        params = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
    ok, data = cv2.imencode(ext, image, params)
    if not ok:
        raise GridDetectionError(f"无法保存图片：{path}")
    data.tofile(str(path))


def output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_5x5粗线{input_path.suffix}")


def projection_peaks(projection: np.ndarray) -> list[tuple[int, float]]:
    if projection.size == 0 or float(projection.max()) <= 0:
        return []

    threshold = max(float(np.percentile(projection, 95)), float(projection.max()) * 0.15)
    indices = np.where(projection >= threshold)[0]
    if indices.size == 0:
        return []

    groups: list[tuple[int, int]] = []
    start = previous = int(indices[0])
    for raw in indices[1:]:
        idx = int(raw)
        if idx <= previous + 3:
            previous = idx
        else:
            groups.append((start, previous))
            start = previous = idx
    groups.append((start, previous))

    peaks: list[tuple[int, float]] = []
    for start, end in groups:
        local = projection[start : end + 1]
        peak = start + int(np.argmax(local))
        peaks.append((peak, float(projection[peak])))
    return peaks


def estimate_cell_size(peaks: list[tuple[int, float]]) -> float:
    coords = [coord for coord, _ in peaks]
    diffs = np.diff(coords)
    plausible = [float(d) for d in diffs if 8 <= d <= 180]
    if len(plausible) < 3:
        raise GridDetectionError("识别到的网格线太少，无法估算格子大小")

    # Adjacent detections can occasionally skip a line. Use the smaller half of
    # distances so the fundamental cell size wins over 2x or 3x gaps.
    cutoff = float(np.percentile(plausible, 60))
    base = [d for d in plausible if d <= cutoff]
    return float(np.median(base or plausible))


def refine_cell_size(peaks: list[tuple[int, float]], estimated: float) -> float:
    coords = [coord for coord, _ in peaks]
    candidates: list[float] = []
    for idx, start in enumerate(coords):
        for end in coords[idx + 1 :]:
            slots = int(round((end - start) / estimated))
            if slots < 1:
                continue
            candidate = (end - start) / slots
            if estimated * 0.75 <= candidate <= estimated * 1.25:
                candidates.append(float(candidate))
    if len(candidates) < 3:
        return estimated
    return float(np.median(candidates))


def split_contiguous_runs(peaks: list[tuple[int, float]], cell_size: float) -> list[list[tuple[int, float]]]:
    if not peaks:
        return []

    runs: list[list[tuple[int, float]]] = [[peaks[0]]]
    for peak in peaks[1:]:
        gap = peak[0] - runs[-1][-1][0]
        if gap > cell_size * 2.15:
            runs.append([peak])
        else:
            runs[-1].append(peak)
    return runs


def phase_distance(value: float, period: float) -> float:
    wrapped = abs(value % period)
    return min(wrapped, period - wrapped)


def phase_aligned_run(peaks: list[tuple[int, float]], cell_size: float) -> list[tuple[int, float]]:
    """Pick the strongest periodic lattice, allowing missing lines in blank areas."""
    if not peaks:
        return []

    best: list[tuple[int, float]] = []
    best_score = float("-inf")
    tolerance = max(2.5, cell_size * 0.22)

    for anchor, _ in peaks:
        aligned: list[tuple[int, float]] = []
        for coord, weight in peaks:
            if phase_distance(coord - anchor, cell_size) <= tolerance:
                aligned.append((coord, weight))
        if len(aligned) < 3:
            continue

        span = aligned[-1][0] - aligned[0][0]
        expected_slots = max(1, int(round(span / cell_size)) + 1)
        density = len(aligned) / expected_slots
        score = span * 2.0 + len(aligned) * 500.0 + density * 200.0 + sum(weight for _, weight in aligned) / 1000.0
        if score > best_score:
            best_score = score
            best = aligned

    return best or peaks


def trim_isolated_edge_peaks(run: list[tuple[int, float]], cell_size: float) -> list[tuple[int, float]]:
    trimmed = list(run)
    gap_limit = cell_size * 2.5

    while len(trimmed) >= 4 and trimmed[1][0] - trimmed[0][0] > gap_limit:
        trimmed.pop(0)

    while len(trimmed) >= 4 and trimmed[-1][0] - trimmed[-2][0] > gap_limit:
        trimmed.pop()

    return trimmed


def dedupe_indexed_peaks(
    coords: list[int],
    weights: list[float],
    cell_size: float,
) -> tuple[list[int], list[int]]:
    anchor = coords[0]
    chosen: dict[int, tuple[int, float]] = {}
    for coord, weight in zip(coords, weights):
        index = int(round((coord - anchor) / cell_size))
        previous = chosen.get(index)
        if previous is None or weight > previous[1]:
            chosen[index] = (coord, weight)

    indices = sorted(chosen)
    deduped_coords = [chosen[index][0] for index in indices]
    return indices, deduped_coords


def fit_axis_grid(peaks: list[tuple[int, float]], axis_name: str) -> AxisGrid:
    cell_size = refine_cell_size(peaks, estimate_cell_size(peaks))
    run = trim_isolated_edge_peaks(phase_aligned_run(peaks, cell_size), cell_size)
    if not run:
        raise GridDetectionError(f"{axis_name} 方向没有识别到连续网格线")
    if len(run) < 6:
        raise GridDetectionError(f"{axis_name} 方向连续网格线不足")

    coords = [coord for coord, _ in run]
    weights = [weight for _, weight in run]
    indices, coords = dedupe_indexed_peaks(coords, weights, cell_size)

    fit = np.polyfit(np.array(indices, dtype=np.float64), np.array(coords, dtype=np.float64), 1)
    fitted_cell = float(fit[0])
    fitted_start = float(fit[1])
    first_index, last_index = min(indices), max(indices)
    lines = [int(round(fitted_start + i * fitted_cell)) for i in range(first_index, last_index + 1)]

    if len(lines) < 6 or fitted_cell < 8:
        raise GridDetectionError(f"{axis_name} 方向拟合出的网格无效")
    return AxisGrid(lines=lines, cell_size=fitted_cell)


def detect_grid(image: np.ndarray, manual_rect: tuple[int, int, int, int] | None = None) -> Grid:
    source = image
    offset_x = offset_y = 0
    if manual_rect is not None:
        x1, y1, x2, y2 = normalize_rect(manual_rect)
        if x2 - x1 < 50 or y2 - y1 < 50:
            raise GridDetectionError("手动选择区域太小")
        source = image[y1:y2, x1:x2]
        offset_x, offset_y = x1, y1

    gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 50, 150, L2gradient=True)

    height, width = gray.shape
    kernel_len = max(12, min(width, height) // 70)
    vertical = cv2.morphologyEx(
        edges,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_len)),
    )
    horizontal = cv2.morphologyEx(
        edges,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_len, 1)),
    )

    x_projection = np.sum(vertical > 0, axis=0).astype(np.float64)
    y_projection = np.sum(horizontal > 0, axis=1).astype(np.float64)

    x_peaks = projection_peaks(x_projection)
    y_peaks = projection_peaks(y_projection)
    x_grid = fit_axis_grid(x_peaks, "横向")
    y_grid = fit_axis_grid(y_peaks, "纵向")

    x_lines = [x + offset_x for x in x_grid.lines]
    y_lines = [y + offset_y for y in y_grid.lines]
    return Grid(
        x=AxisGrid(lines=x_lines, cell_size=x_grid.cell_size),
        y=AxisGrid(lines=y_lines, cell_size=y_grid.cell_size),
    )


def normalize_rect(rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = rect
    left, right = sorted((int(x1), int(x2)))
    top, bottom = sorted((int(y1), int(y2)))
    return left, top, right, bottom


def draw_major_lines(image: np.ndarray, grid: Grid) -> np.ndarray:
    result = image.copy()
    min_cell = max(1.0, min(abs(grid.x.cell_size), abs(grid.y.cell_size)))
    thickness = max(2, int(round(min_cell * 0.1)))
    color = (0, 0, 0)

    x_start, x_end = grid.x.lines[0], grid.x.lines[-1]
    y_start, y_end = grid.y.lines[0], grid.y.lines[-1]

    for idx, x in enumerate(grid.x.lines):
        if idx > 0 and idx % 5 == 0 and idx < len(grid.x.lines) - 1:
            cv2.line(result, (x, y_start), (x, y_end), color, thickness, cv2.LINE_AA)

    for idx, y in enumerate(grid.y.lines):
        if idx > 0 and idx % 5 == 0 and idx < len(grid.y.lines) - 1:
            cv2.line(result, (x_start, y), (x_end, y), color, thickness, cv2.LINE_AA)

    return result


def process_image(path: Path, manual_rect: tuple[int, int, int, int] | None = None) -> Path:
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise GridDetectionError("只支持 JPG、JPEG、PNG 图片")
    image = read_image(path)
    grid = detect_grid(image, manual_rect=manual_rect)
    marked = draw_major_lines(image, grid)
    out = output_path(path)
    write_image(out, marked)
    return out


class ManualSelector:
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path
        self.rect: tuple[int, int, int, int] | None = None

    def select(self) -> tuple[int, int, int, int] | None:
        import tkinter as tk

        root = tk.Tk()
        root.title("手动框选完整网格区域")

        pil_image = Image.open(self.image_path).convert("RGB")
        max_w, max_h = 1200, 820
        scale = min(max_w / pil_image.width, max_h / pil_image.height, 1.0)
        display_size = (int(pil_image.width * scale), int(pil_image.height * scale))
        display = pil_image.resize(display_size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(display)

        canvas = tk.Canvas(root, width=display_size[0], height=display_size[1], cursor="crosshair")
        canvas.pack()
        canvas.create_image(0, 0, image=photo, anchor="nw")
        info = tk.Label(root, text="拖动鼠标框选完整网格外边界，松开后开始处理")
        info.pack(fill="x")

        state: dict[str, int | None] = {"x": None, "y": None, "item": None}

        def on_down(event: tk.Event) -> None:
            state["x"], state["y"] = int(event.x), int(event.y)
            if state["item"] is not None:
                canvas.delete(int(state["item"]))
            state["item"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2)

        def on_move(event: tk.Event) -> None:
            if state["item"] is not None and state["x"] is not None and state["y"] is not None:
                canvas.coords(int(state["item"]), int(state["x"]), int(state["y"]), event.x, event.y)

        def on_up(event: tk.Event) -> None:
            if state["x"] is None or state["y"] is None:
                return
            x1, y1 = int(state["x"] / scale), int(state["y"] / scale)
            x2, y2 = int(event.x / scale), int(event.y / scale)
            self.rect = normalize_rect((x1, y1, x2, y2))
            root.destroy()

        canvas.bind("<ButtonPress-1>", on_down)
        canvas.bind("<B1-Motion>", on_move)
        canvas.bind("<ButtonRelease-1>", on_up)
        root.mainloop()
        return self.rect


def gui_main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()
    selected = filedialog.askopenfilename(
        title="选择拼豆图纸图片",
        filetypes=[("图片", "*.jpg *.jpeg *.png"), ("所有文件", "*.*")],
    )
    if not selected:
        return 0

    path = Path(selected)
    try:
        out = process_image(path)
        messagebox.showinfo("处理完成", f"已生成：\n{out}")
        return 0
    except Exception as exc:
        use_manual = messagebox.askyesno("自动识别失败", f"{exc}\n\n是否手动框选完整网格区域？")
        if not use_manual:
            return 1

    rect = ManualSelector(path).select()
    if rect is None:
        return 1
    try:
        out = process_image(path, manual_rect=rect)
        messagebox.showinfo("处理完成", f"已生成：\n{out}")
        return 0
    except Exception as exc:
        messagebox.showerror("处理失败", str(exc))
        return 1


def cli_main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(description="给拼豆图纸每 5 格加粗网格线")
    parser.add_argument("images", nargs="*", help="要处理的 JPG/PNG 图片路径")
    parser.add_argument("--manual", action="store_true", help="手动框选网格区域")
    args = parser.parse_args(list(argv))

    if not args.images:
        return gui_main()

    if getattr(sys, "frozen", False):
        return frozen_arg_main([Path(raw) for raw in args.images], manual=args.manual)

    exit_code = 0
    for raw in args.images:
        path = Path(raw)
        try:
            rect = ManualSelector(path).select() if args.manual else None
            out = process_image(path, manual_rect=rect)
            print(f"已生成：{out}")
        except Exception as exc:
            print(f"处理失败：{path}\n{exc}", file=sys.stderr)
            exit_code = 1
    return exit_code


def frozen_arg_main(paths: list[Path], manual: bool = False) -> int:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()

    outputs: list[Path] = []
    failures: list[str] = []

    for path in paths:
        try:
            rect = ManualSelector(path).select() if manual else None
            outputs.append(process_image(path, manual_rect=rect))
            continue
        except Exception as exc:
            if manual:
                failures.append(f"{path}\n{exc}")
                continue
            use_manual = messagebox.askyesno(
                "自动识别失败",
                f"{path}\n{exc}\n\n是否手动框选完整网格区域？",
            )
            if not use_manual:
                failures.append(f"{path}\n{exc}")
                continue

        rect = ManualSelector(path).select()
        if rect is None:
            failures.append(f"{path}\n已取消手动框选")
            continue
        try:
            outputs.append(process_image(path, manual_rect=rect))
        except Exception as exc:
            failures.append(f"{path}\n{exc}")

    if outputs:
        messagebox.showinfo("处理完成", "已生成：\n" + "\n".join(str(path) for path in outputs))
    if failures:
        messagebox.showerror("部分图片处理失败", "\n\n".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(cli_main(sys.argv[1:]))
