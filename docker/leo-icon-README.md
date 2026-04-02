# Leo App Icon

**Final icon:** `leo-icon-final.png`

## How it was generated

**Model:** Google Imagen 4.0 (`imagen-4.0-generate-001`)
**API:** Google GenAI Python SDK (`google-genai`)
**Runner:** `uv run --python 3.13 --with google-genai`

### Prompt

```
Digital illustration. Close-up headshot of a male digital agent in a dark trench coat with popped collar, suit and tie underneath. Stylized semi-realistic render. He has brown hair swept to the side, a neatly trimmed full beard and mustache, strong jawline, warm friendly smile showing teeth, blue eyes. Wearing glasses. Looking directly at camera with a confident approachable expression. Green and dark teal color palette on solid black background. Clean lines, no glitch effects. The black background must extend completely to all four edges and corners. No text, no border, no frame.
```

### Generation command

```bash
GEMINI_KEY="<your-key>" uv run --python 3.13 --with google-genai python3 << 'PYEOF'
import os
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_KEY"])

prompt = "Digital illustration. Close-up headshot of a male digital agent in a dark trench coat with popped collar, suit and tie underneath. Stylized semi-realistic render. He has brown hair swept to the side, a neatly trimmed full beard and mustache, strong jawline, warm friendly smile showing teeth, blue eyes. Wearing glasses. Looking directly at camera with a confident approachable expression. Green and dark teal color palette on solid black background. Clean lines, no glitch effects. The black background must extend completely to all four edges and corners. No text, no border, no frame."

response = client.models.generate_images(
    model="imagen-4.0-generate-001",
    prompt=prompt,
    config=types.GenerateImagesConfig(
        number_of_images=4,
        aspect_ratio="1:1",
        output_mime_type="image/png",
    )
)

for i, img in enumerate(response.generated_images):
    img.image.save(f"leo-icon-{i+1}.png")
PYEOF
```

### Key learnings

- Using "app icon" in the prompt causes Imagen to add rounded corners — avoid it
- The API key is stored in Doppler (project: chat-force, config: dev, key: GEMINI_API_KEY)
- Use `uv run` for clean isolated Python execution instead of system pip

### Slack app settings

- **App Name:** Leo
- **Display Name (Bot Name):** Leo
- **Background Color:** `#0F2318`
- **Short Description:** Your AI-powered digital worker for marketing, code, and ops.
