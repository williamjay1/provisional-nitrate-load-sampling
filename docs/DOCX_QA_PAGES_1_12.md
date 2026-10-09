# Final rendered manuscript pages 1–12

The root agent actually inspected every page 1–12 of `temp/render_v4` with native image viewing. The 36-page PDF is the rendering of the final Word document SHA256 `c8ccaf11fc7dae197c3f35c949e52d724e5bf047d7f1ca5922f9aba0bf1c11fc`.

The v3 inspection detected four empty-base superscript equation placeholders in the unit paragraph on page 3. They were changed to proper L⁻¹ and m³ characters, and page 3 was viewed again in v4: the placeholders are gone. The Caption template's inherited whole-paragraph bold formatting was removed; only figure numbers remain bold. The scientific text, values and source figures are unchanged by these presentation repairs.

Pages 1–5 contain readable body text and native equations without missing characters, overlapping baselines or clipped fractions. Pages 6–12 contain main Tables 1–3 and Figures 1–3: figures, external legends, captions, source units and interval panels are readable at the rendered size, with no text crossing a data line or image. Table 2 continues with a repeated header on page 10 and all its rows are preserved. Table 3 is fully visible on page 12. These are native Word tables; independent PDF/SVG companions also passed visual inspection and geometry checks. Page-number and line-number margins do not cross content.

**Status: PASS**, subject to the separate final page 13–24 and page 25–36 reports. All 834 native table cells, 61 native math objects and 11 inline figure relationships were also checked against the sources. Figures are separately supplied in genuine vector PDF/SVG and native 1200 dpi PNG; Word's inline raster is not asserted to be vector.

## Final v5 pagination repair

The released Word document is SHA256 `bf7ec274bb71df3460707d868803ec9886abc066361b232104b01e815a6049d2`, rendered in `temp/render_v5`. Table 2 is now kept together on page 10, with all its rows and source cells intact. The root agent actually viewed both changed final pages, 9 and 10: page 9 has the complete Figure 2 and its caption, and page 10 has the complete Table 2 followed by readable Results text. Neither page has clipping or text/line overlap. The earlier description of a continued Table 2 applies only to v4.

`FINAL_PAGE_INCREMENT_CHECK.json` compares all 36 rendered PNGs: only pages 9 and 10 changed, and all other pages are byte-identical to v4. Thus the actual v4 inspection of pages 1–8 and 11–12 applies to the released rendering without an inferred visual-equivalence shortcut. **Final pages 1–12: PASS.**

## Released v6 identity

A final bibliography-only repair on page 22 produced the released Word SHA256 `1c25b678cb115902cd7fbe8c9826e1e1371a5f0a9e6b6066e452d389cf339d0e`. `FINAL_RENDER_RELEASE_CHECK.json` shows that every page 1–12 is byte-identical to the inspected v5 rendering. The v5 hash above identifies the pagination repair stage; the v6 hash identifies the final delivery. **Released pages 1–12: PASS.**
