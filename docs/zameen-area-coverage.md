# Zameen.com Area Coverage — Learnings

## How Zameen.com Organizes Areas

Zameen.com uses a hierarchical area structure:
```
City (Karachi, ID: 2)
└── Town/District (e.g., Gulshan-e-Iqbal Town, ID: 6858)
    ├── Blocks (e.g., Block 1, ID: 6861)
    └── Named neighborhoods (e.g., Bahadurabad, ID: 524)
```

Each area has:
- A **slug** (URL-safe name): `Karachi_Gulshan_e_Iqbal_Block_1`
- A unique **numeric ID**: `6861`
- URL format: `https://www.zameen.com/Rentals/{slug}-{id}-{page}.html`

## Block-Level Coverage

Not all areas have block-level granularity on Zameen.com. Here's what we've found:

| Area | Blocks on Zameen.com | Notes |
|------|---------------------|-------|
| Clifton | 1-9 | All discovered by crawler |
| Federal B Area | 10-20 | Discovered |
| Gulshan-e-Iqbal | 1, 2, 4, 5, 7 | Blocks 3, 6, 8-13+ don't exist on Zameen.com |
| Gulistan-e-Jauhar | 13 (at minimum) | Partially discovered |
| Gulshan-e-Kaneez Fatima | 1, 2, 4 | Under Scheme 33 |
| North Nazimabad | Multiple blocks | Discovered |
| Naya Nazimabad | Multiple blocks | Discovered |

**Key insight**: If a user searches for "Gulshan-e-Iqbal Block 13", that area simply doesn't exist on Zameen.com. The app falls back to the parent area and shows a notice.

## Discovery Tool Limitations

The `deep_discover.py` crawler has 3 phases:
1. Main Karachi page → finds ~80 areas
2. Property type pages → finds ~20 more
3. Deep crawl of each area → finds sub-areas/blocks

**Limitation**: Phase 3 only crawls pages already discovered. Some blocks (like Gulshan-e-Iqbal blocks) are listed on the "Town" page (`Gulshan_e_Iqbal_Town-6858`) but not on the direct area page (`Gulshan_e_Iqbal-233`). The crawler found the Town sub-areas but missed the blocks because they live under a different hierarchy level.

**Fix applied**: We now check both the direct area page AND the Town page when looking for sub-areas.

## Adding Missing Areas Manually

When users report missing areas:
1. Check if it exists on Zameen.com: `curl -sL "https://www.zameen.com/Rentals/{slug}-{guessed_id}-1.html"`
2. If no ID is known, crawl the parent area page to extract sub-area links
3. Get coordinates from the page's embedded JSON: look for `"lat":XX.XX,"lng":XX.XX`
4. Add to `app/areas.json` and `ROMAN_URDU_AREAS` in `app/data.py`
