# Print Readiness Scoring

JamesOS scores design variations from 0-100.

Categories:

- resolution
- transparency
- safe margin
- composition
- contrast
- typography
- product fit
- commercial style
- recipe adherence
- trademark safety
- Design Critic signal

Underwear scoring rewards pattern, motif, color, and repeat-friendly artwork. It does not penalize no-text designs, and it penalizes large text-heavy underwear designs.

Design Critic can nudge product fit, composition, typography, transparency, and recipe adherence using metadata-only critique.

Promotion requires `print_readiness_score >= 90` and a compatible critic recommendation. If no variation reaches 90, or if the critic recommends rejection, the winner is marked `best_candidate_needs_review`, not `ready_for_printify_review`.
