# LLM prompt templates

Templates here are rendered with Jinja2 via `llm_helper.render_prompt(name, variables)`.

## Conventions

- One file per template, `<name>.txt`. Reference by stem from the concept blob:
  ```json
  "prompt_template": "cohort_labeling"
  ```
- Variables are passed via `blob['prompt_variables']` and merged with the
  `{ "note_text": ... }` injected by `apply_LLM`.
- Use `StrictUndefined` — missing variables raise rather than silently
  rendering empty strings. Add every required variable to the use-case JSON.
- Ask the model to return JSON inside `<json>...</json>` tags. Claude-family
  models reliably honor this; the `coerce_text_to_dict` validator also falls
  back to ` ```json ``` ` fences and brace blocks.

## Adding a new template

1. Drop a new `.txt` file in this directory.
2. Reference it by stem in your concept blob's `prompt_template`.
3. Use `{{ variable }}` placeholders for everything the use-case JSON supplies.
4. Add an example use-case JSON under `sample_files/LLM/`.
