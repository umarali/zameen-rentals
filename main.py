"""
RentKarachi — Fast Zameen.com rental search API + web app.
Run: uvicorn main:app --reload --port 8000
Open: http://localhost:8000
"""
from app import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
