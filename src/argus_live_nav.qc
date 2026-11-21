// Learn directed links from traversal on maps without an authored graph.
float AL_WALK = 0;
float AL_JUMP = 1;
float AL_DROP = 2;
float AL_PORTAL = 3;
float AL_PLAT = 4;
float AL_TRAIN = 5;
float AL_DOOR = 6;
float AL_SWIM = 7;

entity al_nodes;
float al_count;
float al_peak_edicts;
.entity al_next;
.entity al_seat;
.entity al_mover;
.float al_sample;
.float al_air;
.float al_jump;
.float al_wet;
.float al_door_until;
.float al_item_scan;
.float al_swim_until;
.vector al_swim_wish;
.float al_swim_request, al_swim_retry, al_swim_diving;
.vector al_swim_tried;
.float al_exit_scan, al_exit_memory;
.vector al_exit_from, al_exit_avoid, al_exit_previous, al_exit_older, al_exit_oldest;
.entity al_exit_button, al_exit_prize;
.float al_exit_button_after, al_exit_prize_until;

void() Argus_ExploreReset =
{
    self.ar_exploreuntil = 0;
    self.ar_exploring = FALSE;
    self.al_exit_scan = 0;
    self.al_exit_memory = 0;
    self.al_exit_button = world;
    self.al_exit_button_after = 0;
    self.al_exit_prize = world;
    self.al_exit_prize_until = 0;
};

// Use the same weapon value as shopping. A supply behind a wall can bias
// which exit to try, but every candidate still needs a traversable lane.
entity() Argus_ExploreSupply =
{
    local entity item, pick;
    local float score, best, distance;

    best = 0;
    pick = world;
    item = argus_itemchain;
    while (item != world)
    {
        if (item.solid == SOLID_TRIGGER && Argus_ItemClass (item) == AR_C_WEAPON)
        {
            distance = vlen (Argus_GoalPoint (item) - self.origin);
            if (distance < 1450)
            {
                score = Argus_ItemValue (item, AR_C_WEAPON) / (320 + distance);
                if (score > best)
                {
                    best = score;
                    pick = item;
                }
            }
        }
        item = item.ar_nextitem;
    }
    return pick;
};

// A doorway can open onto a lower floor. Require two dry, walkable landing
// samples and clearance at both sides of the body before taking the drop.
vector(vector direction, float distance) Argus_ExploreDrop =
{
    local vector point, landing, side;
    local float drop;

    point = self.origin + direction * distance + '0 0 12';
    traceline (point, point - '0 0 168', TRUE, self);
    if (trace_fraction == 1 || trace_startsolid || trace_plane_normal_z < 0.65
        || pointcontents (trace_endpos + '0 0 4') != CONTENT_EMPTY)
        return self.origin;
    landing = trace_endpos + '0 0 24';
    drop = self.origin_z - landing_z;
    if (drop < 22 || drop > 120) return self.origin;
    point = landing + direction * 28;
    if (!Argus_WalkFloorOK (point, 38)) return self.origin;
    side = direction_y * '-17 0 0' + direction_x * '0 17 0';
    if (!Argus_WalkFloorOK (landing + side, 38) || !Argus_WalkFloorOK (landing - side, 38)
        || !Argus_WalkFloorOK (point + side, 38) || !Argus_WalkFloorOK (point - side, 38))
        return self.origin;
    traceline (landing + side, point + side, TRUE, self);
    if (trace_fraction < 1 || trace_startsolid) return self.origin;
    traceline (landing - side, point - side, TRUE, self);
    if (trace_fraction < 1 || trace_startsolid) return self.origin;
    return point;
};

