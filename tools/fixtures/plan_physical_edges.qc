// PRIVATE physical evidence. Setup assigns one goal and initial conditions.
// Afterwards only ordinary bot execution moves/routes the actor. The one
// environmental change opens the cage when its first real rest expires.
entity pm_bot, pm_goal, pm_wall0, pm_wall1, pm_wall2, pm_wall3, pm_lastleg;
vector pm_start, pm_touchpos;
float pm_begin, pm_next, pm_frames, pm_case, pm_done, pm_contact;
float pm_rest, pm_until, pm_retry, pm_bad, pm_legs, pm_initialdist;

void() PlanPhysicalContact =
{
    if (other != pm_bot || pm_contact) return;
    pm_contact = time;
    pm_touchpos = other.origin;
    dprint ("PMFIX contact t "); dprint (ftos (time - pm_begin));
    dprint (" pos "); dprint (vtos (pm_touchpos));
    dprint (" active "); dprint (ftos (other.ar_goal == self));
    dprint ("\n");
    self.solid = SOLID_NOT;
};

entity(vector offset, vector lo, vector hi) PlanPhysicalWall =
{
    local entity e;
    e = spawn (); e.classname = "plan_physical_wall";
    e.solid = SOLID_BBOX; e.movetype = MOVETYPE_NONE;
    setsize (e, lo, hi); setorigin (e, pm_start + offset);
    return e;
};

