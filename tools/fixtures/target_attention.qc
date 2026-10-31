// Private decision contracts. Production perception and pain choose targets;
// BSP traces establish visible/hidden premises, not a Python policy model.
float at_done, at_checks, at_failures, at_previous, at_dt;
entity at_bot, at_primary, at_challenger, at_goal;
vector at_seat, at_primarypos, at_challengerpos, at_hidden;

void(string label, float ok) AttentionCheck =
{
    at_checks = at_checks + 1;
    if (!ok) at_failures = at_failures + 1;
    dprint ("ATFIX check "); dprint (label); dprint (" ");
    dprint (ftos (ok)); dprint ("\n");
};

void() AttentionPrime =
{
    self = at_bot;
    self.ar_skill = 2; self.ar_reactbase = 0.3;
    self.ar_tactic = 0; self.ar_nemesis = world; self.ar_nemkills = 0;
    self.ar_retreating = 0; self.ar_retreatclass = AR_THREAT_UNKNOWN;
    self.ar_retreatlock = 0; self.ar_covertime = 0;
    self.ar_enemy = at_primary; self.ar_goal = at_goal;
    self.ar_react = 0; self.ar_glimpse = 0;
    self.ar_lastfoe = world; self.ar_sndtime = 0;
    self.health = 100; self.armorvalue = 0;
    setorigin (self, at_seat); self.velocity = '0 0 0';
    self.angles = vectoangles (at_primarypos - at_seat); self.angles_x = 0;
    at_primary.health = 100; at_primary.cam_active = 0;
    at_primary.super_damage_finished = 0; at_primary.invincible_finished = 0;
    at_primary.invisible_finished = 0;
    at_challenger.health = 100; at_challenger.cam_active = 0;
    at_challenger.super_damage_finished = 0; at_challenger.invincible_finished = 0;
    at_challenger.invisible_finished = 0;
    setorigin (at_primary, at_primarypos);
    setorigin (at_challenger, at_challengerpos);
#ifdef ATTENTION_CANDIDATE
    self.ar_hurtfoe = world; self.ar_hurtfoetime = 0;
    self.ar_targetscan = 0; self.ar_targethold = 0;
#endif
    Argus_ObservationReset ();
    Argus_ObserveEnemy (at_primary);
};

void() AttentionHit =
{
    self.health = self.health - 10;
    Argus_Pain (at_challenger, 10);
};

