// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("API Endpoints", () => {
  test("GET /api/health returns ok", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe("ok");
    expect(body.service).toBe("ZameenRentals");
    expect(body.version).toBeTruthy();
  });

  test("GET /api/cities returns all three cities", async ({ request }) => {
    const res = await request.get("/api/cities");
    expect(res.ok()).toBeTruthy();
    const cities = await res.json();
    expect(cities.length).toBe(3);
    const keys = cities.map((c) => c.key);
    expect(keys).toContain("karachi");
    expect(keys).toContain("lahore");
    expect(keys).toContain("islamabad");
    for (const city of cities) {
      expect(city).toHaveProperty("name");
      expect(city).toHaveProperty("lat");
      expect(city).toHaveProperty("lng");
    }
  });

  test("GET /api/areas returns areas for each city", async ({ request }) => {
    for (const city of ["karachi", "lahore", "islamabad"]) {
      const res = await request.get(`/api/areas?city=${city}`);
      expect(res.ok()).toBeTruthy();
      const areas = await res.json();
      expect(areas.length).toBeGreaterThan(50);
      const first = areas[0];
      expect(first).toHaveProperty("name");
      expect(first).toHaveProperty("slug");
      expect(first).toHaveProperty("id");
      expect(first).toHaveProperty("lat");
      expect(first).toHaveProperty("lng");
    }
  });

  test("GET /api/areas defaults to karachi", async ({ request }) => {
    const res = await request.get("/api/areas");
    const areas = await res.json();
    // Karachi has ~366 areas
    expect(areas.length).toBeGreaterThan(300);
  });

  test("GET /api/search-areas fuzzy searches within city", async ({
    request,
  }) => {
    const res = await request.get(
      "/api/search-areas?q=dha&city=karachi&limit=5"
    );
    expect(res.ok()).toBeTruthy();
    const results = await res.json();
    expect(results.length).toBeGreaterThan(0);
    expect(results.length).toBeLessThanOrEqual(5);
    // DHA should be among the results
    const names = results.map((r) => r.name.toLowerCase());
    expect(names.some((n) => n.includes("dha"))).toBeTruthy();
  });

  test("GET /api/property-types returns all types", async ({ request }) => {
    const res = await request.get("/api/property-types");
    expect(res.ok()).toBeTruthy();
    const types = await res.json();
    expect(types.length).toBeGreaterThanOrEqual(7);
    const keys = types.map((t) => t.key);
    expect(keys).toContain("house");
    expect(keys).toContain("apartment");
    expect(keys).toContain("upper_portion");
    expect(keys).toContain("lower_portion");
    expect(keys).toContain("room");
    expect(keys).toContain("penthouse");
    expect(keys).toContain("farm_house");
    // "flat" is an alias and should not appear as separate type
    expect(keys).not.toContain("flat");
  });

  test("GET /api/parse-query parses NL queries", async ({ request }) => {
    const res = await request.get(
      "/api/parse-query?q=2+bed+flat+DHA+under+50k&city=karachi"
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.query).toBeTruthy();
    expect(body.filters).toBeTruthy();
    const f = body.filters;
    expect(f.bedrooms).toBe(2);
    expect(f.property_type).toBe("apartment");
    expect(f.price_max).toBe(50000);
    expect(f.area).toBeTruthy();
  });

  test("GET /api/parse-query flags approximate area match", async ({
    request,
  }) => {
    const res = await request.get(
      "/api/parse-query?q=gulshan+e+iqbal+block+13&city=karachi"
    );
    const body = await res.json();
    // Block 13 doesn't exist, so match should be approximate
    expect(body.filters.area).toContain("Gulshan");
    expect(body.filters.area_approximate).toBe(true);
  });

  test("GET /api/parse-query works for lahore", async ({ request }) => {
    const res = await request.get(
      "/api/parse-query?q=3+bed+house+DHA&city=lahore"
    );
    const body = await res.json();
    expect(body.filters.bedrooms).toBe(3);
    expect(body.filters.property_type).toBe("house");
  });

  test("GET /api/search returns results", async ({ request }) => {
    const res = await request.get("/api/search?city=karachi&page=1", {
      timeout: 20000,
    });
    if (!res.ok()) test.skip(); // Zameen.com may be down/rate-limiting
    const body = await res.json();
    expect(body).toHaveProperty("total");
    expect(body).toHaveProperty("results");
    expect(body.page || body.per_page).toBeTruthy(); // local uses per_page, live uses page
    // Results may be empty if local DB has no data and live scraping is rate-limited
    expect(Array.isArray(body.results)).toBeTruthy();
  });

  test("GET /api/search accepts all filter params", async ({ request }) => {
    const res = await request.get(
      "/api/search?city=karachi&area=DHA+Defence&property_type=house&bedrooms=3&price_min=50000&price_max=200000&furnished=true&sort=price_low&page=1",
      { timeout: 20000 }
    );
    if (!res.ok()) test.skip();
    const body = await res.json();
    expect(body.url).toContain("zameen.com");
    expect(Array.isArray(body.results)).toBeTruthy();
  });

  test("GET /api/search listing has expected fields", async ({ request }) => {
    const res = await request.get("/api/search?city=karachi&page=1", {
      timeout: 20000,
    });
    if (!res.ok()) test.skip();
    const body = await res.json();
    if (body.results.length > 0) {
      const item = body.results[0];
      expect(item.title || item.price).toBeTruthy();
      if (item.url) expect(item.url).toContain("zameen.com");
    }
  });

  test("GET /api/search works for all cities", async ({ request }) => {
    for (const city of ["karachi", "lahore", "islamabad"]) {
      const res = await request.get(`/api/search?city=${city}&page=1`, {
        timeout: 20000,
      });
      if (!res.ok()) continue; // Skip cities that fail due to rate limiting
      const body = await res.json();
      expect(body.results.length).toBeGreaterThan(0);
    }
  });

  test("GET /api/search with property_type overrides listing labels", async ({
    request,
  }) => {
    const res = await request.get(
      "/api/search?city=karachi&property_type=house&page=1",
      { timeout: 20000 }
    );
    if (!res.ok()) test.skip();
    const body = await res.json();
    for (const item of body.results) {
      if (item.property_type) {
        expect(item.property_type).toBe("House");
      }
    }
  });

  test("GET /api/popular-searches returns array", async ({ request }) => {
    const res = await request.get(
      "/api/popular-searches?city=karachi&limit=5"
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body)).toBeTruthy();
  });

  test("GET /api/recent-searches returns array", async ({ request }) => {
    const res = await request.get("/api/recent-searches?city=karachi&limit=5");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body)).toBeTruthy();
  });

  test("GET / serves the frontend HTML", async ({ request }) => {
    const res = await request.get("/");
    expect(res.ok()).toBeTruthy();
    const text = await res.text();
    expect(text).toContain("ZameenRentals");
    expect(text).toContain("<!DOCTYPE html>");
  });

  // ── New: crawl-status endpoint ──

  test("GET /api/crawl-status returns freshness data", async ({ request }) => {
    const res = await request.get("/api/crawl-status");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty("total_listings");
    expect(body).toHaveProperty("detail_coverage");
    expect(body).toHaveProperty("areas_crawled");
    expect(body).toHaveProperty("areas_total");
    expect(body).toHaveProperty("last_crawl_at");
    expect(typeof body.total_listings).toBe("number");
    expect(typeof body.detail_coverage).toBe("number");
  });

  test("GET /api/crawl-status accepts city filter", async ({ request }) => {
    const res = await request.get("/api/crawl-status?city=karachi");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.total_listings).toBeGreaterThanOrEqual(0);
  });

  // ── New: search source field ──

  test("GET /api/search includes source field", async ({ request }) => {
    const res = await request.get("/api/search?city=karachi&page=1", {
      timeout: 20000,
    });
    if (!res.ok()) test.skip();
    const body = await res.json();
    expect(body).toHaveProperty("source");
    expect(["local", "live"]).toContain(body.source);
  });
});
