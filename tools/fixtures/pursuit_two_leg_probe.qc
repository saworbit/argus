// Prototype used only by the private pursuit verifier.
float(vector from, vector to) PursuitProbeDryWalk =
{
    local vector point, delta;
    local float length, offset;

    traceline (from + '0 0 16', to, TRUE, self);
    if (trace_fraction != 1 || trace_startsolid || trace_allsolid) return FALSE;
    delta = to - from;
    length = vlen (delta);
    if (length < 24 || length > 192 || fabs (delta_z) > 18) return FALSE;
    offset = 0;
    while (offset <= length)
    {
        point = from + delta * (offset / length);
        traceline (point + '0 0 16', point - '0 0 60', TRUE, self);
        if (trace_fraction == 1 || trace_startsolid || trace_allsolid || trace_ent != world
            || trace_plane_normal_z < 0.7 || pointcontents (trace_endpos + '0 0 2') <= CONTENT_WATER)
            return FALSE;
        offset = offset + 12;
    }
    return TRUE;
};

entity(entity seat, vector sighting) PursuitProbeTwoLeg =
{
    local entity first, second, best;
    local float i, j, cost, bestcost;

    best = world;
    bestcost = 350;
    i = 0;
    while (i < seat.an_nlinks)
    {
        first = Argus_NavGetLink (seat, i);
        if (!Argus_LinkIsTyped (seat, first) && PursuitProbeDryWalk (self.origin, first.origin)
            && !Argus_MoveHazard (vectoyaw (first.origin - self.origin), 48))
        {
            j = 0;
            while (j < first.an_nlinks)
            {
                second = Argus_NavGetLink (first, j);
                cost = vlen (first.origin - self.origin) + vlen (second.origin - first.origin)
                    + vlen (sighting - second.origin);
                if (second != seat && cost < bestcost && !Argus_LinkIsTyped (first, second)
                    && PursuitProbeDryWalk (first.origin, second.origin))
                {
                    traceline (second.origin + '0 0 16', sighting, TRUE, self);
                    if (trace_fraction == 1 && !trace_startsolid && !trace_allsolid)
                    {
                        bestcost = cost;
                        best = first;
                    }
                }
                j = j + 1;
            }
        }
        i = i + 1;
    }
    return best;
};
