# Natural Language Query Parsing — Learnings

## Dual Parsing Strategy

1. **Claude Haiku via Instructor** (`parse_query_with_claude`): Structured extraction using Pydantic models. Best for complex/ambiguous queries. Requires `ANTHROPIC_API_KEY`.
2. **Regex fallback** (`parse_natural_query`): Pattern matching for English, Roman Urdu, and Urdu script. Always available, no API needed.

## Roman Urdu Support

Common mappings that users expect:
| Roman Urdu | English | Filter |
|-----------|---------|--------|
| ghar, makan | house | property_type |
| flat, flaat | apartment | property_type |
| bala hissa, bala | upper portion | property_type |
| nichla hissa, nichla | lower portion | property_type |
| kamra | room | property_type |
| sasta | cheapest | sort |
| mehenga | expensive | sort |
| naya | newest | sort |
| hazar, hazaar | thousand | price multiplier |
| lac, lakh | lakh (100K) | price multiplier |

## Area Matching Challenges

The `match_area()` function uses 7 strategies in order:
1. Exact Urdu match
2. Fuzzy Urdu match (substring)
3. Roman Urdu alias (exact then substring)
4. Exact English (case-insensitive)
5. Substring match (prefer shorter/more specific)
6. Token overlap (weighted by ratio)
7. SequenceMatcher (threshold: 0.5)

**Key issue**: This aggressive fuzzy matching means "gulshan e iqbal block 13" matches "Gulshan-e-Iqbal" even though block 13 doesn't exist. The approximate match notice (added in routes.py) now warns users when their query was simplified.

## Ambiguous Queries

- "portion" alone → defaults to "upper_portion" (more common in Pakistan)
- "full house" → matches "house" (the word "full" is ignored, which is correct)
- Standalone numbers ≤ 500 in price context → treated as thousands (e.g., "50" = 50K PKR)
- "studio" → mapped to "Room" property type

## Caching NLP Results

Claude parse results are cached by query string (MD5 hash). This prevents redundant API calls for repeated queries within the 5-min TTL window.
