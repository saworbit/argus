// Private decision inputs. The copied production stall block decides outcomes.
// No claim is made that these prescribed positions reproduce a physical wedge.
float sw_done, sw_checks, sw_failures, sw_fighting;
entity sw_actor, sw_goal, sw_door;
vector sw_seed;

void(string label, float ok) StallWaitCheck =
{
    sw_checks = sw_checks + 1;
    if (!ok) sw_failures = sw_failures + 1;
    dprint ("SWCHECK "); dprint (label); dprint (" ");
    dprint (ftos (ok != 0)); dprint ("\n");
};

// INSERT_DECISION

void() StallWaitSetup =
{
    Argus_Nav_Abort (self); Argus_AvoidClear ();
    self.ar_goal = sw_goal; self.ar_goalstart = time - 5;
    self.ar_node = world; self.ar_pending = 0; self.ar_mode = 2;
    self.ar_plan_goal = sw_goal; self.ar_plan_leg = world;
    self.ar_plan_best = 50; self.ar_stallrun = 0; self.ar_stalls = 0;
    self.ar_hoptrain = 0; self.ar_hopjump = 0; self.ar_hoprj = 0;
    self.ar_hopswim = 0; self.ar_hoplift = 0; self.ar_liftwait = 0;
    self.ar_door = world; self.ar_doorbtn = world; self.ar_taskgoal = world;
    self.ar_gaitquiet = 0; self.ar_nextai = time - 0.1;
    self.flags = FL_ONGROUND; self.velocity = '0 0 0';
    setorigin (self, sw_seed); self.ar_lastpos = sw_seed;
    sw_goal.solid = SOLID_TRIGGER; sw_goal.think = SUB_Null;
    sw_goal.nextthink = 0; sw_goal.ar_claimer = world;
    sw_goal.ar_claimtime = 0; sw_goal.ar_failtime = 0;
    sw_goal.claimed_by = self;
    setorigin (sw_goal, sw_seed + '1000 0 0');
    sw_fighting = 0;
};

void(float kind) StallWaitArm =
{
    if (kind == 0) self.ar_hoptrain = 1;
    else if (kind == 1) self.ar_hopjump = 1;
    else if (kind == 2) self.ar_hoprj = 1;
    else if (kind == 3) self.ar_hopswim = 1;
    else self.ar_door = sw_door;
};

void(vector p) StallWaitStep =
{
    setorigin (self, p); self.ar_nextstall = time - 0.1;
    StallWaitDecision ();
};

void() StallWaitFixture =
{
    local entity saved;
    local float i, ok, deadline;
    local string label;
    if (sw_done || time < 2) return;
    sw_done = 1; saved = self;
    sw_actor = spawn (); sw_goal = spawn (); sw_door = spawn ();
    self = sw_actor; self.netname = "stall_fixture";
    sw_goal.classname = "stall_goal"; sw_door.classname = "door";
    sw_seed = '0 0 24';
    dprint ("BHVRPL begin stall_ownership\nSWCHECK begin dt_ms ");
    dprint (ftos (frametime * 1000)); dprint (" layout 1\n");
    i = 0;
    while (i < 5)
    {
        StallWaitSetup (); StallWaitArm (i);
        self.ar_shopping = 1;
        StallWaitStep (sw_seed); StallWaitStep (sw_seed);
        if (i == 0) label = "stationary_train_released";
        else if (i == 1) label = "stationary_jump_released";
        else if (i == 2) label = "stationary_rj_released";
        else if (i == 3) label = "stationary_swim_released";
        else label = "stationary_door_released";
        StallWaitCheck (label, self.ar_goal == world
            && sw_goal.ar_claimer == self && self.ar_stalls == 2
            && !self.ar_hoptrain && !self.ar_hopjump && !self.ar_hoprj
            && !self.ar_hopswim && self.ar_door == world
            && sw_goal.claimed_by != self && !self.ar_shopping);
        i = i + 1;
    }
    i = 0; ok = 1;
    while (i < 5)
    {
        StallWaitSetup (); StallWaitArm (i); self.ar_stallrun = 1;
        StallWaitStep (sw_seed + '0 40 0');
        if (self.ar_goal != sw_goal || self.ar_stallrun != 0) ok = 0;
        i = i + 1;
    }
    StallWaitCheck ("moving_typed_pause", ok);
    i = 0;
    while (i < 4)
    {
        StallWaitSetup (); self.ar_stallrun = 1;
        if (i == 0) { sw_fighting = 1; label = "combat_wait"; }
        else if (i == 1) { self.ar_liftwait = 1; label = "lift_wait"; }
        else if (i == 2) { self.ar_hoplift = 1; label = "lift_hop_wait"; }
        else { self.ar_gaitquiet = time; label = "gait_tail"; }
        StallWaitStep (sw_seed); StallWaitStep (sw_seed);
        StallWaitCheck (label, self.ar_goal == sw_goal
            && self.ar_stallrun == 0 && self.ar_stalls == 0);
        i = i + 1;
    }
    StallWaitSetup (); self.ar_mode = 1;
    setorigin (sw_goal, sw_seed + '90 0 0');
    sw_goal.solid = SOLID_NOT; sw_goal.think = SUB_regen;
    sw_goal.nextthink = time + 15; deadline = self.ar_goalstart;
    StallWaitStep (sw_seed);
    self.ar_mode = 1; self.ar_pending = 0;
    StallWaitStep (sw_seed + '0 40 0');
    self.ar_mode = 1; self.ar_pending = 0;
    StallWaitStep (sw_seed + '0 40 0');
    StallWaitCheck ("camp_orbit_keeps_goal", self.ar_goal == sw_goal
        && self.ar_stallrun == 1 && self.ar_stalls == 2);
    StallWaitCheck ("camp_deadline_unchanged", self.ar_goalstart == deadline);
    StallWaitStep (sw_seed + '0 40 0');
    StallWaitCheck ("camp_wedge_released", self.ar_goal == world
        && sw_goal.ar_claimer == self);

    StallWaitSetup (); self.ar_mode = 1; self.ar_stallrun = 1;
    sw_goal.solid = SOLID_NOT; sw_goal.think = SUB_regen;
    sw_goal.nextthink = time + 15;
    StallWaitStep (sw_seed + '0 40 0');
    StallWaitCheck ("far_item_not_pause", self.ar_stallrun == 1);
    StallWaitSetup (); self.ar_mode = 1; self.ar_stallrun = 1;
    setorigin (sw_goal, sw_seed + '90 0 0');
    StallWaitStep (sw_seed + '0 40 0');
    StallWaitCheck ("live_item_not_pause", self.ar_stallrun == 1);

    dprint ("SWCHECK end checks "); dprint (ftos (sw_checks));
    dprint (" failures "); dprint (ftos (sw_failures)); dprint ("\n");
    remove (sw_actor); remove (sw_goal); remove (sw_door); self = saved;
};
