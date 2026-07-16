# Office to Markdown

Convert Office and other formats to Markdown using **markitdown** (Microsoft).

## Supported input formats

| Format | Extension |
|--------|-----------|
| Word | .docx |
| Excel | .xlsx |
| PowerPoint | .pptx |
| PDF | .pdf |
| HTML | .html, .htm |
| Images (OCR) | .jpg, .png, .gif, .webp |
| Audio (transcription) | .mp3, .wav, .ogg |
| ZIP (batch) | .zip |

## Parameters

- `path` (required): Absolute path to the source file
- `output_path` (optional): Where to save the Markdown output

## Output

- `markdown_output`: Path to the generated .md file

## Dependencies

```bash
pip install markitdown
# For image/audio support:
pip install markitdown[all]
```
