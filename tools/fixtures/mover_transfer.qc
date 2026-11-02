// Private transfer task: production AI/physics owns every movement after
// placement. The checkpoint is dry static floor on the continuing route,
// not a goal-selection event or a claim that the later prize was picked up.
float mv_started, mv_done, mv_when, mv_previous_time, mv_dt;
float mv_nextsample;
float mv_frames, mv_generation, mv_step, mv_exit_consumed;
float mv_boarded, mv_launches, mv_badlaunch, mv_completed, mv_landed, mv_lost;
entity mv_bot, mv_marker, mv_mover, mv_exitnode, mv_successor;
vector mv_start, mv_goal, mv_exit;

// Read-only callbacks surround the production arrival assignment in the
// private source. Slot zero's generation-stamped route cache is the plan.
void(entity consumed) MoverTransferWillConsume =
{
    if (!mv_started || mv_done || self != mv_bot || consumed != mv_exitnode) return;
    mv_step = mv_step + 1; mv_exit_consumed = 0;
    mv_successor = world; mv_generation = self.ar_routegen;
    if (self.ar_slot == 0 && consumed.an_ng0 == self.ar_routegen)
        mv_successor = consumed.an_next0;
    dprint ("MVFIX expect step "); dprint (ftos (mv_step));
    dprint (" generation "); dprint (ftos (mv_generation));
    dprint (" from "); dprint (vtos (consumed.origin));
    dprint (" to "); dprint (vtos (mv_successor.origin)); dprint ("\n");
};

void(entity consumed, entity successor) MoverTransferConsumed =
{
    if (!mv_started || mv_done || self != mv_bot || consumed != mv_exitnode) return;
    mv_exit_consumed = (mv_successor != world && successor == mv_successor
        && self.ar_node == successor && self.ar_routegen == mv_generation
        && self.ar_goal == mv_marker && self.ar_taskgoal == mv_marker);
    dprint ("MVFIX consumed step "); dprint (ftos (mv_step));
    dprint (" generation "); dprint (ftos (self.ar_routegen));
    dprint (" from "); dprint (vtos (consumed.origin));
    dprint (" to "); dprint (vtos (successor.origin));
    dprint (" accepted "); dprint (ftos (mv_exit_consumed)); dprint ("\n");
};

float(entity bot) MoverTransferHandoffOK =
{
    return (mv_exit_consumed && mv_successor != world && bot.ar_node == mv_successor
        && bot.ar_routegen == mv_generation && bot.ar_goal == mv_marker
        && bot.ar_taskgoal == mv_marker && !mv_lost);
};

void() MoverTransferBefore =
{
    local entity b, saved, probe_expected, probe_wrong;
    if (mv_previous_time > 0) mv_dt = time - mv_previous_time;
    mv_previous_time = time;
    if (mv_started || time < 2) return;
    mv_started = 1; mv_when = time;
    if (mapname == "e1m6")
    {
        mv_start = '625 1425 24'; mv_exit = '529 1393 344';
        mv_goal = '433 1297 208';
    }
    else
    {
        mv_start = '485 929 40'; mv_exit = '517 801 216';
        mv_goal = '517 673 216';
    }
    b = argus_bots;
    while (b != world)
    {
        Argus_Nav_Abort (b);
        if (b.ar_slot == 0) mv_bot = b;
        else
        {
            b.health = 0; b.solid = SOLID_NOT; b.takedamage = DAMAGE_NO;
            b.movetype = MOVETYPE_NONE; b.nextthink = 0; b.think = SUB_Null;
            b.ar_respawntime = time + 3600;
        }
        b = b.ar_chain;
    }
    saved = self; self = mv_bot; Argus_BaseStats ();
    setorigin (self, mv_start); self.velocity = '0 0 0';
    self.angles = '0 0 0'; self.ar_moveyaw = 0; self.ar_jump = 0;
    self.ar_lastpos = self.origin; self.ar_nextstall = time + 2;
    self.ar_enemy = world; self.ar_node = world; self.ar_pending = 1; self.ar_mode = 0;
    self.ar_hoplift = 0; self.ar_hopjump = 0; self.ar_hoprj = 0; self.ar_hoptrain = 0;
    self.ar_hopswim = 0; self.ar_hopdoor = 0; self.ar_sprintstate = 0;
    self.ar_taskstart = time; self.ar_taskdeadline = time + 60;
    mv_marker = spawn (); mv_marker.classname = "argus_task_goal";
    mv_marker.solid = SOLID_TRIGGER; mv_marker.flags = FL_ITEM;
    setsize (mv_marker, '-8 -8 -8', '8 8 8'); setorigin (mv_marker, mv_goal);
    self.ar_taskgoal = mv_marker; self.ar_goal = mv_marker;
    self.ar_goalstart = time + 3600;
    mv_exitnode = Argus_NearestNode (mv_exit);
    if (mv_exitnode == world || vlen (mv_exitnode.origin - mv_exit) > 1)
        error ("MVFIX exit layout changed");
    // Oracle-only controls run during setup, then restore the task before
    // production owns movement. Neither node is added to the real graph.
    probe_expected = spawn (); probe_wrong = spawn ();
    probe_expected.origin = mv_exit + '64 0 0';
    probe_wrong.origin = mv_exit + '128 0 0';
    mv_successor = probe_expected; mv_generation = self.ar_routegen;
    mv_exit_consumed = 1;
    self.ar_node = probe_wrong;
    dprint ("MVFIX oracle different_node accepted ");
    dprint (ftos (MoverTransferHandoffOK (self))); dprint ("\n");
    self.ar_node = probe_expected; mv_exit_consumed = 0;
    dprint ("MVFIX oracle expected_without_consumption accepted ");
    dprint (ftos (MoverTransferHandoffOK (self))); dprint ("\n");
    self.ar_node = world; mv_successor = world; mv_generation = 0;
    remove (probe_expected); remove (probe_wrong);
    dprint ("BHVRPL begin mover_transfer\n");
    dprint ("MVFIX begin dt_ms "); dprint (ftos (mv_dt * 1000));
    dprint (" layout 3 exit "); dprint (vtos (mv_exit)); dprint ("\n");
    self = saved;
};

