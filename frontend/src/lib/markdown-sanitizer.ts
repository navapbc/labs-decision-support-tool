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

  // Fix tokenization splits within words - be conservative to avoid joining real words
  // Only fix patterns that are clearly tokenization artifacts

  // Single uppercase letter followed by space and more uppercase (acronyms): `W IC` → `WIC`
  result = result.replace(/\b([A-Z])\s+([A-Z]+)\b/g, '$1$2');

  // Single uppercase followed by space and lowercase (word starts): `D ried` → `Dried`, `C anned` → `Canned`
  // But NOT after common words - only at start of sentence or after punctuation
  result = result.replace(/(^|[.!?:]\s*)([A-Z])\s+([a-z]{3,})/gm, '$1$2$3');

  // Fix specific common tokenization patterns (suffixes getting split)
  // `ort ified` → `ortified` (fragments before -ified, -tion, -ing, -ness, etc.)
  result = result.replace(/\b([a-z]{2,4})\s+(ified|tion|ing|ness|ment|able|ible)\b/g, '$1$2');

  // Fix word-internal splits where first fragment isn't a common word
  // Common 2-3 letter words to preserve: a, an, as, at, be, by, do, go, he, if, in, is, it, me, my, no, of, on, or, so, to, up, us, we
  // `Yog urt` → `Yogurt` - capital + lowercase fragment not in common words list
  const commonWords = /^(a|an|as|at|be|by|do|go|he|if|in|is|it|me|my|no|of|on|or|so|to|up|us|we|the|and|for|are|but|not|you|all|can|has|her|was|one|our|out|his|its)$/i;

  result = result.replace(/\b([A-Z][a-z]{1,2})\s+([a-z]{2,})\b/g, (match, p1, p2) => {
    // Only join if the first part isn't a common word
    if (commonWords.test(p1)) {
      return match; // Keep as-is
    }
    return p1 + p2;
  });

  return result;
}
