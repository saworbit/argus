// Engine integration fixture. Explicit developer + scratch1 197 + impulse
// 217 opt-in only; scratch2: 0 stationary, 1 rush, 2 leave, 3 initial low HP,
// 4 damage during cover, 5 weapon change, 6 moving entry, 7 new attacker.
// No feature state is forced. The ordinary bot must choose and execute it.
// This rewrites live bot/loadout/pickup state and freezes the other bots for
// six seconds. Keep scratch1 197 disarmed on shared servers (#540).
entity ar_tf_target;
entity ar_tf_secondary;
vector ar_tf_start;
vector ar_tf_enemy;
float ar_tf_begin, ar_tf_next, ar_tf_hidden, ar_tf_moved, ar_tf_frames;
float ar_tf_case;
float ar_tf_ammo, ar_tf_fired;
.float ar_tf_solid, ar_tf_camera, ar_tf_weapon;

// The fixed target cannot move. T_Damage still adds bot knockback, so clear
// that velocity immediately or ordinary aim leads a stationary dummy.
void(entity attacker, float damage) Argus_TacticFixtureTargetPain =
{
    self.velocity = '0 0 0';
};

void() Argus_TacticFixtureShopChecks =
{
    local entity node, owner;
    local float ok, oldoff;
    node = Argus_NearestNode (self.origin);
    // Other bots are frozen for this fixture, but their sliced flood may
    // still own the shared queue. Release it and re-arm its ordinary errand.
    owner = an_bot;
    if (an_busy && owner != self && owner != world)
    {
        Argus_Nav_Abort (owner);
        if (owner.ar_goal != world) owner.ar_pending = 1;
    }
    ok = Argus_Shop_Start (self, node);
    self.health = 0;
    Argus_Die ();
    ok = ok && !self.ar_shopping && !an_shop && !an_busy;
    Argus_Respawn ();
    ok = ok && Argus_Shop_Start (self, node);
    Argus_Respawn ();
    ok = ok && !self.ar_shopping && !an_shop && !an_busy;
    ok = ok && Argus_Shop_Start (self, node);
    oldoff = self.ar_skilloff;
    self.ar_skilloff = 2;
    Argus_SetSkill ();
    ok = ok && !self.ar_shopping && !an_shop && !an_busy;
    self.ar_skilloff = oldoff;
    Argus_SetSkill ();
    // Cancelling an unrelated bot must leave the owner's queue intact.
    ok = ok && Argus_Shop_Start (self, node);
    Argus_Nav_Abort (ar_tf_target);
    ok = ok && an_busy && an_shop && self.ar_shopping && an_bot == self;
    Argus_Nav_Abort (self);
    dprint ("TACFIX shopchecks "); dprint (ftos (ok)); dprint ("\n");
};

