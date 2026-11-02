// Private body-height contracts and continuing-route escape. All placement
// and real-QC invocations are setup. The observer cannot steer the subject.
entity bh_bot, bh_goal;
float bh_started, bh_done, bh_when, bh_lasttime, bh_dt, bh_frames;
float bh_checks, bh_failures, bh_lost, bh_discontinuous, bh_next;
vector bh_seed, bh_target, bh_previous;

void(string label, float ok) BodyHeightCheck =
{
    bh_checks = bh_checks + 1;
    if (!ok) bh_failures = bh_failures + 1;
    dprint ("BHCHECK "); dprint (label); dprint (" ");
    dprint (ftos (ok != 0)); dprint ("\n");
};

void(vector seat, vector neighbour, float firing, string label, float distance) BodyHeightCase =
{
    local entity mate;
    local vector before, delta;
    local float initialfit, finalfit;
    setorigin (self, seat); self.velocity = '0 0 0';
    self.flags = FL_ONGROUND; self.ar_dodgetime = 0; self.button0 = 1;
    mate = spawn (); mate.classname = "player"; mate.health = 1000;
    mate.flags = FL_ONGROUND; mate.solid = SOLID_SLIDEBOX;
    mate.movetype = MOVETYPE_NONE; mate.button0 = firing;
    setsize (mate, '-16 -16 -24', '16 16 32'); setorigin (mate, neighbour);
    initialfit = walkmove (0, 0); before = self.origin;
    // Fit uses the engine's floor epsilon. Touch the fitted bounds,
    // so a rounded seat does not create a small real overlap.
    if (label == "touch_upper")
    { neighbour_z = self.origin_z + self.maxs_z - mate.mins_z; setorigin (mate, neighbour); }
    if (label == "touch_lower")
    { neighbour_z = self.origin_z + self.mins_z - mate.maxs_z; setorigin (mate, neighbour); }
    Argus_BodyBlockCheck ();
    delta = self.origin - before; finalfit = walkmove (0, 0);
    dprint ("BHCASE "); dprint (label); dprint (" initialfit "); dprint (ftos (initialfit));
    dprint (" finalfit "); dprint (ftos (finalfit));
    dprint (" distance "); dprint (ftos (vlen (delta)));
    dprint (" dodge "); dprint (ftos (self.ar_dodgetime > time));
    dprint (" firing "); dprint (ftos (self.button0 != 0)); dprint ("\n");
    BodyHeightCheck (label, (initialfit && finalfit && !self.ar_dodgetime
        && self.button0 && fabs (vlen (delta) - distance) < 0.1));
    remove (mate);
};

void() BodyHeightBefore =
{
    local entity b, saved;
    local float beforefit, upperfit, afterfit;
    local vector before;
    if (bh_lasttime > 0) bh_dt = time - bh_lasttime;
    bh_lasttime = time;
    if (bh_started || time < 2) return;
    bh_started = 1; bh_when = time;
    dprint ("BHVRPL begin body_height\nBHFIX begin dt_ms ");
    dprint (ftos (bh_dt * 1000)); dprint (" layout 1\n");
    b = argus_bots;
    while (b != world)
    {
        Argus_Nav_Abort (b);
        if (b.ar_slot == 0) bh_bot = b;
        else
        {
            b.health = 0; b.solid = SOLID_NOT; b.takedamage = DAMAGE_NO;
            b.movetype = MOVETYPE_NONE; b.nextthink = 0; b.think = SUB_Null;
            b.ar_respawntime = time + 3600;
        }
        b = b.ar_chain;
    }
    saved = self; self = bh_bot; Argus_BaseStats ();
    if (mapname == "dm3")
    {
        BodyHeightCase ('338.1 125.9 -200', '371.1 125.9 56', 0, "upper_floor", 0);
        BodyHeightCase ('371.1 125.9 56', '338.1 125.9 -200', 0, "lower_floor", 0);
        BodyHeightCase ('338.1 125.9 -200', '371.1 125.9 56', 1, "upper_fire", 0);
        BodyHeightCase ('371.1 125.9 56', '338.1 125.9 -200', 1, "lower_fire", 0);
        // Synthetic transient bounds touch but do not overlap in height.
        BodyHeightCase ('400.1 125.9 -200', '433.1 125.9 -144', 0, "touch_upper", 0);
        BodyHeightCase ('400.1 125.9 -200', '433.1 125.9 -256', 0, "touch_lower", 0);
        BodyHeightCase ('400.1 125.9 -200', '433.1 125.9 -200', 0, "same_floor", 3);
        bh_seed = '338.1 125.9 -200'; bh_target = '677 193 -200';
    }
    else if (mapname == "e1m6")
    { bh_seed = '-157.1 833 -232'; bh_target = '-719 977 -232'; }
    // #723: a respawned bot on the walkway with another player passing
    // beneath it on the pit floor. Without a height gate the nudge lands
    // 0.9u inside the south wall and every move starts in solid.
    else if (mapname == "dm4")
    { bh_seed = '7.6 -262.1 -72'; bh_target = '145 -247 -72'; }
    else { error ("BHFIX wrong map"); return; }
    Argus_BaseStats (); Argus_AvoidClear (); Argus_TacticReset ();
    setorigin (self, bh_seed); self.velocity = '0 0 0'; self.flags = FL_ONGROUND;
    self.angles = '0 11 0'; self.ar_moveyaw = 11;
    if (mapname == "e1m6") { self.angles_y = 147; self.ar_moveyaw = 147; }
    beforefit = walkmove (0, 0); before = self.origin;
    b = spawn (); b.classname = "player"; b.health = 1000;
    b.flags = FL_ONGROUND; b.solid = SOLID_SLIDEBOX; b.movetype = MOVETYPE_STEP;
    setsize (b, '-16 -16 -24', '16 16 32');
    if (mapname == "dm3") setorigin (b, '371.1 125.9 56');
    else if (mapname == "dm4") setorigin (b, '-2.8 -240.5 -296');
    else setorigin (b, '-124.1 833 216');
    self = b; upperfit = walkmove (0, 0); self = bh_bot;
    Argus_BodyBlockCheck (); afterfit = walkmove (0, 0);
    dprint ("BHENTRY beforefit "); dprint (ftos (beforefit));
    dprint (" upperfit "); dprint (ftos (upperfit));
    dprint (" afterfit "); dprint (ftos (afterfit));
    dprint (" movement "); dprint (ftos (vlen (self.origin - before))); dprint ("\n");
    BodyHeightCheck ("entry_bodies_fit", (beforefit && upperfit));
    BodyHeightCheck ("entry_kept", (afterfit && vlen (self.origin - before) < 0.01));
    remove (b);
    bh_previous = self.origin;
    self.ar_goal = world; self.ar_node = world; self.ar_pending = 1;
    self.ar_mode = 0; self.ar_enemy = world; self.ar_sndtime = 0;
    self.ar_dodgetime = 0; self.ar_gaitpause = 0; self.ar_gaitroll = time + 100;
    self.ar_lastpos = self.origin; self.ar_nextstall = time + 2;
    self.ar_taskstart = time; self.ar_taskdeadline = time + 60;
    bh_goal = spawn (); bh_goal.classname = "argus_task_goal";
    bh_goal.flags = FL_ITEM; bh_goal.solid = SOLID_TRIGGER;
    setsize (bh_goal, '-8 -8 -8', '8 8 8'); setorigin (bh_goal, bh_target);
    self.ar_taskgoal = bh_goal; self.ar_goal = bh_goal;
    self.ar_laststart = world; self.ar_goalstart = time + 3600;
    self = saved;
};

