/* Pink Diamond — vortex particle math kernel (C).
   Pure float math, no allocation: callable from Python via ctypes for the
   landing/agent vortex background, and small enough for an iOS watch face
   if the Swift companion ever wants it. Build: cc -O2 -shared -fPIC
   -o libpd_vortex.{so,dll} vortex.c && cc -O2 -DPD_VORTEX_DEMO vortex.c */
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

void pd_vortex_particles(const float *in, float *out, int count,
                         float dt, float cx, float cy) {
    /* in/out layout per particle: angle, radius, angular_speed, drift,
       x, y  (x/y written; angle/radius advanced in place). */
    for (int i = 0; i < count; i++) {
        const float *p = in + i * 5;
        float *q = out + i * 5;
        float a = p[0] + p[2] * dt;
        float r = p[1] + p[3];
        q[0] = a; q[1] = r; q[2] = p[2]; q[3] = p[3];
        q[4] = cx + cosf(a) * r;
        q[5] = cy + sinf(a) * r * 0.62f; /* elliptical swirl like the site */
    }
}

#ifdef PD_VORTEX_DEMO
#include <stdio.h>
int main(void) {
    float p[5] = { 0.0f, 100.0f, 1.5f, -0.01f };
    float q[6];
    pd_vortex_particles(p, q, 1, 0.016f, 640.0f, 360.0f);
    printf("particle at (%.2f, %.2f)\n", q[4], q[5]);
    return 0;
}
#endif