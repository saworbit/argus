// Private real-hull nudge checks and a continuing dm3 route. Production
// body-block handling is called once per initial condition; the observer
// assigns no movement, route or goal after setup.
entity bn_bot, bn_goal;
float bn_started, bn_done, bn_begin, bn_lasttime, bn_dt, bn_next;
float bn_checks, bn_failures, bn_frames, bn_tasklost, bn_discontinuous;
vector bn_previous, bn_seed, bn_target;

void(string label, float ok) BodyNudgeCheck =
{
    bn_checks = bn_checks + 1;
    if (!ok) bn_failures = bn_failures + 1;
    dprint ("BNCHECK "); dprint (label); dprint (" ");
    dprint (ftos (ok != 0)); dprint ("\n");
};

void(vector seat, vector neighbour, float firing, string label, float clearcase) BodyNudgeCase =
{
    local entity mate;
    local float initialfit, finalfit, distance, ok;
    local vector delta;
    setorigin (self, seat); self.velocity = '0 0 0';
    self.flags = FL_ONGROUND; self.ar_dodgetime = 0;
    self.button0 = 1;
    mate = spawn (); mate.classname = "player"; mate.health = 1000;
    mate.flags = FL_ONGROUND; mate.solid = SOLID_SLIDEBOX;
    mate.movetype = MOVETYPE_NONE; mate.button0 = firing;
    setsize (mate, '-16 -16 -24', '16 16 32'); setorigin (mate, neighbour);
    initialfit = walkmove (0, 0);
    // The zero-step preflight seats on the engine's floor epsilon. Measure
    // the nudge from that fitted origin, not the rounded fixture coordinate.
    seat = self.origin;
    Argus_BodyBlockCheck ();
    delta = self.origin - seat; distance = vlen (delta);
    finalfit = walkmove (0, 0);
    ok = (initialfit == (clearcase < 2) && finalfit && !self.ar_dodgetime && self.button0);
    if (clearcase == 1) ok = (ok && fabs (distance - 3) < 0.1 && fabs (delta_z) < 0.1);
    else if (clearcase == 2) ok = (ok && fabs (distance - 16) < 0.1 && fabs (delta_z) < 0.1);
    else if (clearcase == 3) ok = (ok && fabs (distance - 22.6274) < 0.1 && fabs (delta_z) < 0.1);
    else ok = (ok && distance < 0.01);
    dprint ("BNCASE "); dprint (label);
    dprint (" initialfit "); dprint (ftos (initialfit));
    dprint (" finalfit "); dprint (ftos (finalfit));
    dprint (" distance "); dprint (ftos (distance));
    dprint (" dodge "); dprint (ftos (self.ar_dodgetime > time)); dprint ("\n");
    BodyNudgeCheck (label, ok);
    remove (mate);
};