void() TargetAttentionFixture =
{
    local entity b, n, saved;
    local float haveprimary, havechallenger, havehidden, d, primarydistance;
    local float calls, firstcalls, held, savedcoop;
    if (at_done) return;
    if (at_previous > 0) at_dt = time - at_previous;
    at_previous = time;
    if (time < 2) return;
    at_done = 1; saved = self;
    dprint ("BHVRPL begin target_attention\nATFIX begin dt_ms ");
    dprint (ftos (at_dt * 1000)); dprint ("\n");
    b = argus_bots;
    while (b != world)
    {
        Argus_Nav_Abort (b);
        b.cam_active = 1; b.solid = SOLID_NOT; b.movetype = MOVETYPE_NONE;
        if (b.ar_slot == 0) at_bot = b;
        else b.health = 0;
        b = b.ar_chain;
    }
    if (at_bot == world) { dprint ("ATFIX refused missing_bot\n"); return; }
    self = at_bot; at_seat = self.origin;
    // Select actual graph seats visible from this spawn. Their distances
    // differ by less than the switch margin, so the hit/pent must matter.
    n = find (world, classname, "argus_node");
    while (n != world)
    {
        d = vlen (n.origin - at_seat);
        if (d > 300 && d < 1000)
        {
            traceline (at_seat + '0 0 22', n.origin + '0 0 22', TRUE, self);
            if (trace_fraction == 1)
            {
                if (!haveprimary)
                { haveprimary = 1; at_primarypos = n.origin; primarydistance = d; }
                else if (!havechallenger && fabs (d - primarydistance) < 200
                    && vlen (n.origin - at_primarypos) > 48)
                { havechallenger = 1; at_challengerpos = n.origin; }
            }
        }
        if (!havehidden && d > 100 && d < 1600)
        {
            traceline (at_seat + '0 0 22', n.origin + '0 0 22', TRUE, self);
            if (trace_fraction < 1) { havehidden = 1; at_hidden = n.origin; }
        }
        n = find (n, classname, "argus_node");
    }
    if (!haveprimary || !havechallenger || !havehidden)
    { dprint ("ATFIX refused geometry\n"); return; }
    at_primary = spawn (); at_primary.classname = "player";
    at_primary.netname = "attention_primary"; at_primary.weapon = IT_SHOTGUN;
    at_challenger = spawn (); at_challenger.classname = "player";
    at_challenger.netname = "attention_challenger"; at_challenger.weapon = IT_SHOTGUN;
    at_goal = spawn (); at_goal.classname = "argus_task_goal";
    AttentionPrime ();
    AttentionCheck ("geometry", Argus_CanSee (at_primary) && Argus_CanSee (at_challenger));

    Argus_Perceive ();
    AttentionCheck ("minor_difference_keeps_focus", self.ar_enemy == at_primary);
    AttentionPrime ();
    self.ar_secondary = at_challenger; self.ar_secondaryscan = time + 1;
    AttentionHit (); Argus_Perceive ();
    AttentionCheck ("answers_visible_attacker", self.ar_enemy == at_challenger);
    AttentionCheck ("switch_reaction_delayed", self.ar_enemy == at_challenger && self.ar_react > time);
    AttentionCheck ("goal_retained", self.ar_goal == at_goal);
    AttentionCheck ("secondary_is_not_primary", self.ar_secondary != self.ar_enemy);

    AttentionPrime (); at_primary.invincible_finished = time + 20;
    Argus_ObserveEnemy (at_primary); Argus_Perceive ();
    AttentionCheck ("avoids_invulnerable_fixation", self.ar_enemy == at_challenger);

    AttentionPrime (); self.health = 45; self.ar_retreating = 1;
    self.ar_retreatclass = AR_THREAT_BEAM;
    self.ar_covertime = time + 5; self.ar_retreatlock = time + 10;
    AttentionHit (); Argus_Perceive ();
    held = self.ar_retreating && self.ar_retreatlock == time + 10;
    if (self.ar_enemy == at_challenger)
        held = held && self.ar_retreatclass == self.ar_threatclass && !self.ar_covertime;
    AttentionCheck ("retreat_intent_retained", held);

    AttentionPrime (); AttentionHit ();
#ifdef ATTENTION_CANDIDATE
    self.ar_targethold = time + 1;
#endif
    Argus_Perceive ();
    AttentionCheck ("commitment_held", self.ar_enemy == at_primary);
    AttentionPrime (); AttentionHit ();
#ifdef ATTENTION_CANDIDATE
    self.ar_targetscan = time + 1;
#endif
    Argus_Perceive ();
    AttentionCheck ("scan_clock_held", self.ar_enemy == at_primary);

    AttentionPrime (); self.ar_skill = 0; AttentionHit (); Argus_Perceive ();
    AttentionCheck ("warmup_keeps_policy", self.ar_enemy == at_primary);
    AttentionPrime (); self.ar_tactic = 1; AttentionHit (); Argus_Perceive ();
    AttentionCheck ("tactic_keeps_owner", self.ar_enemy == at_primary);

    AttentionPrime (); setorigin (at_challenger, at_hidden);
    AttentionHit (); calls = at_rngcalls; Argus_Perceive ();
    firstcalls = at_rngcalls - calls;
    held = self.ar_enemy == at_primary && self.ar_obsenemy == at_primary;
    AttentionPrime (); setorigin (at_challenger, at_hidden);
    at_challenger.health = 999; at_challenger.armorvalue = 200;
    at_challenger.ammo_rockets = 100; at_challenger.weapon = IT_LIGHTNING;
    at_challenger.super_damage_finished = time + 20;
    at_challenger.invincible_finished = time + 20;
    at_challenger.invisible_finished = time + 20;
    AttentionHit (); calls = at_rngcalls; Argus_Perceive ();
    AttentionCheck ("hidden_attacker_not_seen", held && self.ar_enemy == at_primary
        && self.ar_obsenemy == at_primary);
    AttentionCheck ("hidden_changes_preserve_rng", at_rngcalls - calls == firstcalls && !firstcalls);

    AttentionPrime (); setorigin (at_primary, at_hidden);
    at_primary.invincible_finished = time + 20;
    Argus_Perceive ();
    AttentionCheck ("hidden_current_uses_cached_cues", self.ar_enemy == at_primary && self.ar_obspower == 0);
    AttentionPrime (); at_challenger.invisible_finished = time + 20;
    AttentionHit (); Argus_Perceive ();
    AttentionCheck ("ring_still_requires_sight", self.ar_enemy == at_primary);
    AttentionPrime (); AttentionHit ();
#ifdef ATTENTION_CANDIDATE
    self.ar_hurtfoetime = time - 3;
#endif
    Argus_Perceive ();
    AttentionCheck ("old_aggression_expires", self.ar_enemy == at_primary);

    AttentionPrime (); savedcoop = coop; coop = 1;
    AttentionHit (); coop = savedcoop;
#ifdef ATTENTION_CANDIDATE
    held = self.ar_hurtfoe == world;
#else
    held = 1;
#endif
    AttentionCheck ("ally_damage_not_hostile", held && self.ar_enemy == at_primary);
    AttentionPrime (); Argus_Pain (world, 10); Argus_Pain (self, 10);
#ifdef ATTENTION_CANDIDATE
    held = self.ar_hurtfoe == world;
#else
    held = 1;
#endif
    AttentionCheck ("world_self_not_hostile", held);
    AttentionPrime (); AttentionHit (); Argus_ObservationRemoved (at_challenger);
#ifdef ATTENTION_CANDIDATE
    held = self.ar_hurtfoe == world && !self.ar_hurtfoetime;
#else
    held = 1;
#endif
    AttentionCheck ("removed_attacker_forgotten", held && self.ar_enemy == at_primary);
    AttentionPrime (); AttentionHit (); Argus_BaseStats ();
#ifdef ATTENTION_CANDIDATE
    held = self.ar_hurtfoe == world && !self.ar_hurtfoetime
        && !self.ar_targetscan && !self.ar_targethold;
#else
    held = self.ar_enemy == world;
#endif
    AttentionCheck ("respawn_clears_attention", held);
    self = saved;
    dprint ("ATFIX end checks "); dprint (ftos (at_checks));
    dprint (" failures "); dprint (ftos (at_failures)); dprint ("\n");
};
