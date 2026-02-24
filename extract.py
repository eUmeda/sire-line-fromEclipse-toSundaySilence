#!/usr/bin/env python3
"""Extract horse data from existing HTML pages to JSON.

Run once to bootstrap the data/ directory:
    python3 extract.py
"""

import json
import re
import html
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

ROOT = Path(__file__).parent
HORSES_DIR = ROOT / "horses"
DATA_DIR = ROOT / "data"
INDEX_HTML = ROOT / "index.html"

LINE_ORDER = [
    "eclipse", "pot-8-os", "waxy", "whalebone", "sir-hercules",
    "birdcatcher", "the-baron", "stockwell", "doncaster", "bend-or",
    "bona-vista", "cyllene", "polymelus", "phalaris", "pharos",
    "nearco", "royal-charger", "turn-to", "hail-to-reason", "halo",
    "sunday-silence"
]


def decode_entities(text):
    """Decode HTML entities to Unicode characters."""
    if not text:
        return text
    return html.unescape(text).strip()


def get_text_content(el):
    """Get text content, decoding entities."""
    if el is None:
        return ""
    return decode_entities(el.get_text())


def inner_html(el):
    """Get inner HTML of an element as string."""
    return "".join(str(c) for c in el.children).strip()


def extract_nav(soup):
    """Extract navigation data."""
    nav = soup.find("nav", class_="horse-nav")
    gen_text = get_text_content(nav.find("div", class_="nav-gen"))
    # e.g. "Generation XXI" -> "XXI"
    generation = gen_text.replace("Generation ", "").strip()

    prev_next = nav.find("div", class_="prev-next")
    links = prev_next.find_all("a")
    spans = prev_next.find_all("span", style=True)

    prev_data = None
    next_data = None

    for link in links:
        href = link.get("href", "")
        name_text = get_text_content(link)
        # Previous: "◀ Eclipse" or "◁ Eclipse"
        # Next: "Pot-8-Os ▶" or "Pot-8-Os ▷"
        slug = href.replace(".html", "")
        cleaned = re.sub(r'[◀◁▶▷◄►\u25C0\u25C1\u25B6\u25B7\u25C4\u25BA\u9654\u9664]', '', name_text).strip()
        if not cleaned:
            cleaned = name_text.strip()
        # Detect direction from character codes
        raw = link.decode_contents()
        if "9664" in raw or "◀" in raw or "◁" in raw:
            prev_data = {"slug": slug, "name": cleaned}
        elif "9654" in raw or "▶" in raw or "▷" in raw:
            next_data = {"slug": slug, "name": cleaned}
        elif links.index(link) == 0 and not prev_data:
            prev_data = {"slug": slug, "name": cleaned}
        else:
            next_data = {"slug": slug, "name": cleaned}

    return generation, prev_data, next_data


def extract_profile(soup):
    """Extract profile info items."""
    section = soup.find("section", class_="info-section")
    items = []
    for div in section.find_all("div", class_="info-item"):
        label = get_text_content(div.find("span", class_="info-label"))
        value_span = div.find("span", class_="info-value")
        unknown_span = value_span.find("span", class_="info-unknown")
        if unknown_span:
            value = get_text_content(unknown_span)
            items.append({"label": label, "value": value, "unknown": True})
        else:
            value = get_text_content(value_span)
            items.append({"label": label, "value": value})
    return items


def extract_biography(soup):
    """Extract biography paragraphs."""
    sections = soup.find_all("section", class_="bio-section")
    # First bio-section is the Biography
    if not sections:
        return []
    bio_section = sections[0]
    title = get_text_content(bio_section.find("h2"))
    if title != "Biography":
        return []
    paragraphs = []
    for p in bio_section.find("div", class_="bio-text").find_all("p"):
        paragraphs.append(get_text_content(p))
    return paragraphs


