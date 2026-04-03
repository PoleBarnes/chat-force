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
- "Count the words in this text"
- "What's the word count?"
- "How long is this text?"
- "Character count for this paragraph"
- Checking text against a word/character limit

## When NOT to Use

❌ **DON'T use this skill when:**

- Grammar or spell checking → use a grammar tool
- Readability scoring → use readability analyzers
- Content quality analysis → use content review tools
- Counting code tokens/LLM tokens → use a tokenizer

## How to Count

### From Inline Text

When the user provides text directly in their message:

```bash
# Word count
echo "<text>" | wc -w

# Character count (excluding newlines)
echo "<text>" | wc -m

# Line count
echo "<text>" | wc -l

# All stats at once (lines, words, characters)
echo "<text>" | wc
```

### From a File

When the user references a file:

```bash
# Word count
wc -w < file.txt

# Character count
wc -m < file.txt

# Line count
wc -l < file.txt

# All stats
wc file.txt
```

### Sentence Count

```bash
# Approximate sentence count (splits on . ! ?)
grep -oP '[.!?]+' file.txt | wc -l
```

### Multiple Files

```bash
# Word counts for multiple files (includes total)
wc -w file1.txt file2.txt file3.txt
```

## Response Format

Report results concisely:

- **Words:** X
- **Characters:** X (with/without spaces)
- **Lines:** X
- **Sentences:** ~X (approximate)

Only include the metrics the user asked for. If they just said "word count," give them the word count — don't dump every stat unless asked.

## Notes

- For large text blocks, prefer `wc` over manual counting
- Sentence counting via regex is approximate — edge cases exist (e.g., "Dr.", "U.S.A.")
- `wc -m` counts characters; `wc -c` counts bytes (differs for Unicode)
- When text is provided inline (not as a file), you can also count programmatically without shell commands
