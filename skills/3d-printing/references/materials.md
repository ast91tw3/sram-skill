# Materials for the X1C (typical values; confirm on the filament's own datasheet)

| Material | Use | Nozzle C | Bed C | Notes |
|---|---|---|---|---|
| PLA | prototypes, visual models | 190-230 | 35-60 | easiest; softens near 55-60 C, avoid hot cars/enclosures |
| PETG | tougher, some chemical resistance | 230-260 | 70-80 | stringing; AMS fine if dry |
| ABS / ASA | heat-resistant, outdoor (ASA) | 240-270 | 90-100 | needs closed door, ventilation, warps; keep out of living space |
| TPU | flexible parts | 220-240 | 30-45 | slow; use the external spool unless the filament is rated for AMS (check the spool) |
| PA / PC (nylon / polycarbonate) | strong, hot parts | 260-300 | 90-110 | must be dry, hardened nozzle advisable, warps heavily |
| CF / GF filled | stiff parts | per base | per base | **abrasive: hardened-steel nozzle required**, dry, ventilate |

## Drying
Hygroscopic: nylon, PETG, TPU, PC, and most filled filaments. Wet filament causes stringing, popping sounds, rough surface, weak parts. Dry per the manufacturer (often 4-12 h at 45-80 C depending on material).

## AMS notes
- Use Bambu-profiled spools where possible; RFID tags set the profile and remaining %.
- Third-party spools report remaining -1 (unknown) in `bambu-x1 status`; that is not "empty".
- Brittle, abrasive or very flexible filament can jam the AMS path; feed those from the external spool.
- Different materials in one print need compatible bed/nozzle temperatures and a purge tower.

## Choosing quickly
Fit check or looks: PLA. Needs to survive heat or outdoors: ASA. Needs some flex or impact: PETG or TPU. Needs real stiffness at heat: PA-CF / PC, only with the right nozzle and dry filament.