def extract_extra_sections(soup):
    """Extract extra bio-style sections (e.g. Eclipse's 学術的評価)."""
    sections = soup.find_all("section", class_="bio-section")
    extras = []
    for section in sections:
        title = get_text_content(section.find("h2"))
        if title == "Biography":
            continue
        bio_text = section.find("div", class_="bio-text")
        if not bio_text:
            continue
        subsections = []
        current_title = None
        current_text = []
        for child in bio_text.children:
            if isinstance(child, NavigableString):
                continue
            if child.name == "h3":
                if current_title:
                    subsections.append({"title": current_title, "text": "\n".join(current_text)})
                current_title = get_text_content(child)
                current_text = []
            elif child.name == "p":
                current_text.append(get_text_content(child))
        if current_title:
            subsections.append({"title": current_title, "text": "\n".join(current_text)})
        extras.append({"title": title, "subsections": subsections})
    return extras


def extract_race_record(soup):
    """Extract race record data."""
    section = soup.find("section", class_="race-section")
    if not section:
        return None

    # Stats
    stats = {}
    unknown_stats = []
    stat_labels_map = {"出走": "starts", "勝利": "wins", "2着": "seconds", "3着": "thirds"}
    for stat_div in section.find_all("div", class_="race-stat"):
        num_span = stat_div.find("span", class_="race-stat-num")
        label_span = stat_div.find("span", class_="race-stat-label")
        label_text = get_text_content(label_span)
        key = stat_labels_map.get(label_text, label_text)

        unknown_inner = num_span.find("span", class_="info-unknown")
        if unknown_inner:
            stats[key] = get_text_content(unknown_inner)
            unknown_stats.append(key)
        else:
            stats[key] = get_text_content(num_span)

    # Narrative
    narrative_p = section.find("p", class_="race-narrative")
    narrative = get_text_content(narrative_p) if narrative_p else ""

    # Subsections (主な勝鞍, 種牡馬成績, 主な表彰, etc.)
    subsections = []
    for h3 in section.find_all("h3", class_="subsec-title"):
        title = get_text_content(h3)
        ul = h3.find_next_sibling("ul", class_="wins-list")
        items = []
        if ul:
            for li in ul.find_all("li"):
                items.append(get_text_content(li))
        subsections.append({"title": title, "items": items})

    # Historical note
    note_p = section.find("p", class_="historical-note")
    historical_note = get_text_content(note_p) if note_p else None

    result = {
        "stats": stats,
        "narrative": narrative,
        "subsections": subsections,
    }
    if unknown_stats:
        result["unknownStats"] = unknown_stats
    if historical_note:
        result["historicalNote"] = historical_note
    return result


