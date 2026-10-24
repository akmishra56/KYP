"""Label parsing without identity or health inference."""
import re
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Token:
    raw: str
    text: str
    position: int
    optional: bool = False
    ocr_confidence: float | None = None

    parent_path: tuple[str, ...] = ()
    structure_uncertain: bool = False

    def to_dict(self):
        return asdict(self) | {"parent_path": list(self.parent_path)}


def parse_label(text: str, confidence: float | None = None, context: str = 'general', comma_review: bool = False) -> list[Token]:
    if len(text) > 30000:
        raise ValueError('Label text exceeds 30,000 characters')
    text = re.sub(r'(?<=\w)-[ \t]*\r?\n(?=\w)', '', text)
    anchor = re.search(r'\b(?:ingredients|ingrédients|inci)\b\s*:?', text, re.I)
    if anchor:
        text = text[anchor.end():]
    text = re.split(r'\b(?:directions|warnings|made in|usage instructions|nutrition(?:al)?\s+(?:information|facts)|nutrient\s+information|how\s+to\s+use|manufactured\s+by|marketed\s+by|(?:spice|salt)\s+content\s+above)\b\s*[:.]?', text, maxsplit=1, flags=re.I)[0]
    if context == 'food':
        depth = 0
        for index, char in enumerate(text):
            if char in '([': depth += 1
            elif char in ')]': depth -= 1
            if depth == 0 and (index == 0 or not text[index-1].isalnum()) and re.match(r'(?:contains\s*:|may\s+contain\b|allergen\s+(?:information|advice)\s*:)', text[index:], re.I):
                text = text[:index]
                break
    else:
        text = re.sub(r'\bmay\s+contain\b\s*:?|\+\s*/\s*-', '\x00', text, flags=re.I)
    if comma_review:
        # Explicit recovery only: do not guess a lost bracket hierarchy.
        chunks = []
        optional = False
        for raw in re.split(r'[,;]', text):
            if '\x00' in raw: optional = True
            cleaned = re.sub(r'\b\d+(?:\.\d+)?\s*%', '', raw)
            cleaned = re.sub(r'[()\[\]\x00*]', ' ', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip(' \t\r\n:.')
            if cleaned: chunks.append(Token(raw.strip(), cleaned, len(chunks), optional, confidence, (), True))
        if len(chunks) > 200: raise ValueError('No more than 200 ingredient tokens are supported')
        return chunks
    chunks, buf, stack, optional = [], [], [], False
    def emit():
        raw = ''.join(buf).strip()
        buf.clear()
        cleaned = re.sub(r'\b\d+(?:\.\d+)?\s*%', '', raw).replace('*', '').strip(' \t\r\n:.')
        cleaned = re.sub(r'\(\s*\)|\[\s*\]', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned:
            chunks.append(Token(raw, cleaned, len(chunks), optional, confidence))
    for char in text:
        if char == '\x00':
            emit()
            optional = True
            continue
        if char in '([':
            stack.append(char)
            if len(stack) > 12:
                raise ValueError("No more than 12 nested ingredient groups are supported")
        elif char in ')]':
            if not stack or (stack[-1], char) not in [('(', ')'), ('[', ']')]:
                raise ValueError('Unbalanced brackets: correct the ingredient text')
            stack.pop()
        if char in ',;' and not stack:
            emit()
        else:
            buf.append(char)
    if stack:
        raise ValueError('Unbalanced brackets: correct the ingredient text')
    emit()
    if context == 'food':
        expanded = []
        for token in chunks:
            # Expand only explicit comma/semicolon lists in a single trailing
            # bracket group. Parenthetical botanical/alias spellings stay intact.
            opening = next((i for i, ch in enumerate(token.text) if ch in '(['), None)
            group = None
            if opening is not None:
                depth = 0
                for i in range(opening, len(token.text)):
                    ch = token.text[i]
                    if ch in '([': depth += 1
                    elif ch in ')]': depth -= 1
                    if depth == 0:
                        if i == len(token.text)-1: group = token.text[opening+1:i]
                        break
            if group and any(ch in group for ch in ',;'):
                parent = token.text[:opening].strip() or 'Declared blend'
                # Recover the original list contents, including percentages, for
                # leaf raw text; cleaned text is used only to recognize structure.
                source = token.raw.rstrip(' \t\r\n:.')
                for start, character in enumerate(source):
                    if character not in '([': continue
                    depth = 0
                    for end in range(start, len(source)):
                        if source[end] in '([': depth += 1
                        elif source[end] in ')]': depth -= 1
                        if depth == 0:
                            if end == len(source)-1 and any(c in source[start+1:end] for c in ',;'):
                                group = source[start+1:end]
                            break
                children = parse_label(group, confidence, context='food')
                for child in children:
                    expanded.append(Token(child.raw, child.text, len(expanded), token.optional or child.optional, confidence, (parent,) + child.parent_path))
            else:
                expanded.append(Token(token.raw, token.text, len(expanded), token.optional, confidence, token.parent_path))
            if len(expanded) > 200:
                raise ValueError('No more than 200 ingredient tokens are supported')
        chunks = expanded
    if len(chunks) > 200:
        raise ValueError('No more than 200 ingredient tokens are supported')
    return chunks
