---
name: html-review
description: Produce a readable standalone HTML artifact whenever presenting a review, plan, audit, proposal, comparison or other material for Umar to review. Keep evidence and source files alongside it when useful.
---

# HTML review delivery

Umar's standing preference is HTML for anything he is asked to review. The HTML is the primary deliverable; Markdown or data files may remain as supporting sources. Brief conversational replies and progress updates need no separate artifact. An explicit request for another format takes precedence for that deliverable.

Lead with the decision or recommendation. Let the reader inspect evidence, options and uncertainty without reading the whole document. Scale the layout to the task: simple prose for short reviews; navigation and tables for long ones. Separate observed facts from interpretation, include measurement units and denominators, and make actions concrete. Do not add approval gates or recommendations that exceed the request.

Produce a self-contained `.html` file with inline styles, semantic headings, readable tables, keyboard-accessible navigation, mobile layout and print styles. Avoid remote fonts, scripts and telemetry. Escape untrusted excerpts. Preserve all important findings when converting an existing review. Do not silently publish the file to a website.

For a Markdown source, the bundled renderer provides a quiet, accessible default:

```bash
python3 <skill-dir>/scripts/render_review.py --input <source.md> --output <review.html> --title 'Review title' --subtitle 'Scope or date'
```

The renderer requires the `markdown-it-py` and `beautifulsoup4` Python packages. Use an existing environment; if unavailable, create equivalent HTML directly rather than adding project dependencies for a document. Local code links retain the line as metadata and open the actual file. Cross-machine sharing needs portable attachments or repository URLs instead of absolute paths.

Open and inspect generated HTML using an existing headless browser when available. Check desktop and narrow layout, navigation, tables, links and browser errors. Do not install browsers or open visible test windows just to validate a document. For a long conversion, compare text and finding counts with the source. State any unverified behavior.

Return a concise summary and a clickable link to the HTML file. Do not hand the user only Markdown and offer HTML later.