void() Argus_TacticFixture =
{
    local entity b, saved, pack, nextpack;
    local vector p, q;
    if (ar_tacfixture_until)
    { dprint ("TACFIX busy\n"); return; }
    if (mapname == "dm4")
    { p = '465 -279 -104'; q = '337 -247 -296'; }
    else if (mapname == "dm2")
    { p = '2209 -279 24'; q = '2433 -183 24'; }
    else return;
    b = argus_bots;
    while (b != world && b.ar_slot != 1) b = b.ar_chain;
    if (b == world) return;
    pack = argus_bots;
    while (pack != world)
    {
        if (pack != b)
        {
            pack.ar_tf_solid = pack.solid; pack.ar_tf_camera = pack.cam_active;
            pack.solid = SOLID_NOT; pack.cam_active = 1; pack.button0 = 0;
        }
        pack = pack.ar_chain;
    }
    // Dropped packs have no classname in stock QC. Clear by model, and
    // clear old projectiles so a repeated trial cannot inherit a prior shot.
    pack = find (world, model, "progs/backpack.mdl");
    while (pack != world)
    {
        nextpack = find (pack, model, "progs/backpack.mdl");
        Argus_ItemChain_Remove (pack);
        remove (pack); pack = nextpack;
    }
    pack = find (world, classname, "rocket");
    while (pack != world)
    { nextpack = find (pack, classname, "rocket"); remove (pack); pack = nextpack; }
    pack = find (world, classname, "grenade");
    while (pack != world)
    { nextpack = find (pack, classname, "grenade"); remove (pack); pack = nextpack; }
    // Keep the specified loadout throughout a trial. A weapon respawning
    // under the opening seat must not turn a crossfire case into a weapon
    // switch case. Restore ordinary touches when this six-second trial ends.
    pack = argus_itemchain;
    while (pack != world)
    {
        if (pack.touch == weapon_touch)
        { pack.ar_tf_weapon = 1; pack.touch = SUB_Null; }
        pack = pack.ar_nextitem;
    }
    if (ar_tf_secondary != world) remove (ar_tf_secondary);
    ar_tf_secondary = world;
    if (ar_tf_target != world) remove (ar_tf_target);
    ar_tf_target = spawn ();
    ar_tf_target.classname = "player";
    ar_tf_target.netname = "tacticfixture";
    // It is an edict, not a network client: item touches must use the bot
    // path, or a respawning armour at its seat can stuffcmd a non-client.
    ar_tf_target.ar_isbot = 1;
    ar_tf_target.solid = SOLID_SLIDEBOX;
    ar_tf_target.movetype = MOVETYPE_NONE;
    ar_tf_target.takedamage = DAMAGE_AIM;
    ar_tf_target.th_pain = Argus_TacticFixtureTargetPain;
    ar_tf_target.health = 5000;
    ar_tf_target.weapon = IT_SHOTGUN;
    ar_tf_target.flags = FL_ONGROUND;
    setmodel (ar_tf_target, "progs/player.mdl");
    setsize (ar_tf_target, '-16 -16 -24', '16 16 32');
    setorigin (ar_tf_target, q);
    if (cvar ("scratch2") == 13)
    {
        // The top of a player hull reaches 32u down into a trigger.
        // Its bottom reaches only 24u up. Exercise the asymmetric slab.
        if (Argus_InTriggerBox (ar_tf_target, ar_tf_target.origin - '0 0 52')
            && !Argus_InTriggerBox (ar_tf_target, ar_tf_target.origin - '0 0 64')
            && !Argus_InTriggerBox (ar_tf_target, ar_tf_target.origin + '0 0 64'))
            dprint ("TACFIX hull ok\n");
        else dprint ("TACFIX hull FAILED\n");
    }
    saved = self; self = b;
    if (b.ar_goal != world && b.ar_goal.claimed_by == b) ReleaseClaim (b.ar_goal);
    Argus_Nav_Abort (b);
    // Reset through the existing lifecycle, then seat with a normal loadout.
    Argus_Respawn ();
    Argus_AvoidClear ();
    b.ar_bitem = world; b.ar_bitemlast = world;
    b.ar_bitemend = 0; b.ar_bitemcool = 0; b.ar_bitemscan = 0;
    b.ar_lastfoe = world;
    setorigin (b, p);
    b.velocity = '0 0 0';
    if (cvar ("scratch2") == 6) b.velocity = '-240 0 0';
    b.flags = b.flags | FL_ONGROUND;
    b.items = IT_AXE | IT_SHOTGUN | IT_ROCKET_LAUNCHER;
    b.ammo_rockets = 20; b.weapon = IT_ROCKET_LAUNCHER;
    b.health = 100; b.armorvalue = 0; b.armortype = 0;
    if (cvar ("scratch2") == 3) b.health = 20;
    b.ar_enemy = ar_tf_target;
    b.ar_seen = time; b.ar_lastseen = q;
    b.ar_react = time + 0.25;
    b.angles = vectoangles (q - p); b.angles_x = 0;
    b.ar_moveyaw = b.angles_y;
    b.ar_goal = world; b.ar_node = world; b.ar_pending = 0;
    b.ar_mode = 0; b.ar_nextai = time + 12;
    b.ar_retreating = 0; b.ar_dodgetime = 0;
    b.ar_hopjump = 0; b.ar_hoprj = 0; b.ar_hoplift = 0;
    b.ar_hopswim = 0; b.ar_hoptrain = 0; b.ar_hopdoor = 0;
    b.ar_sprintstate = 0; b.ar_wetlevel = 0; b.teleport_time = 0;
    b.ar_secondary = world; b.ar_tactic_check = 0;
    b.ar_secondaryscan = 0;
    b.ar_aimvel = 0; b.ar_mottarget = world;
    b.ar_motoff = '0 0 0'; b.ar_motprev = '0 0 0';
    if (cvar ("scratch2") == 12)
    {
        Argus_TacticFixtureShopChecks ();
        setorigin (b, p); b.velocity = '0 0 0';
        b.ar_enemy = ar_tf_target; b.ar_seen = time; b.ar_lastseen = q;
        b.ar_nextai = time + 12;
        b.items = IT_AXE | IT_SHOTGUN | IT_ROCKET_LAUNCHER;
        b.ammo_rockets = 20; b.weapon = IT_ROCKET_LAUNCHER;
        b.health = 100; b.armorvalue = 0; b.armortype = 0;
        b.flags = b.flags | FL_ONGROUND;
        b.angles = vectoangles (q - p); b.angles_x = 0;
        b.ar_react = time + 0.25;
    }
    if (cvar ("scratch2") == 8)
    {
        b.ar_node = Argus_TacticNode (q);
        b.ar_goal = b.ar_node; b.ar_mode = 2;
        b.velocity = '70 0 0'; // safe braking, but inside DROP's speed gate
    }
    if (cvar ("scratch2") == 9)
    { b.items = b.items | IT_LIGHTNING; b.ammo_cells = 30; }
    dprint ("TACFIX visible "); dprint (ftos (Argus_CanSee (ar_tf_target)));
    dprint (" walk ");
    if (mapname == "dm4") dprint (ftos (Argus_TacticWalk (p, '561 -183 -104')));
    else dprint (ftos (Argus_TacticWalk (p, '2241 -87 24')));
    dprint (" cover ");
    if (mapname == "dm4") dprint (ftos (Argus_TacticHidden ('561 -183 -104', q)));
    else dprint (ftos (Argus_TacticHidden ('2177 -23 24', q)));
    dprint (" shot "); dprint (ftos (Argus_TacticShotLine (p, q))); dprint ("\n");
    W_SetCurrentAmmo ();
    self = saved;
    ar_tacfixture_bot = b; ar_tacfixture_until = time + 6;
    ar_tf_start = p; ar_tf_enemy = q; ar_tf_begin = time;
    ar_tf_next = 0; ar_tf_hidden = 0; ar_tf_moved = 0; ar_tf_frames = 0;
    ar_tf_case = cvar ("scratch2");
    ar_tf_ammo = b.ammo_rockets; ar_tf_fired = 0;
    dprint ("TACFIX begin "); dprint (mapname);
    dprint (" case "); dprint (ftos (ar_tf_case)); dprint ("\n");
    if (ar_tf_case == 8)
    {
        dprint ("TACFIX route_setup mode "); dprint (ftos (b.ar_mode));
        dprint (" node "); dprint (vtos (b.ar_node.origin));
        dprint (" velocity "); dprint (vtos (b.velocity)); dprint ("\n");
    }
};

