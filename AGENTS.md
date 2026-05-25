# AGENTS.md

## Project

`bead-grid-marker` is a small Windows desktop tool for adding bold 5-cell guide lines to bead-pattern images.

## Key Files

- `main.py` contains the full application: image loading/saving, grid detection, manual selection fallback, GUI, and CLI handling.
- `assets/bead_grid_marker.ico` is the PyInstaller icon.
- `README.md` is written for non-technical users first; keep technical content short and below the user-facing sections.

## Build And Test

Use the project virtual environment:

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m py_compile main.py
.\.venv\Scripts\python main.py "C:\path\to\image.jpg"
.\.venv\Scripts\pyinstaller --onefile --noconsole --icon assets\bead_grid_marker.ico --name bead_grid_marker main.py
```

## Implementation Notes

- Preserve Chinese-path support by using `np.fromfile` for reads and encoded bytes plus `tofile` for writes.
- Keep `social/`, `dist/`, `build/`, `.venv/`, and generated spec files out of Git.
- Grid detection uses strong-line fitting first, then weak-line boundary extension for low-contrast edges. Avoid changes that let legends, watermarks, or text determine the grid period.
- The manual fallback should remain available when automatic detection cannot reliably determine the grid.
