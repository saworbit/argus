// Private physical waypoint-entry fixture. Only initial placement/route is
// assigned. Scheduled bot execution owns every subsequent step and handoff.
entity oe_bot, oe_goal, oe_from, oe_to;
float oe_started, oe_next, oe_frames, oe_done, oe_case, oe_contact, oe_slide_next;
vector oe_start, oe_contactpos;

void() OffsetEntryTouch =
{
    if (other != oe_bot || oe_contact) return;
    oe_contact = time; oe_contactpos = other.origin;
    dprint ("OFFIX contact t "); dprint (ftos (time - oe_started));
    dprint (" pos "); dprint (vtos (other.origin));
    dprint (" active "); dprint (ftos (other.ar_goal == self)); dprint ("\n");
    self.solid = SOLID_NOT;
};

void() OffsetEntryFixture =
{
    local entity b, saved;
    local float active, ok;
    if (time < 2 || oe_done) return;
    if (!oe_started)
    {
        if (mapname != "e1m2" || coop || !deathmatch) { error ("OFFIX wrong world"); return; }
        oe_case = cvar ("scratch2");
        b = argus_bots;
        while (b != world)
        {
            Argus_Nav_Abort (b);
            if (b.ar_slot == 1) oe_bot = b;
            else { b.solid = SOLID_NOT; b.cam_active = 1; b.button0 = 0; }
            b = b.ar_chain;
        }
        b = find (world, classname, "argus_node");
        while (b != world)
        {
            if (vlen (b.origin - '1361 33 320') < 1) oe_from = b;
            if (vlen (b.origin - '1361 -191 320') < 1) oe_to = b;
            b = find (b, classname, "argus_node");
        }
        if (oe_bot == world || oe_from == world || oe_to == world)
        { error ("OFFIX missing setup entity"); return; }
        saved = self; self = oe_bot;
        Argus_BaseStats (); Argus_AvoidClear (); Argus_TacticReset ();
        self.ar_tactic_settle = 0; self.ar_retreating = 0; self.ar_dodgetime = 0;
        self.ar_hopjump = 0; self.ar_hopspeed = 0; self.ar_sprintstate = 0;
        self.ar_hoprj = 0; self.ar_hoplift = 0; self.ar_hopswim = 0;
        self.ar_hoptrain = 0; self.ar_hopdoor = 0; self.ar_liftwait = 0;
        self.ar_jump = 0; self.ar_routefail = 0; self.ar_failstreak = 0;
        self.ar_traptime = -100; self.ar_stucktime = 0;
        self.ar_enemy = world; self.ar_sndtime = 0;
        self.ar_door = world; self.ar_doorbtn = world; self.ar_goal_count = 0;
        self.ar_greeted = 1; self.angles_y = 270; self.ar_moveyaw = 270;
        oe_start = '1361 33 320';
        if (oe_case == 2) oe_start = '1348 32 320';
        if (oe_case == 3) oe_start = '1348.9 32 358.7';
        if (oe_case == 4) oe_start = '1361 33 358.7';
        setorigin (self, oe_start); self.velocity = '0 0 0';
        self.flags = self.flags | FL_ONGROUND;
        if (oe_case >= 3)
        {
            self.flags = self.flags - (self.flags & FL_ONGROUND);
            self.velocity = '0 -160 0';
        }
        oe_goal = spawn (); oe_goal.classname = "offset_entry_goal";
        oe_goal.solid = SOLID_TRIGGER; oe_goal.movetype = MOVETYPE_NONE;
        setsize (oe_goal, '-16 -16 -24', '16 16 32');
        setorigin (oe_goal, oe_to.origin); oe_goal.touch = OffsetEntryTouch;
        self.ar_goal = oe_goal; self.ar_goalstart = time;
        oe_goal.ar_goalnode = oe_to; oe_goal.ar_gnodeset = 1;
        self.ar_routegen = self.ar_routegen + 1;
        Argus_SetNext (oe_from, self, oe_to); Argus_SetNext (oe_to, self, world);
        self.ar_node = oe_from; self.ar_pending = 0; self.ar_mode = 2;
        self.ar_lastpos = self.origin; self.ar_nextstall = time + 0.7;
        self.ar_nextai = time + 0.2;
        ar_tacfixture_until = time + 100; ar_tacfixture_bot = self;
        oe_started = time;
        dprint ("BHVRPL begin offset_entry\nOFFIX begin case "); dprint (ftos (oe_case));
        dprint (" start "); dprint (vtos (oe_start));
        dprint (" solid "); dprint (ftos (pointcontents (self.origin) == CONTENT_SOLID));
        dprint ("\n"); self = saved;
    }
    oe_frames = oe_frames + 1;
    active = (oe_bot.ar_goal == oe_goal);
    if (time >= oe_next || oe_contact || !active || time > oe_started + 6)
    {
        oe_next = time + 0.1;
        dprint ("OFFIX sample t "); dprint (ftos (time - oe_started));
        dprint (" pos "); dprint (vtos (oe_bot.origin));
        dprint (" active "); dprint (ftos (active));
        dprint (" from "); dprint (ftos (oe_bot.ar_node == oe_from));
        dprint (" hp "); dprint (ftos (oe_bot.health));
        dprint (" frames "); dprint (ftos (oe_frames)); dprint ("\n");
    }
    if (oe_contact || !active || time > oe_started + 6 || oe_bot.health != 100)
    {
        ok = (oe_contact && oe_bot.health == 100);
        dprint ("OFFIX end ok "); dprint (ftos (ok)); dprint ("\n");
        oe_done = 1; ar_tacfixture_bot = world;
        oe_bot.velocity = '0 0 0'; oe_bot.button0 = 0;
        Argus_Nav_Abort (oe_bot); remove (oe_goal);
        dprint ("OFFIX cleanup owned_engine_pending_stop\n");
    }
};
