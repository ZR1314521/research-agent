# Markdown to Office

Convert Markdown to Office formats using **Pandoc**.

## Supported target formats

docx, pptx, pdf, html, epub, tex, rst, odt

## Parameters

- `path` or `text`: Markdown source (file path or inline text)
- `target_format` (required): Target format (default: docx)
- `template` (optional): Path to a reference document for styling
- `output_path` (optional): Where to save the output

## Output

- `office_{format}`: Path to the generated file

## Dependencies

```bash
# Windows
choco install pandoc
# Or download from https://pandoc.org
```
