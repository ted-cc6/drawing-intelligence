# Reference tables

Data the `lookup` rules check against (ADR 0010): one YAML file per table, named as the rules' `params.table`
names it. Every table says where it comes from. Their content is part of the rulebook version recorded in every
review result, so a table change shows up like a rule change.

| File | What it holds | Source |
|---|---|---|
| `materials.yaml` | How a title-block material designation maps to a material class and family | PARI DES-11, US–India equivalents, the designations printed on the client drawings |
| `plating_processes.yaml` | PARI's surface treatments, how they are written, and the materials each suits | PARI PRD-GD-DES-12 rev 4 |

Patterns are case-insensitive regular expressions matched anywhere in the field. The first match wins, so list
specific patterns (hard anodizing) before general ones (anodizing).
