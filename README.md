# ZameenRentals

A fast rental property search engine powered by [Zameen.com](https://www.zameen.com) data. Built with FastAPI and vanilla JavaScript.

Currently supports **Karachi**, with **Lahore** and **Islamabad** coming soon.

## Features

- Search rental listings across 80+ Karachi areas
- Interactive Leaflet map with area labels and result count badges
- Filter by area, property type, bedrooms, price range, and furnishing
- Natural language search (powered by Claude) — e.g. "2 bed flat DHA under 50k"
- Sort by price or date
- Image carousels and detail drawer for each listing
- Quick-access preset chips (Budget 1BR, Family Home, etc.)
- Mobile-friendly responsive UI with full-screen map overlay
- In-memory caching (5 min TTL) and rate limiting

## Tech Stack

- **Backend:** Python, FastAPI, httpx, BeautifulSoup
- **Frontend:** Vanilla HTML/CSS/JS, Tailwind CSS (CDN), Leaflet.js
- **Data Source:** Zameen.com public listings

## Getting Started

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000)

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Web app |
| `GET /api/search` | Search listings (params: `area`, `property_type`, `bedrooms`, `price_min`, `price_max`, `furnished`, `sort`, `page`) |
| `GET /api/areas` | List all supported areas |
| `GET /api/property-types` | List all property types |
| `GET /api/parse-query` | Parse natural language query into filters |
| `GET /api/health` | Health check |

## Project Structure

```
main.py              # Entry point
app/
  __init__.py        # FastAPI app setup
  routes.py          # API endpoints
  scraper.py         # Zameen.com scraper & parser
  data.py            # Area definitions, property types, translations
  cache.py           # In-memory cache with TTL
  parsing.py         # Claude-powered NL query parsing
static/
  index.html         # Frontend (HTML + CSS + JS)
tools/
  discover_areas.py  # Utility to discover new areas from Zameen.com
```

## Roadmap

- [ ] Lahore support
- [ ] Islamabad support
- [ ] Favourites / saved searches
- [ ] Price trend charts
- [ ] Push notifications for new listings

## Disclaimer

This project scrapes publicly available data from Zameen.com for personal use. It is not affiliated with or endorsed by Zameen.com.
