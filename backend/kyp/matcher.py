import re
import hashlib
import json
from pathlib import Path
import unicodedata
from .vector_match import CosineIndex

POLICY = json.loads(Path(__file__).with_name('matching-policy.json').read_text(encoding='utf-8'))
MATCHER_VERSION = POLICY['version']
if POLICY['auto_accept_fuzzy']:
    raise ValueError('Automatic fuzzy identity acceptance is prohibited in this MVP')

def normalize(value):
    value = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value).casefold()).strip()
    return re.sub(r'^(e|ins)[ -]+(?=\d{3,4}(?:\([ivx]+\))?$)', r'\1', value)

def _resolve(token, repository, index):
    query = normalize(token.text)
    canonical = [item for item in index if normalize(item['name']) == query]
    aliases = [item for item in index if query in [normalize(alias) for alias in item['aliases']]]
    # A canonical/alias collision is ambiguous even when one is a canonical spelling.
    all_matches = {item['id']: item for item in canonical + aliases}
    result = token.to_dict() | {'match_status': 'unmatched', 'match_method': None, 'ingredient': None, 'suggestions': [], 'matcher_version': MATCHER_VERSION}
    if len(all_matches) == 1:
        item = next(iter(all_matches.values()))
        return result | {'match_status': 'matched', 'match_method': 'canonical' if canonical else 'alias', 'ingredient': repository.ingredient(item['id'])}
    # Composite INCI spellings resolve only when every component independently
    # identifies the same unambiguous canonical ingredient.
    composite = re.fullmatch(r'([^()]+)\(([^()]+)\)', token.text)
    if not all_matches and composite:
        parts = [composite.group(1).strip()] + [part.strip() for part in composite.group(2).split('/')]
        candidates = []
        for part in parts:
            ids = {item['id'] for item in index if normalize(part) in [normalize(item['name'])] + [normalize(alias) for alias in item['aliases']]}
            if len(ids) != 1:
                break
            candidates.append(next(iter(ids)))
        if len(candidates) == len(parts) and len(set(candidates)) == 1:
            return result | {'match_status': 'matched', 'match_method': 'composite_alias', 'ingredient': repository.ingredient(candidates[0])}
    if len(all_matches) > 1:
        return result | {'match_status': 'ambiguous', 'suggestions': [{'id': i['id'], 'name': i['name']} for i in all_matches.values()]}
    # Cosine candidates are added by the request-level vector index. They do not
    # turn an uncertain phrase into a confirmed ingredient automatically.
    return result


def match_many(tokens, repository, context='general', review_scope=''):
    # One catalog read per confirmation; cache details only within this request.
    class RequestRepository:
        def __init__(self):
            self.details = {}
        def ingredient(self, identity):
            if identity not in self.details:
                self.details[identity] = repository.ingredient(identity, context=context)
            return self.details[identity]
    index = repository.index(context=context)
    vectors = CosineIndex(index, normalize, POLICY)
    request = RequestRepository()
    results = []
    for token in tokens:
        result = _resolve(token, request, index)
        candidates = vectors.rank(token.text) if len(normalize(token.text)) <= POLICY['max_vector_text_length'] else []
        result.update(normalized_text=normalize(token.text), words=re.findall(r'[^\W_]+', normalize(token.text), re.UNICODE), product_context=context, vector_model=POLICY['vector_model'], closest_candidates=candidates, match_probability=None, probability_status='not_calibrated', match_similarity=None)
        if result['ingredient']:
            result['match_similarity'] = next((candidate['similarity'] for candidate in candidates if candidate['id'] == result['ingredient']['id']), None)
        elif result['match_status'] != 'ambiguous':
            result['suggestions'] = [candidate for candidate in candidates if candidate['similarity'] >= POLICY['suggestion_threshold']]
        reasons = ["uncertain_structure"] if token.structure_uncertain else []
        if result['match_status'] != 'matched':
            reasons.append('ambiguous_name' if result['match_status'] == 'ambiguous' else 'no_exact_match')
        elif result['match_similarity'] is None or result['match_similarity'] < POLICY['review_similarity_threshold']:
            reasons.append('low_text_similarity')
        if token.ocr_confidence is not None and token.ocr_confidence < POLICY['low_ocr_threshold']:
            reasons.append('low_ocr_quality')
        options = {candidate['id']: {'id': candidate['id'], 'name': candidate['name']} for candidate in candidates if candidate['similarity'] >= POLICY['suggestion_threshold']}
        if result['match_status'] == 'ambiguous': options.update({item['id']: item for item in result['suggestions']})
        if result['ingredient']: options[result['ingredient']['id']] = {'id': result['ingredient']['id'], 'name': result['ingredient']['name']}
        key = hashlib.sha256(json.dumps({'scope': review_scope, 'token': token.to_dict(), 'context': context, 'matcher': MATCHER_VERSION, 'options': sorted(options)}, sort_keys=True).encode()).hexdigest()
        result.update(confirmation_required=bool(reasons), confirmation_reasons=reasons, confirmation_options=list(options.values()), confirmation_key=key, confirmation_status='pending' if reasons else 'not_required')
        results.append(result)
    return results


def match(token, repository, context='general'):
    return match_many([token], repository, context)[0]


class ConfirmationRequired(ValueError):
    def __init__(self, positions):
        super().__init__('Confirm each flagged ingredient or keep it unknown before continuing.')
        self.positions = positions


def apply_confirmations(results, decisions, repository, context):
    by_position = {}
    for decision in decisions:
        position = decision['position']
        if position in by_position or position < 0 or position >= len(results):
            raise ValueError('Invalid or duplicate ingredient confirmation position')
        token = results[position]
        if not token['confirmation_required']:
            raise ValueError('This ingredient does not require individual confirmation')
        if decision['confirmation_key'] != token['confirmation_key']:
            raise ValueError('Ingredient text, product type or candidates changed. Review again.')
        chosen = decision['ingredient_id']
        allowed = {item['id'] for item in token['confirmation_options']}
        if chosen is not None and chosen not in allowed:
            raise ValueError('Choose a displayed candidate, correct the text, or keep the ingredient unknown')
        by_position[position] = chosen
    pending = [token['position'] for token in results if token['confirmation_required'] and token['position'] not in by_position]
    if pending: raise ConfirmationRequired(pending)
    for token in results:
        if token['position'] not in by_position: continue
        chosen = by_position[token['position']]
        token.update(confirmation_required=False, confirmation_status='confirmed' if chosen is not None else 'kept_unknown')
        if chosen is None:
            token.update(match_status='unmatched', match_method=None, ingredient=None, match_similarity=None)
        else:
            token.update(match_status='matched', match_method='user_confirmed', ingredient=repository.ingredient(chosen, context=context))
            token['match_similarity'] = next((item['similarity'] for item in token['closest_candidates'] if item['id'] == chosen), None)
    return results
