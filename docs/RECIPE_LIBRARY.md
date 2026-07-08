# Recipe Library

Recipes are reusable business/design assets for JamesOS Creative Studio.

Storage:

```text
~/JamesOSData/JamesOS/CreativeStudio/Recipes/
```

Default folders include `pride`, `underwear`, `halloween`, `teacher`, `programmer`, `mom_family`, `thai_english`, `market_chaos`, and `massage_therapist`.

Underwear recipes favor pattern, motif, color, symbol, and repeat-style design. Typography badge recipes avoid underwear by default.

Design Planner consumes recipes and Design DNA to create concrete product-aware plans. Design Critic then evaluates the plan before generation, so reusable recipes can stay broad while each variation gets specific composition, typography, palette, coverage, margin, and reuse guidance.

API:

```text
GET /recipes
GET /recipes/{recipe_id}
GET /recipes/by-product/{product_type}
```