vector(vector direction, float distance, float wet) Argus_ExploreLane =
{
    local vector side, start, offset, landing;
    local float sample, contents;

    side = direction_y * '-18 0 0' + direction_x * '0 18 0';
    start = self.origin + '0 0 10';
    offset = direction * distance;
    traceline (start + side, start + side + offset, TRUE, self);
    if (trace_startsolid) return self.origin;
    if (trace_fraction < 1) distance = distance * trace_fraction - 18;
    if (distance < 44) return self.origin;
    offset = direction * distance;
    traceline (start - side, start - side + offset, TRUE, self);
    if (trace_startsolid) return self.origin;
    if (trace_fraction < 1) distance = distance * trace_fraction - 18;
    sample = 24;
    while (sample <= distance)
    {
        offset = self.origin + direction * sample;
        if (!wet)
        {
            if (!Argus_WalkFloorOK (offset, 44))
            {
                if (sample + 28 <= distance)
                {
                    landing = Argus_ExploreDrop (direction, sample);
                    if (landing != self.origin) return landing;
                }
                return self.origin + direction * (sample - 28);
            }
        }
        else
        {
            contents = pointcontents (offset - '0 0 20');
            if (contents == CONTENT_LAVA || contents == CONTENT_SLIME)
                return self.origin + direction * (sample - 28);
        }
        sample = sample + 36;
    }
    return self.origin + direction * distance;
};

// Find a dry landing just beyond a low wall so swim steering can take
// the ordinary water vault. A long channel alone can circle a pool.
vector(vector direction, float wall) Argus_ExploreBank =
{
    local vector start, landing;

    if (wall < 22 || wall > 114) return '0 0 0';
    start = self.origin + '0 0 56';
    landing = start + direction * (wall + 34);
    traceline (start, landing, TRUE, self);
    if (trace_fraction < 1 || trace_startsolid) return '0 0 0';
    traceline (landing, landing - '0 0 88', TRUE, self);
    if (trace_fraction == 1 || trace_startsolid || trace_plane_normal_z < 0.65
        || pointcontents (trace_endpos + '0 0 4') != CONTENT_EMPTY)
        return '0 0 0';
    landing = trace_endpos + '0 0 24';
    if (landing_z > self.origin_z + 48 || landing_z < self.origin_z - 8
        || pointcontents (landing + '0 0 28') != CONTENT_EMPTY)
        return '0 0 0';
    return landing;
};

// A nearby touch button is worth a short detour when it opens a door to
// a useful weapon. Compare weapons on the far side of this door together.
entity(entity door) Argus_SwitchPrize =
{
    local entity item, prize;
    local vector doorpoint, supply;
    local float value, best;

    best = 39;
    prize = world;
    doorpoint = Argus_DoorShut (door);
    item = argus_itemchain;
    while (item != world)
    {
        if (item.solid == SOLID_TRIGGER && Argus_ItemClass (item) == AR_C_WEAPON)
        {
            supply = Argus_GoalPoint (item);
            value = Argus_ItemValue (item, AR_C_WEAPON);
            if (value > best && vlen (doorpoint - supply) < 340
                && !Argus_DoorPast (door, supply))
            {
                best = value;
                prize = item;
            }
        }
        item = item.ar_nextitem;
    }
    return prize;
};

vector(entity button) Argus_SwitchApproach =
{
    local vector point;

    point = (button.absmin + button.absmax) * 0.5 - button.movedir * 44;
    traceline (point + '0 0 20', point - '0 0 96', TRUE, self);
    if (trace_fraction < 1 && !trace_startsolid && trace_plane_normal_z > 0.65
        && pointcontents (trace_endpos + '0 0 26') == CONTENT_EMPTY)
        return trace_endpos + '0 0 24';
    return Argus_GoalPoint (button);
};

// Find a prerequisite while there is still room to work towards it. On a
// learned graph the switch may sit on a deck we have not visited yet.
entity() Argus_ExploreSwitch =
{
    local entity button, door, prize, bestbutton;
    local vector point;
    local float distance, limit, score, best;

    bestbutton = world;
    best = 0;
    limit = 172;
    if (argus_live_nav) limit = 1050;
    button = find (world, classname, "func_button");
    while (button != world)
    {
        if (button.health <= 0 && button.state == STATE_BOTTOM && button.target != "")
        {
            point = (button.absmin + button.absmax) * 0.5;
            distance = vlen (point - self.origin);
            if (distance < limit)
            {
                door = find (world, targetname, button.target);
                if (Argus_IsDoor (door) && !door.items && door.state == STATE_BOTTOM)
                {
                    prize = Argus_SwitchPrize (door);
                    if (prize != world)
                    {
                        score = Argus_ItemValue (prize, AR_C_WEAPON) / (360 + distance);
                        if (score > best)
                        {
                            best = score;
                            bestbutton = button;
                        }
                    }
                }
            }
        }
        button = find (button, classname, "func_button");
    }
    return bestbutton;
};

