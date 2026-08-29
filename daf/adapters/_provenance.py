"""The acquisition-provenance vocabulary, shared by every adapter.

WHY IT MOVED HERE. It was defined in `daf.adapters.gpc_report`, and the
second GPC source needed it. Importing it from there would have made one
adapter depend on another -- and two adapters that drifted is a
detectable state, while one adapter reaching into another is a coupling
nothing reports. Factored into a module neither owns.

AND THE SECOND SOURCE MOVED WHERE IT COMES FROM. `gpc_report` reads
`data_provenance` from the DOCUMENT, because that fixture was written to
carry it. A real vendor SEC export does not: no chromatography software
writes a field saying whether its own output is fabricated. Provenance is
a property of the ACQUISITION -- of who ran what against which file --
not of the document, and the first adapter conflated the two because its
document was written by the same author as its adapter.

So this vocabulary is supplied by the CALLER for sources that cannot
declare it, and read from the document for sources that do. Neither is
defaulted: an adapter that cannot obtain it refuses.
"""

from __future__ import annotations

#: A closed vocabulary on purpose. `fabricated_fixture` is not a hedge --
#: it is the only honest label for every GPC payload this repository can
#: currently produce, and it must be as declarable as the other one.
INSTRUMENT_MEASUREMENT = "instrument_measurement"
FABRICATED_FIXTURE = "fabricated_fixture"
DATA_PROVENANCE_KINDS = (INSTRUMENT_MEASUREMENT, FABRICATED_FIXTURE)
