// PRIVATE component and goal-selector fixture. No prescribed movement route.
entity plan_subject, plan_a, plan_b, plan_leg, plan_old;
vector plan_seed;
float plan_started, plan_phase, plan_fighting, plan_checks, plan_ok, plan_move;

void(string label, float ok) PlanCheck =
{
    plan_checks = plan_checks + 1;
    if (!ok) plan_ok = 0;
    dprint ("PLANFIX check "); dprint (label); dprint (" ");
    dprint (ftos (ok)); dprint ("\n");
};

// INSERT_DECISION

void(entity goal) PlanSetup =
{
    Argus_Nav_Abort (self); Argus_AvoidClear ();
    self.ar_goal = goal; self.ar_goalstart = time;
    self.ar_node = world; self.ar_pending = 0; self.ar_mode = 1;
    self.ar_plan_goal = world; self.ar_plan_leg = world; self.ar_plan_best = 0;
    self.ar_stallrun = 0; self.ar_nextai = time + 0.2;
    self.ar_hoplift = 0; self.ar_hoptrain = 0; self.ar_hopjump = 0;
    self.ar_hoprj = 0; self.ar_hopswim = 0; self.ar_liftwait = 0;
    self.ar_door = world; self.ar_doorbtn = world; self.ar_enemy = world;
    self.ar_stucktime = 0; self.ar_sndtime = 0; self.ar_jump = 0;
    self.ar_lastpos = plan_seed; setorigin (self, plan_seed);
    self.velocity = '0 0 0'; self.movetype = MOVETYPE_NONE;
    self.flags = self.flags | FL_ONGROUND;
    goal.ar_claimer = world; goal.ar_claimtime = 0; goal.ar_failtime = 0;
    plan_fighting = FALSE;
};

void(vector p) PlanStep =
{
    setorigin (self, p); self.velocity = '0 0 0';
    self.ar_nextstall = time - 0.1;
    PlanDecision ();
};

void() PlanCases =
{
    local vector p;
    local entity oldgoal;
    // Synthetic public goals deliberately lie >200 units away. No map or
    // pickup-class condition can satisfy the plan-progress contract.
    PlanSetup (plan_a);
    PlanStep (plan_seed);
    PlanStep (plan_seed + '0 40 0');
    PlanCheck ("sideways_retains_failure", self.ar_stallrun == 1);
    PlanStep (plan_seed + '0 40 0');
    PlanCheck ("failed_plan_released", self.ar_goal != plan_a && plan_a.ar_claimer == self);

    PlanSetup (plan_a); PlanStep (plan_seed);
    PlanStep (plan_seed + '5 40 0');
    PlanCheck ("small_gain_not_success", self.ar_stallrun == 1);
    PlanStep (plan_seed + '10 -40 0');
    PlanCheck ("partial_gain_accumulates", self.ar_stallrun == 1);
    PlanStep (plan_seed + '20 40 0');
    PlanCheck ("useful_progress_resets", self.ar_stallrun == 0 && self.ar_goal == plan_a);

    PlanSetup (plan_a); PlanStep (plan_seed);
    self.ar_goal = plan_b;
    PlanStep (plan_seed);
    PlanCheck ("new_goal_fresh_attempt", self.ar_goal == plan_b && self.ar_stallrun == 1);

    PlanSetup (plan_a); PlanStep (plan_seed);
    self.ar_node = plan_leg;
    PlanStep (plan_seed + '0 40 0');
    PlanCheck ("route_rebuild_not_success", self.ar_stallrun == 1);
    setorigin (self, plan_seed);
    Argus_PlanObserve (FALSE, plan_leg);
    PlanCheck ("reached_waypoint_counts", self.ar_stallrun == 0);
    self.ar_stallrun = 1;
    Argus_PlanObserve (FALSE, plan_leg);
    PlanCheck ("same_waypoint_not_new_evidence", self.ar_stallrun == 1);

    PlanSetup (plan_a); PlanStep (plan_seed);
    plan_fighting = TRUE; PlanStep (plan_seed);
    PlanCheck ("combat_ownership_pauses", self.ar_stallrun == 0 && self.ar_goal == plan_a);
    plan_fighting = FALSE; PlanStep (plan_seed);
    PlanCheck ("resume_has_fresh_attempt", self.ar_goal == plan_a && self.ar_stallrun == 1);

    PlanSetup (plan_a); PlanStep (plan_seed);
    self.ar_liftwait = 1; PlanStep (plan_seed);
    PlanCheck ("mover_wait_not_failure", self.ar_goal == plan_a && self.ar_stallrun == 0);
    self.ar_liftwait = 0;

    PlanSetup (plan_a); PlanStep (plan_seed);
    self.ar_hopjump = 1; PlanStep (plan_seed + '0 40 0');
    PlanCheck ("typed_link_pause", self.ar_goal == plan_a && self.ar_stallrun == 0);
    self.ar_hopjump = 0;

    PlanSetup (plan_a);
    plan_a.solid = SOLID_NOT; plan_a.think = SUB_regen; plan_a.nextthink = time + 15;
    self.ar_lastpos = plan_seed + '0 -40 0';
    PlanStep (plan_seed); PlanStep (plan_seed + '0 40 0'); PlanStep (plan_seed);
    PlanCheck ("healthy_wait_no_timeout", self.ar_goal == plan_a && self.ar_stallrun == 0);
    PlanSetup (plan_a); PlanStep (plan_seed);
    PlanStep (plan_seed + '0 40 0'); PlanStep (plan_seed + '0 40 0');
    PlanCheck ("blocked_wait_reconsiders", self.ar_goal != plan_a && plan_a.ar_claimer == self);
    plan_a.solid = SOLID_TRIGGER; plan_a.think = SUB_Null; plan_a.nextthink = 0;

    PlanSetup (plan_a); PlanStep (plan_seed);
    Argus_BaseStats ();
    self.ar_goal = plan_a; self.ar_node = world; self.ar_pending = 0;
    self.ar_mode = 1; self.ar_lastpos = plan_seed;
    PlanStep (plan_seed);
    PlanCheck ("new_life_fresh_attempt", self.ar_goal == plan_a && self.ar_stallrun == 1);

    if (cvar ("scratch3") == 589) PlanEdgeCases ();

    // Final integration: real item goal fails, then the existing selector
    // must choose an alternative. No alternative is assigned by the fixture.
    PlanSetup (plan_old);
    p = Argus_GoalPoint (plan_old) + '1000 0 0';
    self.ar_lastpos = p; PlanStep (p);
    PlanStep (p + '0 40 0'); PlanStep (p + '0 40 0');
    PlanCheck ("real_goal_failure_released", self.ar_goal != plan_old && plan_old.ar_claimer == self);
    setorigin (self, plan_seed); self.velocity = '0 0 0';
    self.movetype = MOVETYPE_NONE; self.cam_active = 0;
    self.ar_nextai = time - 0.1; self.ar_nextstall = time + 10;
    self.ar_stucktime = 0;
    ar_tacfixture_bot = world;
};

