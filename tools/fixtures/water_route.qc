// Private route-entry witness. Only initial placement/task is assigned;
// production AI, router and physics own every subsequent movement.
void() plat_go_down;
entity wr_bot, wr_goal, wr_first, wr_lastnode, wr_from, wr_to, wr_mid;
float wr_started, wr_done, wr_begin, wr_next, wr_frames, wr_handoffs;
float wr_previous, wr_dt, wr_case, wr_limit;
vector wr_seed, wr_target;

void() WaterRouteBefore =
{
    local entity b, saved;
    if (wr_previous > 0) wr_dt = time - wr_previous;
    wr_previous = time;
    if (wr_started || time < 2) return;
    wr_started = 1; wr_begin = time; wr_case = cvar ("scratch2");
    wr_limit = 18; if (wr_case == 8 || wr_case == 9) wr_limit = 30;
    if (mapname == "e1m5")
    {
        wr_seed = '-279 425 8'; wr_target = '-183 73 80';
        if (wr_case == 2) wr_seed = '-791 233 8';
        if (wr_case == 3)
        { wr_seed = '41 713 47'; wr_target = '-87 809 111'; }
        if (wr_case == 4)
        { wr_seed = '41 713 47'; wr_target = '20 889 104'; }
        if (wr_case == 5)
        { wr_seed = '20 889 105'; wr_target = '-87 809 111'; }
        if (wr_case == 6 || wr_case == 7)
        { wr_seed = '41 713 47'; wr_target = '-87 809 111'; }
        if (wr_case == 8) wr_target = '-535 1353 152';
        if (wr_case == 9) wr_target = '-87 809 111';
    }
    else if (mapname == "dm3")
    {
        wr_seed = '1093 -159 -336'; wr_target = '1349 545 -392';
    }
    else if (mapname == "e1m1" && (wr_case == 10 || wr_case == 11 || wr_case == 12))
    {
        wr_seed = '823.9 496 -257.9'; wr_target = '1201 961 -256';
        if (wr_case == 11 || wr_case == 12) { wr_seed = '810.5 505.1 -223.5'; wr_target = '689 481 104'; }
    }
    else { error ("WRFIX wrong map"); return; }
    b = argus_bots;
    while (b != world)
    {
        Argus_Nav_Abort (b);
        if (b.ar_slot == 0) wr_bot = b;
        else
        {
            b.health = 0; b.solid = SOLID_NOT; b.takedamage = DAMAGE_NO;
            b.movetype = MOVETYPE_NONE; b.nextthink = 0; b.think = SUB_Null;
            b.ar_respawntime = time + 3600;
        }
        b = b.ar_chain;
    }
    saved = self; self = wr_bot;
    RouteDecisionContracts ();
    Argus_BaseStats (); Argus_AvoidClear (); Argus_TacticReset ();
    setorigin (self, wr_seed); self.velocity = '0 0 0';
    self.flags = self.flags - (self.flags & FL_ONGROUND);
    self.angles = '0 0 0'; self.ar_moveyaw = 0;
    if (mapname == "e1m5" && wr_case == 5)
    { self.angles_y = 90; self.ar_moveyaw = 90; }
    self.ar_goal = world; self.ar_node = world; self.ar_pending = 1;
    self.ar_mode = 0; self.ar_enemy = world; self.ar_sndtime = 0;
    self.ar_hopjump = 0; self.ar_hoprj = 0; self.ar_hoplift = 0;
    self.ar_hopswim = 0; self.ar_hoptrain = 0; self.ar_hopdoor = 0;
    self.ar_jump = 0; self.ar_liftwait = 0; self.ar_tactic_settle = 0;
    self.ar_lastpos = self.origin; self.ar_nextstall = time + 2;
    self.ar_taskstart = time; self.ar_taskdeadline = time + 60;
    wr_goal = spawn (); wr_goal.classname = "argus_task_goal";
    wr_goal.flags = FL_ITEM; wr_goal.solid = SOLID_TRIGGER;
    setsize (wr_goal, '-8 -8 -8', '8 8 8'); setorigin (wr_goal, wr_target);
    self.ar_taskgoal = wr_goal; self.ar_goal = wr_goal;
    self.ar_laststart = world;
    self.ar_goalstart = time + 3600;
    // Resume the exact shipped lift action seen in the broader-map pin.
    // The observer never renews its flags or controls subsequent motion.
    if (wr_case == 11 || wr_case == 12)
    {
        b = find (world, classname, "argus_node");
        while (b != world)
        {
            if (vlen (b.origin - wr_target) < 1) self.ar_node = b;
            b = find (b, classname, "argus_node");
        }
        if (self.ar_node == world) { error ("WRFIX missing lift seat"); return; }
        self.ar_pending = 0; self.ar_mode = 2; self.ar_hoplift = 1;
        self.ar_liftstart = time; self.ar_boarded = 0;
        self.ar_moveyaw = 187; self.angles_y = 187;
        if (wr_case == 12)
        {
            b = find (world, classname, "plat");
            while (b != world && b.model != "*22") b = find (b, classname, "plat");
            if (b == world) { error ("WRFIX missing observed platform"); return; }
            // Initial raised slab; its normal three-second call cycle and
            // engine crushing/boarding physics own everything after setup.
            setorigin (b, b.pos1); b.velocity = '0 0 0'; b.state = STATE_TOP;
            b.think = plat_go_down; b.nextthink = b.ltime + 3;
        }

    }
    // Case 3 tests a candidate exit absent from the shipped graph. It is
    // added once before execution; it is never a prescribed movement path.
    if (mapname == "e1m5" && wr_case == 3)
    {
        b = find (world, classname, "argus_node");
        while (b != world)
        {
            if (vlen (b.origin - '41 713 7.2') < 1) wr_from = b;
            if (vlen (b.origin - wr_target) < 1) wr_to = b;
            b = find (b, classname, "argus_node");
        }
        if (wr_from == world || wr_to == world) { error ("WRFIX missing exit seats"); return; }
        Argus_NavLinkSwim (wr_from, wr_to);
    }
    if (mapname == "e1m5" && wr_case >= 4 && wr_case <= 6)
    {
        b = find (world, classname, "argus_node");
        while (b != world)
        {
            if (vlen (b.origin - '41 713 7.2') < 1) wr_from = b;
            if (vlen (b.origin - '-87 809 111') < 1) wr_to = b;
            b = find (b, classname, "argus_node");
        }
        if (wr_from == world || wr_to == world) { error ("WRFIX missing ramp seats"); return; }
        b = Argus_NavNode ('20 889 104');
        if (wr_case == 6)
        {
            wr_mid = Argus_NavNode ('20 841 80');
            Argus_NavLink (wr_from, wr_mid);
            Argus_NavLinkJump (wr_mid, b, 0);
        }
        else Argus_NavLink (wr_from, b);
        Argus_NavLinkJump (b, wr_to, 0);
    }
    dprint ("BHVRPL begin water_route\nWRFIX begin dt_ms ");
    dprint (ftos (wr_dt * 1000)); dprint (" layout 2 case "); dprint (ftos (wr_case)); dprint (" start ");
    dprint (vtos (wr_seed)); dprint (" goal "); dprint (vtos (wr_target)); dprint ("\n");
    self = saved;
};

