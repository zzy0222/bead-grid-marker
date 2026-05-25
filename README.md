# 拼豆图纸 5 格粗线工具

这是一个给拼豆图纸自动加粗分区线的小工具。

很多拼豆图纸格子很多，数格子时容易看错。这个工具会自动找到图纸里的小格子，并把每 5 格的分界线画粗，让图纸更容易看、也更方便一块一块地完成。

## 怎么使用

下载并双击打开 `bead_grid_marker.exe`，选择你的拼豆图纸图片即可。

也可以直接把图片拖到 `bead_grid_marker.exe` 上，工具会自动处理。

支持常见的 JPG、JPEG、PNG 图片。

处理完成后，新图片会保存在原图同一个文件夹里，文件名类似：

```text
原文件名_5x5粗线.原扩展名
```

原图不会被覆盖。

## 如果识别不准

有些图纸比较特别，自动识别可能会失败。遇到这种情况时，工具会提示你进入手动模式。

手动模式里，只需要用鼠标框选“完整网格区域”的外边界，松开鼠标后工具会继续处理。

## 适合谁

适合喜欢拼豆、钻石画、像素图纸，或者经常需要按格子数图的朋友。

不需要会编程，也不需要安装复杂软件。

## 开发运行

下面是给开发者看的内容，普通使用者可以忽略。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python main.py "C:\path\to\image.jpg"
```

## 打包

```powershell
.\.venv\Scripts\pyinstaller --onefile --noconsole --name bead_grid_marker main.py
```

带图标打包：

```powershell
.\.venv\Scripts\pyinstaller --onefile --noconsole --icon assets\bead_grid_marker.ico --name bead_grid_marker main.py
```
