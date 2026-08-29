"""A forward instrument model: a known distribution to a reported moment.

WHAT THIS IS FOR. Every fixture in this repository so far was written by
the author of the checks it exercises, and WO-3 measured what that costs
-- a case-sensitive enumeration admitted eight derived quantities as
`measured`, and no amount of testing against the first fixture could have
found it. A forward model is a different kind of fixture: the ground
truth is a mathematical object rather than an author's belief, and the
reported values are produced by a modelled instrument rather than typed
in.

WHY A CLEAN SIMULATOR WOULD BE WORTHLESS. Conventional GPC software
computes Mn and Mw from concentration and slice area, because molecule
counts are not measurable that way. So the generating distribution and
the software's estimator are DIFFERENT MATHEMATICAL OBJECTS, and the
report is not the truth even when every stage works correctly. That
discrepancy is the product. If reported equalled true, this would teach
nothing the closed-form moments do not already state.

WHAT IT IS NOT. Not a chromatography package -- SEC is the simple mode
and a general-rate solver is heavy machinery for a polynomial. Not a
dependency on any external simulator. Not a source of `measured`
evidence: everything it emits that could reach a pool is a FIXTURE
labelled fabricated, and the truth record never reaches a pool at all.

LAYER RULE. Nothing in the product may import this package. It is a
fixture generator, and a product path that could reach it is ground truth
leaking into the measurement. Enforced in
tests/test_forward_instrument_model.py.
"""
