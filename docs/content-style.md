# ZameenRentals product language

Use the installed unslop skill when editing product copy. Preserve source listing titles, descriptions and dates; those are attributed source data.

- Use sentence case for labels: Near me, Clear all, Newest first.
- Use Saved homes for the renter's saved listings, My rentals for the panel, and Get alerts for a saved search. Internal API identifiers such as favorites stay unchanged.
- Describe actions directly: Search rentals, Save home, Compare. Avoid promises such as instant, verified or freshest unless the relevant behavior has evidence.
- A source fetch is not confirmed availability. Do not label search results Live. Identify the source or the selected ordering instead.
- Distinguish source dates, first-seen dates and retrieval times. If a stored value mixes date types, use Recorded date and explain the ambiguity. Never relabel it Posted or Data updated.
- Keep Zameen.com attribution. Describe Graana and OLX as planned, and Facebook as exploratory, until integrations exist.
- State current pricing as PKR 0 during beta. Do not promise free forever, unlimited usage, a paid feature, a launch date or automatic billing behavior that the product does not support.
- State limitations near the relevant action. Keep search accessible before requesting notifications or payment.
- Use English and Roman Urdu examples. Do not rewrite source descriptions or translate proper area names to make copy sound more polished.

Public information pages live in frontend/public/about.html, pricing.html and faq.html. Keep FAQ structured answers identical to the visible answers. Root canonical URLs, public-page metadata, structured data and sitemap.xml must use the same public domain. Rebuild with npm run build after source edits.