void() PlanFixture =
{
    local entity b, saved;
    if (time < 2 || plan_phase == 2) return;
    if (!plan_phase)
    {
        ar_tacfixture_until = time + 100; ar_tacfixture_bot = world;
        b = argus_bots;
        while (b != world)
        {
            Argus_Nav_Abort (b);
            if (b.ar_slot == 1) plan_subject = b;
            else { b.solid = SOLID_NOT; b.cam_active = 1; b.button0 = 0; }
            b = b.ar_chain;
        }
        if (plan_subject == world) { error ("Plan fixture subject"); return; }
        plan_seed = plan_subject.origin; plan_move = plan_subject.movetype;
        plan_a = spawn (); plan_a.classname = "plan_goal_a";
        setorigin (plan_a, plan_seed + '1000 0 0'); plan_a.solid = SOLID_TRIGGER;
        plan_b = spawn (); plan_b.classname = "plan_goal_b";
        setorigin (plan_b, plan_seed + '1000 500 0'); plan_b.solid = SOLID_TRIGGER;
        plan_leg = spawn (); plan_leg.classname = "plan_leg";
        // Choose a genuine available prize; no map token or coordinate.
        b = argus_itemchain;
        while (b != world && plan_old == world)
        {
            if (b.solid == SOLID_TRIGGER && vlen (b.origin - plan_seed) > 300)
                plan_old = b;
            b = b.ar_nextitem;
        }
        if (plan_old == world) { error ("Plan fixture live goal"); return; }
        saved = self; self = plan_subject;
        Argus_BaseStats ();
        plan_ok = 1; plan_started = time;
        dprint ("PLANFIX begin "); dprint (mapname); dprint ("\n");
        PlanCases ();
        self = saved; plan_phase = 1;
        return;
    }
    // Keep position fixed while the unmodified goal selector/route search
    // runs. This prevents an ordinary pickup from masquerading as replanning.
    saved = self; self = plan_subject;
    setorigin (self, plan_seed); self.velocity = '0 0 0';
    self.ar_nextstall = time + 10;
    Argus_AI (); self = saved;
    if ((plan_subject.ar_goal != world && plan_subject.ar_goal != plan_old)
        || time > plan_started + 4)
    {
        PlanCheck ("alternative_selected", plan_subject.ar_goal != world
            && plan_subject.ar_goal != plan_old);
        dprint ("PLANFIX alternative "); dprint (plan_subject.ar_goal.classname);
        dprint (" elapsed "); dprint (ftos (time - plan_started)); dprint ("\n");
        dprint ("PLANFIX end checks "); dprint (ftos (plan_checks));
        dprint (" ok "); dprint (ftos (plan_ok)); dprint ("\n");
        plan_phase = 2;
        // The disposable engine is stopped by the owner; no match history
        // restoration is claimed. Remove the three private marker entities.
        remove (plan_a); remove (plan_b); remove (plan_leg);
        plan_subject.ar_plan_goal = world; plan_subject.ar_plan_leg = world;
        plan_subject.ar_goal = world; plan_subject.ar_node = world;
        Argus_Nav_Abort (plan_subject);
        ar_tacfixture_bot = world;
        dprint ("PLANFIX cleanup owned_engine_pending_stop\n");
    }
};
