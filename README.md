# ZameenRentals

A fast rental property search engine powered by [Zameen.com](https://www.zameen.com) data. Built with FastAPI and vanilla JavaScript.

Currently supports **Karachi**, with **Lahore** and **Islamabad** coming soon.

## Features

- Search rental listings across 40+ areas
- Filter by property type, bedrooms, price range, and furnishing
- Sort by price or date
- Quick-access chips for popular areas
- Mobile-friendly responsive UI
- In-memory caching and rate limiting

## Tech Stack

- **Backend:** Python, FastAPI, httpx, BeautifulSoup
- **Frontend:** Vanilla HTML/CSS/JS (single file)
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
| `GET /api/health` | Health check |

## Roadmap

- [ ] Lahore support
- [ ] Islamabad support
- [ ] Favourites / saved searches
- [ ] Price trend charts
- [ ] Push notifications for new listings

## Disclaimer

This project scrapes publicly available data from Zameen.com for personal use. It is not affiliated with or endorsed by Zameen.com.
