# Troubleshooting (symptom -> likely cause -> try)

| Symptom | Likely cause | Try |
|---|---|---|
| First layer does not stick / peels | dirty or wrong plate, bed too cool, Z offset | clean plate (IPA / water+soap), correct plate type in slicer, rerun auto calibration, add brim |
| Corners lift / warping | cooling too early, large flat part, draft | brim, door closed, higher bed temp for the material, round corners |
| Stringing / hairs | wet filament, nozzle too hot, retraction | dry filament, lower temp 5-10 C, check retraction, travel less |
| Rough or popping extrusion | moisture | dry the spool |
| Under-extrusion / gaps | partial clog, wet filament, too fast | cold-pull or replace nozzle, dry filament, slow volumetric speed |
| Layer shift | collision with curled part, belt/mechanical issue, too fast | slow down, check for tall curled edges, inspect belts and axes |
| Elephant foot | first layers squished | chamfer the bottom edge, first-layer compensation in slicer |
| Holes too small / parts do not fit | normal FDM shrink and over-extrusion | enlarge hole 0.1-0.2 mm, print a tolerance coupon |
| Weak parts along layers | layer-line weakness, low walls | orient so load is not across layers, more walls, hotter, dry filament |
| Poor overhangs | too steep, hot, little cooling | supports, orient differently, lower temp, more cooling (PLA) |
| Blob/zits at seam | seam placement | change seam position (aligned / back), tune pressure advance |
| Print stops / AMS error | tangle, jam, empty spool | clear path, check spool, retract by hand; check `bambu-x1 status` print_error |
| Chamber smells / fumes | ABS/ASA/PA/PC | ventilate the room; consider a different material indoors |

## Rule of thumb
Change one thing at a time and print a small test piece, not the full job. If a failure could burn something (clog heating, spaghetti against the hotend), stop the print rather than letting it finish.
