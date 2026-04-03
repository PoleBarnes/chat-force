---
name: word-count
description: Count words, characters, sentences, and paragraphs in provided text
triggers:
  - word count
  - count words
  - how many words
  - text length
  - character count
enabled_by_default: true
category: utility
---

# Word Count

You are counting words and providing text statistics. Give clear, accurate counts without unnecessary commentary.

---

## How to Count

### Step 1: Receive the Text

The user will provide text in one of these ways:
- Pasted directly in the message
- Referenced in a file (read the file first)
- A URL (fetch and extract the content first)

If no text is provided, ask for it.

### Step 2: Compute Statistics

Calculate the following metrics:

| Metric | Method |
|---|---|
| **Words** | Split on whitespace, count tokens. Hyphenated words count as one. |
| **Characters** | Total characters including spaces |
| **Characters (no spaces)** | Total characters excluding spaces |
| **Sentences** | Split on `.` `!` `?` (handle abbreviations and decimals sensibly) |
| **Paragraphs** | Blocks separated by blank lines |
| **Lines** | Total line count |

### Step 3: Report Results

Present results in a clean table:

```
| Metric                  | Count |
|-------------------------|-------|
| Words                   | X     |
| Characters              | X     |
| Characters (no spaces)  | X     |
| Sentences               | X     |
| Paragraphs              | X     |
| Lines                   | X     |
```

---

## Optional Extras

Only provide these if the user asks:

- **Reading time**: Estimate at 238 words per minute (average adult reading speed)
- **Speaking time**: Estimate at 150 words per minute
- **Top words**: Most frequent words (excluding common stop words)
- **Readability**: Flesch-Kincaid grade level if requested

---

## Edge Cases

- **Empty text**: Report all zeros, don't error
- **Code blocks**: Count code as text unless the user says to exclude it
- **Markdown**: Count the rendered text, not the markup syntax (strip `#`, `*`, `[]()`, etc.) unless the user wants raw counts
- **Multiple sections**: If the user asks for counts on specific sections, break them out separately

---

## Principles

- **Accuracy over speed**: Double-check counts on short texts where exactness matters
- **Don't editorialize**: The user asked for counts, not a critique of their writing
- **Be precise**: "About 500 words" is worse than "487 words"
- **For files**: Show the filename and path in the results header
