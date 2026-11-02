// Private state contracts through the actual mover observer functions.
// These prescribed states do not claim physical landings or gameplay parity.
float mp_done, mp_rows;
string mp_label;
entity mp_actor, mp_marker, mp_alternate, mp_node;

void(float family, float retained, float dry, float lost) MoverPredicateWitness =
{
    mp_rows = mp_rows + 1;
    dprint ("MVPRED ");
    if (family == 0) dprint ("transfer "); else dprint ("forecast ");
    dprint (mp_label);
    dprint (" retained "); dprint (ftos (retained));
    dprint (" dry "); dprint (ftos (dry));
    dprint (" lost "); dprint (ftos (lost)); dprint ("\n");
};

void(float family, string label, float taskmatch, float goalmatch, float nodematch, float wet, float feet) MoverPredicateCase =
{
    mp_label = label;
    mp_actor.ar_taskgoal = mp_alternate;
    if (taskmatch) mp_actor.ar_taskgoal = mp_marker;
    mp_actor.ar_goal = mp_alternate;
    if (goalmatch) mp_actor.ar_goal = mp_marker;
    mp_actor.ar_node = world;
    if (nodematch) mp_actor.ar_node = mp_node;
    mp_actor.ar_wetlevel = wet; mp_actor.ar_feettype = feet;
    if (family == 0)
    {
        mv_started = 1; mv_done = 0; mv_when = time;
        mv_bot = mp_actor; mv_marker = mp_marker;
        mv_exit = '1000 1000 1000'; mv_landed = 0; mv_lost = 0;
        mv_nextsample = time + 1000;
        mp_actor.flags = 0;
        MoverTransferAfter ();
    }
    else
    {
        mc_bot = mp_actor; mc_goal = mp_marker; mc_node = mp_node;
        mc_lost = 0; mc_wet = 0; mc_dry = 0; mc_floor = 0;
        mp_actor.flags = FL_ONGROUND;
        MoverForecastObserve ();
        dprint ("MPLATCH "); dprint (label);
        dprint (" dry "); dprint (ftos (mc_dry));
        dprint (" lost "); dprint (ftos (mc_lost)); dprint ("\n");
    }
};

void() MoverPredicateFixture =
{
    local entity ent;
    local float family, before, after;
    if (mp_done || time < 2) return;
    mp_done = 1;
    dprint ("BHVRPL begin mover_predicates\nMPP begin dt_ms ");
    dprint (ftos (frametime * 1000)); dprint (" layout 1\n");
    ent = nextent (world);
    while (ent != world) { before = before + 1; ent = nextent (ent); }
    mp_actor = spawn (); mp_actor.classname = "predicate_fixture";
    mp_actor.health = 100;
    mp_marker = spawn (); mp_alternate = spawn (); mp_node = spawn ();
    family = 0;
    while (family < 2)
    {
        MoverPredicateCase (family, "owned", 1, 1, 1, 0, CONTENT_EMPTY);
        MoverPredicateCase (family, "missing_task", 0, 1, 1, 0, CONTENT_EMPTY);
        MoverPredicateCase (family, "missing_goal", 1, 0, 1, 0, CONTENT_EMPTY);
        MoverPredicateCase (family, "neither", 0, 0, 1, 0, CONTENT_EMPTY);
        if (family) MoverPredicateCase (family, "missing_node", 1, 1, 0, 0, CONTENT_EMPTY);
        MoverPredicateCase (family, "water_feet", 1, 1, 1, 0, CONTENT_WATER);
        MoverPredicateCase (family, "lava_feet", 1, 1, 1, 0, CONTENT_LAVA);
        MoverPredicateCase (family, "slime_feet", 1, 1, 1, 0, CONTENT_SLIME);
        MoverPredicateCase (family, "wet_body", 1, 1, 1, 2, CONTENT_EMPTY);
        family = family + 1;
    }
    remove (mp_actor); remove (mp_marker); remove (mp_alternate); remove (mp_node);
    mv_bot = world; mv_marker = world; mv_done = 1;
    mc_bot = world; mc_goal = world; mc_node = world; mc_done = 1;
    ent = nextent (world);
    while (ent != world) { after = after + 1; ent = nextent (ent); }
    dprint ("MPP end rows "); dprint (ftos (mp_rows));
    dprint (" cleanup "); dprint (ftos (before == after)); dprint ("\n");
};
