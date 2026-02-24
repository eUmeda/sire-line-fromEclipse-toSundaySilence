#!/usr/bin/env python3
"""Build script for sire-line static site.

Usage:
    python3 build.py              # Generate all HTML pages
    python3 build.py --serve      # Start dev server for admin UI
"""

import json
import sys
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, Undefined

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
TEMPLATE_DIR = ROOT / "templates"
OUTPUT_HORSES = ROOT / "horses"
OUTPUT_INDEX = ROOT / "index.html"


class SilentUndefined(Undefined):
    """Return empty string for undefined variables instead of raising."""
    def __str__(self):
        return ""
    def __iter__(self):
        return iter([])
    def __bool__(self):
        return False


def load_line_order():
    with open(DATA_DIR / "_line_order.json", encoding="utf-8") as f:
        return json.load(f)


def load_horse(slug):
    with open(DATA_DIR / f"{slug}.json", encoding="utf-8") as f:
        return json.load(f)


def get_ped_css(level, is_sire_side, node):
    """Determine CSS classes for a pedigree cell."""
    classes = []
    if level == 0:
        classes.append("ped-self")
    elif level == 1:
        classes.append("ped-sire" if is_sire_side else "ped-dam")
    else:
        classes.append(f"ped-g{level}")

    if node.get("sireLine"):
        classes.append("ped-sire-line")
    if node.get("unknown"):
        classes.append("ped-unknown")

    return " ".join(classes)


def flatten_pedigree(horse_data):
    """Convert pedigree binary tree to 32-row table for template rendering."""
    pedigree = horse_data.get("pedigree")
    if not pedigree:
        return []

    depth = 5
    rows = [[] for _ in range(32)]

    def traverse(node, level, start_row, is_sire_side):
        if node is None:
            node = {"name": "不詳", "unknown": True}

        rowspan = 2 ** (depth - level)
        css = get_ped_css(level, is_sire_side, node)

        cell = {
            "name": node.get("name", "不詳"),
            "year": node.get("year"),
            "rowspan": rowspan,
            "css": css,
            "link": node.get("link"),
            "is_self": level == 0,
            "display_html": horse_data.get("nameDisplayPed", horse_data["name"]),
        }
        rows[start_row].append(cell)

        if level < depth:
            sire = node.get("sire")
            dam = node.get("dam")
            traverse(sire, level + 1, start_row, True)
            traverse(dam, level + 1, start_row + rowspan // 2, False)

    # Level 0: self
    self_node = {
        "name": horse_data["name"],
        "year": str(horse_data["birthYear"]),
    }
    rows[0].append({
        "name": horse_data["name"],
        "year": str(horse_data["birthYear"]),
        "rowspan": 32,
        "css": "ped-self",
        "link": None,
        "is_self": True,
        "display_html": horse_data.get("nameDisplayPed", horse_data["name"]),
    })

    # Level 1+: sire side (rows 0-15), dam side (rows 16-31)
    traverse(pedigree.get("sire"), 1, 0, True)
    traverse(pedigree.get("dam"), 1, 16, False)

    return rows


def build_horse_page(env, horse_data):
    """Render a single horse page."""
    template = env.get_template("horse.html.j2")
    ped_rows = flatten_pedigree(horse_data)

    html = template.render(h=horse_data, ped_rows=ped_rows)
    output_path = OUTPUT_HORSES / f"{horse_data['id']}.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_index(env, all_horses):
    """Render the index/timeline page."""
    template = env.get_template("index.html.j2")
    html = template.render(horses=all_horses)
    OUTPUT_INDEX.write_text(html, encoding="utf-8")
    return OUTPUT_INDEX


def build_all():
    """Build all pages."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
        undefined=SilentUndefined,
    )

    line_order = load_line_order()
    all_horses = []

    OUTPUT_HORSES.mkdir(exist_ok=True)

    for slug in line_order:
        data = load_horse(slug)
        all_horses.append(data)
        path = build_horse_page(env, data)
        print(f"  Built {path.relative_to(ROOT)}")

    path = build_index(env, all_horses)
    print(f"  Built {path.relative_to(ROOT)}")
    print(f"\nDone. {len(all_horses)} horse pages + index.html generated.")


def serve(port=8080):
    """Start a development server with API endpoints for admin UI."""
    import http.server
    import urllib.parse

    class AdminHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path.startswith("/api/save/"):
                slug = parsed.path.split("/api/save/")[1]
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    data = json.loads(body)
                    out_path = DATA_DIR / f"{slug}.json"
                    out_path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True}).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())

            elif parsed.path == "/api/build":
                try:
                    build_all()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True}).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

    print(f"Serving at http://localhost:{port}")
    print(f"Admin UI: http://localhost:{port}/admin/")
    print("Press Ctrl+C to stop.")
    server = http.server.HTTPServer(("", port), AdminHandler)
    server.serve_forever()


def main():
    if "--serve" in sys.argv:
        port = 8080
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        serve(port)
    else:
        build_all()


if __name__ == "__main__":
    main()
