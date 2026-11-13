# Design: "Faceplate + Bauhaus"

How the Recording Assistant looks and why. The values are in [`tokens.css`](tokens.css) (generated from
`assets/coach.html` by `scripts/export_tokens.py`). The list of every picture, with links to copy, is in
[`README.md`](README.md).

## Direction

The page is the front panel of a reel-to-reel recorder, the same object as the FlowGT Recorder app icon:

- a **brushed aluminium plate** with round screw bosses for the project list, the side panel and the transport;
- **cream paper** for what you read: the script, the project labels, the manual, a take;
- **dark glass** for what the machine reports: progress strip, level meter, timer, messages;
- **round, convex keys** in the manner of Braun (SK 4, ET 66) and Bang & Olufsen: lit from the top left, pressed
  in when held or chosen.

On top of that sits a Bauhaus layer: the circle, the square and the triangle, and the three primaries, each with
one job. It must never look like a generic admin template.

| Colour | Job | Where |
|---|---|---|
| Red `#E2452D` | records | the REC key (red convex button; while recording it turns white, rings red and pulses), the take lamp in the prompter, the triangle of "this segment's takes" |
| Yellow `#F2B705` | moves on | "next segment", the main key of a page ("open camera", "resume", "save"), a tool that is on, the current segment on the progress strip, the first step of the manual |
| Blue `#1F5FA8` (night `#6E9FDA`) | marks what is chosen | the lamp on the chosen key of a switch, the ring around the chosen project and the picked take, picked segments on the progress strip (pale blue: recorded, not picked yet), the square of "devices" |

Everything else is ink, paper, aluminium and glass.

## Rules

1. **No coloured stripe down the side of a card, notice or container.** Not on the left, not on any side. Group
   with spacing, a printed label, a hairline, a change of material (plate, paper, glass) or a geometric mark
   (circle, square, triangle). Gabriel rejected side stripes on 2026-11-13.
2. Red only for recording. Yellow only for "go on". Blue only for "chosen". A fourth accent needs a reason
   written here first.
3. Round shapes for keys: transport keys are circles (50 px, REC 76 px); text keys, switches and tools are pills;
   panels 22 px radius, cards 14 px, keys 12 px, read-out bars fully rounded. Nothing is square-cornered.
4. Status is a lamp, not a coloured box: a 9 to 12 px circle that is off (plate grey), green, amber or red, with
   a soft glow when lit.
5. Night is the same object in graphite: the plate turns dark, paper turns charcoal, keys stay light so they still
   read as keys. Both themes are designed, neither is an inversion.
6. The teleprompter stays black with its own colours: it is read through a mirror and must not follow the theme.
7. Every colour is a token. A rule never carries its own hex except the fixed materials (dial metal, glass glare).
8. Restyling never moves a control without a reason Gabriel gave. People record long sessions with this page; where
   things are is a habit.
9. One control, one place. The version switch (Chinese / English) lives only at the top right; the copy in the
   bottom bar is hidden.
10. Keys in a row share one key size and one caption line, so their tops and labels align to the pixel. A key
   without a shortcut still keeps the empty caption line.
11. A read-out has one layer. No track inside a track, no outline around a fill.

## Type

| Use | Font | Notes |
|---|---|---|
| UI and script | Inter, Helvetica Neue, PingFang SC, Microsoft YaHei UI, Segoe UI | script 30 to 54 px, weight 650; stressed syllables in `--gold` |
| Titles, labels, numbers | Futura, Avenir Next, Avenir, Century Gothic | section names, key captions, segment counter, timer, speed |
| Figures that change, paths | JetBrains Mono, SF Mono, Menlo, Consolas | `--font-mono`; tabular numbers |

Labels printed on the plate are 11 to 12.5 px, bold, letter-spaced 0.1 to 0.14 em, in `--plate-mut`.

## Space and shape

| Token | Value | Use |
|---|---|---|
| `--r-panel` | 22 px | plates: project list, script sheet, side panel, transport |
| `--r-card` | 14 px | paper: project label, manual, take, dialogs |
| `--r-key` | 12 px | text keys and selects (most are drawn as pills: 999 px) |
| margins | 8 / 12 / 14 / 16 / 24 px | panels sit 14 px from the window and from each other |
| `--side` | 340 px (300 / 270 / 240 on smaller screens) | side panel width |

## Components

| Component | How it looks |
|---|---|
| Panel | `--alu` brushed plate, 1 px `--plate-lo` edge, top highlight, soft drop shadow, four screw bosses on the large ones |
| Paper card | `--card`, 1 px `--line2`, small shadow; chosen = 2 px blue ring |
| Key | light gradient `--key-hi` to `--key`, 1 px `--key-edge`, bottom edge and shadow; pressed = `--key-down` with inset shadow |
| Round key | `--dial` (B&O aluminium: conic sheen plus concentric brushing), highlight at top left, 4 px plate ring |
| REC | red radial gradient, highlight at top left, 6 px plate ring; recording: white face, red ring, pulsing glow (off with reduced motion) |
| Next / main key | Braun yellow radial gradient, ink text |
| Switch | rounded slot (`--well`, inset), 36 px high like the project select, holding pill keys; the chosen pill stands up with a blue lamp |
| Tool | the same round 50 px dial key as back and forward, with the name and key cap on the caption line under it; on = the key turns yellow. Tools sit on the transport row and align with it |
| Top bar | three parts on a grid: back to the list (with the icon) on the left, the project name centred, the version switch and the theme key on the right |
| Progress strip | one row of pills straight on the housing, one per segment: grey = not recorded, pale blue = recorded, blue = picked; the current one is yellow, taller and carries its number (CSS counter). Click a pill to go there |
| Section | printed name with a circle, square or triangle before it, hairline above, chevron at the end |
| Glass | `--glass`, inset shadow; contents in `--glass-fg`; level meter as a row of round lamps, warm near the top, red at clipping |
| Message | glass card with 24 px corners and a plate ring around it |
| Key cap | `<kbd>`: small off-white cap, mono 11 px |

## Screens

Designed for Mac and Windows laptops up to 1920 px wide and iPad in both orientations. Below 1060 px the tool keys
keep only the key and its key cap (the caption line stays); below 700 px the layout stacks. Phones are not a target.

## Origin

The icon and the plate, glass and paper materials come from FlowGT Recorder (Gabriel's own brand). The Bauhaus
layer was added on 2026-11-13 after the first faceplate was judged too square.

## 中文速览

- **方向：** 磁带机前面板 + 包豪斯。面板是拉丝铝，稿子和卡片是奶白纸，读数是深色玻璃，按键是 Braun、B&O 式的圆形立体键。
- **三原色各管一件事：** 红色是录制，黄色是往前走（下一段、主按钮），蓝色表示选中。
- **硬规矩：** 卡片、提示框、主容器都**不加侧边彩色竖条**。分组用小标题、细线、材质，或圆、方、三角。
- **一处一个：** 中/英切换只在右上角；顶栏左边返回总目录、中间项目名、右边版本和主题。
- **进度条只有一层：** 灰色是没录，浅蓝是录过，蓝色是已选，当前段是黄色、更高、带段号。
- **一排键一样大：** 右下角工具键和上一段、下一段一样是圆键，名字在键下面，没有快捷键的也留一行。
- **形状：** 走带键是圆的；开关和工具键是胶囊形；面板圆角 22，卡片 14，按键 12。
- **字体：** 正文 Inter / 苹方；标题、标签、数字用 Futura / Avenir；会变的数字和路径用等宽字体。
- **白天、黑夜两套都是设计出来的，不是反色。** 提词器始终黑底，不跟主题。
