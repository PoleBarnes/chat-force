---
name: word-count
description: "Count words, characters, lines, and sentences in text. Use when: user asks for word count, character count, line count, or text statistics. NOT for: readability analysis, sentiment analysis, or language detection."
metadata:
  { "openclaw": { "emoji": "🔢" } }
---

# Word Count Skill

Count words, characters, lines, and sentences in provided text.

## When to Use

✅ **USE this skill when:**

- "How many words is this?"
- "Count the characters in this text"
- "How long is this document?"
- "Word count for this file"
- Checking text against length limits (tweets, meta descriptions, etc.)

## When NOT to Use

❌ **DON'T use this skill when:**

- Readability scoring → use readability tools
- Sentiment analysis → use NLP tools
- Grammar/spell checking → use grammar tools
- Language detection → use language ID tools

## Methods

### From Inline Text

Count words, characters, lines, and sentences directly from text provided in the conversation.

```bash
# Word count
echo "your text here" | wc -w

# Character count (excluding newline)
echo -n "your text here" | wc -c

# Line count
echo "your text here" | wc -l

# All at once (lines, words, characters)
echo "your text here" | wc
```

### From a File

```bash
# Word count
wc -w file.txt

# Character count
wc -c file.txt

# Line count
wc -l file.txt

# All stats
wc file.txt
```

### Sentence Count

```bash
# Approximate sentence count (splits on . ? !)
grep -oP '[.?!]' file.txt | wc -l
```

### Multiple Files

```bash
# Word counts for all .txt files
wc -w *.txt

# Recursive word count
find . -name "*.md" -exec wc -w {} + | tail -1
```

## Response Format

When reporting counts, use this structure:

| Metric     | Count |
| ---------- | ----- |
| Words      | X     |
| Characters | X     |
| Lines      | X     |
| Sentences  | ~X    |

Mark sentence count as approximate (~) since punctuation-based counting isn't perfect.

## Common Length References

| Format            | Typical Limit      |
| ----------------- | ------------------ |
| Tweet / X post    | 280 characters      |
| Meta description  | 155–160 characters  |
| Email subject     | 60 characters       |
| SMS               | 160 characters      |
| LinkedIn post     | 3,000 characters    |

## Notes

- `wc` counts whitespace-separated tokens as words
- Character count includes spaces unless using `wc -m` (multibyte-aware)
- Sentence counting via punctuation is an approximation — abbreviations (Dr., U.S.) can skew results
- For large files, `wc` is fast and streams efficiently
