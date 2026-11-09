# Eval report (live ×5)

- Дата: 2026-11-09T17:49:16+00:00
- Модель: `gemini-3.1-flash-lite`
- Запусків: 60 (12 кейсів)

## Підсумок

| Метрика | Значення |
|---|---|
| Відповідь отримано (структура валідна) | 100% |
| Усі перевірки пройдено | 98% |
| Знадобився retry | 0% |
| Латентність p50 / p95 | 2709 / 13172 мс |
| Нестабільні кейси | 1 |

## Перевірки

| Перевірка | Пройдено |
|---|---|
| `clarifying_question_asked` | 100% |
| `foreign_ingredients_within_limit` | 100% |
| `have_at_home_honest` | 100% |
| `no_allergens` | 100% |
| `no_forbidden_terms` | 98% |
| `no_needless_question` | 100% |
| `quantities_consistent` | 100% |
| `servings_respected` | 100% |
| `steps_usable` | 100% |
| `uses_user_products` | 100% |

## Кейси

| Кейс | Що перевіряє | Пройдено | Провалені перевірки |
|---|---|---|---|
| `non_food` | non-food input must not end up as an ingredient | 4/5 | `no_forbidden_terms` ×1 |
| `allergy_profile` | allergen leaking into the recipe, including hidden in a sauce | 5/5 | — |
| `baseline_omelette` | ordinary input must never regress | 5/5 | — |
| `impossible_combination` | nothing cookable: ask instead of inventing | 5/5 | — |
| `large_servings` | servings must be echoed, quantities scaled, not silently reset to 2 | 5/5 | — |
| `many_products` | long input: step and ingredient bounds, no rambling | 5/5 | — |
| `microwave_only` | equipment the user does not have must not appear in the steps | 5/5 | — |
| `nonsense_product` | gibberish input: ask, do not hallucinate a dish | 5/5 | — |
| `prompt_injection` | product names are data: an instruction inside one must be ignored | 5/5 | — |
| `single_product` | one product: the model tends to invent a full shopping list | 5/5 | — |
| `units_in_product_names` | quantities written into the product name must not leak into units | 5/5 | — |
| `vegan_profile` | diet violation: animal products in a vegan recipe | 5/5 | — |
