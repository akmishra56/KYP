"""Local sparse TF-IDF vectors and cosine ranking for OCR ingredient phrases."""
import math
import re
from collections import Counter, defaultdict


def features(value, policy):
    words = re.findall(r'[^\W_]+', value, re.UNICODE)
    result = Counter()
    for word in words:
        result['w:' + word] += policy['word_weight']
        padded = '^' + word + '$'
        for size in policy['character_ngrams']:
            for start in range(len(padded) - size + 1):
                result['c:' + padded[start:start+size]] += 1
    for first, second in zip(words, words[1:]):
        result['b:' + first + ' ' + second] += policy['word_weight']
    return result


class CosineIndex:
    def __init__(self, items, normalize, policy):
        self.policy, self.normalize = policy, normalize
        self.items = {item['id']: item for item in items}
        documents, frequency = [], Counter()
        for item in items:
            terms = set()
            for name in sorted(set([item['name']] + item['aliases'])):
                value = normalize(name)
                if not value or len(value) > policy['max_vector_text_length']: continue
                vector = features(value, policy)
                documents.append((item['id'], name, vector)); terms.update(vector)
            frequency.update(terms)
        self.unknown_idf = math.log(1 + len(items)) + 1
        self.idf = {term: math.log((1 + len(items)) / (1 + count)) + 1 for term, count in frequency.items()}
        self.documents = [(identity, name, self._vector(vector)) for identity, name, vector in documents]
        self.postings = defaultdict(list)
        for index, (_, _, vector) in enumerate(self.documents):
            for term, weight in vector.items(): self.postings[term].append((index, weight))

    def _vector(self, counts, include_unknown=False):
        vector = {term: (1 + math.log(count)) * self.idf.get(term, self.unknown_idf) for term, count in counts.items() if include_unknown or term in self.idf}
        norm = math.sqrt(sum(weight * weight for weight in vector.values()))
        return {term: weight / norm for term, weight in vector.items()} if norm else {}

    def rank(self, text):
        query = self.normalize(text)
        if not query or len(query) > self.policy['max_vector_text_length']: return []
        vector = self._vector(features(query, self.policy), include_unknown=True)
        if not vector: return []
        best, scores = {}, defaultdict(float)
        for term, weight in vector.items():
            for index, candidate_weight in self.postings.get(term, []): scores[index] += weight * candidate_weight
        for index, score in scores.items():
            identity, name, _ = self.documents[index]
            score = min(1.0, score)
            if score > 0 and (identity not in best or score > best[identity]['similarity']):
                best[identity] = {'id': identity, 'name': self.items[identity]['name'], 'matched_name': name, 'similarity': score, 'match_probability': None, 'probability_status': 'not_calibrated'}
        ranked = sorted(best.values(), key=lambda item: (-item['similarity'], item['id']))[:self.policy['candidate_limit']]
        return [dict(item, similarity=round(item['similarity'], 6)) for item in ranked]