void() BodyNudgeBefore =
{
    local entity b, mate, saved;
    if (bn_lasttime > 0) bn_dt = time - bn_lasttime;
    bn_lasttime = time;
    if (bn_started || time < 2) return;
    bn_started = 1; bn_begin = time;
    dprint ("BHVRPL begin body_nudge\nBNFIX begin dt_ms ");
    dprint (ftos (bn_dt * 1000)); dprint (" layout 1\n");
    b = argus_bots;
    while (b != world)
    {
        Argus_Nav_Abort (b);
        if (b.ar_slot == 0) bn_bot = b;
        else
        {
            b.health = 0; b.solid = SOLID_NOT; b.takedamage = DAMAGE_NO;
            b.movetype = MOVETYPE_NONE; b.nextthink = 0; b.think = SUB_Null;
            b.ar_respawntime = time + 3600;
        }
        b = b.ar_chain;
    }
    saved = self; self = bn_bot; Argus_BaseStats ();
    BodyNudgeCase ('338.1 125.9 -200', '371.1 125.9 56', 0, "upper_floor", 0);
    BodyNudgeCase ('338.1 125.9 -200', '371.1 125.9 -200', 0, "wall_refused", 0);
    BodyNudgeCase ('400.1 125.9 -200', '433.1 125.9 -200', 0, "clear_step", 1);
    BodyNudgeCase ('338.1 125.9 -200', '371.1 125.9 56', 1, "upper_fire", 0);
    BodyNudgeCase ('400.1 125.9 -200', '420.1 125.9 -200', 0, "overlap_axis", 2);
    BodyNudgeCase ('400.1 125.9 -200', '420.1 145.9 -200', 0, "overlap_diagonal", 3);
    Argus_BaseStats (); Argus_AvoidClear (); Argus_TacticReset ();
    bn_seed = '338.1 125.9 -200'; bn_target = '677 193 -200';
    setorigin (self, bn_seed); self.velocity = '0 0 0'; self.flags = FL_ONGROUND;
    self.angles = '0 11 0'; self.ar_moveyaw = 11;
    mate = spawn (); mate.classname = "player"; mate.health = 1000;
    mate.flags = FL_ONGROUND; mate.solid = SOLID_SLIDEBOX;
    setsize (mate, '-16 -16 -24', '16 16 32'); setorigin (mate, '371.1 125.9 56');
    Argus_BodyBlockCheck (); remove (mate);
    bn_previous = self.origin;
    self.ar_goal = world; self.ar_node = world; self.ar_pending = 1;
    self.ar_mode = 0; self.ar_enemy = world; self.ar_sndtime = 0;
    self.ar_dodgetime = 0;
    self.ar_gaitpause = 0; self.ar_gaitroll = time + 100;
    self.ar_lastpos = self.origin; self.ar_nextstall = time + 2;
    self.ar_taskstart = time; self.ar_taskdeadline = time + 60;
    bn_goal = spawn (); bn_goal.classname = "argus_task_goal";
    bn_goal.flags = FL_ITEM; bn_goal.solid = SOLID_TRIGGER;
    setsize (bn_goal, '-8 -8 -8', '8 8 8'); setorigin (bn_goal, bn_target);
    self.ar_taskgoal = bn_goal; self.ar_goal = bn_goal;
    self.ar_laststart = world; self.ar_goalstart = time + 3600;
    self = saved;
};

void() BodyNudgeAfter =
{
    local float completed, active;
    if (!bn_started || bn_done) return;
    bn_frames = bn_frames + 1;
    active = (bn_bot.ar_taskgoal == bn_goal && bn_bot.ar_goal == bn_goal);
    if (!active) bn_tasklost = 1;
    if (vlen (bn_bot.origin - bn_previous) > 2 * AR_MAXSPEED * bn_dt + 4)
        bn_discontinuous = 1;
    bn_previous = bn_bot.origin;
    completed = (vlen (bn_bot.origin - bn_target) < 48);
    if (time >= bn_next)
    {
        bn_next = time + 0.5;
        dprint ("BNPOSE t "); dprint (ftos (time - bn_begin));
        dprint (" pos "); dprint (vtos (bn_bot.origin));
        dprint (" node "); dprint (vtos (bn_bot.ar_node.origin));
        dprint (" active "); dprint (ftos (active));
        dprint (" wet "); dprint (ftos (bn_bot.ar_wetlevel));
        dprint (" flags "); dprint (ftos (bn_bot.flags));
        dprint (" blocked "); dprint (ftos (bn_bot.ar_blockedfrom));
        dprint (" enemy "); dprint (bn_bot.ar_enemy.netname); dprint ("\n");
    }
    if (completed || time > bn_begin + 10 || bn_bot.health <= 0)
    {
        bn_done = 1;
        BodyNudgeCheck ("route_complete", completed && time < bn_begin + 3);
        BodyNudgeCheck ("continuous_motion", !bn_discontinuous);
        BodyNudgeCheck ("task_preserved", !bn_tasklost);
        BodyNudgeCheck ("dry_and_alive", bn_bot.health > 0 && bn_bot.ar_wetlevel == 0);
        dprint ("BNFIX end checks "); dprint (ftos (bn_checks));
        dprint (" failures "); dprint (ftos (bn_failures));
        dprint (" seconds "); dprint (ftos (time - bn_begin));
        dprint (" frames "); dprint (ftos (bn_frames)); dprint ("\n");
        dprint ("BNRESULT pos "); dprint (vtos (bn_bot.origin));
        dprint (" lost "); dprint (ftos (bn_tasklost));
        dprint (" discontinuous "); dprint (ftos (bn_discontinuous));
        dprint (" hp "); dprint (ftos (bn_bot.health));
        dprint (" wet "); dprint (ftos (bn_bot.ar_wetlevel)); dprint ("\n");
        bn_bot.velocity = '0 0 0'; bn_bot.movetype = MOVETYPE_NONE;
        bn_bot.think = SUB_Null; bn_bot.nextthink = 0;
    }
};
