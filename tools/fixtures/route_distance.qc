// Private routing contract. Synthetic links exercise production search code;
// no model of its algorithm supplies the expected result.
float rd_done, rd_checks, rd_failures;
float rd_lastframe, rd_dt;
entity rd_bot, rd_goal;

void(string label, float ok) RouteDistanceCheck =
{
    rd_checks = rd_checks + 1;
    if (!ok) rd_failures = rd_failures + 1;
    dprint ("RDFIX check "); dprint (label); dprint (" ");
    dprint (ftos (ok)); dprint ("\n");
};

void(entity start, entity goal) RouteDistanceRun =
{
    local float frames;
    Argus_Nav_Abort (rd_bot);
    rd_bot.ar_goal = rd_goal;
    rd_bot.ar_routefail = 0;
    rd_bot.ar_pending = 1;
    Argus_Route_Start (rd_bot, start, goal);
    frames = 0;
    while (an_busy && frames < 64)
    {
        Argus_Nav_Frame ();
        frames = frames + 1;
    }
    RouteDistanceCheck ("settles", !an_busy && frames < 64);
};

void() RouteDistanceFixture =
{
    local entity s, a, b, c, g, h, missing, saved, bot;
    local float budget, frames;
    if (rd_done) return;
    if (rd_lastframe > 0) rd_dt = time - rd_lastframe;
    rd_lastframe = time;
    if (time < 2) return; // map warmup executes StartFrame before live ticks
    rd_done = 1;
    dprint ("BHVRPL begin route_distance\nRDFIX begin dt_ms ");
    dprint (ftos (rd_dt * 1000)); dprint ("\n");
    bot = argus_bots;
    while (bot != world)
    {
        Argus_Nav_Abort (bot);
        bot.cam_active = 1; bot.solid = SOLID_NOT;
        bot = bot.ar_chain;
    }
    Argus_AvoidClear ();
    rd_bot = spawn (); rd_bot.health = 100; rd_bot.ar_skill = 2;
    rd_bot.ar_slot = 0; rd_bot.netname = "routefixture";
    rd_goal = spawn (); rd_goal.solid = SOLID_TRIGGER;
    saved = self; self = rd_bot;
    budget = ANQ_POPS; ANQ_POPS = 1;
    s = Argus_NavNode ('0 0 0');
    a = Argus_NavNode ('0 400 0');
    b = Argus_NavNode ('100 0 0');
    c = Argus_NavNode ('200 0 0');
    g = Argus_NavNode ('300 0 0');
    h = Argus_NavNode ('400 0 0');
    missing = Argus_NavNode ('500 0 0');
    Argus_NavLink (s, a); Argus_NavLink (s, b);
    Argus_NavLink (a, g); Argus_NavLink (b, c);
    Argus_NavLink (g, h); Argus_NavLink (c, g);
    Argus_NavLink (h, b); // a positive cycle cannot improve its ancestors
    RouteDistanceRun (s, h);
    RouteDistanceCheck ("fewest_hops_first", fabs (h.an_dist - 1000) < 0.1);
    RouteDistanceCheck ("first_parent", h.an_par == g && g.an_par == a);
    RouteDistanceCheck ("step_discipline", Argus_GetNext (s, rd_bot) == a);
    RouteDistanceCheck ("route_chain", Argus_GetNext (a, rd_bot) == g
        && Argus_GetNext (g, rd_bot) == h
        && Argus_GetNext (h, rd_bot) == world);
    RouteDistanceCheck ("no_parent_cycle", b.an_par == s && s.an_par == world);
    RouteDistanceCheck ("route_ownership", rd_bot.ar_node == s && !rd_bot.ar_pending);
    // Equal step count: A discovers G first; B must improve that queued
    // node before its cheaper distance propagates to the descendant H.
    Argus_NavLink (b, g);
    RouteDistanceRun (s, h);
    RouteDistanceCheck ("equal_hops_shorter", fabs (h.an_dist - 400) < 0.1);
    RouteDistanceCheck ("equal_hops_branch", Argus_GetNext (s, rd_bot) == b);
    RouteDistanceCheck ("descendant_distance", h.an_par == g && g.an_par == b);
    // Improve a node while it is still queued; it must not be appended twice.
    Argus_NavLink (a, c);
    RouteDistanceRun (s, h);
    RouteDistanceCheck ("pending_improvement", fabs (c.an_dist - 200) < 0.1);
    RouteDistanceCheck ("queue_drained", anq_head == world && anq_tail == world);
    RouteDistanceRun (s, missing);
    RouteDistanceCheck ("unreachable", rd_bot.ar_routefail && !rd_bot.ar_pending);
    // Reused stamps and an aborted queue must not retain the previous root.
    Argus_Route_Start (rd_bot, s, h);
    Argus_Nav_Frame ();
    RouteDistanceCheck ("frame_budget", an_busy && anq_head != world);
    Argus_Nav_Abort (rd_bot);
    RouteDistanceRun (b, h);
    RouteDistanceCheck ("abort_and_new_root", fabs (h.an_dist - 300) < 0.1
        && b.an_par == world && rd_bot.ar_node == b);
    // Equipment and skill gates continue to constrain the cheaper branch.
    s.an_nlinks = 0; a.an_nlinks = 0;
    Argus_NavLink (b, h);
    Argus_NavLinkRocket (s, b); Argus_NavLink (s, a);
    Argus_NavLink (a, h);
    RouteDistanceRun (s, h);
    RouteDistanceCheck ("rocket_toll", Argus_GetNext (s, rd_bot) == a);
    s.an_rjmask = 0; s.an_sprintmask = 1; rd_bot.ar_skill = 1;
    RouteDistanceRun (s, h);
    RouteDistanceCheck ("sprint_toll", Argus_GetNext (s, rd_bot) == a);
    rd_bot.ar_skill = 2;
    RouteDistanceRun (s, h);
    RouteDistanceCheck ("sprint_permitted", Argus_GetNext (s, rd_bot) == b);
    s.an_sprintmask = 0; s.an_jumpmask = 1;
    setorigin (b, '100 0 100');
    RouteDistanceRun (s, h);
    RouteDistanceCheck ("jump_apex_toll", Argus_GetNext (s, rd_bot) == a);
    s.an_jumpmask = 0; setorigin (b, '100 0 0');
    // Shopping must also improve a queued alternative, rather than passing
    // only because the cheaper branch happened to be inserted first.
    s.an_nlinks = 0; Argus_NavLink (s, a); Argus_NavLink (s, b);
    Argus_Shop_Start (rd_bot, s);
    rd_bot.ar_goal = world;
    frames = 0;
    while (an_busy && frames < 64)
    {
        Argus_Nav_Frame ();
        frames = frames + 1;
    }
    RouteDistanceCheck ("shopping_distance", h.an_mark == an_gen
        && fabs (h.an_dist - 400) < 0.1);
    RouteDistanceCheck ("shopping_cleanup", !an_busy && !an_shopready
        && !rd_bot.ar_shopping && frames < 64);
    ANQ_POPS = budget;
    Argus_Nav_Abort (rd_bot);
    self = saved;
    dprint ("RDFIX end checks "); dprint (ftos (rd_checks));
    dprint (" failures "); dprint (ftos (rd_failures)); dprint ("\n");
};
