// The fixture seats a continuing train hop once per case. Production owns
// the live car, steering, recovery and any subsequent route.
float tw_case, tw_next, tw_started, tw_sample, tw_released, tw_boarded, tw_replanned;
float tw_dismounted;
entity tw_bot, tw_goal, tw_car, tw_dock, tw_exit;

void(entity routed) TrainWaitRouteReady =
{
    if (routed != tw_bot || !tw_released || tw_replanned) return;
    if (routed.ar_goal == tw_goal || routed.ar_node == tw_exit) return;
    tw_replanned = 1;
    dprint ("TW replan "); dprint (ftos (tw_case)); dprint (" elapsed ");
    dprint (ftos (time - tw_started)); dprint ("\n");
};

void() TrainWaitBefore =
{
    local entity b, saved;
    local vector seat;
    local float support;

    if (mapname != "dm2" || cvar ("scratch2") != 3003 || time < 2 || time < tw_next) return;
#ifdef TRAIN_WAIT_NEAR_SEATS
    if (tw_case == 3) return;
#else
    if (tw_case == 9) return;
#endif
    if (!tw_case)
    {
        dprint ("BHVRPL begin train_wait\n");
        b = argus_bots;
        while (b != world)
        {
            if (b.ar_slot == 0) tw_bot = b;
            else
            {
                b.health = 0; b.solid = SOLID_NOT; b.takedamage = DAMAGE_NO;
                b.movetype = MOVETYPE_NONE; b.nextthink = 0; b.think = SUB_Null;
                b.ar_respawntime = time + 3600;
            }
            b = b.ar_chain;
        }
        tw_car = find (world, model, "*11");
        if (tw_bot == world || tw_car.classname != "train") error ("TW missing stock train or bot");
        tw_dock = Argus_NearestNode ('1441 -1015 344');
        tw_exit = Argus_NearestNode ('1921 -1047 344');
        if (tw_dock.origin != '1441 -1015 344' || tw_exit.origin != '1921 -1047 344')
            error ("TW missing stock train seats");
        dprint ("TW begin dt_ms "); dprint (ftos (frametime * 1000)); dprint ("\n");
    }

    tw_case = tw_case + 1;
    tw_started = time; tw_next = time + 18.3; tw_sample = time;
    tw_released = 0; tw_boarded = 0; tw_replanned = 0;
    tw_dismounted = 0;
#ifdef TRAIN_WAIT_NEAR_SEATS
    if (tw_case == 1) seat = '1372.7 -912.5 344';
    else if (tw_case == 2) seat = '1370.4 -907.6 344';
    else seat = '1453 -1024 344';
#else
    if (tw_case <= 3) seat = '1375 -714 344';
    else if (tw_case <= 6) seat = '1375 -729.7 344';
    else seat = '1441 -1015 344';
#endif

    saved = self; self = tw_bot;
    Argus_TaskClear (self); Argus_Nav_Abort (self);
    Argus_BaseStats (); Argus_TacticReset (); Argus_AvoidClear ();
    setorigin (self, seat + '0 0 1');
    self.flags = self.flags - (self.flags & FL_ONGROUND); self.groundentity = world;
    support = droptofloor ();
    if (!support || vlen (self.origin - seat) > 2) error ("TW start did not settle at requested floor");
    setorigin (self, seat); self.velocity = '0 0 0';
    self.ar_goal = world; self.ar_enemy = world; self.ar_routefail = 0;
    self.ar_hopjump = 0; self.ar_hoprj = 0; self.ar_hoplift = 0; self.ar_hopswim = 0;
    self.ar_hopdoor = 0; self.ar_hopair = 0; self.ar_jump = 0; self.ar_sprintstate = 0;
    self.ar_padcooltime = 0; self.ar_liftwait = 0; self.ar_traptime = 0;
    self.ar_lastpos = seat; self.ar_nextstall = time + 2;
    self.ar_hoptrain = 1; self.ar_boarded = 0; self.ar_liftstart = time;
#ifdef TRAIN_WAIT_HAS_SEAT
    self.ar_trainfrom = tw_dock;
#endif
    self.ar_mode = 2; self.ar_node = tw_exit; self.ar_pending = 0;
    self.ar_moveyaw = 0; self.angles_y = 0;
    tw_goal = spawn (); tw_goal.classname = "argus_task_goal";
    tw_goal.flags = FL_ITEM; tw_goal.solid = SOLID_TRIGGER;
    setsize (tw_goal, '-8 -8 -8', '8 8 8'); setorigin (tw_goal, '1910 -970 344');
    self.ar_goal = tw_goal; self.ar_taskgoal = tw_goal;
    self.ar_taskstart = time; self.ar_taskdeadline = time + 18.2; self.ar_goalstart = time + 3600;
    dprint ("TW start "); dprint (ftos (tw_case)); dprint (" support "); dprint (ftos (support));
    dprint (" pos "); dprint (vtos (seat)); dprint (" car "); dprint (vtos (tw_car.origin));
    dprint (" carvel "); dprint (vtos (tw_car.velocity)); dprint ("\n");
    self = saved;
};

void() TrainWaitAfter =
{
    if (!tw_case || time > tw_started + 18) return;
    if (!tw_boarded && tw_bot.groundentity == tw_car)
    {
        tw_boarded = 1;
        dprint ("TW board "); dprint (ftos (tw_case)); dprint (" elapsed ");
        dprint (ftos (time - tw_started)); dprint ("\n");
    }
    if (!tw_released && !tw_bot.ar_hoptrain)
    {
        tw_released = 1;
        dprint ("TW release "); dprint (ftos (tw_case)); dprint (" elapsed ");
        dprint (ftos (time - tw_started)); dprint ("\n");
    }
    if (tw_boarded && !tw_dismounted && tw_bot.groundentity == world
        && (tw_bot.flags & FL_ONGROUND) && tw_bot.origin_x >= tw_exit.origin_x
        && fabs (tw_bot.origin_y - tw_exit.origin_y) <= 128
        && fabs (tw_bot.origin_z - tw_exit.origin_z) <= 18
        && pointcontents (tw_bot.origin + '0 0 -22') == CONTENT_EMPTY)
    {
        tw_dismounted = 1;
        dprint ("TW dismount "); dprint (ftos (tw_case)); dprint (" elapsed ");
        dprint (ftos (time - tw_started)); dprint ("\n");
    }
    if (time < tw_sample) return;
    tw_sample = time + 0.5;
    dprint ("TW sample "); dprint (ftos (tw_case)); dprint (" elapsed "); dprint (ftos (time - tw_started));
    dprint (" pos "); dprint (vtos (tw_bot.origin)); dprint (" car "); dprint (vtos (tw_car.origin));
    dprint (" hold "); dprint (ftos (tw_bot.ar_liftwait)); dprint (" hp "); dprint (ftos (tw_bot.health));
    dprint (" goal "); dprint (ftos (tw_bot.ar_goal == tw_goal));
    dprint (" node "); dprint (vtos (tw_bot.ar_node.origin)); dprint ("\n");
};
