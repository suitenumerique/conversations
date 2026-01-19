import { createHighlighterCore } from 'shiki/core';
import { createOnigurumaEngine } from 'shiki/engine/oniguruma';
import langBash from 'shiki/langs/bash.mjs';
import langCss from 'shiki/langs/css.mjs';
import langHtml from 'shiki/langs/html.mjs';
import langJavascript from 'shiki/langs/javascript.mjs';
import langJson from 'shiki/langs/json.mjs';
import langMarkdown from 'shiki/langs/markdown.mjs';
import langPython from 'shiki/langs/python.mjs';
import langSql from 'shiki/langs/sql.mjs';
import langTypescript from 'shiki/langs/typescript.mjs';
import langYaml from 'shiki/langs/yaml.mjs';
import themeDimmed from 'shiki/themes/github-dark-dimmed.mjs';

export const getHighlighter = () =>
  createHighlighterCore({
    themes: [themeDimmed],
    langs: [
      langJavascript,
      langTypescript,
      langPython,
      langBash,
      langJson,
      langHtml,
      langCss,
      langSql,
      langYaml,
      langMarkdown,
    ],

    engine: createOnigurumaEngine(import('shiki/wasm')),
  });
