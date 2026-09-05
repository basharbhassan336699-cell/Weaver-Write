# html2pptx-core — install

Native HTML→PPTX converter (no browser needed). Integrated from
abdelkrimkr/html2pptx (MIT), with reference material from GX-Alex/html2pptx.

## One-time setup
```
cd engines/html2pptx-core
npm install        # installs adm-zip, cheerio, css, pptxgenjs
```
Termux: `pkg install nodejs` first.

## How it's used
The pptx_builder skill generates themed HTML (html_deck_generator.py),
then html2pptx_bridge.py calls this engine to produce native, editable PPTX.

This is the "design in HTML/CSS → convert to PPTX" approach (the Claude way),
giving full theme variety via CSS instead of one hard-coded layout.

## Enabling the creative path in the pipeline
Fully enabling the creative (LLM-authored) deck path requires
`pkg install nodejs` then `cd engines/html2pptx-core && npm install`
(and an API key, since authoring needs the model). Without them the pipeline
automatically falls back to the template builder (build_pptx) — nothing breaks.
