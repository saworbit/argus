// Private stock-map fixture. Place once and let QuakeSpasm land each jump.
entity climb_bot;
float climb_stage, climb_start, climb_step;

void(vector push) ClimbTakeoff =
{
    self.velocity = push;
    self.velocity_z = 270 + Argus_Gravity () * frametime * 0.5;
    self.flags = self.flags - (self.flags & FL_ONGROUND);
    climb_step = time;
    dprint ("TREAD takeoff "); dprint (ftos (climb_stage));
    dprint (" pos "); dprint (vtos (self.origin)); dprint ("\n");
};

void() ShelfTreadFixture =
{
    local entity saved, b;
    local float rise, bottom;
    local vector push;
    if (time < 2 || climb_stage > 4) return;
    if (climb_bot == world)
    {
        b = argus_bots;
        while (b != world)
        {
            if (b.ar_slot == 0) climb_bot = b;
            b.solid = SOLID_NOT; b.movetype = MOVETYPE_NONE;
            b.think = SUB_Null; b.nextthink = 0;
            b = b.ar_chain;
        }
        if (climb_bot == world) return;
        dprint ("BHVRPL begin e1m3_tread_chain\n");
        dprint ("TREAD begin dt_ms "); dprint (ftos (frametime * 1000)); dprint ("\n");
    }
    saved = self; self = climb_bot;
    if (!climb_stage)
    {
        self.movetype = MOVETYPE_STEP; self.solid = SOLID_SLIDEBOX;
        self.flags = self.flags - (self.flags & FL_ONGROUND);
        setorigin (self, '873 -494 -157');
        if (!droptofloor () || fabs (self.origin_z + 160) > 2)
            error ("tread route could not stage");
        climb_start = time; climb_stage = 1;
    }
    else if (time >= climb_step + 0.22 && self.velocity_z <= 0 && (self.flags & FL_ONGROUND))
    {
        bottom = checkbottom (self);
        dprint ("TREAD land "); dprint (ftos (climb_stage));
        dprint (" pos "); dprint (vtos (self.origin)); dprint (" bottom "); dprint (ftos (bottom)); dprint ("\n");
        // Narrow treads can give world contact while CheckBottom refuses.
        // Require a dry floor at the expected next height before taking off.
        if (self.groundentity != world
            || pointcontents (self.origin + '0 0 -22') != CONTENT_EMPTY)
        {
            climb_stage = 5;
            dprint ("TREAD refused\n");
            self = saved; return;
        }
        rise = -128;
        if (climb_stage == 2) rise = -104;
        if (climb_stage == 3) rise = -72;
        if (climb_stage == 4) rise = -40;
        if (fabs (self.origin_z - rise) > 2)
        {
            climb_stage = 5;
            dprint ("TREAD refused\n");
            self = saved; return;
        }
        climb_stage = climb_stage + 1;
        if (climb_stage > 4)
        {
            self.velocity = '0 0 0';
            dprint ("TREAD completed "); dprint (ftos (time - climb_start)); dprint ("\n");
            self = saved; return;
        }
    }
    else
    {
        if (time > climb_step + 1.5) { climb_stage = 5; dprint ("TREAD timeout\n"); }
        self = saved; return;
    }
    push = '0 56 0';
    if (climb_stage == 2) push = '0 78 0';
    if (climb_stage == 3) push = '0 86 0';
    if (climb_stage == 4) push = '-40 0 0';
    ClimbTakeoff (push);
    self = saved;
};