void() BodyHeightAfter =
{
    local float completed, active, distance;
    if (!bh_started || bh_done) return;
    bh_frames = bh_frames + 1;
    active = (bh_bot.ar_taskgoal == bh_goal && bh_bot.ar_goal == bh_goal);
    if (!active) bh_lost = 1;
    if (vlen (bh_bot.origin - bh_previous) > 2 * AR_MAXSPEED * bh_dt + 4)
        bh_discontinuous = 1;
    bh_previous = bh_bot.origin;
    distance = vlen (bh_bot.origin - bh_seed);
    completed = (vlen (bh_bot.origin - bh_target) < 48);
    if (mapname == "e1m6" || mapname == "dm4") completed = (distance >= 64);
    if (!(bh_bot.flags & FL_ONGROUND) || bh_bot.groundentity != world
        || bh_bot.ar_wetlevel || bh_bot.health <= 0) completed = 0;
    if (time >= bh_next)
    {
        bh_next = time + 0.5;
        dprint ("BHPOSE t "); dprint (ftos (time - bh_when));
        dprint (" pos "); dprint (vtos (bh_bot.origin));
        dprint (" active "); dprint (ftos (active));
        dprint (" hp "); dprint (ftos (bh_bot.health)); dprint ("\n");
    }
    if (completed || time > bh_when + 3 || bh_bot.health <= 0)
    {
        bh_done = 1;
        BodyHeightCheck ("physical_exit", (completed && time < bh_when + 3));
        BodyHeightCheck ("continuous_motion", !bh_discontinuous);
        BodyHeightCheck ("task_preserved", !bh_lost);
        BodyHeightCheck ("alive_and_dry", (bh_bot.health > 0 && !bh_bot.ar_wetlevel));
        dprint ("BHRESULT completed "); dprint (ftos (completed));
        dprint (" seconds "); dprint (ftos (time - bh_when));
        dprint (" frames "); dprint (ftos (bh_frames));
        dprint (" pos "); dprint (vtos (bh_bot.origin));
        dprint (" hp "); dprint (ftos (bh_bot.health));
        dprint (" grounded "); dprint (ftos ((bh_bot.flags & FL_ONGROUND) != 0));
        dprint (" worldfloor "); dprint (ftos (bh_bot.groundentity == world));
        dprint (" wet "); dprint (ftos (bh_bot.ar_wetlevel));
        dprint (" lost "); dprint (ftos (bh_lost));
        dprint (" discontinuous "); dprint (ftos (bh_discontinuous)); dprint ("\n");
        dprint ("BHFIX end checks "); dprint (ftos (bh_checks));
        dprint (" failures "); dprint (ftos (bh_failures)); dprint ("\n");
        bh_bot.velocity = '0 0 0'; bh_bot.movetype = MOVETYPE_NONE;
        bh_bot.think = SUB_Null; bh_bot.nextthink = 0;
    }
};
