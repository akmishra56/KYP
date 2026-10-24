"""Explicit simulated reviewer for synthetic integration fixtures only."""
def decisions(scan):
 return [{'position':t['position'],'confirmation_key':t['confirmation_key'],'ingredient_id':t['ingredient']['id'] if t['ingredient'] else None} for t in scan['match_preview'] if t['confirmation_required']]

def review_browser(page):
 # Fixture policy: acknowledge existing exact identities; keep non-exact unknown.
 choices=page.evaluate("session.match_preview.filter(t=>t.confirmation_required).map(t=>({position:t.position,id:t.ingredient?.id??null}))")
 for choice in choices:
  row=page.locator('[data-review-row="'+str(choice['position'])+'"]')
  row.locator('[data-unknown="true"]' if choice['id'] is None else '[data-candidate-id="'+choice['id']+'"]').click()
