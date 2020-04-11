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
