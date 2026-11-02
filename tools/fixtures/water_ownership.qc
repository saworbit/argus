// Private language/observer regression. Call the actual WaterRouteAfter
// observer with each combination of task and current-goal identity.
float wo_done;

void(string label, entity task, entity goal) WaterOwnershipCase =
{
    wr_bot.ar_taskgoal = task; wr_bot.ar_goal = goal; wr_next = 0;
    dprint ("WRID case "); dprint (label); dprint ("\n");
    WaterRouteAfter ();
};

void() WaterOwnershipFixture =
{
    local entity alternate, ent;
    local float before, after;
    if (wo_done || time < 2) return;
    wo_done = 1;
    dprint ("BHVRPL begin water_ownership\nWRID begin dt_ms ");
    dprint (ftos (frametime * 1000)); dprint (" layout 1\n");
    ent = nextent (world);
    while (ent != world) { before = before + 1; ent = nextent (ent); }
    wr_bot = spawn (); wr_bot.classname = "ownership_fixture"; wr_bot.health = 100;
    wr_goal = spawn (); wr_goal.classname = "argus_task_goal";
    alternate = spawn (); alternate.classname = "alternate_goal";
    wr_started = 1; wr_done = 0; wr_begin = time; wr_limit = 100;
    wr_target = '1000 1000 1000'; wr_frames = 0; wr_handoffs = 0;
    WaterOwnershipCase ("owned", wr_goal, wr_goal);
    WaterOwnershipCase ("task_only", wr_goal, alternate);
    WaterOwnershipCase ("goal_only", alternate, wr_goal);
    WaterOwnershipCase ("neither", alternate, alternate);
    remove (wr_bot); remove (wr_goal); remove (alternate);
    wr_bot = world; wr_goal = world; wr_done = 1;
    ent = nextent (world);
    while (ent != world) { after = after + 1; ent = nextent (ent); }
    dprint ("WRID end cases 4 cleanup "); dprint (ftos (before == after)); dprint ("\n");
};
