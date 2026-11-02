// Native production predicate contracts. Private nodes are never inserted
// into the shipped graph and are removed before ordinary AI resumes.
float ch_done, ch_checks, ch_failures;
void(string label, float ok) CoverHopCheck =
{
    ch_checks = ch_checks + 1;
    if (!ok) ch_failures = ch_failures + 1;
    dprint ("CHFIX check "); dprint (label); dprint (" ");
    dprint (ftos (ok != 0)); dprint ("\n");
};

void() CoverHopFixture =
{
    local entity a, b;
    if (ch_done || time < 2) return;
    ch_done = 1; a = spawn (); b = spawn ();
    a.origin = '0 0 24'; b.origin = '80 0 24';
    dprint ("BHVRPL begin cover_hop\nCHFIX begin dt_ms ");
    dprint (ftos (frametime * 1000)); dprint (" layout 1\n");
    CoverHopCheck ("missing_source", !Argus_CoverHopOK (world, b));
    CoverHopCheck ("missing_hop", !Argus_CoverHopOK (a, world));
    CoverHopCheck ("unlinked", !Argus_CoverHopOK (a, b));
    b.an_nlinks = 1; b.an_l0 = a;
    CoverHopCheck ("reverse_only", !Argus_CoverHopOK (a, b));
    a.an_nlinks = 1; a.an_l0 = b;
    CoverHopCheck ("ordinary_walk", Argus_CoverHopOK (a, b));
    a.an_jumpmask = 1;
    CoverHopCheck ("jump", !Argus_CoverHopOK (a, b)); a.an_jumpmask = 0;
    a.an_sprintmask = 1;
    CoverHopCheck ("sprint", !Argus_CoverHopOK (a, b)); a.an_sprintmask = 0;
    a.an_rjmask = 1;
    CoverHopCheck ("rocket", !Argus_CoverHopOK (a, b)); a.an_rjmask = 0;
    a.an_liftmask = 1;
    CoverHopCheck ("lift", !Argus_CoverHopOK (a, b)); a.an_liftmask = 0;
    a.an_swimmask = 1;
    CoverHopCheck ("swim", !Argus_CoverHopOK (a, b)); a.an_swimmask = 0;
    a.an_trainmask = 1;
    CoverHopCheck ("train", !Argus_CoverHopOK (a, b)); a.an_trainmask = 0;
    a.an_doormask = 1;
    CoverHopCheck ("door", !Argus_CoverHopOK (a, b)); a.an_doormask = 0;
    b.origin_z = 6;
    CoverHopCheck ("step_down", Argus_CoverHopOK (a, b));
    b.origin_z = 5;
    CoverHopCheck ("deliberate_drop", !Argus_CoverHopOK (a, b));
    b.origin_z = 56;
    CoverHopCheck ("ordinary_stairs", Argus_CoverHopOK (a, b));
    dprint ("CHFIX end checks "); dprint (ftos (ch_checks));
    dprint (" failures "); dprint (ftos (ch_failures)); dprint ("\n");
    remove (a); remove (b);
};