def extract_pedigree(soup):
    """Extract 5-gen pedigree table into a binary tree."""
    section = soup.find("section", class_="pedigree-section")
    if not section:
        return None

    table = section.find("table", class_="ped-table")
    tbody = table.find("tbody")
    rows = tbody.find_all("tr")

    # Build a 32x6 grid
    grid = [[None] * 6 for _ in range(32)]
    occupied = [[False] * 6 for _ in range(32)]

    for row_idx, tr in enumerate(rows):
        col_idx = 0
        for td in tr.find_all("td", recursive=False):
            while col_idx < 6 and occupied[row_idx][col_idx]:
                col_idx += 1
            if col_idx >= 6:
                break

            rowspan = int(td.get("rowspan", 1))
            css_classes = td.get("class", [])

            # Parse cell content
            cell = parse_ped_cell(td, css_classes)
            grid[row_idx][col_idx] = cell

            for r in range(row_idx, min(row_idx + rowspan, 32)):
                if col_idx < 6:
                    occupied[r][col_idx] = True
            col_idx += 1

    # Extract ped-self display name (col 0, row 0)
    self_cell = grid[0][0]
    name_display_ped = inner_html(
        tbody.find("td", class_="ped-self")
    ) if self_cell else ""

    # Build binary tree from grid (skip col 0 = self)
    def build_node(col, start_row):
        if col > 5 or col >= 6:
            return None
        cell = grid[start_row][col]
        if cell is None:
            return {"name": "不詳", "unknown": True}

        node = {
            "name": cell["name"],
        }
        if cell.get("year"):
            node["year"] = cell["year"]
        if cell.get("sireLine"):
            node["sireLine"] = True
        if cell.get("unknown"):
            node["unknown"] = True
        if cell.get("link"):
            node["link"] = cell["link"]

        if col < 5:
            span = 2 ** (5 - col)
            node["sire"] = build_node(col + 1, start_row)
            node["dam"] = build_node(col + 1, start_row + span // 2)

        return node

    tree = {
        "sire": build_node(1, 0),
        "dam": build_node(1, 16),
    }

    # Pedigree note
    note_p = section.find("p", class_="historical-note")
    if note_p:
        tree["note"] = get_text_content(note_p)

    return tree, name_display_ped


def parse_ped_cell(td, css_classes):
    """Parse a single pedigree table cell."""
    is_sire_line = "ped-sire-line" in css_classes
    is_unknown = "ped-unknown" in css_classes

    # Extract link if present
    link_el = td.find("a")
    link = None
    if link_el:
        href = link_el.get("href", "")
        link = href.replace(".html", "")

    # Extract name: could be in <a> or direct text
    # Remove <small> to get clean name
    small = td.find("small")
    year = get_text_content(small) if small else None

    if link_el:
        name = get_text_content(link_el)
    else:
        # Get text without <small>
        texts = []
        for child in td.children:
            if isinstance(child, NavigableString):
                t = str(child).strip()
                if t and t != "\n":
                    texts.append(decode_entities(t))
            elif child.name != "small" and child.name != "br":
                texts.append(get_text_content(child))
        name = " ".join(texts).strip()
        if not name:
            name = get_text_content(td)
            if year and name.endswith(year):
                name = name[:-len(year)].strip()

    result = {"name": name}
    if year:
        result["year"] = year
    if is_sire_line:
        result["sireLine"] = True
    if is_unknown:
        result["unknown"] = True
    if link:
        result["link"] = link
    return result


def extract_offspring(soup):
    """Extract notable offspring list."""
    section = soup.find("section", class_="offspring-section")
    if not section:
        return []

    offspring = []
    for li in section.find_all("li", class_="offspring-item"):
        name_span = li.find("span", class_="offspring-name")
        year_span = li.find("span", class_="offspring-year")
        desc_span = li.find("span", class_="offspring-desc")

        link_el = name_span.find("a") if name_span else None
        link = None
        if link_el:
            href = link_el.get("href", "")
            link = href.replace(".html", "")
            name = get_text_content(link_el)
        else:
            name = get_text_content(name_span) if name_span else ""

        year_text = get_text_content(year_span) if year_span else ""
        year = year_text.strip("()")

        desc = get_text_content(desc_span) if desc_span else ""

        item = {"name": name, "year": year, "desc": desc}
        if link:
            item["link"] = link
        offspring.append(item)
    return offspring


def extract_sire_line(soup):
    """Extract sire line chain."""
    section = soup.find("section", class_="lineage-section")
    if not section:
        return []

    chain = []
    lineage_div = section.find("div", class_="lineage-chain")
    for child in lineage_div.children:
        if isinstance(child, NavigableString):
            continue
        if "lineage-arrow" in child.get("class", []):
            continue
        is_current = "lineage-current" in child.get("class", [])
        name = get_text_content(child.find("span", class_="lineage-node-name"))
        year = get_text_content(child.find("span", class_="lineage-node-year"))

        node = {"name": name, "year": year, "current": is_current}
        if not is_current:
            href = child.get("href", "")
            node["slug"] = href.replace(".html", "")
        else:
            node["slug"] = None
        chain.append(node)
    return chain


def extract_references(soup):
    """Extract reference sections."""
    section = soup.find("section", class_="ref-section")
    if not section:
        return []

    groups = []
    current_title = None
    current_items = []

    for child in section.children:
        if isinstance(child, NavigableString):
            continue
        if child.name == "h2":
            continue  # Skip the main "References" title
        if child.name == "h3":
            if current_items:
                groups.append({"title": current_title, "items": current_items})
            current_title = get_text_content(child)
            current_items = []
        elif child.name == "ul" and "ref-list" in child.get("class", []):
            for li in child.find_all("li"):
                a = li.find("a")
                if a:
                    text = get_text_content(a)
                    url = a.get("href", "")
                    current_items.append({"text": text, "url": url})
                else:
                    # Academic reference without link
                    # Preserve <em> tags
                    text_parts = []
                    for c in li.children:
                        if isinstance(c, NavigableString):
                            text_parts.append(str(c))
                        elif c.name == "em":
                            text_parts.append(f"<em>{c.get_text()}</em>")
                        else:
                            text_parts.append(c.get_text())
                    text = decode_entities("".join(text_parts).strip())
                    current_items.append({"text": text})

    if current_items:
        groups.append({"title": current_title, "items": current_items})

    return groups


def extract_card_descs(index_path):
    """Extract card descriptions from index.html timeline."""
    soup = BeautifulSoup(index_path.read_text("utf-8"), "lxml")
    descs = {}
    for item in soup.find_all("div", class_="tl-item"):
        a = item.find("h2", class_="card-name").find("a")
        href = a.get("href", "")
        slug = href.replace("horses/", "").replace(".html", "")
        desc_p = item.find("p", class_="card-desc")
        descs[slug] = get_text_content(desc_p)
    return descs


def extract_horse(html_path, card_descs):
    """Extract all data from a single horse HTML file."""
    soup = BeautifulSoup(html_path.read_text("utf-8"), "lxml")
    slug = html_path.stem
    data = {"id": slug}

    # Body class (era)
    body = soup.find("body")
    era_classes = [c for c in body.get("class", []) if c.startswith("e")]
    data["era"] = era_classes[0] if era_classes else "e1"

    # Navigation
    generation, prev_data, next_data = extract_nav(soup)
    data["generation"] = generation
    data["nav"] = {"prev": prev_data, "next": next_data}

    # Hero
    header = soup.find("header", class_="horse-hero")
    data["eraLabel"] = get_text_content(header.find("div", class_="horse-era"))
    data["name"] = get_text_content(header.find("h1", class_="horse-name"))
    data["dates"] = get_text_content(header.find("p", class_="horse-dates"))
    data["epithet"] = get_text_content(header.find("p", class_="horse-epithet"))

    # Birth year from dates
    year_match = re.search(r'(\d{4})', data["dates"])
    data["birthYear"] = int(year_match.group(1)) if year_match else 0

    # Card description from index
    data["cardDesc"] = card_descs.get(slug, "")

    # Profile
    data["profile"] = extract_profile(soup)

    # Biography
    data["biography"] = extract_biography(soup)

    # Extra sections
    data["extraSections"] = extract_extra_sections(soup)

    # Race Record
    data["raceRecord"] = extract_race_record(soup)

    # Pedigree
    ped_result = extract_pedigree(soup)
    if ped_result:
        data["pedigree"] = ped_result[0]
        data["nameDisplayPed"] = ped_result[1]

    # Offspring
    data["offspring"] = extract_offspring(soup)

    # Sire Line
    data["sireLine"] = extract_sire_line(soup)

    # References
    data["references"] = extract_references(soup)

    # Footer
    footer = soup.find("footer", class_="footer")
    footer_text = get_text_content(footer.find("p", class_="footer-text"))
    data["footerText"] = footer_text

    return data


def main():
    DATA_DIR.mkdir(exist_ok=True)

    # Extract card descriptions from index
    card_descs = extract_card_descs(INDEX_HTML)
    print(f"Extracted {len(card_descs)} card descriptions from index.html")

    # Extract each horse
    for slug in LINE_ORDER:
        html_path = HORSES_DIR / f"{slug}.html"
        if not html_path.exists():
            print(f"  SKIP {slug} (file not found)")
            continue

        data = extract_horse(html_path, card_descs)
        out_path = DATA_DIR / f"{slug}.json"
        out_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        print(f"  {slug}.json ({len(data.get('offspring', []))} offspring, "
              f"{sum(len(g.get('items',[])) for g in data.get('references',[]))} refs)")

    # Write line order
    order_path = DATA_DIR / "_line_order.json"
    order_path.write_text(
        json.dumps(LINE_ORDER, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print(f"\n_line_order.json written ({len(LINE_ORDER)} horses)")
    print("Done.")


if __name__ == "__main__":
    main()
