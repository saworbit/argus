// Passive diagnostics only. No sensing, RNG, movement or gameplay writes.
// developer 1 + scratch4 590 enables the five-Hz snapshots independently of
// scratch1's existing decision/debug/fixture controls. Evidence is reported,
// not inferred: "visible" below means the bot's existing ar_seen stamp.
.float ar_bd_next;
.float ar_bd_valid;
.float ar_bd_best;
.vector ar_bd_pos;
.entity ar_bd_enemy;
.entity ar_bd_goal;
.entity ar_bd_node;
.float ar_bd_tactic;

// Vanilla builtin 25 accepts multiple strings (PF_VarString). Keep at most
// ONE ftos/vtos per call: original Quake shares their temporary buffer.
void(string a, string b, string c) Argus_BehaviourPrint = #25;

void() Argus_BehaviourReset =
{
    self.ar_bd_next = 0;
    self.ar_bd_valid = 0;
    self.ar_bd_best = 0;
    self.ar_bd_pos = '0 0 0';
    self.ar_bd_enemy = world;
    self.ar_bd_goal = world;
    self.ar_bd_node = world;
    self.ar_bd_tactic = 0;
};

void(string reason) Argus_BehaviourEvent =
{
    if (!cvar ("developer")) return;
    if (cvar ("scratch4") != 590 && cvar ("scratch4") != 592) return;
    Argus_BehaviourPrint ("BHVDBG ", self.netname, " t ");
    Argus_BehaviourPrint (ftos (time), " event ", reason);
    dprint ("\n");
};

void() Argus_BehaviourObserve =
{
    local string source, intent, reason;
    local float dist, gain, moved, mode;
    if (!cvar ("developer")) return;
    mode = cvar ("scratch4");
    // 591 measures observer computation without formatting/output; 592 is
    // the original fragmented output reference. Neither changes decisions.
    if (mode != 590 && mode != 591 && mode != 592) return;
    if (time < self.ar_bd_next) return;
    self.ar_bd_next = time + 0.2;

    source = "none";
    if (self.ar_enemy != world)
    {
        source = "remembered";
        if (self.ar_seen == time) source = "reported_visible";
    }
    else if (self.ar_sndtime > 0 && time < self.ar_sndtime + 2)
        source = "heard";

    // Descriptive state, not a new steering arbiter or exclusive last writer.
    intent = "wander";
    if (self.ar_goal != world) intent = "item_route";
    if (self.ar_enemy != world) intent = "combat";
    if (self.ar_pursuing) intent = "pursuit";
    if (self.ar_retreating) intent = "retreat";
    if (time < self.ar_dodgetime) intent = "dodge";
    if (self.ar_tactic) intent = "tactic";
    if (self.ar_liftwait || self.ar_hoplift || self.ar_hoptrain) intent = "mover";
    if (self.health <= 0) intent = "dead";

    reason = "sample";
    if (!self.ar_bd_valid) reason = "initial";
    else if (self.ar_enemy != self.ar_bd_enemy) reason = "target_changed";
    else if (self.ar_goal != self.ar_bd_goal) reason = "goal_changed";
    else if (self.ar_tactic != self.ar_bd_tactic) reason = "tactic_changed";
    dist = -1; gain = 0; moved = 0;
    if (self.ar_bd_valid) moved = vlen (self.origin - self.ar_bd_pos);
    if (self.ar_node != world)
    {
        dist = vlen (self.ar_node.origin - self.origin);
        if (self.ar_bd_valid && self.ar_node == self.ar_bd_node
            && self.ar_goal == self.ar_bd_goal)
        {
            gain = self.ar_bd_best - dist;
            if (dist < self.ar_bd_best) self.ar_bd_best = dist;
        }
        else self.ar_bd_best = dist;
    }
    // Negative gain is meaningful: displacement is not route progress.
    if (mode == 592)
    {
    dprint ("BHVDBG "); dprint (self.netname);
    dprint (" t "); dprint (ftos (time));
    dprint (" source "); dprint (source);
    dprint (" intent "); dprint (intent);
    dprint (" reason "); dprint (reason);
    dprint (" pos "); dprint (vtos (self.origin));
    dprint (" memory "); dprint (vtos (self.ar_lastseen));
    dprint (" goal "); dprint (self.ar_goal.classname);
    dprint (" node "); dprint (vtos (self.ar_node.origin));
    dprint (" distance "); dprint (ftos (dist));
    dprint (" gain "); dprint (ftos (gain));
    dprint (" moved "); dprint (ftos (moved));
    dprint (" mode "); dprint (ftos (self.ar_mode));
    dprint (" tactic "); dprint (ftos (self.ar_tactic));
    dprint (" dt "); dprint (ftos (frametime)); dprint ("\n");
    }
    else if (mode == 590)
    {
        Argus_BehaviourPrint ("BHVDBG ", self.netname, " t ");
        Argus_BehaviourPrint (ftos (time), " source ", source);
        Argus_BehaviourPrint (" intent ", intent, " reason ");
        Argus_BehaviourPrint (reason, " pos ", vtos (self.origin));
        Argus_BehaviourPrint (" memory ", vtos (self.ar_lastseen), " goal ");
        Argus_BehaviourPrint (self.ar_goal.classname, " node ", vtos (self.ar_node.origin));
        Argus_BehaviourPrint (" distance ", ftos (dist), "");
        Argus_BehaviourPrint (" gain ", ftos (gain), "");
        Argus_BehaviourPrint (" moved ", ftos (moved), "");
        Argus_BehaviourPrint (" mode ", ftos (self.ar_mode), "");
        Argus_BehaviourPrint (" tactic ", ftos (self.ar_tactic), "");
        Argus_BehaviourPrint (" dt_ms ", ftos (frametime * 1000), "\n");
    }
    self.ar_bd_valid = 1;
    self.ar_bd_pos = self.origin;
    self.ar_bd_enemy = self.ar_enemy;
    self.ar_bd_goal = self.ar_goal;
    self.ar_bd_node = self.ar_node;
    self.ar_bd_tactic = self.ar_tactic;
};
