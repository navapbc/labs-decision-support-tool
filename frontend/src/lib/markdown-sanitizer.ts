/**
 * Sanitizes streaming markdown content by fixing LLM tokenization artifacts.
 *
 * NOTE: This is COMPLEMENTARY to Streamdown's `remend` package, not a replacement.
 * - `remend` handles UNTERMINATED markdown (e.g., `**bold` without closing `**`)
 * - This sanitizer handles MALFORMED markdown from tokenization spacing
 *
 * LLM tokenization often breaks markdown syntax by inserting spaces between tokens:
 * - `** Income Limits **` instead of `**Income Limits**`
 * - `https :// as pe .h hs .gov` instead of `https://aspe.hhs.gov`
 * - `word 's` instead of `word's`
 *
 * These spacing issues are NOT handled by Streamdown/remend, which only deals with
 * unterminated syntax. This preprocessor fixes tokenization artifacts before rendering.
 */

export function sanitizeStreamingMarkdown(content: string): string {
  if (!content) return content;

  let result = content;

  // Fix URLs first - remove ALL spaces from URL patterns
  // URLs should never have spaces (they'd be %20 encoded)
  // Match URLs that may have spaces inserted by tokenization
  result = result.replace(
    /\]\(\s*(https?\s*:\s*\/\s*\/[^)]*)\)/g,
    (match, url) => {
      // Remove all spaces from the URL
      const cleanUrl = url.replace(/\s+/g, '');
      return `](${cleanUrl})`;
    }
  );

  // Also fix standalone URLs (not in markdown links)
  result = result.replace(
    /(https?\s*:\s*\/\s*\/\S+)/g,
    (match) => {
      // Only fix if it has spaces that look like tokenization artifacts
      if (match.includes(' ')) {
        return match.replace(/\s+/g, '');
      }
      return match;
    }
  );

  // Fix bold markers: `** text **` → `**text**`
  result = result.replace(/\*\*\s+/g, '**');
  result = result.replace(/\s+\*\*/g, '**');

  // Fix underline bold: `__ text __` → `__text__`
  result = result.replace(/__\s+/g, '__');
  result = result.replace(/\s+__/g, '__');

  // Fix italic markers (single asterisk/underscore)
  // Be more careful here - only fix adjacent to word characters
  result = result.replace(/\*\s+(\w)/g, '*$1');
  result = result.replace(/(\w)\s+\*/g, '$1*');
  result = result.replace(/_\s+(\w)/g, '_$1');
  result = result.replace(/(\w)\s+_/g, '$1_');

  // Fix link brackets: `[ text ]` → `[text]`
  result = result.replace(/\[\s+/g, '[');
  result = result.replace(/\s+\]/g, ']');

  // Fix link URL formatting: `]( url )` → `](url)`
  result = result.replace(/\]\s*\(\s*/g, '](');
  result = result.replace(/\s+\)(?=\s|$|[.,!?;:])/g, ')');

  // Fix spaces before punctuation (common tokenization issue)
  // `word .` → `word.`
  result = result.replace(/\s+([.,!?;:)])/g, '$1');

  // Fix spaces after opening punctuation
  // `( word` → `(word`
  result = result.replace(/([(\[])\s+/g, '$1');

  // Fix heading markers: normalize multiple spaces
  result = result.replace(/^(#{1,6})\s{2,}/gm, '$1 ');

  // Fix list markers with extra spaces
  result = result.replace(/^(\s*)[-*+]\s{2,}/gm, '$1- ');
  result = result.replace(/^(\s*\d+\.)\s{2,}/gm, '$1 ');

  // Fix code block markers
  result = result.replace(/```\s+(\w)/g, '```$1');

  // Fix inline code
  result = result.replace(/`\s+/g, '`');
  result = result.replace(/\s+`/g, '`');

  // Fix contractions that got split: `'s` `'t` `'re` `'ve` `'ll` `'d`
  // `word 's` → `word's`
  result = result.replace(/(\w)\s+'([stdre]|ve|ll)\b/gi, "$1'$2");

  // Fix split words around hyphens: `non -citizens` → `non-citizens`
  result = result.replace(/(\w)\s+-\s*(\w)/g, '$1-$2');
  result = result.replace(/(\w)\s*-\s+(\w)/g, '$1-$2');

  return result;
}