float(entity button, vector point) Argus_SwitchDirect =
{
    local vector approach, direction;
    local float distance;

    distance = vlen (point - self.origin);
    if (distance >= 172 || fabs (point_z - self.origin_z) >= 32) return FALSE;
    traceline (self.origin + '0 0 12', point, TRUE, self);
    if (trace_ent != button && trace_fraction != 1) return FALSE;
    direction = point - self.origin;
    direction_z = 0;
    approach = self.origin + normalize (direction) * (distance - 24);
    return Argus_WalkFloorOK (approach, 32) && Argus_SafeLine (approach);
};

// A blocked walkmove may leave the bot touching the brush without
// delivering the client's impact callback. Confirm contact and the exact
// brush before using the stock touch handler.
void(entity button) Argus_ExplorePress =
{
    local entity actor, savedother, savedactivator;
    local vector point;

    if (button.state != STATE_BOTTOM || button.touch != button_touch
        || !Argus_TouchingBox (button)) return;
    point = (button.absmin + button.absmax) * 0.5;
    traceline (self.origin + '0 0 12', point, TRUE, self);
    if (trace_ent != button) return;

    actor = self;
    savedother = other;
    savedactivator = activator;
    self = button;
    other = actor;
    button_touch ();
    self = actor;
    other = savedother;
    activator = savedactivator;
};

