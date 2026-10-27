// Private deadline, co-op controller and route-cycle inputs. No movement script.
// Epoch declaration is supplied by the verifier only for pre-fix controls.
// INSERT_EPOCH_DECLARATION
void() PlanEdgeCases =
{
    local entity saved, peer, n, first, second, third;
    local float wascoop, wasdm, serial, count, ok;
    local vector p;
    saved = self; wascoop = coop; wasdm = deathmatch;
    first = find (world, classname, "argus_node");
    second = find (first, classname, "argus_node");
    third = find (second, classname, "argus_node");
    if (first == world || second == world || third == world) { error ("Edge fixture nodes"); return; }

    coop = 1; deathmatch = 0;
    PlanSetup (plan_a); self.ar_goal_count = 0; self.ar_fetchcool = 0;
    Argus_GoalPush (GOAL_FETCH, plan_a, plan_a.origin, 75, time + 60, 0);
    PlanStep (plan_seed); PlanStep (plan_seed + '0 40 0'); PlanStep (plan_seed + '0 40 0');
    Argus_CoopThink ();
    PlanCheck ("fetch_stall_rests", self.ar_goal != plan_a);
    PlanCheck ("fetch_stack_kept", Argus_GoalTopKind () == GOAL_FETCH && Argus_GoalTopSubj () == plan_a);
    peer = argus_bots; while (peer != world && peer == self) peer = peer.ar_chain;
    if (peer == world) { error ("Edge fixture peer"); return; }
    self = peer; self.ar_goal_count = 0; self.ar_goal = world; self.ar_fetchcool = 0;
    Argus_GoalPush (GOAL_FETCH, plan_a, plan_a.origin, 75, time + 60, 0);
    Argus_CoopThink ();
    PlanCheck ("fetch_peer_independent", self.ar_goal == plan_a);
    self.ar_goal_count = 0; self.ar_goal = world; self = saved;
    self.ar_goal = world; self.ar_fetchcool = time - 0.1;
    Argus_CoopThink ();
    PlanCheck ("fetch_retry_after_rest", self.ar_goal == plan_a);
    // A retry starts a fresh deadline, rather than expiring immediately.
    self.ar_goal = world; self.ar_goalstart = time - 21;
    Argus_CoopThink ();
    self.ar_nextai = time - 0.1; self.ar_nextstall = time + 10;
    Argus_AI ();
    PlanCheck ("fetch_retry_gets_fresh_deadline", self.ar_goal == plan_a && self.ar_goalstart >= time - 0.1);
    self.ar_goalstart = time - 21; self.ar_enemy = peer;
    self.ar_nextai = time - 0.1; Argus_AI ();
    PlanCheck ("fetch_combat_preserves_deadline", self.ar_goal == plan_a && self.ar_goalstart >= time - 15.1);
    self.ar_enemy = world;

    // Real route-failure maintenance already has a rest; it must belong to
    // the failed subject, without suppressing a different requested errand.
    PlanSetup (plan_a); self.ar_goal_count = 0; self.ar_fetchcool = 0;
    Argus_GoalPush (GOAL_FETCH, plan_a, plan_a.origin, 75, time + 60, 0);
    self.ar_routefail = 1; self.ar_nextai = time - 0.1;
    self.ar_nextstall = time + 10; Argus_AI ();
    self.ar_goal = world; Argus_CoopThink ();
    PlanCheck ("fetch_routefail_rests", self.ar_goal != plan_a);
    Argus_GoalPop ();
    Argus_GoalPush (GOAL_FETCH, plan_b, plan_b.origin, 75, time + 60, 0);
    Argus_CoopThink ();
    PlanCheck ("fetch_new_subject_allowed", self.ar_goal == plan_b);

    PlanSetup (plan_a); self.ar_goal_count = 0; self.ar_fetchcool = 0;
    Argus_GoalPush (GOAL_FETCH, plan_a, plan_a.origin, 75, time + 60, 0);
    self.ar_goalstart = time - 21; self.ar_nextai = time - 0.1;
    self.ar_nextstall = time + 10; Argus_AI ();
    self.ar_goal = world; Argus_CoopThink ();
    PlanCheck ("fetch_timeout_rests", self.ar_goal != plan_a);
    self.ar_goal_count = 0; coop = wascoop; deathmatch = wasdm;

    PlanSetup (plan_a); Argus_PlanObserve (FALSE, world);
    self.ar_goalstart = time - 21;
    Argus_PlanObserve (FALSE, first);
    PlanCheck ("detour_renews_deadline", self.ar_goalstart >= time - 0.1);
    self.ar_nextai = time - 0.1; self.ar_nextstall = time + 10;
    Argus_AI ();
    PlanCheck ("detour_survives_old_deadline", self.ar_goal == plan_a);

    PlanSetup (plan_a); Argus_PlanObserve (FALSE, world);
    count = 0; ok = 1; n = first;
    while (n != world && count < 24)
    {
        // A long detour can initially increase straight-line goal distance.
        p = plan_seed - count * '20 0 0'; setorigin (self, p);
        self.ar_stallrun = 1; self.ar_goalstart = time - 21;
        Argus_PlanObserve (FALSE, n);
        if (self.ar_stallrun != 0 || self.ar_goalstart < time - 0.1) ok = 0;
        count = count + 1; n = find (n, classname, "argus_node");
    }
    PlanCheck ("long_unique_detour", ok && count == 24 && self.ar_goal == plan_a);

    PlanSetup (plan_a); self.ar_taskgoal = plan_a;
    self.ar_goalstart = time + 3600;
    Argus_PlanObserve (FALSE, first);
    PlanCheck ("fixed_task_deadline_preserved", self.ar_goalstart == time + 3600);
    self.ar_taskgoal = world;

    PlanSetup (plan_a); Argus_PlanObserve (FALSE, first);
    setorigin (self, plan_seed - '100 0 0'); Argus_PlanObserve (FALSE, second);
    self.ar_stallrun = 1; setorigin (self, plan_seed);
    Argus_PlanObserve (FALSE, first);
    PlanCheck ("two_node_cycle_not_progress", self.ar_stallrun == 1);
    PlanCheck ("cycle_best_stays_monotonic", self.ar_plan_best <= vlen (Argus_GoalPoint (plan_a) - plan_seed));

    PlanSetup (plan_a); Argus_PlanObserve (FALSE, first);
    Argus_PlanObserve (FALSE, second); Argus_PlanObserve (FALSE, third);
    self.ar_stallrun = 1; Argus_PlanObserve (FALSE, first);
    PlanCheck ("multi_node_cycle_not_progress", self.ar_stallrun == 1);
    self.ar_goalstart = time - 21; Argus_PlanObserve (FALSE, second);
    self.ar_nextai = time - 0.1; self.ar_nextstall = time + 10;
    Argus_AI ();
    PlanCheck ("cycle_eventually_reconsiders", self.ar_goal != plan_a);

    PlanSetup (plan_a); Argus_PlanObserve (FALSE, first);
    self.ar_goal = plan_b; self.ar_stallrun = 1;
    Argus_PlanObserve (FALSE, first);
    PlanCheck ("new_goal_gets_new_visits", self.ar_stallrun == 0);
    self = peer; PlanSetup (plan_a); Argus_PlanObserve (FALSE, world);
    self.ar_stallrun = 1; Argus_PlanObserve (FALSE, first);
    PlanCheck ("visit_marks_per_bot", self.ar_stallrun == 0);
    self.ar_stallrun = 1; Argus_PlanObserve (FALSE, first);
    PlanCheck ("peer_revisit_not_progress", self.ar_stallrun == 1);
    self = saved;

    PlanSetup (plan_a); serial = argus_plan_serial;
    argus_plan_serial = 16777215;
    Argus_PlanObserve (FALSE, first);
    PlanCheck ("epoch_rollover", argus_plan_serial == 1 && self.ar_stallrun == 0);
    argus_plan_serial = serial + 1;
    peer.ar_goal = world; peer.ar_goal_count = 0;
    coop = wascoop; deathmatch = wasdm;
};
