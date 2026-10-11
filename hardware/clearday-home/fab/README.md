# Review exports, not manufacturing files

The board is an **unrouted placement study**. Do not order it.

`placement-front.png` and `placement-back.png` are 2D KiCad layer renders.
The rear view is mirrored so it reads as a view from the back of the board.
`unrouted-review/` contains Gerber and drill exports only to check the export
pipeline and mechanical outline. These files contain unrouted copper pads and
provisional ground pours. They do not describe a working board.

See `../drc.rpt` for the actual violations. No DRC exclusions have been added.
Finish routing, review the antenna and mechanical clearances, resolve DRC,
choose a fabricator stackup, then regenerate and review fabrication outputs.
