// Private transfer task: production AI/physics owns every movement after
// placement. The checkpoint is dry static floor on the continuing route,
// not a goal-selection event or a claim that the later prize was picked up.
float mv_started, mv_done, mv_when, mv_previous_time, mv_dt;
float mv_boarded, mv_launches, mv_badlaunch, mv_completed;
entity mv_bot, mv_marker, mv_mover;
vector mv_start, mv_goal, mv_exit;

void() MoverTransferBefore =
{
    local entity b, saved;
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
    dprint ("MVFIX begin dt_ms "); dprint (ftos (mv_dt * 1000)); dprint ("\n");
    self = saved;
};

void() MoverTransferAfter =
{
    local vector to, launch_velocity;
    local float retained, dry;
    if (!mv_started || mv_done) return;
    if (mv_bot.groundentity.classname == "plat" && (mv_bot.flags & FL_ONGROUND))
    {
        mv_boarded = 1; mv_mover = mv_bot.groundentity;
    }
    if (mv_boarded && mv_bot.groundentity == mv_mover
        && mv_bot.ar_hopair && !mv_bot.ar_hoplift && mv_bot.velocity_z == AR_JUMPVEL)
    {
        mv_launches = mv_launches + 1;
        launch_velocity = mv_bot.velocity; launch_velocity_z = 0;
        if (mv_mover.state != STATE_TOP || vlen (launch_velocity) > 330) mv_badlaunch = 1;
    }
    to = mv_bot.origin - mv_exit; to_z = 0;
    retained = mv_bot.ar_goal == mv_marker && mv_bot.ar_taskgoal == mv_marker;
    dry = mv_bot.ar_wetlevel < 2 && mv_bot.ar_feettype != CONTENT_LAVA
        && mv_bot.ar_feettype != CONTENT_SLIME;
    mv_completed = (mv_boarded && retained && dry && mv_bot.health > 0
        && (mv_bot.flags & FL_ONGROUND) && mv_bot.groundentity != mv_mover
        && fabs (mv_bot.origin_z - mv_exit_z) <= 18 && vlen (to) < 96);
    if (mv_completed || time > mv_when + 18 || mv_bot.health <= 0)
    {
        mv_done = 1;
        dprint ("MVFIX result completed "); dprint (ftos (mv_completed));
        dprint (" seconds "); dprint (ftos (time - mv_when));
        dprint (" boarded "); dprint (ftos (mv_boarded));
        dprint (" route_retained "); dprint (ftos (retained));
        dprint (" dry "); dprint (ftos (dry));
        dprint (" alive "); dprint (ftos (mv_bot.health > 0));
        dprint (" launches "); dprint (ftos (mv_launches));
        dprint (" bad_launch "); dprint (ftos (mv_badlaunch));
        dprint (" pos "); dprint (vtos (mv_bot.origin)); dprint ("\n");
        mv_bot.velocity = '0 0 0'; mv_bot.movetype = MOVETYPE_NONE;
        mv_bot.think = SUB_Null; mv_bot.nextthink = 0;
    }
};
