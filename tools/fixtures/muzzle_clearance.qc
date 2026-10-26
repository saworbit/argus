// PRIVATE native-engine fixture. Never included by production progs.src.
float mf_done, mf_checks, mf_ok;
vector mf_wall, mf_wallangle, mf_clear, mf_clearangle, mf_roof, mf_roofangle;
float mf_walldist;

void(string label, float ok) MuzzleCheck =
{
    mf_checks = mf_checks + 1;
    if (!ok) mf_ok = 0;
    dprint ("MFIX check "); dprint (label); dprint (" "); dprint (ftos (ok)); dprint ("\n");
};

void(string label, vector origin, vector angles, float range, float gun, float phase, float expired, float blocked) MuzzleCase =
{
    local entity saved, b, missile, next;
    local vector aimpt;
    local float allowed, before, after, count, ok;
    saved = self; b = spawn (); self = b;
    self.classname = "player"; self.netname = "muzzlefixture";
    self.ar_isbot = 1; self.health = 100;
    self.movetype = MOVETYPE_NONE; self.solid = SOLID_NOT;
    self.items = IT_ROCKET_LAUNCHER | IT_GRENADE_LAUNCHER | IT_SHOTGUN;
    self.weapon = gun; self.ammo_rockets = 2; self.ammo_shells = 2;
    self.ar_tactic = phase; self.ar_tactic_progress = time;
    if (expired) self.ar_tactic_progress = time - 1;
    self.v_angle = angles; self.velocity = '23 7 0'; self.ar_moveyaw = 137;
    setorigin (self, origin); W_SetCurrentAmmo ();
    makevectors (angles); aimpt = origin + '0 0 16' + v_forward * range;
    self.button0 = 1;
    allowed = Argus_MuzzleClear (aimpt);
    ok = allowed == !blocked && self.button0 == !blocked;
    ok = ok && self.velocity == '23 7 0' && self.ar_moveyaw == 137;
    if (phase == 4 && expired && blocked) ok = ok && !self.ar_tactic;
    else ok = ok && self.ar_tactic == phase;
    // Exercise the real stock weapon emission after the shared firing gate.
    // This is a gate-to-fire harness, not a replay of the whole combat AI.
    before = self.currentammo;
    if (allowed) W_Attack ();
    after = self.currentammo; count = 0;
    missile = nextent (world);
    while (missile != world)
    {
        next = nextent (missile);
        if (missile.owner == self && (missile.classname == "rocket" || missile.classname == "grenade"))
        { count = count + 1; remove (missile); }
        missile = next;
    }
    if (blocked) ok = ok && before == after && count == 0;
    else
    {
        ok = ok && before - after == 1;
        if (gun != IT_SHOTGUN) ok = ok && count == 1;
    }
    MuzzleCheck (label, ok);
    self = saved; remove (b); newmis = world;
};

void() MuzzleFixture =
{
    local entity node, roster, ent;
    local float yaw, pitch, wall, clear, roof, distance, olddm, before, after;
    local vector src, angles;
    if (mf_done || time < 1) return;
    mf_done = 1; mf_ok = 1;
    dprint ("MFIX begin "); dprint (mapname); dprint (" dt_ms "); dprint (ftos (frametime * 1000)); dprint ("\n");
    // Independently find/prove real BSP premises. No fake traces or nav edits.
    node = find (world, classname, "argus_node");
    while (node != world && !(wall && clear && roof))
    {
        src = node.origin + '0 0 16'; yaw = 0;
        while (yaw < 360)
        {
            pitch = 0;
            while (pitch < 2)
            {
                angles = '0 0 0'; angles_y = yaw; angles_x = -45 * pitch;
                makevectors (angles);
                traceline (src, src + v_forward * 240, TRUE, world);
                distance = trace_fraction * 240;
                if (pointcontents (src) != CONTENT_SOLID && !trace_startsolid && !trace_allsolid)
                {
                    if (!pitch && !wall && distance > 160 && distance < 220)
                    { wall = 1; mf_wall = node.origin; mf_wallangle = angles; mf_walldist = distance; }
                    if (!pitch && !clear && trace_fraction == 1)
                    { clear = 1; mf_clear = node.origin; mf_clearangle = angles; }
                    if (pitch && !roof && distance > 32 && distance < 220 && trace_plane_normal_z < -0.5)
                    { roof = 1; mf_roof = node.origin; mf_roofangle = angles; }
                }
                pitch = pitch + 1;
            }
            yaw = yaw + 45;
        }
        node = find (node, classname, "argus_node");
    }
    MuzzleCheck ("wall_geometry", wall);
    MuzzleCheck ("clear_geometry", clear);
    MuzzleCheck ("overhang_geometry", roof);
    if (wall && clear && roof)
    {
        before = 0; ent = nextent (world);
        while (ent != world) { before = before + 1; ent = nextent (ent); }
        roster = argus_bots; argus_bots = world; olddm = deathmatch; deathmatch = 1;
        MuzzleCase ("ordinary_wall", mf_wall, mf_wallangle, 400, IT_ROCKET_LAUNCHER, 0, 0, 1);
        MuzzleCase ("ordinary_overhang", mf_roof, mf_roofangle, 400, IT_ROCKET_LAUNCHER, 0, 0, 1);
        MuzzleCase ("ordinary_clear", mf_clear, mf_clearangle, 400, IT_ROCKET_LAUNCHER, 0, 0, 0);
        MuzzleCase ("wall_behind_target", mf_wall, mf_wallangle, mf_walldist - 32, IT_ROCKET_LAUNCHER, 0, 0, 0);
        MuzzleCase ("shotgun_unchanged", mf_wall, mf_wallangle, 400, IT_SHOTGUN, 0, 0, 0);
        MuzzleCase ("grenade_unchanged", mf_wall, mf_wallangle, 400, IT_GRENADE_LAUNCHER, 0, 0, 0);
        MuzzleCase ("tactical_full_reach", mf_wall, mf_wallangle, mf_walldist - 32, IT_ROCKET_LAUNCHER, 1, 0, 1);
        MuzzleCase ("tactical_settle", mf_wall, mf_wallangle, 400, IT_ROCKET_LAUNCHER, 4, 0, 1);
        MuzzleCase ("tactical_abort", mf_wall, mf_wallangle, 400, IT_ROCKET_LAUNCHER, 4, 1, 1);
        MuzzleCase ("tactical_clear", mf_clear, mf_clearangle, 400, IT_ROCKET_LAUNCHER, 4, 1, 0);
        deathmatch = olddm; argus_bots = roster;
        after = 0; ent = nextent (world);
        while (ent != world) { after = after + 1; ent = nextent (ent); }
        MuzzleCheck ("cleanup", before == after);
    }
    dprint ("MFIX end checks "); dprint (ftos (mf_checks));
    dprint (" ok "); dprint (ftos (mf_ok)); dprint ("\n");
};