// Keep the selected passage until arrival or timeout. Penalise recent
// departures so the next scan looks beyond the room we just left.
float() Argus_ExploreExit =
{
    local float wet, remaining, range, yaw, reach, wall, score, best, i, door, approachdist, rise, rays;
    local float directed, prize;
    local vector direction, heading, supply, start, point, chosen, bank, approach;
    local entity item, button;

    if (!deathmatch || coop || self.ar_taskgoal != world || self.ar_mode == 2
        || self.ar_feettype < CONTENT_WATER || self.teleport_time > time)
        return FALSE;
    if (self.ar_feettype == CONTENT_WATER && time < self.ar_swimescape_until)
        return FALSE;

    wet = self.ar_feettype == CONTENT_WATER;
    if (self.ar_exploreuntil > 0)
    {
        remaining = vlen (self.ar_exploregoal - self.origin);
        if (remaining < 380 && time < self.ar_exploreuntil)
        {
            if (self.al_exit_button != world)
            {
                Argus_ExplorePress (self.al_exit_button);
                if (self.al_exit_button.state == STATE_BOTTOM) return TRUE;
                self.al_exit_prize_until = time + 7;
            }
            else if (remaining > 30) return TRUE;
        }
        self.al_exit_button = world;
        self.al_exit_oldest = self.al_exit_older;
        self.al_exit_older = self.al_exit_previous;
        self.al_exit_previous = self.al_exit_avoid;
        self.al_exit_avoid = self.al_exit_from;
        if (vlen (self.origin - self.al_exit_from) < 64)
            self.al_exit_avoid = self.ar_exploregoal;
        if (self.al_exit_memory <= time)
        {
            self.al_exit_previous = self.al_exit_avoid;
            self.al_exit_older = self.al_exit_avoid;
            self.al_exit_oldest = self.al_exit_avoid;
        }
        self.al_exit_memory = time + 16;
        self.ar_exploreuntil = 0;
    }
    if (time < self.al_exit_scan || (!wet && !(self.flags & FL_ONGROUND)))
        return FALSE;
    self.al_exit_scan = time + 0.55;

    supply = '0 0 0';
    self.al_exit_button = world;
    button = world;
    if (!wet && time >= self.al_exit_button_after && time >= self.al_exit_prize_until)
        button = Argus_ExploreSwitch ();
    if (button != world)
    {
        point = (button.absmin + button.absmax) * 0.5;
        if (Argus_SwitchDirect (button, point))
        {
            self.al_exit_button = button;
            self.al_exit_prize = Argus_SwitchPrize (find (world, targetname, button.target));
            self.al_exit_from = self.origin;
            self.ar_exploregoal = point;
            self.ar_exploreuntil = time + 1.3;
            self.al_exit_button_after = time + 5;
            dprint ("ARGUS explore switch "); dprint (self.netname); dprint ("\n");
            return TRUE;
        }
        if (!argus_live_nav) button = world;
    }
    item = self.al_exit_prize;
    prize = (item != world && time < self.al_exit_prize_until && item.solid == SOLID_TRIGGER);
    if (!prize) item = Argus_ExploreSupply ();
    if (item != world)
    {
        approach = Argus_GoalPoint (item);
        supply = approach - self.origin;
        supply_z = 0;
        supply = normalize (supply);
    }
    if (button != world)
        approach = Argus_SwitchApproach (button);
    directed = (button != world || prize);
    if (directed)
    {
        supply = approach - self.origin;
        approachdist = vlen (supply);
        rise = fabs (supply_z);
        supply_z = 0;
        supply = normalize (supply);
    }
    makevectors (self.ar_moveyaw * '0 1 0');
    heading = v_forward;
    range = 250;
    if (prize) range = 320;
    if (wet) range = 224;
    start = self.origin + '0 0 10';
    best = 0;
    rays = 17;
    if (directed) rays = 21;
    i = 0;
    while (i < rays)
    {
        yaw = self.ar_moveyaw + i * 22.5;
        if (i >= 16 && supply != '0 0 0')
        {
            yaw = vectoyaw (supply);
            if (i > 16) yaw = yaw + (i - 18.5) * 10;
        }
        makevectors (yaw * '0 1 0');
        direction = v_forward;
        traceline (start, start + direction * range, TRUE, self);
        door = (!wet && Argus_IsDoor (trace_ent) && !Argus_DoorMaster (trace_ent).items);
        wall = trace_fraction * range;
        reach = wall;
        bank = '0 0 0';
        if (wet && trace_fraction < 1) bank = Argus_ExploreBank (direction, reach);
        score = direction * supply * 100 + direction * heading * 20;
        if (bank != '0 0 0')
        {
            point = bank;
            reach = vlen (bank - self.origin);
            score = score + 170;
        }
        else
        {
            if (door) score = score + 64;
            if (reach < 74 || (!directed && reach + score + wet * 52 <= best))
            {
                i = i + 1;
                continue;
            }
            point = Argus_ExploreLane (direction, reach - 28, wet);
            reach = vlen (point - self.origin);
            if (wet && pointcontents (point - '0 0 20') == CONTENT_EMPTY)
                if (Argus_WalkFloorOK (point, 40)) score = score + 52;
        }
        score = score + reach;
        if (directed)
            score = score + (approachdist - vlen (approach - point)) * 1.3
                    + (rise - fabs (approach_z - point_z)) * 2;
        if (time < self.al_exit_memory)
        {
            if (vlen (point - self.al_exit_avoid) < 128) score = score - 150;
            else if (vlen (point - self.al_exit_previous) < 144) score = score - 130;
            else if (vlen (point - self.al_exit_older) < 144) score = score - 105;
            else if (vlen (point - self.al_exit_oldest) < 144) score = score - 80;
        }
        if (reach >= 44 && score > best && !Argus_MoveHazard (yaw, 48))
        {
            if (door && reach + 38 >= wall) point = point + direction * 40;
            chosen = point;
            best = score;
        }
        i = i + 1;
    }
    if (!best) return FALSE;

    self.al_exit_from = self.origin;
    self.ar_exploregoal = chosen;
    self.ar_exploreuntil = time + 1.8;
    if (wet) self.ar_exploreuntil = time + 2.6;
    dprint ("ARGUS explore "); dprint (self.netname); dprint (" ");
    dprint (vtos (self.origin)); dprint (" -> "); dprint (vtos (chosen)); dprint ("\n");
    return TRUE;
};

