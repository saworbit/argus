// Private component checks. Temporary nodes never enter the movement trial.
#ifdef ROUTE_DECISION_COMPONENTS
float rd_checks, rd_failures;
void(string label, float ok) RouteDecisionCheck =
{
    rd_checks = rd_checks + 1;
    if (!ok) rd_failures = rd_failures + 1;
    dprint ("RDEC check "); dprint (label); dprint (" ");
    dprint (ftos (ok != 0)); dprint ("\n");
};
#endif

void() RouteDecisionContracts =
{
#ifdef ROUTE_DECISION_COMPONENTS
    local entity saved, actor, a, b, c, n;
    local vector base;
    local float pause_clock;
    saved = self;
    n = find (world, classname, "argus_node");
    while (n != world && pointcontents (n.origin) == CONTENT_WATER)
        n = find (n, classname, "argus_node");
    if (n == world) { error ("RDEC no dry context"); return; }
    base = n.origin;
    actor = spawn (); self = actor;
    self.ar_slot = 0; self.ar_skill = 2; self.health = 100;
    a = Argus_NavNode (base); b = Argus_NavNode (base + '80 0 0');
    c = Argus_NavNode (base + '160 0 0');
    Argus_NavLink (a, b); Argus_NavLink (b, c);
    Argus_SetNext (a, self, b); Argus_SetNext (b, self, c);
    Argus_SetNext (c, self, world); self.ar_node = a;
    dprint ("RDEC begin checks 56\n");
    RouteDecisionCheck ("walk_chain", Argus_RouteCanShortcut ());
    b.an_jumpmask = 1;
    RouteDecisionCheck ("typed_jump", !Argus_RouteCanShortcut ()); b.an_jumpmask = 0;
    b.an_sprintmask = 1;
    RouteDecisionCheck ("typed_sprint", !Argus_RouteCanShortcut ()); b.an_sprintmask = 0;
    b.an_rjmask = 1;
    RouteDecisionCheck ("typed_rocket", !Argus_RouteCanShortcut ()); b.an_rjmask = 0;
    b.an_swimmask = 1;
    RouteDecisionCheck ("typed_swim", !Argus_RouteCanShortcut ()); b.an_swimmask = 0;
    b.an_liftmask = 1;
    RouteDecisionCheck ("typed_lift", !Argus_RouteCanShortcut ()); b.an_liftmask = 0;
    b.an_trainmask = 1;
    RouteDecisionCheck ("typed_train", !Argus_RouteCanShortcut ()); b.an_trainmask = 0;
    b.an_doormask = 1;
    RouteDecisionCheck ("typed_door", !Argus_RouteCanShortcut ()); b.an_doormask = 0;
    setorigin (c, base + '160 0 40');
    RouteDecisionCheck ("height_change", !Argus_RouteCanShortcut ()); setorigin (c, base + '160 0 0');
    self.ar_hopjump = 1;
    RouteDecisionCheck ("active_action", !Argus_RouteCanShortcut ()); self.ar_hopjump = 0;
    self.ar_feettype = CONTENT_WATER;
    RouteDecisionCheck ("swimming_keeps_depth", !Argus_RouteCanShortcut ()); self.ar_feettype = CONTENT_EMPTY;
    self.ar_node = world;
    RouteDecisionCheck ("no_route", !Argus_RouteCanShortcut ()); self.ar_node = a;
    Argus_SetNext (c, self, a);
    RouteDecisionCheck ("cycle_is_bounded", !Argus_RouteCanShortcut ()); Argus_SetNext (c, self, world);

    Argus_NavLink (a, b); a.an_rjmask = 1; a.an_swimmask = 2;
    RouteDecisionCheck ("action_without_rockets", Argus_RouteLinkBit (a, b, self) == 2);
    a.an_nlinks = 1;
    RouteDecisionCheck ("rocket_only_requires_gear", Argus_RouteLinkBit (a, b, self) == 0);
    self.items = IT_ROCKET_LAUNCHER; self.ammo_rockets = 1;
    RouteDecisionCheck ("rocket_only_with_gear", Argus_RouteLinkBit (a, b, self) == 1);
    a.an_rjmask = 0; a.an_sprintmask = 1; a.an_nlinks = 2; self.ar_skill = 1;
    RouteDecisionCheck ("sprint_requires_skill", Argus_RouteLinkBit (a, b, self) == 2);
    a.an_sprintmask = 0; a.an_jumpmask = 1; a.an_nlinks = 1;
    setorigin (b, base + '80 0 100');
    RouteDecisionCheck ("impossible_jump_rejected", Argus_RouteLinkBit (a, b, self) == 0);
    setorigin (b, base + '80 0 0'); setorigin (self, base);
    RouteDecisionCheck ("jump_waits_for_seat", !Argus_WalkArrivalReady (a));
    self.flags = FL_ONGROUND;
    RouteDecisionCheck ("jump_ready_on_seat", Argus_WalkArrivalReady (a));
    a.an_jumpmask = 0; self.ar_hopswim = 1; self.flags = 0;
    RouteDecisionCheck ("bank_waits_for_ground", !Argus_WalkArrivalReady (a));
    self.flags = FL_ONGROUND; setorigin (self, base + '0 0 40');
    RouteDecisionCheck ("bank_waits_for_height", !Argus_WalkArrivalReady (a));
    setorigin (self, base); self.ar_wetlevel = 1;
    RouteDecisionCheck ("wading_bank_is_support", Argus_WalkArrivalReady (a));
    self.ar_mode = 2; self.ar_node = b; self.ar_goal = c;
    c.solid = SOLID_TRIGGER; self.ar_actionnode = world;
    RouteDecisionCheck ("action_starts_clock", !Argus_ActionBlocked (FALSE)
        && self.ar_actiontime == time);
    self.ar_actiontime = time - 3.1;
    RouteDecisionCheck ("action_times_out", Argus_ActionBlocked (FALSE));
    setorigin (self, base + '20 0 0');
    RouteDecisionCheck ("action_approach_renews", !Argus_ActionBlocked (FALSE)
        && self.ar_actiontime == time);
    self.ar_actiontime = time - 3.1; setorigin (self, base);
    RouteDecisionCheck ("action_oscillation_not_progress", Argus_ActionBlocked (FALSE));
    pause_clock = self.ar_actiontime;
    RouteDecisionCheck ("action_pause_suspends", !Argus_ActionBlocked (TRUE)
        && self.ar_actionnode == b
        && fabs (self.ar_actiontime - pause_clock - frametime) < 0.001);
    RouteDecisionCheck ("action_contact_does_not_renew", Argus_ActionBlocked (FALSE));
    Argus_ActionBlocked (FALSE); self.ar_actiontime = time - 3.1;
    self.ar_node = c;
    RouteDecisionCheck ("action_new_seat_resets", !Argus_ActionBlocked (FALSE));
    self.ar_goal = a; a.solid = SOLID_TRIGGER; self.ar_actiontime = time - 3.1;
    RouteDecisionCheck ("action_new_goal_resets", !Argus_ActionBlocked (FALSE));
    self.ar_mode = 1;
    RouteDecisionCheck ("action_direct_held", !Argus_ActionBlocked (FALSE));
    self.ar_mode = 2; self.ar_node = b; self.ar_goal = c; self.ar_taskgoal = c;
    Argus_ActionBlocked (FALSE); self.ar_actiontime = time - 3.1;
    self.ar_hopjump = 1; Argus_ActionObserve (FALSE);
    RouteDecisionCheck ("action_task_preserved", self.ar_taskgoal == c
        && self.ar_goal == c && self.ar_pending && self.ar_node == world && !self.ar_hopjump);
    self.ar_taskgoal = world; self.ar_node = b; self.ar_mode = 2;
    Argus_ActionBlocked (FALSE); self.ar_actiontime = time - 3.1;
    Argus_ActionObserve (FALSE);
    RouteDecisionCheck ("action_goal_shelved", self.ar_goal == world
        && c.ar_failtime == time && !self.ar_pending);
    self.ar_hoplift = 1; self.ar_liftwait = 1; self.ar_feettype = CONTENT_EMPTY;
    self.groundentity = world; self.flags = FL_ONGROUND;
    RouteDecisionCheck ("action_dry_wait_owned", Argus_ActionWaitOwned ());
    self.flags = 0;
    RouteDecisionCheck ("action_dry_airborne_wait_unowned", !Argus_ActionWaitOwned ());
    self.ar_feettype = CONTENT_WATER;
    RouteDecisionCheck ("action_floating_wait_unowned", !Argus_ActionWaitOwned ());
    self.flags = FL_ONGROUND;
    RouteDecisionCheck ("action_wading_wait_unowned", !Argus_ActionWaitOwned ());
    self.flags = 0; self.groundentity = b; b.classname = "plat";
    setsize (self, '-16 -16 -24', '16 16 32'); setorigin (self, base);
    setsize (b, '-32 -32 -8', '32 32 0'); setorigin (b, base - '0 0 24');
    RouteDecisionCheck ("action_rider_must_progress", !Argus_ActionWaitOwned ());
    setorigin (self, base + '0 0 64');
    RouteDecisionCheck ("action_stale_contact_unowned", !Argus_ActionWaitOwned ());
    self.ar_hoplift = 0; self.ar_liftwait = 0;
    RouteDecisionCheck ("action_no_wait_unowned", !Argus_ActionWaitOwned ());
    self.ar_hopswim = 0; self.ar_hopjump = 0;
    RouteDecisionCheck ("noise_walk_allowed", Argus_CanInvestigateNoise ());
    self.ar_hopjump = 1;
    RouteDecisionCheck ("noise_jump_held", !Argus_CanInvestigateNoise ()); self.ar_hopjump = 0;
    self.ar_hopswim = 1;
    RouteDecisionCheck ("noise_swim_held", !Argus_CanInvestigateNoise ()); self.ar_hopswim = 0;
    self.ar_hoplift = 1;
    RouteDecisionCheck ("noise_lift_held", !Argus_CanInvestigateNoise ()); self.ar_hoplift = 0;
    self.ar_hoptrain = 1;
    RouteDecisionCheck ("noise_train_held", !Argus_CanInvestigateNoise ()); self.ar_hoptrain = 0;
    self.ar_hoprj = 1;
    RouteDecisionCheck ("noise_rocket_held", !Argus_CanInvestigateNoise ()); self.ar_hoprj = 0;
    self.ar_hopdoor = 1;
    RouteDecisionCheck ("noise_door_held", !Argus_CanInvestigateNoise ()); self.ar_hopdoor = 0;
    self.ar_sprintstate = 1;
    RouteDecisionCheck ("noise_runup_held", !Argus_CanInvestigateNoise ()); self.ar_sprintstate = 0;
    self.ar_tactic = 1;
    RouteDecisionCheck ("noise_tactic_held", !Argus_CanInvestigateNoise ()); self.ar_tactic = 0;
    setorigin (a, base); setorigin (b, base + '80 0 0');
    setorigin (c, base + '160 0 0'); setorigin (self, base);
    self.ar_node = a; self.ar_mode = 2; self.ar_enemy = world;
    self.groundentity = world; self.flags = FL_ONGROUND;
    self.ar_feettype = CONTENT_EMPTY; self.ar_wetlevel = 0;
    self.ar_goal = world; self.ar_taskgoal = world;
    RouteDecisionCheck ("gait_plain_route_allowed", !Argus_GaitApproachAction ());
    a.an_liftmask = 1;
    RouteDecisionCheck ("gait_immediate_action", Argus_GaitApproachAction ()); a.an_liftmask = 0;
    b.an_jumpmask = 1;
    RouteDecisionCheck ("gait_second_action", Argus_GaitApproachAction ());
    setorigin (self, base - '300 0 0');
    RouteDecisionCheck ("gait_distant_action_allowed", !Argus_GaitApproachAction ());
    setorigin (self, base); self.ar_gaitpause = time + 1;
    RouteDecisionCheck ("gait_action_releases_hold", !Argus_GaitHold ()); b.an_jumpmask = 0;
    RouteDecisionCheck ("gait_plain_hold_kept", Argus_GaitHold ());
    dprint ("RDEC end checks "); dprint (ftos (rd_checks));
    dprint (" failures "); dprint (ftos (rd_failures)); dprint ("\n");
    self = saved; remove (actor); remove (a); remove (b); remove (c);
#endif
};
