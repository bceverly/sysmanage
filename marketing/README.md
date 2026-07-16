# SysManage — Marketing Collateral

Source files for SysManage go-to-market collateral. Everything here is authored in
Markdown as the master source and is designed to convert cleanly to **DOCX** and
**PDF** later without rework.

## Contents

| File | Purpose |
|---|---|
| `executive-opportunity-brief.md` | The primary document — a ~12–15 page executive opportunity brief (strategy & commercial overview). |
| `cover-email.md` | The outreach email that accompanies the brief when sent to colleagues for introductions. |
| `images/` | Logo and screenshot/diagram assets referenced by the brief. |

## Screenshots & diagrams

Real product screenshots and diagrams (sourced from the `sysmanage-docs` asset library)
are already placed in `images/` and embedded in the brief:

| Image in `images/` | Source asset | Used for |
|---|---|---|
| `sysmanage-logo.svg` | logo | Cover |
| `cover-dashboard.png` | `map.png` | Cover background (fade behind title) |
| `product-dashboard.png` | `dashboard-screenshot.png` | Unified fleet dashboard |
| `product-host-detail.png` | `host-detail-windows.png` | Host detail |
| `product-vulnerabilities.png` | `vuln-overview.png` | Vulnerability & advisory mgmt |
| `product-compliance.png` | `compliance-overview.png` | Compliance |
| `product-patching.png` | `updates-page.png` | Patch & update orchestration |
| `product-automation.png` | `scripts.png` | Automation |
| `product-tenancy.png` | `sites-map.png` | Multi-tenant administration |
| `product-reporting.png` | `reports-overview.png` | Reporting |
| `architecture.svg` | `architecture-diagram.svg` | Reference architecture |
| `multi-tenancy-topology.svg` | `multi-tenancy-topology.svg` | Tenant isolation |

Swap any of these for a different screenshot by overwriting the file in `images/`
(keep the name) or updating the reference in the brief. The full asset library lives at
`../../sysmanage-docs/assets/images/` if you want a different shot.

**Two figures still need a designer** — they are conceptual, so no screenshot exists.
They remain as `[FIGURE: ...]` placeholders in the brief, each with a full description:

1. The fragmented **"before"** diagram (each OS wired to a different point tool).
2. The unified **"after"** diagram (six OSes converging into one SysManage control plane).

## Building the DOCX

The `executive-opportunity-brief.md` master is the single source of truth. To
regenerate the branded Word document after any edit, run the build script from the
repo root:

```
.venv/bin/python scripts/build-marketing-brief.py
```

That produces **both** `executive-opportunity-brief.docx` and
`executive-opportunity-brief.pdf` — a fully branded document with a cover page, colored
section headings, callout/thesis boxes, styled tables, embedded screenshots and
diagrams, and a page-numbered footer. Iterate on the `.md`, re-run the script, done.
(The `.docx`, `.pdf`, and the `.build/` cache are git-ignored build outputs.)

> **Note on the DOCX vs. the PDF.** Word/LibreOffice may show faint white horizontal
> lines across the diagrams *on screen* — that is a viewer scaling/interpolation
> artifact, not corrupt image data. The exported **PDF renders the diagrams cleanly**
> (verified), so send the PDF.

### How it handles graphics — and the white-line fix

SVG diagrams are rasterized with a clean pipeline: **SVG → PDF (LibreOffice) → PNG
(Ghostscript @300 DPI)**. ImageMagick's built-in SVG renderer produces the white
horizontal seam lines we kept fighting; this pipeline does not. Rasterized PNGs are
cached in `.build/` and only re-rendered when the source SVG changes. Requires
`libreoffice`/`soffice` and `gs` (both already installed on this machine), plus the
`python-docx` and `Pillow` packages in the project `.venv`.

### Markdown conventions the script understands

- `## Heading` → blue section heading with a hairline rule; `### Heading` → subheading.
- `<!-- PAGEBREAK -->` → a real page break. (Only an exact `PAGEBREAK` marker counts —
  comments that merely mention the word, like this list, are ignored.)
- `> **CALLOUT** —` / `> **THESIS** —` blockquotes → shaded callout boxes.
- Pipe tables with `:---:` alignment → styled tables (blue header, zebra rows).
- `![alt](path)` → centered, width-fit image; `.svg` paths are auto-rasterized.
- `**bold**`, `*italic*`, `` `code` ``, and `[text](url)` render as expected.

### The PDF

The build script exports the PDF automatically (via LibreOffice) right after the DOCX,
so `executive-opportunity-brief.pdf` is always in sync. To regenerate a PDF by hand from
an edited DOCX:

```
soffice --headless --convert-to pdf --outdir . executive-opportunity-brief.docx
```

### Highest-fidelity path (for the version you actually send)

For a truly bespoke look, import the `.docx` (or the Markdown text) into InDesign /
Affinity Publisher / Word, apply the sysmanage.org typography, and fine-tune. The
generated `.docx` is already presentable enough to send as-is or to hand a designer as
a starting point.

## Editorial guardrails (keep these true across every revision)

- **Never** call SysManage a "side project." It is an early-stage enterprise software company.
- **Never** sum the overlapping market segments into one TAM — sophisticated readers will
  catch it. Present them individually; the position, not a single number, is the point.
- Keep the softened, defensible differentiator claim ("to the best of our knowledge, no
  commercially available platform...") rather than an absolute "no other product."
- Do not name the European VC or their former company.
- Refresh the market-sizing figures against the latest published reports before any
  external distribution; source URLs are in the brief's References section.
