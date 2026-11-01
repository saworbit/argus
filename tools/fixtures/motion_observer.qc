// Private contracts for passive motion diagnostics. No movement task is
// steered. The temporary actor is removed before production AI resumes.
float mo_done, mo_checks, mo_failures;
void(string label, float ok) MotionObserverCheck =
{
    mo_checks = mo_checks + 1;
    if (!ok) mo_failures = mo_failures + 1;
    dprint ("MOCHECK "); dprint (label); dprint (" ");
    dprint (ftos (ok != 0)); dprint ("\n");
};

void() MotionObserverFixture =
{
    local entity saved, actor;
    local vector forward, right, endpoint;
    local float i, yaw, previous, enabled, fraction;
    if (mo_done || time < 2) return;
    mo_done = 1; saved = self; enabled = argus_motion_diag;
    actor = spawn (); self = actor; self.netname = "motion_fixture";
    self.ar_moveyaw = 37; self.ar_motioncause = "sentinel";
    makevectors ('8 33 0'); forward = v_forward; right = v_right;
    traceline ('0 0 0', '0 0 64', TRUE, self);
    endpoint = trace_endpos; fraction = trace_fraction;
    dprint ("BHVRPL begin motion_observer\n");
    argus_motion_diag = 0;
    MotionObserverCheck ("disabled_yaw", Argus_MotionTurn (12, 721, "fixture") == 721);
    MotionObserverCheck ("disabled_fields", self.ar_motioncause == "sentinel");
    argus_motion_diag = 1;
    i = 0;
    while (i < 7)
    {
        yaw = -720 + i * 241;
        previous = self.ar_moveyaw;
        MotionObserverCheck ("raw_yaw", Argus_MotionTurn (previous, yaw, "fixture") == yaw);
        i = i + 1;
    }
    MotionObserverCheck ("no_steering_write", self.ar_moveyaw == 37);
    MotionObserverCheck ("basis_preserved", v_forward == forward && v_right == right);
    MotionObserverCheck ("trace_preserved", trace_fraction == fraction && trace_endpos == endpoint);
    dprint ("MOCHECK end checks "); dprint (ftos (mo_checks));
    dprint (" failures "); dprint (ftos (mo_failures)); dprint ("\n");
    argus_motion_diag = enabled; remove (actor); self = saved;
};
