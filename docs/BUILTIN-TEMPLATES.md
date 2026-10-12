# Built-in FX Templates

RetroStation FX v0.1.0 includes an immutable built-in broadcast graphics catalog.

Built-in templates are product content, not active Styles. Browsing or previewing a template does not create an ErsatzTV Script Graphics YAML file and does not require an ErsatzTV restart.

## Initial catalog

| Template | Family | Intent |
| --- | --- | --- |
| Classic Cable Lower Third | Classic cable/satellite | Restrained general-purpose NOW/NEXT lower third |
| 1980s Broadcast | 1980s broadcast | Hard-edged geometric character-generator-era presentation |
| 1990s Cable | 1990s cable network | Layered, energetic cable presentation |
| Digital Cable 2000 | Early-2000s digital cable | Polished translucent digital-cable treatment |
| Retro Local Station | Retro local station | Practical station-ID-oriented local television treatment |
| Saturday Morning | Cartoon / Saturday morning | Bright playful cartoon-block presentation |
| Movie Channel | Movie channel | Restrained cinematic title treatment |
| Sports Info Banner | Sports | Compact segmented sports-broadcast information banner |
| Modern Minimal | Modern minimal | Flat contemporary presentation with minimal ornamentation |

The designs are original RSFX broadcast-inspired treatments. They are not intended to reproduce a specific network's protected branding or graphics package.

## Workflow

1. Open the Template Library.
2. Select **Preview / use** on a built-in template.
3. RSFX loads the template values into the normal Style editor without creating a persistent Style.
4. Preview and adjust the Style settings.
5. Save the Style.
6. RSFX creates the normal reusable Style and, when YAML management is enabled, writes its managed ErsatzTV Script Graphics YAML.
7. Restart ErsatzTV when RSFX reports that a restart is required.

After a Style is created from a template, it is independent of the built-in template. Future changes to the shipped catalog do not rewrite the user's saved Style.

## Architecture

Built-in templates live outside the SQLite `styles` table and have stable string identifiers. The catalog supplies normal `StylePut` values to the editor. This keeps the template library read-only and prevents installation or catalog refresh from creating runtime graphics definitions.

The `Appearance.theme` property selects the visual composition used by both the browser preview and the Packet v1 renderer. Existing Styles that predate the template catalog default to `classic-cable`.

## v0.1.0 boundary

The initial release ships one baseline design for each template family. Additional variants such as Compact, Standard, Wide, title-card, or alternate lower-third arrangements can be added after live validation establishes which layouts deserve permanent catalog entries.

User-owned template cloning and saving are planned for a future release and are not included in v0.1.0.