void() MoverTransferAfter =
{
    local vector to, launch_velocity;
    local float retained, dry;
    if (!mv_started || mv_done) return;
    mv_frames = mv_frames + 1;
    if (mv_bot.groundentity.classname == "plat" && (mv_bot.flags & FL_ONGROUND))
    {
        mv_boarded = 1; mv_mover = mv_bot.groundentity;
    }
    if (mv_boarded && mv_bot.groundentity == mv_mover
        && mv_bot.ar_hopair && mv_bot.velocity_z == AR_JUMPVEL)
    {
        mv_launches = mv_launches + 1;
        launch_velocity = mv_bot.velocity; launch_velocity_z = 0;
        if (mv_mover.state != STATE_TOP || vlen (launch_velocity) > 330) mv_badlaunch = 1;
    }
    to = mv_bot.origin - mv_exit; to_z = 0;
    retained = (mv_bot.ar_goal == mv_marker && mv_bot.ar_taskgoal == mv_marker);
    if (!retained) mv_lost = 1;
    dry = (mv_bot.ar_wetlevel == 0 && mv_bot.ar_feettype != CONTENT_WATER
        && mv_bot.ar_feettype != CONTENT_LAVA
        && mv_bot.ar_feettype != CONTENT_SLIME);
    if (!mv_landed && mv_boarded && retained && dry && mv_bot.health > 0
        && (mv_bot.flags & FL_ONGROUND) && mv_bot.groundentity == world
        && fabs (mv_bot.origin_z - mv_exit_z) <= 18 && vlen (to) < 96)
    {
        mv_landed = 1;
        dprint ("MVFIX landed pos "); dprint (vtos (mv_bot.origin));
        dprint (" world "); dprint (ftos (mv_bot.groundentity == world));
        dprint (" floor "); dprint (ftos ((mv_bot.flags & FL_ONGROUND) != 0));
        dprint (" dry "); dprint (ftos (dry));
        dprint (" retained "); dprint (ftos (retained)); dprint ("\n");
    }
    // A landing beside the node is insufficient: the controller must accept
    // the exit and install the continuing route without replacing its goal.
    mv_completed = (mv_landed && !mv_lost && retained && dry && mv_bot.health > 0
        && MoverTransferHandoffOK (mv_bot));
    if (time >= mv_nextsample)
    {
        mv_nextsample = time + 0.5;
        dprint ("MTRACE t "); dprint (ftos(time - mv_when));
        dprint (" pos "); dprint (vtos(mv_bot.origin));
        dprint (" node "); dprint (vtos(mv_bot.ar_node.origin));
        dprint (" mode "); dprint (ftos(mv_bot.ar_mode));
        dprint (" lift "); dprint (ftos(mv_bot.ar_hoplift));
        dprint (" wait "); dprint (ftos(mv_bot.ar_liftwait));
        dprint (" ground "); dprint (mv_bot.groundentity.classname);
        dprint (" floor "); dprint (ftos((mv_bot.flags & FL_ONGROUND) != 0));
        dprint (" state "); dprint (ftos(mv_mover.state));
        dprint (" mz "); dprint (ftos(mv_mover.absmax_z));
        dprint (" velocity "); dprint (vtos(mv_bot.velocity));
        dprint (" budget "); dprint (ftos(mv_bot.ar_actiontime));
        dprint (" best "); dprint (ftos(mv_bot.ar_actionbest));
        dprint (" retained "); dprint (ftos(retained)); dprint ("\n");
    }
    if (mv_completed || time > mv_when + 18 || mv_bot.health <= 0)
    {
        mv_done = 1;
        dprint ("MVFIX result completed "); dprint (ftos (mv_completed));
        dprint (" seconds "); dprint (ftos (time - mv_when));
        dprint (" boarded "); dprint (ftos (mv_boarded));
        dprint (" route_retained "); dprint (ftos (retained && !mv_lost));
        dprint (" dry "); dprint (ftos (dry));
        dprint (" alive "); dprint (ftos (mv_bot.health > 0));
        dprint (" launches "); dprint (ftos (mv_launches));
        dprint (" bad_launch "); dprint (ftos (mv_badlaunch));
        dprint (" landed "); dprint (ftos (mv_landed));
        dprint (" handoff "); dprint (ftos (MoverTransferHandoffOK (mv_bot)));
        dprint (" exit_consumed "); dprint (ftos (mv_exit_consumed));
        dprint (" frames "); dprint (ftos (mv_frames));
        dprint (" node "); dprint (vtos (mv_bot.ar_node.origin));
        dprint (" generation "); dprint (ftos (mv_bot.ar_routegen));
        dprint (" pos "); dprint (vtos (mv_bot.origin)); dprint ("\n");
        mv_bot.velocity = '0 0 0'; mv_bot.movetype = MOVETYPE_NONE;
        mv_bot.think = SUB_Null; mv_bot.nextthink = 0;
    }
};
