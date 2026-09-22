// vortex.h — see vortex.c
#ifndef PD_VORTEX_H
#define PD_VORTEX_H
void pd_vortex_particles(const float *in, float *out, int count,
                         float dt, float cx, float cy);
#endif