# Design System: Leadgen Pipeline

## 1. Visual theme
A 1970s print-poster ledger: maroon ink on beige stock, flat colour, hard unblurred shadows. Density is a balanced working tool. Motion is short and only shows a state change. One light theme, locked, so the palette never changes with system settings.

## 2. Colour roles
- **Beige Stock** (#EFE3CC): page background
- **Pale Beige** (#F8F0DF): inputs, panels, default buttons
- **Light Brown** (#D9BC94): table headers, panel shadows, passive detail
- **Brown Rule** (#8A6A45): input borders and row dividers
- **Maroon** (#6E1423, rail #5C1A1B): the rail, h1, gate bar, selected rows, sent messages
- **Rusty Red** (#9C3A18): primary buttons, h2, focus ring, page-head rule
- **Dark Ink** (#2B1210): body text

Maroon always marks where you are. Rusty red always marks what to do next.

## 3. Type levels
| Level | Font | Use |
|---|---|---|
| Display | Shrikhand | Page titles, large scores, funnel counts |
| Title | Righteous | Section titles, pipeline steps, list names |
| Subtitle | Syne, bold | Page intros, labels, buttons, table headers |
| Body | Bricolage Grotesque | Text and field values |
| Data | Space Mono | IDs, table numbers, band labels, timestamps |

Shrikhand and Righteous have one weight, so never apply bold to them.

## 4. Components
- **Buttons:** 2px maroon outline, 3px hard shadow. Pressing moves the button into its shadow. One primary rusty red action per area. 44px tall, 36px for small row actions.
- **Panels:** 2px maroon outline with a light brown hard shadow. Only for a working surface, not as decoration.
- **Inputs:** label above, 2px brown border, maroon on hover, rusty red focus ring.
- **Corners:** 10px everywhere. Band labels and only band labels are full pills.
- **Bands:** always show the word, never colour alone.

## 5. Layout
Maroon rail on the left, sticky rust-ruled page head, and a maroon gate bar at the end of each page. Everything collapses to one column below 860px with no sideways scrolling.

## 6. Motion
150 to 260ms ease-out on transform and opacity only. All of it switches off under reduced motion.

## 7. Banned
Blurred or glowing shadows, gradients, purple or blue, emoji, pure black, grey neutrals, and a new font or colour outside this file.