// When exploration reaches a pool with no route, retain the clearest
// channel long enough to get out of a wall pocket. The swim physics still
// owns depth, breathing and the vault across any bank found.
vector(vector wish) Argus_LiveSwimWish =
{
    local float i, base, angle, score, bestscore, water;
    local vector direction, chosen, start, target;

    if (time < self.al_swim_until) return self.al_swim_wish;
    self.al_swim_until = time + 0.55;
    chosen = wish;
    bestscore = -1;
    base = vectoyaw (wish);
    start = self.origin + '0 0 8';
    i = 0;
    while (i < 8)
    {
        angle = base + i * 45;
        makevectors (angle * '0 1 0');
        direction = v_forward;
        target = start + direction * 105;
        traceline (start, target, TRUE, self);
        score = trace_fraction * 105;
        if (!trace_startsolid && score > 12)
        {
            water = pointcontents (trace_endpos - direction * 6);
            if (water == CONTENT_LAVA || water == CONTENT_SLIME)
                score = -1;
            else if (trace_fraction == 1 && water == CONTENT_EMPTY)
            {
                traceline (target, target - '0 0 40', TRUE, self);
                if (trace_fraction < 1 && trace_plane_normal_z > 0.65
                    && pointcontents (trace_endpos + '0 0 2') == CONTENT_EMPTY)
                    score = score + 28;
            }
            if (score >= 0) score = score + direction * wish * 14;
            if (score > bestscore)
            {
                bestscore = score;
                chosen = direction;
            }
        }
        i = i + 1;
    }
    self.al_swim_wish = chosen;
    return chosen;
};

void() Argus_RequestSwimEscape =
{
    if (time >= self.ar_swimescape_until)
        self.al_swim_request = time + 0.7;
};

// A muzzle ray can see through a spillway while the swimmer's head or
// shoulders still meet the brush. Clip the run at each face of the body.
float(vector start, vector direction, float distance) Argus_SwimLane =
{
    local vector side, top, feet;
    local float sample;

    top = start + '0 0 28';
    feet = start - '0 0 22';
    side = direction_y * '-14 0 0' + direction_x * '0 14 0';
    traceline (top, top + direction * distance, TRUE, self);
    if (trace_startsolid) return 0;
    if (trace_fraction < 1) distance = distance * trace_fraction - 18;
    if (distance < 56) return 0;
    traceline (feet, feet + direction * distance, TRUE, self);
    if (trace_startsolid) return 0;
    if (trace_fraction < 1) distance = distance * trace_fraction - 18;
    if (distance < 56) return 0;
    traceline (start + side, start + side + direction * distance, TRUE, self);
    if (trace_startsolid) return 0;
    if (trace_fraction < 1) distance = distance * trace_fraction - 18;
    if (distance < 56) return 0;
    traceline (start - side, start - side + direction * distance, TRUE, self);
    if (trace_startsolid) return 0;
    if (trace_fraction < 1) distance = distance * trace_fraction - 18;
    sample = distance;
    while (sample > 0)
    {
        if (pointcontents (feet + direction * sample) != CONTENT_WATER) return 0;
        sample = sample - 36;
    }
    return distance;
};

