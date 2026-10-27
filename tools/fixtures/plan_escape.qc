// Private physical fixture. After setup, only the normal bot code moves
// the subject or selects another goal. Compiled only by the verifier.
entity pe_bot, pe_goal;
vector pe_start;
float pe_begin, pe_next, pe_frames, pe_done, pe_case, pe_solid;

void() PlanEscapeFixture =
{
    local entity b, saved;
    local vector delta;
    local float released, chosen, escaped, ok;
    if (time < 2 || pe_done) return;
    if (!pe_begin)
    {
        if (mapname != "dm2") { error ("Physical fixture needs dm2"); return; }
        pe_case = cvar ("scratch2");
        b = argus_bots;
        while (b != world)
        {
            Argus_Nav_Abort (b);
            if (b.ar_slot == 1) pe_bot = b;
            else { b.solid = SOLID_NOT; b.cam_active = 1; b.button0 = 0; }
            b = b.ar_chain;
        }
        pe_goal = find (world, classname, "item_armor2");
        while (pe_goal != world && vlen (pe_goal.origin - '1312 -952 20') > 50)
            pe_goal = find (pe_goal, classname, "item_armor2");
        if (pe_bot == world || pe_goal == world) { error ("Physical fixture setup"); return; }
        saved = self; self = pe_bot;
        Argus_BaseStats (); Argus_AvoidClear ();
        pe_start = '1424 -983.6 20'; setorigin (self, pe_start);
        self.velocity = '0 0 0'; self.flags = self.flags | FL_ONGROUND;
        self.ar_goal = pe_goal; self.ar_goalstart = time;
        self.ar_node = world; self.ar_pending = 0; self.ar_mode = 1;
        self.ar_nextai = time + 0.2; self.ar_nextstall = time + 0.7;
        self.ar_lastpos = self.origin; self.ar_stucktime = 0;
        self.ar_stallrun = 0; self.ar_stalls = 0;
        self.ar_door = world; self.ar_doorbtn = world;
        self.ar_enemy = world; self.ar_sndtime = 0;
        if (pe_case == 2)
        {
            pe_goal.solid = SOLID_NOT; pe_goal.think = SUB_regen;
            pe_goal.nextthink = time + 15;
            self.armorvalue = 150; self.armortype = 0.6;
            self.items = self.items | IT_ARMOR2;
        }
        pe_solid = pe_goal.solid;
        ar_tacfixture_until = time + 100; ar_tacfixture_bot = self;
        pe_begin = time;
        dprint ("PEFIX begin dm2 case "); dprint (ftos (pe_case));
        dprint (" start "); dprint (vtos (pe_start));
        dprint (" solid "); dprint (ftos (pe_solid));
        dprint (" respawn "); dprint (ftos (pe_goal.nextthink - time));
        dprint (" actor_solid "); dprint (ftos (pointcontents (self.origin) == CONTENT_SOLID));
        dprint ("\n");
        self = saved;
    }
    pe_frames = pe_frames + 1;
    if (time < pe_next) return;
    pe_next = time + 0.2;
    delta = pe_bot.origin - pe_start; delta_z = 0;
    released = (pe_bot.ar_goal != pe_goal && pe_goal.ar_claimer == pe_bot
        && pe_bot.ar_stalls >= 2 && pe_goal.solid == pe_solid);
    chosen = (pe_bot.ar_goal != world && pe_bot.ar_goal != pe_goal
        && Argus_GoalOK (pe_bot.ar_goal));
    escaped = vlen (delta) > 220;
    dprint ("PEFIX sample t "); dprint (ftos (time - pe_begin));
    dprint (" pos "); dprint (vtos (pe_bot.origin));
    dprint (" released "); dprint (ftos (released));
    dprint (" chosen "); dprint (ftos (chosen));
    dprint (" escaped "); dprint (ftos (escaped));
    dprint (" mode "); dprint (ftos (pe_bot.ar_mode));
    dprint (" goal "); dprint (pe_bot.ar_goal.classname);
    dprint (" hp "); dprint (ftos (pe_bot.health));
    dprint (" frames "); dprint (ftos (pe_frames)); dprint ("\n");
    ok = (released && chosen && escaped && pe_bot.health == 100);
    if (ok || time > pe_begin + 12)
    {
        pe_done = 1;
        ar_tacfixture_bot = world; // end observation; stop owned engine next
        pe_bot.button0 = 0; pe_bot.velocity = '0 0 0';
        dprint ("PEFIX end ok "); dprint (ftos (ok)); dprint ("\n");
        dprint ("PEFIX cleanup owned_engine_pending_stop\n");
    }
};
