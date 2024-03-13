## 2.4.1

* Automatically remove empty `for` attribute in `<label>` element if it contains nested `<input>` or `<textarea>` element.

## 2.4.0

* Emmet just got better for JSX and Vue devs: use cleaner and shorter
  abbreviations to work with CSS modules and CSS-in-JS. For example, you can
  write `..my-class` abbreviation to get `<div styleName={styles['my-class']}>`.
  Read more in py-emmet v1.2.0 CHANGELOG: https://github.com/emmetio/py-emmet/blob/master/CHANGELOG.md#120-2023-01-19
  Feature discussion: https://github.com/emmetio/emmet/issues/589
* Fixed missing semicolon inside `@media` rule (#173)
* Support abbreviations inside `@supports (...) {}` query
* Removed extra spaces in CSS snippet output with parentheses in value (https://github.com/emmetio/emmet/issues/647).
* Added `script:module` HTML snippet.
* Added `g` (`gap`) CSS snippet, replaced `dc` with `display: contents` instead of invalid `display: compact`.

## 2.3.0

* Stability improvements in main Emmet package

## 2.2.0

* Expand abbreviations from multiple cursors.

## 2.1.0

* Introduce `known_snippets_only` option, which is enabled by default for HTML syntaxes. It allows to expand a single-word abbreviation only if it’s a known HTML tag, Emmet snippet or common component pattern.
* Improved unmatched CSS abbreviations handling: https://github.com/emmetio/sublime-text-plugin/issues/45


## 2.0.0

Final release of Emmet.

## v0.2.4

* Support TSX syntax.
* Minor tweaks and improvements in abbreviation activation scopes.

## v0.2.1

* Improved typing experience: detect unwanted abbreviations in some common cases.
* Improved error snippet for invalid abbreviation
* Disabled Emmet commenting by default

## v0.2.0

* Complete rewrite of abbreviation tracker (detect abbreviation as-you-type). It should be less annoying: display expanded preview only if abbreviation contains more than one element.
* Explicit Abbreviation Mode: run `Emmet: Enter Abbreviation Mode` to enter explicit abbreviation typing mode. Run this action in *any* syntax to enter abbreviation with real-time preview and validation. Hit <kbd>Enter</kbd> or <kbd>Tab</kbd> to expand abbreviation, <kbd>Esc</kbd> to clear entered abbreviation and exit mode.
* Moved preferences from `Preferences.sublime-settings` (global to Sublime Text) into `Emmet.sublime-settings` file.
* Syntax highlighting of HTML abbreviation preview.