void() PlanPhysicalEdges =
{
    local entity b, saved;
    local float active, stacked, ok, lost, deadline;
    if (time < 2 || pm_done) return;
    if (!pm_begin)
    {
        pm_case = cvar ("scratch2");
        if ((pm_case == 3 && mapname != "dm2") || (pm_case != 3 && mapname != "e1m2"))
        { error ("PMFIX wrong map"); return; }
        if ((pm_case == 3 && (!coop || deathmatch))
            || (pm_case != 3 && (coop || !deathmatch)))
        { error ("PMFIX wrong engine mode"); return; }
        b = argus_bots;
        while (b != world)
        {
            Argus_Nav_Abort (b);
            if ((pm_case == 3 && b.ar_slot == 0)
                || (pm_case != 3 && b.ar_slot == 1)) pm_bot = b;
            else { b.solid = SOLID_NOT; b.cam_active = 1; b.button0 = 0; }
            b = b.ar_chain;
        }
        if (pm_bot == world) { error ("PMFIX missing actor"); return; }
        saved = self; self = pm_bot;
        Argus_BaseStats (); Argus_AvoidClear ();
        if (pm_case != 3)
        {
            // Do not inherit the two pre-setup seconds' route/tactical state.
            Argus_TacticReset (); self.ar_tactic_settle = 0;
            self.ar_retreating = 0; self.ar_dodgetime = 0;
            self.ar_hopjump = 0; self.ar_hopspeed = 0; self.ar_sprintstate = 0;
            self.ar_hoprj = 0; self.ar_hoplift = 0; self.ar_hopswim = 0;
            self.ar_hoptrain = 0; self.ar_hopdoor = 0; self.ar_liftwait = 0;
            self.ar_jump = 0; self.ar_routefail = 0; self.ar_failstreak = 0;
            self.ar_traptime = -100;
            self.angles_y = 90; self.ar_moveyaw = 90;
        }
        pm_start = '1745 -191 312';
        if (pm_case == 3) pm_start = '2209 -279 24';
        setorigin (self, pm_start); self.velocity = '0 0 0';
        self.flags = self.flags | FL_ONGROUND;
        self.ar_enemy = world; self.ar_sndtime = 0;
        self.ar_node = world; self.ar_pending = 1; self.ar_mode = 0;
        self.ar_door = world; self.ar_doorbtn = world;
        self.ar_goal_count = 0; self.ar_greeted = 1;
        self.ar_coop_seektime = time + 100; self.ar_stucktime = 0;
        self.ar_lastpos = self.origin; self.ar_nextstall = time + 0.7;
        self.ar_nextai = time + 0.2;
        if (pm_case != 3) self.ar_nextai = time - 0.1;
        pm_goal = spawn (); pm_goal.classname = "plan_physical_goal";
        pm_goal.solid = SOLID_TRIGGER; pm_goal.movetype = MOVETYPE_NONE;
        setsize (pm_goal, '-16 -16 -24', '16 16 32');
        if (pm_case == 3) setorigin (pm_goal, '2433 -183 24');
        else setorigin (pm_goal, '-111 -511 384');
        pm_goal.touch = PlanPhysicalContact;
        self.ar_goal = pm_goal; self.ar_goalstart = time;
        if (pm_case == 3)
        {
            Argus_GoalPush (GOAL_FETCH, pm_goal, pm_goal.origin, 75, time + 90, 0);
            pm_wall0 = PlanPhysicalWall ('64 0 24', '-8 -72 -48', '8 72 96');
            pm_wall1 = PlanPhysicalWall ('-64 0 24', '-8 -72 -48', '8 72 96');
            pm_wall2 = PlanPhysicalWall ('0 64 24', '-72 -8 -48', '72 8 96');
            pm_wall3 = PlanPhysicalWall ('0 -64 24', '-72 -8 -48', '72 8 96');
        }
        // A declared low walking pace stretches actual travel past 20 s.
        // This is one initial test input, not a per-frame velocity script.
        if (pm_case == 4) AR_MAXSPEED = 160;
        pm_initialdist = vlen (pm_goal.origin - self.origin);
        ar_tacfixture_until = time + 100; ar_tacfixture_bot = self;
        pm_begin = time;
        dprint ("BHVRPL begin plan_physical_edges\nPMFIX begin ");
        dprint (mapname); dprint (" case ");
        dprint (ftos (pm_case)); dprint (" coop "); dprint (ftos (coop));
        dprint (" dm "); dprint (ftos (deathmatch));
        dprint (" pace "); dprint (ftos (AR_MAXSPEED));
        dprint (" start "); dprint (vtos (pm_start));
        dprint (" goal "); dprint (vtos (pm_goal.origin));
        dprint (" solid "); dprint (ftos (pointcontents (self.origin) == CONTENT_SOLID));
        dprint ("\n"); self = saved;
    }
    pm_frames = pm_frames + 1;
    saved = self; self = pm_bot;
    active = (self.ar_goal == pm_goal);
    stacked = (Argus_GoalTopKind () == GOAL_FETCH && Argus_GoalTopSubj () == pm_goal);
    if (pm_case == 3)
    {
        if (!pm_rest && self.ar_fetchfailed == pm_goal && !active && self.ar_fetchcool > time)
        {
            pm_rest = time; pm_until = self.ar_fetchcool;
            dprint ("PMFIX rest t "); dprint (ftos (time - pm_begin));
            dprint (" until "); dprint (ftos (pm_until - pm_begin)); dprint ("\n");
        }
        if (pm_rest && time < pm_until)
        {
            if (active || !stacked || self.ar_fetchcool != pm_until) pm_bad = 1;
        }
        if (pm_rest && time >= pm_until && pm_wall0 != world)
        {
            remove (pm_wall0); remove (pm_wall1); remove (pm_wall2); remove (pm_wall3);
            pm_wall0 = world; pm_wall1 = world; pm_wall2 = world; pm_wall3 = world;
            dprint ("PMFIX gate t "); dprint (ftos (time - pm_begin)); dprint ("\n");
        }
        if (pm_rest && time >= pm_until && active && !pm_retry)
        {
            pm_retry = time;
            dprint ("PMFIX retry t "); dprint (ftos (time - pm_begin));
            dprint (" deadline "); dprint (ftos (self.ar_goalstart - pm_begin)); dprint ("\n");
        }
    }
    if (self.ar_plan_leg != world && self.ar_plan_leg != pm_lastleg)
    {
        pm_lastleg = self.ar_plan_leg; pm_legs = pm_legs + 1;
        dprint ("PMFIX leg t "); dprint (ftos (time - pm_begin));
        dprint (" pos "); dprint (vtos (self.origin));
        dprint (" node "); dprint (vtos (pm_lastleg.origin)); dprint ("\n");
    }
    lost = (!active && !pm_contact && pm_case != 3);
    deadline = 40; if (pm_case == 3) deadline = 35;
    if (time >= pm_next || pm_contact || lost || time > pm_begin + deadline)
    {
        pm_next = time + 0.2;
        dprint ("PMFIX sample t "); dprint (ftos (time - pm_begin));
        dprint (" pos "); dprint (vtos (self.origin));
        dprint (" active "); dprint (ftos (active));
        dprint (" stacked "); dprint (ftos (stacked));
        dprint (" hp "); dprint (ftos (self.health));
        dprint (" frames "); dprint (ftos (pm_frames)); dprint ("\n");
    }
    if (pm_contact || lost || time > pm_begin + deadline || self.health != 100 || pm_bad)
    {
        ok = (pm_contact && !pm_bad && self.health == 100);
        if (pm_case == 3 && (!pm_rest || !pm_retry || pm_contact < pm_retry)) ok = 0;
        dprint ("PMFIX end ok "); dprint (ftos (ok));
        dprint (" lost "); dprint (ftos (lost));
        dprint (" bad "); dprint (ftos (pm_bad)); dprint ("\n");
        pm_done = 1; ar_tacfixture_bot = world;
        self.velocity = '0 0 0'; self.button0 = 0; Argus_Nav_Abort (self);
        remove (pm_goal);
        if (pm_wall0 != world)
        { remove (pm_wall0); remove (pm_wall1); remove (pm_wall2); remove (pm_wall3); }
        dprint ("PMFIX cleanup owned_engine_pending_stop\n");
    }
    self = saved;
};
