// Exercise the real movement guard at dm4's node 111.
float rf_done;

void(string label, float phase, float jump, float grounded, float yaw) RunupFloorCheck =
{
    self.ar_sprintstate = phase;
    self.ar_hopjump = jump;
    self.flags = 0;
    if (grounded)
        self.flags = FL_ONGROUND;
    dprint ("RFCHECK "); dprint (label); dprint (" ");
    dprint (ftos (Argus_MoveHazard (yaw, 48))); dprint ("\n");
};

void() RunupFloorFixture =
{
    local entity saved, actor;
    local vector ahead;
    if (rf_done || time < 2)
        return;
    if (mapname != "dm4" || !deathmatch)
        error ("run-up floor fixture requires dm4 deathmatch");
    rf_done = TRUE;
    saved = self;
    actor = spawn ();
    self = actor;
    self.movetype = MOVETYPE_STEP;
    self.solid = SOLID_SLIDEBOX;
    setsize (self, '-16 -16 -24', '16 16 32');
    setorigin (self, '849 -343 25');
    if (!droptofloor () || self.groundentity != world || fabs (self.origin_z - 24) > 1)
        error ("run-up floor fixture lost its seat");

    // The south-west step finds a dry floor 128 units below the deck.
    makevectors ('0 240 0');
    ahead = self.origin + v_forward * 48;
    traceline (ahead + '0 0 4', ahead - '0 0 280', TRUE, self);
    if (trace_fraction == 1 || trace_startsolid || trace_allsolid
        || fabs (trace_endpos_z + 128) > 1
        || pointcontents (trace_endpos + '0 0 2') != CONTENT_EMPTY)
        error ("run-up floor fixture lost its dry drop");

    dprint ("BHVRPL begin runup_floor\nRFCHECK begin dt_ms ");
    dprint (ftos (frametime * 1000)); dprint (" layout 1\n");
    RunupFloorCheck ("backstep", -1, 1, TRUE, 240);
    RunupFloorCheck ("lineup", 1, 1, TRUE, 240);
    RunupFloorCheck ("charge", 2, 1, TRUE, 240);
    RunupFloorCheck ("other_move", 1, 0, TRUE, 240);
    RunupFloorCheck ("in_air", 1, 1, FALSE, 240);
    RunupFloorCheck ("level_floor", 1, 1, TRUE, 90);
    dprint ("RFCHECK end\n");
    self = saved;
    remove (actor);
};
