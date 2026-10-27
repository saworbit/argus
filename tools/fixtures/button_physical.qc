// PRIVATE physical button comparison. Initial placement and wish only.
entity bp_actor, bp_button;
float bp_begin, bp_next, bp_done, bp_frames, bp_touches, bp_context_bad, bp_support;

void() ButtonPhysicalFixture =
{
    local entity b, saved;
    local float kind;
    if (time < 2 || bp_done) return;
    kind = cvar ("scratch2");
    if (!bp_begin)
    {
        b = argus_bots;
        while (b != world)
        {
            b.solid = SOLID_NOT; b.cam_active = 1; b.button0 = 0;
            if (kind == 1 && b.ar_slot == 1) bp_actor = b;
            b = b.ar_chain;
        }
        ar_tacfixture_until = time + 100;
        if (kind == 2)
        {
            b = find (world, classname, "player");
            while (b != world)
            {
                if ((b.flags & FL_CLIENT) && b.netname == "labprobe") bp_actor = b;
                b = find (b, classname, "player");
            }
        }
        if (bp_actor == world) return;
        b = find (world, classname, "func_button");
        while (b != world)
        {
            if (b.model == "*16") bp_button = b;
            b = find (b, classname, "func_button");
        }
        if (bp_button == world) { error ("BPFIX missing real button"); return; }
        saved = self; self = bp_actor;
        if (kind == 1)
        {
            Argus_BaseStats (); Argus_AvoidClear (); Argus_Nav_Abort (self); Argus_TacticReset ();
            self.ar_nextai = time + 100; self.ar_mode = 1;
            self.ar_goal = spawn (); self.ar_goal.classname = "button_fixture_goal";
            self.ar_goal.solid = SOLID_TRIGGER;
            setsize (self.ar_goal, '-16 -16 -24', '16 16 32');
            setorigin (self.ar_goal, '-224 288 320');
            self.ar_moveyaw = 180; self.ar_liftwait = 0;
            ar_tacfixture_bot = self;
        }
        self.solid = SOLID_SLIDEBOX; self.cam_active = 0; self.health = 100;
        setsize (self, '-16 -16 -24', '16 16 32');
        setorigin (self, '-45 288 320'); self.velocity = '0 0 0';
        self.flags = self.flags | FL_ONGROUND;
        self.angles = '0 180 0'; self.v_angle = self.angles; self.fixangle = 1;
        bp_begin = time;
        dprint ("BHVRPL begin button_physical\nBPFIX begin case "); dprint (ftos (kind));
        dprint (" start "); dprint (vtos (self.origin)); dprint ("\n");
        self = saved;
    }
    bp_frames = bp_frames + 1;
    if (bp_actor.groundentity == bp_button && (bp_actor.flags & FL_ONGROUND)) bp_support = 1;
    if (time >= bp_next || bp_actor.origin_x < -160 || time >= bp_begin + 6)
    {
        bp_next = time + 0.2;
        dprint ("BPFIX sample t "); dprint (ftos (time - bp_begin));
        dprint (" pos "); dprint (vtos (bp_actor.origin));
        dprint (" state "); dprint (ftos (bp_button.state));
        dprint (" touches "); dprint (ftos (bp_touches));
        dprint (" support "); dprint (ftos (bp_actor.groundentity == bp_button));
        dprint (" grounded "); dprint (ftos ((bp_actor.flags & FL_ONGROUND) != 0));
        dprint (" hp "); dprint (ftos (bp_actor.health));
        dprint (" frames "); dprint (ftos (bp_frames)); dprint ("\n");
    }
    if (bp_actor.origin_x < -160 || time >= bp_begin + 6)
    {
        bp_done = 1;
        dprint ("BPFIX end touched "); dprint (ftos (bp_touches > 0));
        dprint (" activated "); dprint (ftos (bp_button.state != STATE_BOTTOM));
        dprint (" owner "); dprint (ftos (bp_button.enemy == bp_actor));
        dprint (" ctx "); dprint (ftos (!bp_context_bad));
        dprint (" support "); dprint (ftos (bp_support)); dprint ("\n");
        dprint ("BPFIX cleanup owned_engine_pending_stop\n");
    }
};

// Passive callback-context guard, invoked in place of the private call site.
void() ButtonSupportGuard =
{
    local entity expectedself, expectedother, expectedactivator;
    expectedself = self; expectedother = other; expectedactivator = activator;
    if (self == bp_actor && self.groundentity == bp_button && (self.flags & FL_ONGROUND)) bp_support = 1;
    Argus_SupportButton ();
    if (self != expectedself || other != expectedother || activator != expectedactivator)
        bp_context_bad = 1;
};