// Try a clear run at the current depth or below an obstruction. Keep the
// dive short and leave five seconds of air for the ordinary ascent policy.
float() Argus_SwimEscape =
{
    local float depth, angle, i, distance, score, best, reached;
    local vector start, direction, point, chosen;

    if (!argus_live_nav || self.ar_enemy != world || self.ar_taskgoal != world
        || self.ar_mode == 2 || self.air_finished <= time + 5)
    {
        self.ar_swimescape_until = 0;
        return FALSE;
    }
    reached = FALSE;
    if (time < self.ar_swimescape_until)
    {
        if (vlen (self.ar_swimescape_goal - self.origin) > 24) return TRUE;
        reached = TRUE;
        dprint ("ARGUS swim escape reached "); dprint (self.netname); dprint (" ");
        dprint (vtos (self.origin)); dprint ("\n");
    }
    self.ar_swimescape_until = 0;
    if (time >= self.al_swim_request && (!reached || self.al_swim_diving)) return FALSE;
    self.al_swim_request = 0;

    best = 0;
    depth = 0;
    // A surface leg can reach the mouth of a passage that was occluded
    // at the stall. Look below it once before reverting to surface swim.
    if (reached) depth = 28;
    while (depth <= 56)
    {
        start = self.origin - '0 0 1' * depth;
        traceline (self.origin - '0 0 22', start - '0 0 24', TRUE, self);
        if (depth > 0 && (trace_fraction < 1 || trace_startsolid))
            break;
        i = 0;
        while (i < 12)
        {
            angle = self.ar_moveyaw + i * 30;
            makevectors (angle * '0 1 0');
            direction = v_forward;
            distance = Argus_SwimLane (start, direction, 176);
            if (distance >= 56)
            {
                point = start + direction * distance;
                score = distance - depth * 0.5;
                if (depth > 0)
                {
                    traceline (self.origin + '0 0 28', self.origin + '0 0 28' + direction * distance, TRUE, self);
                    if (trace_fraction < 0.7) score = score + 32;
                }
                if (time < self.al_swim_retry && vlen (point - self.al_swim_tried) < 70)
                    score = score - 80;
                if (score > best)
                {
                    best = score;
                    chosen = point;
                }
            }
            i = i + 1;
        }
        depth = depth + 28;
    }
    if (!best) return FALSE;

    self.ar_swimescape_goal = chosen;
    self.ar_swimescape_until = time + 2.3;
    self.al_swim_diving = (chosen_z < self.origin_z - 14);
    self.al_swim_tried = chosen;
    self.al_swim_retry = time + 6;
    self.al_swim_until = 0;
    self.ar_exploreuntil = 0;
    dprint ("ARGUS swim escape "); dprint (self.netname); dprint (" ");
    dprint (vtos (self.origin)); dprint (" -> "); dprint (vtos (chosen)); dprint ("\n");
    return TRUE;
};

// Check clearance at the centre and both shoulders. Check support separately,
// because a chest ray over a gap is a valid shot and an invalid walk.
float(vector from, vector to) Argus_LiveWalk =
{
    local vector side, ray;
    local float distance, step, contents;

    ray = to - from;
    ray_z = 0;
    distance = vlen (ray);
    if (distance > 136 || fabs (to_z - from_z) > 22)
        return FALSE;
    side = normalize (ray);
    side = side_y * '-14 0 0' + side_x * '0 14 0';
    traceline (from + '0 0 8', to + '0 0 8', TRUE, self);
    if (trace_fraction < 1 || trace_startsolid) return FALSE;
    traceline (from + side, to + side, TRUE, self);
    if (trace_fraction < 1 || trace_startsolid) return FALSE;
    traceline (from - side, to - side, TRUE, self);
    if (trace_fraction < 1 || trace_startsolid) return FALSE;
    step = 16;
    while (step <= distance + 12 && distance > 0)
    {
        if (step > distance) step = distance;
        ray = from + (to - from) * (step / distance);
        traceline (ray + '0 0 8', ray - '0 0 48', TRUE, self);
        if (trace_fraction == 1 || trace_startsolid) return FALSE;
        contents = pointcontents (trace_endpos + '0 0 2');
        if (contents != CONTENT_EMPTY) return FALSE;
        step = step + 16;
    }
    return TRUE;
};