void() Argus_TacticFixtureTick =
{
    local entity b, otherbot, saved;
    local float k, hidden;
    local vector p;
    if (!ar_tacfixture_until) return;
    b = ar_tacfixture_bot;
    ar_tf_frames = ar_tf_frames + 1;
    if (time >= ar_tacfixture_until)
    {
        dprint ("TACFIX end frames "); dprint (ftos (ar_tf_frames));
        dprint (" seconds "); dprint (ftos (time - ar_tf_begin)); dprint ("\n");
        ar_tacfixture_until = 0;
        otherbot = argus_itemchain;
        while (otherbot != world)
        {
            if (otherbot.ar_tf_weapon)
            { otherbot.touch = weapon_touch; otherbot.ar_tf_weapon = 0; }
            otherbot = otherbot.ar_nextitem;
        }
        otherbot = argus_bots;
        while (otherbot != world)
        {
            if (otherbot != b)
            { otherbot.solid = otherbot.ar_tf_solid; otherbot.cam_active = otherbot.ar_tf_camera; }
            otherbot = otherbot.ar_chain;
        }
        // Clear every bot reference before the fixture edicts can be reused.
        otherbot = argus_bots;
        while (otherbot != world)
        {
            saved = self; self = otherbot;
            Argus_TacticReset ();
            self.ar_enemy = world; self.ar_lastfoe = world;
            self.ar_secondary = world; self.ar_mottarget = world;
            self.button0 = 0;
            self = saved;
            otherbot = otherbot.ar_chain;
        }
        remove (ar_tf_target); ar_tf_target = world;
        if (ar_tf_secondary != world) remove (ar_tf_secondary);
        ar_tf_secondary = world;
        ar_tacfixture_bot = world;
        return;
    }
    if (time < ar_tf_next) return;
    ar_tf_next = time + 0.04;
    // Independent observer: all eight hull corners plus centre, actual
    // target position, actual engine traces. No tactical helper is called.
    hidden = 1; k = 0;
    while (k < 9)
    {
        p = b.origin;
        if (k < 8)
        {
            p_x = p_x - 16 + 32 * (k & 1);
            p_y = p_y - 16 + 16 * (k & 2);
            p_z = p_z - 24 + 14 * (k & 4);
        }
        traceline (ar_tf_target.origin + '0 0 22', p, TRUE, ar_tf_target);
        if (trace_fraction == 1) hidden = 0;
        k = k + 1;
    }
    if (ar_tf_case == 10 && !ar_tf_moved && b.ar_tactic == 1)
    {
        b.ammo_rockets = b.ammo_rockets + 5;
        ar_tf_moved = 1;
        dprint ("TACFIX ammo_added\n");
    }
    if (ar_tf_case == 11 && !ar_tf_moved && b.ar_tactic == 4)
    {
        ar_tf_moved = 1;
        if (mapname == "dm4") setorigin (ar_tf_target, '776 -808 -232');
        else setorigin (ar_tf_target, '2209 -1687 24');
        dprint ("TACFIX target_moved\n");
    }
    if (ar_tf_case == 11 && !ar_tf_moved && b.ar_tactic == 3)
        b.ar_react = time + 0.4; // leave a visible return-shot observation window
    if (b.ammo_rockets < ar_tf_ammo) ar_tf_fired = 1;
    ar_tf_ammo = b.ammo_rockets;
    if (hidden && ar_tf_fired) ar_tf_hidden = 1;
    if (ar_tf_hidden && !ar_tf_moved && (ar_tf_case == 1 || ar_tf_case == 2 || ar_tf_case == 4 || ar_tf_case == 5 || ar_tf_case == 7))
    {
        ar_tf_moved = 1;
        if (ar_tf_case == 7)
        {
            ar_tf_secondary = spawn ();
            ar_tf_secondary.classname = "player";
            ar_tf_secondary.netname = "secondfixture";
            ar_tf_secondary.ar_isbot = 1;
            ar_tf_secondary.health = 5000;
            ar_tf_secondary.weapon = IT_SHOTGUN;
            ar_tf_secondary.solid = SOLID_SLIDEBOX;
            ar_tf_secondary.movetype = MOVETYPE_NONE;
            setmodel (ar_tf_secondary, "progs/player.mdl");
            setsize (ar_tf_secondary, '-16 -16 -24', '16 16 32');
            if (mapname == "dm4") setorigin (ar_tf_secondary, '465 -151 -104');
            else setorigin (ar_tf_secondary, '2145 -119 24');
        }
        else if (ar_tf_case == 5) b.weapon = IT_SHOTGUN;
        else if (ar_tf_case == 4) b.health = 20;
        else if (ar_tf_case == 2)
        {
            if (mapname == "dm4") setorigin (ar_tf_target, '776 -808 -232');
            else setorigin (ar_tf_target, '2209 -1687 24');
        }
        else
        {
            if (mapname == "dm4") setorigin (ar_tf_target, '465 -151 -104');
            else setorigin (ar_tf_target, '2145 -119 24');
        }
        dprint ("TACFIX target_moved\n");
    }
    dprint ("TACFIX sample "); dprint (ftos (time - ar_tf_begin));
    dprint (" pos "); dprint (vtos (b.origin));
    dprint (" hidden "); dprint (ftos (hidden));
    dprint (" rockets "); dprint (ftos (b.ammo_rockets));
    dprint (" targethp "); dprint (ftos (ar_tf_target.health));
    dprint (" hp "); dprint (ftos (b.health));
    dprint (" state "); dprint (ftos (b.ar_tactic));
    dprint (" memory "); dprint (vtos (b.ar_lastseen));
    dprint (" targetvel "); dprint (vtos (ar_tf_target.velocity));
    dprint ("\n");
};
