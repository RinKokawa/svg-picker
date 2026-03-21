# svg-picker

A native GUI tool to search and pick SVG icons from [Iconify](https://iconify.design/).

## Features

- Search SVG icons by keyword via Iconify API
- Native dark-themed GUI window
- Click to select one or more icons
- Confirm to output SVG source code to stdout

## Install

```bash
pip install svg-picker
```

## Usage

```bash
svg-picker <keyword>
```

Example:

```bash
svg-picker home
```

1. The window opens and loads matching icons
2. Click icons to select them
3. Press **Confirm** — SVG source code is printed to stdout, then the window closes
