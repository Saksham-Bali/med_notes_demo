TEMPLATE_GUIDANCE = """
Use the NABH discharge summary section order exactly:
1. Patient Demographics
2. Admission Details
3. Clinical History
4. Investigations
5. Treatment Given
6. Disease Progression
7. Counselling Summary
8. Condition at Discharge
9. Discharge Instructions
10. Summary Narrative

Requirements:
- Keep the content concise, clinical, and documentation-ready.
- Use "Not available" for any unavailable string field.
- Use empty arrays instead of fabricated list items.
- Keep dates specific whenever the source includes enough detail.
""".strip()