entity(vector point, float radius) Argus_LiveNear =
{
    local entity node, best;
    local float dist;

    node = al_nodes;
    best = world;
    while (node != world)
    {
        dist = vlen (node.origin - point);
        if (dist < radius && fabs (node.origin_z - point_z) < 19)
        {
            traceline (point, node.origin, TRUE, self);
            if (trace_fraction == 1 && !trace_startsolid)
            {
                best = node;
                radius = dist;
            }
        }
        node = node.al_next;
    }
    return best;
};

entity(vector point) Argus_LiveSeat =
{
    local entity node;
    local float count;

    node = Argus_LiveNear (point, 66);
    if (node != world || al_count >= 104 || an_busy)
        return node;
    // Leave capacity for projectiles, players, body queues and map logic.
    count = 1;
    node = nextent (world);
    while (node != world && count < 456)
    {
        count = count + 1;
        node = nextent (node);
    }
    if (count >= 456) return world;
    node = Argus_NavNode (point);
    node.al_next = al_nodes;
    al_nodes = node;
    al_count = al_count + 1;
    if (count + 1 > al_peak_edicts) al_peak_edicts = count + 1;
    if (al_count == 1 || al_count == 104 || al_count == floor (al_count / 16) * 16)
    {
        dprint ("ARGUS live graph nodes "); dprint (ftos (al_count));
        dprint (" allocated_edicts "); dprint (ftos (al_peak_edicts)); dprint ("\n");
    }
    return node;
};

entity(entity item) Argus_LiveItemSeat =
{
    local vector point;
    local entity seat;

    if (time < item.al_item_scan) return world;
    item.al_item_scan = time + 1.0;
    point = Argus_GoalPoint (item);
    seat = Argus_LiveNear (point + '0 0 22', 90);
    if (seat != world && Argus_LiveWalk (seat.origin, point + '0 0 22'))
        return seat;
    seat = Argus_LiveNear (point, 72);
    if (seat != world && Argus_LiveWalk (seat.origin, point))
        return seat;
    return world;
};

void(entity from, entity to, float kind) Argus_LiveLink =
{
    local float bit;

    if (from == world || to == world || from == to || from.an_nlinks >= 8) return;
    if (Argus_NavGetLinkBit (from, to)) return;
    if (kind == AL_JUMP) Argus_NavLinkJump (from, to, 0);
    else if (kind == AL_PLAT) Argus_NavLinkLift (from, to);
    else if (kind == AL_TRAIN) Argus_NavLinkTrain (from, to);
    else if (kind == AL_DOOR) Argus_NavLinkDoor (from, to);
    else if (kind == AL_SWIM) Argus_NavLinkSwim (from, to);
    else Argus_NavLink (from, to);
    bit = Argus_NavGetLinkBit (from, to);
    if (kind == AL_DROP) from.al_dropmask = from.al_dropmask | bit;
    if (kind == AL_PORTAL)
    {
        from.an_telemask = from.an_telemask | bit;
        from.an_telecost = 224;
    }
    if (!from.al_linkLogged)
    {
        from.al_linkLogged = TRUE;
        dprint ("ARGUS live link "); dprint (ftos (kind)); dprint (" ");
        dprint (vtos (from.origin)); dprint (" -> ");
        dprint (vtos (to.origin)); dprint ("\n");
    }
};

void() Argus_LiveNavReset =
{
    self.al_seat = world;
    self.al_mover = world;
    self.al_sample = 0;
    self.al_air = 0;
    self.al_jump = 0;
    self.al_door_until = 0;
    self.al_wet = 0;
    self.al_swim_until = 0;
    self.al_swim_request = 0;
    self.al_swim_retry = 0;
    self.ar_swimescape_until = 0;
};

void(entity actor) Argus_LiveNavDoor =
{
    if (argus_live_nav && actor.classname == "player")
        actor.al_door_until = time + 1.6;
};

