---
name: word-count
description: "Count words, characters, lines, and sentences in text. Use when: user asks to count words, get a word count, check text length, or analyze text statistics. NOT for: grammar checking, spell checking, or content analysis beyond counting."
metadata:
  { "openclaw": { "emoji": "🔢" } }
---

# Word Count Skill

Count words, characters, lines, and sentences in provided text.

## When to Use

✅ **USE this skill when:**

- "How many words is this?"
- "Word count for this text"
- "How long is this document?"
- "Count the characters/words/lines"
- Checking text against a target length

## When NOT to Use

❌ **DON'T use this skill when:**

- Grammar or spelling checks → use a proofreading tool
- Readability analysis → use readability scoring tools
- Content summarization → just summarize directly
- Keyword frequency/density → use text analysis tools

## Methods

### From Inline Text

Count words directly from text provided in the conversation:

```bash
echo "Your text here" | wc -w    # word count
echo "Your text here" | wc -m    # character count
echo "Your text here" | wc -l    # line count
```

### From a File

```bash
# Word count
wc -w file.txt

# All stats (lines, words, characters)
wc file.txt

# Multiple files
wc -w *.txt
```

### Detailed Breakdown

```bash
# Words, characters, lines, and sentences
TEXT="Your text here"
echo "Words:      $(echo "$TEXT" | wc -w)"
echo "Characters: $(echo "$TEXT" | wc -m)"
echo "Lines:      $(echo "$TEXT" | wc -l)"
echo "Sentences:  $(echo "$TEXT" | grep -oP '[.!?]+' | wc -l)"
```

### For Large Documents

```bash
# Word count for a file with summary
wc -w < document.txt

# Count words excluding blank lines
grep -c '\S' document.txt   # non-empty lines
cat document.txt | tr -s '[:space:]' '\n' | grep -c '\S'  # words
```

## Quick Responses

**"How many words?"** — Count and report: `X words, Y characters, Z lines`

**"Is this under 500 words?"** — Count and compare against the target, give a clear yes/no with the actual count.

**"Word count for this file"** — Run `wc -w <file>` and report the number.

## Notes

- `wc` is available on all Unix/Linux/macOS systems
- For text provided inline (not in a file), you can also count programmatically without shell commands
- When counting words in conversation text, prefer counting directly over writing temp files
- Sentence counting via grep is approximate — it splits on `.!?` punctuation