void() WaterRouteAfter =
{
    local float completed, active;
    local vector displacement;
    if (!wr_started || wr_done) return;
    wr_frames = wr_frames + 1;
    if (wr_bot.ar_node != world)
    {
        if (wr_first == world)
        { wr_first = wr_bot.ar_laststart; wr_lastnode = wr_first; }
        if (wr_lastnode != world && wr_lastnode != wr_bot.ar_node)
            wr_handoffs = wr_handoffs + 1;
        wr_lastnode = wr_bot.ar_node;
    }
    completed = (vlen (wr_bot.origin - wr_target) < 48);
    if (wr_case == 11 || wr_case == 12)
    {
        displacement = wr_bot.origin - wr_seed; displacement_z = 0;
        completed = vlen (displacement) >= 64;
    }
    if (wr_case >= 3 && wr_case <= 9)
    {
        if (!(wr_bot.flags & FL_ONGROUND)) completed = 0;
        if (wr_bot.ar_feettype == CONTENT_WATER) completed = 0;
        if (fabs (wr_bot.origin_z - wr_target_z) > 18) completed = 0;
    }
    active = (wr_bot.ar_taskgoal == wr_goal && wr_bot.ar_goal == wr_goal);
    if (time >= wr_next)
    {
        wr_next = time + 0.5;
        dprint ("WRFIX sample t "); dprint (ftos (time - wr_begin));
        dprint (" pos "); dprint (vtos (wr_bot.origin));
        dprint (" node "); dprint (vtos (wr_bot.ar_node.origin));
        dprint (" grounded "); dprint (ftos ((wr_bot.flags & FL_ONGROUND) != 0));
        dprint (" wet "); dprint (ftos (wr_bot.ar_wetlevel));
        dprint (" feet "); dprint (ftos (wr_bot.ar_feettype));
        dprint (" handoffs "); dprint (ftos (wr_handoffs));
        dprint (" active "); dprint (ftos (active));
        dprint (" hp "); dprint (ftos (wr_bot.health));
        dprint (" frames "); dprint (ftos (wr_frames)); dprint ("\n");
#ifdef ROUTE_ACTION_COMPONENTS
        if (wr_case == 8 || wr_case == 10)
        {
            dprint ("AWATCH mode "); dprint (ftos (wr_bot.ar_mode));
            dprint (" jump "); dprint (ftos (wr_bot.ar_hopjump));
            dprint (" door "); dprint (wr_bot.ar_door.classname);
            dprint (" state "); dprint (ftos (wr_bot.ar_door.state));
            dprint (" target "); dprint (wr_bot.ar_door.targetname);
            dprint (" deadline "); dprint (ftos (wr_bot.ar_doortime));
            dprint (" lift "); dprint (ftos (wr_bot.ar_hoplift));
            dprint (" wait "); dprint (ftos (wr_bot.ar_liftwait));
            dprint (" train "); dprint (ftos (wr_bot.ar_hoptrain));
            dprint (" tactic "); dprint (ftos (wr_bot.ar_tactic));
            dprint (" gait "); dprint (ftos (wr_bot.ar_gaitpause));
            dprint (" enemy "); dprint (wr_bot.ar_enemy.netname);
            dprint (" clock "); dprint (ftos (wr_bot.ar_actiontime));
            dprint (" from "); dprint (vtos (wr_bot.ar_jumpfrom.origin));
            dprint ("\n");
        }
#endif

    }
    if (completed || time > wr_begin + wr_limit || wr_bot.health <= 0)
    {
        wr_done = 1;
        dprint ("WRFIX end completed "); dprint (ftos (completed));
        dprint (" seconds "); dprint (ftos (time - wr_begin));
        dprint (" handoffs "); dprint (ftos (wr_handoffs));
        dprint (" active "); dprint (ftos (active));
        dprint (" pos "); dprint (vtos (wr_bot.origin));
        dprint (" hp "); dprint (ftos (wr_bot.health));
        dprint (" frames "); dprint (ftos (wr_frames));
        dprint (" grounded "); dprint (ftos ((wr_bot.flags & FL_ONGROUND) != 0));
        dprint (" feet "); dprint (ftos (wr_bot.ar_feettype)); dprint ("\n");
        wr_bot.velocity = '0 0 0'; wr_bot.movetype = MOVETYPE_NONE;
        wr_bot.think = SUB_Null; wr_bot.nextthink = 0;
    }
};