void(entity rider, entity gate, vector entry) Argus_LiveNavWarp =
{
    local entity from, to, saved;

    if (!argus_live_nav || rider.classname != "player" || rider.health <= 0)
        return;
    if (rider.ar_node != world && rider.ar_node.al_gate == gate)
        rider.ar_node = rider.ar_node.al_exit;
    saved = self;
    self = rider;
    Argus_LiveNavReset ();
    if (!an_busy && gate.targetname == string_null)
    {
        from = Argus_LiveSeat (entry);
        to = Argus_LiveSeat (rider.origin);
        if (from != world && to != world && from != to && from.al_gate == world)
        {
            Argus_LiveLink (from, to, AL_PORTAL);
            if (Argus_NavGetLinkBit (from, to) & from.an_telemask)
            {
                from.al_gate = gate;
                from.al_exit = to;
            }
        }
        self.al_seat = to;
    }
    self = saved;
};

void() Argus_LiveNavSample =
{
    local entity from, to, support;
    local float contents, distance, kind;
    local vector feet, delta;

    if (!argus_live_nav || self.health <= 0 || self.cam_active || self.ar_taskgoal != world)
        return;
    if (self.teleport_time > time) return;
    feet = self.origin + '0 0 -23';
    contents = pointcontents (feet);
    if (contents < CONTENT_WATER)
    {
        Argus_LiveNavReset ();
        return;
    }
    if (!(self.flags & FL_ONGROUND) && contents != CONTENT_WATER)
    {
        self.al_air = TRUE;
        if (self.velocity_z > 120) self.al_jump = TRUE;
        return;
    }
    support = self.groundentity;
    if (self.flags & FL_ONGROUND)
        if (support.classname == "plat" || support.classname == "train")
        {
            if (self.al_seat != world) self.al_mover = support;
            return;
        }
    if (an_busy || time < self.al_sample) return;
    self.al_sample = time + 0.21;
    from = self.al_seat;
    if (from != world && vlen (self.origin - from.origin) < 56)
    {
        self.al_air = 0;
        self.al_jump = 0;
        self.al_mover = world;
        return;
    }
    to = Argus_LiveSeat (self.origin);
    if (to == world || from == to) return;
    if (from != world)
    {
        delta = to.origin - from.origin;
        distance = vlen (delta);
        kind = -1;
        if (self.al_mover != world && distance < 720)
        {
            kind = AL_PLAT;
            if (self.al_mover.classname == "train") kind = AL_TRAIN;
        }
        else if (self.al_wet && contents != CONTENT_WATER && distance < 155)
            kind = AL_SWIM;
        else if (contents == CONTENT_WATER && distance < 135)
        {
            traceline (from.origin, to.origin, TRUE, self);
            if (trace_fraction == 1) kind = AL_WALK;
        }
        else if (Argus_LiveWalk (from.origin, to.origin))
            kind = AL_WALK;
        else if (!self.al_air && time < self.al_door_until && distance < 136
                 && fabs (delta_z) < 24)
            kind = AL_DOOR;
        else if (self.al_air && delta_z < -22 && delta_z >= -176 && distance < 220)
            kind = AL_DROP;
        else if (self.al_jump && delta_z > -30 && delta_z < 44 && distance < 180)
            kind = AL_JUMP;
        if (kind >= 0) Argus_LiveLink (from, to, kind);
        if (kind == AL_WALK && contents != CONTENT_WATER
            && Argus_LiveWalk (to.origin, from.origin))
            Argus_LiveLink (to, from, AL_WALK);
    }
    self.al_seat = to;
    self.al_air = 0;
    self.al_jump = 0;
    self.al_mover = world;
    self.al_wet = (contents == CONTENT_WATER);
};

void() Argus_LiveNavReject =
{
    local entity from;
    local float bit;

    if (!argus_live_nav || self.ar_node == world) return;
    from = self.al_seat;
    if (from == world || from == self.ar_node) from = self.ar_laststart;
    if (from == world) return;
    bit = Argus_NavGetLinkBit (from, self.ar_node);
    if (!bit) return;
    if (from.al_badbit != bit || time > from.al_baduntil + 20)
        from.al_failures = 0;
    from.al_badbit = bit;
    if (from.al_failures < 4) from.al_failures = from.al_failures + 1;
    from.al_baduntil = time + 5 * from.al_failures;
};
