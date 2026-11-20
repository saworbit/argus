entity pl_bot, pl_goal;
vector pl_start, pl_cue;
float pl_begin, pl_done, pl_frames;

void() PursuitLiveFrame =
{
    local entity bot, saved;
    local float owns_steering, before_yaw, feet, fitted;
    saved = self;
    if (pl_done) return;
    if (time < 2 || argus_bots == world) { Argus_FrameAll (); return; }
    if (!pl_begin)
    {
        if (mapname == "dm2") { pl_start = '1281 -599 192'; pl_cue = '1441 -375 184'; }
        else if (mapname == "dm4") { pl_start = '529 -407 24'; pl_cue = '337 -599 24'; }
        else error ("PL wrong map");
        bot = argus_bots;
        while (bot != world)
        {
            Argus_Nav_Abort (bot);
            if (bot.ar_slot == 0) pl_bot = bot;
            else
            {
                bot.solid = SOLID_NOT; bot.movetype = MOVETYPE_NONE;
                bot.takedamage = DAMAGE_NO; bot.think = SUB_Null; bot.nextthink = 0;
            }
            bot = bot.ar_chain;
        }
        if (pl_bot == world) error ("PL missing bot");
        self = pl_bot;
        Argus_BaseStats (); Argus_TacticReset (); Argus_AvoidClear ();
        self.ar_enemy = world; self.ar_node = world; self.ar_mode = 0;
        self.ar_hopjump = 0; self.ar_hoprj = 0; self.ar_hoplift = 0; self.ar_hopswim = 0;
        self.ar_hoptrain = 0; self.ar_hopdoor = 0; self.ar_sprintstate = 0;
        self.ar_door = world; self.ar_hopair = 0; self.ar_stallflight = 0;
        self.ar_liftwait = 0; self.ar_retreating = 0; self.ar_jump = 0;
        self.ar_skill = 1; self.ar_moveyaw = 0; self.velocity = '0 0 0';
        setorigin (self, pl_start + '0 0 12');
        self.flags = self.flags - (self.flags & FL_ONGROUND); self.groundentity = world;
        fitted = droptofloor ();
        dprint ("PL support "); dprint (ftos (fitted)); dprint (" at "); dprint (vtos (self.origin));
        dprint (" entity "); dprint (self.groundentity.classname); dprint ("\n");
        if (!fitted) error ("PL no starting floor");
        if (vlen (self.origin - pl_start) > 3) error ("PL settled too far from the requested seat");
        pl_goal = spawn (); self.ar_goal = pl_goal;
        self.ar_lastpos = self.origin; self.ar_nextstall = time + 4;
        self.ar_sndpos = pl_cue; self.ar_sndweap = IT_ROCKET_LAUNCHER;
        pl_begin = time;
        dprint ("BHVRPL begin live_pursuit\n");
        dprint ("PL begin dt_ms "); dprint (ftos (frametime * 1000)); dprint ("\n");

        self.ar_sndspent = 0; self.ar_sndtime = time - 1.3;
        owns_steering = Argus_InvestigateNoise ();
        dprint ("PL expired "); dprint (ftos (owns_steering)); dprint ("\n");
        self.ar_sndspent = 0; self.ar_sndtime = time - 0.2;
        self.ar_hoptrain = 1;
        owns_steering = Argus_InvestigateNoise ();
        dprint ("PL committed "); dprint (ftos (owns_steering)); dprint ("\n");
        self.ar_hoptrain = 0; self.ar_skill = 0;
        owns_steering = Argus_InvestigateNoise ();
        dprint ("PL novice "); dprint (ftos (owns_steering)); dprint ("\n");
        self.ar_skill = 1; self.ar_sndspent = 0;
    }
    self = pl_bot;
    before_yaw = self.ar_moveyaw;
    owns_steering = Argus_InvestigateNoise ();
    feet = pointcontents (self.origin + '0 0 -23');
    dprint ("PL frame "); dprint (ftos (floor ((time - pl_begin) * 1000)));
    dprint (" active "); dprint (ftos (owns_steering)); dprint (" pos "); dprint (vtos (self.origin));
    dprint (" feet "); dprint (ftos (feet)); dprint (" speed "); dprint (ftos (vlen (self.velocity)));
    dprint (" age "); dprint (ftos (time - self.ar_sndtime));
    dprint (" goal "); dprint (ftos (self.ar_goal == pl_goal));
    dprint (" before "); dprint (ftos (before_yaw));
    dprint (" after "); dprint (ftos (self.ar_moveyaw)); dprint ("\n");
    pl_frames = pl_frames + 1;
    if (!owns_steering || pl_frames >= 250)
    {
        pl_done = 1; self.velocity = '0 0 0'; self.movetype = MOVETYPE_NONE;
    }
    else Argus_Physics ();
    self = saved;
};
