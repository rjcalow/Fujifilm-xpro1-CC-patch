/* X-Pro1 SD chain loader: inflate the stock boot loader to address 0 and start it (normal boot from flash).
   Green LED: ON at start, toggles every 32 KiB of output, then a long steady ON (= loader verified), OFF, jump.
   Error blink codes (N pulses, pause, repeat): 4 = CRC mismatch, 5 = inflate error, 6 = bad config. */
typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32;
void *memset(void *d, int v, unsigned n) { u8 *p = d; while (n--) *p++ = (u8)v; return d; }
void *memcpy(void *d, const void *s, unsigned n) { u8 *p = d; const u8 *q = s; while (n--) *p++ = *q++; return d; }

struct cfg { u32 image_size, payload_off, payload_len, out_len, out_crc, magic; };
extern struct cfg cfg;
extern u8 _start[];
static u8 *volatile dest_base;          /* 0, read through a volatile so the compiler cannot assume NULL */

#define REG(a) (*(volatile u32 *)(a))
#define GPIO15 0xfff893c0u
static int led_state;
static void led_init(void) {            /* port 15: pin 2 = green LED (active low), pin 0 = other LED kept off */
    REG(GPIO15 + 0x18) &= ~0x33u;
    REG(GPIO15 + 0x0c) = 0x00330000u;
    REG(GPIO15 + 0x08) = 0x00050005u;
    REG(GPIO15 + 0x00) = 0x00050001u;   /* pin0 high (off), pin2 low (on) */
    REG(GPIO15 + 0x04) = 0x00050005u;
    led_state = 1;
}
static void led(int on) { REG(GPIO15) = on ? 0x00040000u : 0x00040004u; led_state = on; }
static void delay(void) { for (volatile u32 i = 0; i < 0x00500000u; i++) { } }   /* one blink phase (~2 s at the ROM clock) */
static void fail(int code) {
    for (;;) {
        for (int i = 0; i < code; i++) { led(1); delay(); led(0); delay(); }
        delay(); delay(); delay(); delay();
    }
}

/* ---- raw DEFLATE decoder (RFC 1951), written for this stub ---- */
struct in { const u8 *p; u32 n, pos, buf, cnt; int err; };
struct out { u8 *p; u32 n, pos, mark; };
struct huff { u16 count[16]; u16 sym[288]; };

static u32 getbits(struct in *s, int need) {
    u32 v = s->buf;
    while (s->cnt < (u32)need) {
        if (s->pos >= s->n) { s->err = 1; return 0; }
        v |= (u32)s->p[s->pos++] << s->cnt; s->cnt += 8;
    }
    s->buf = v >> need; s->cnt -= need;
    return v & ((1u << need) - 1);
}
static void build(struct huff *h, const u8 *len, int n) {
    u16 offs[16];
    for (int i = 0; i < 16; i++) h->count[i] = 0;
    for (int i = 0; i < n; i++) h->count[len[i]]++;
    h->count[0] = 0; offs[1] = 0;
    for (int i = 1; i < 15; i++) offs[i + 1] = offs[i] + h->count[i];
    for (int i = 0; i < n; i++) if (len[i]) h->sym[offs[len[i]]++] = (u16)i;
}
static int decode(struct in *s, const struct huff *h) {
    int code = 0, first = 0, index = 0;
    for (int l = 1; l < 16; l++) {
        code |= (int)getbits(s, 1);
        if (s->err) return -1;
        int c = h->count[l];
        if (code - first < c) return h->sym[index + (code - first)];
        index += c; first += c; first <<= 1; code <<= 1;
    }
    return -1;
}
static void put(struct out *o, u8 b) {
    if (o->pos < o->n) o->p[o->pos] = b;
    o->pos++;
    if (o->pos - o->mark >= 0x8000) { o->mark = o->pos; led(!led_state); }
}
static const u16 lbase[29] = {3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258};
static const u8  lext[29]  = {0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0};
static const u16 dbase[30] = {1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577};
static const u8  dext[30]  = {0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13};

static int codes(struct in *s, struct out *o, const struct huff *lh, const struct huff *dh) {
    for (;;) {
        int sym = decode(s, lh);
        if (sym < 0) return -1;
        if (sym < 256) { put(o, (u8)sym); continue; }
        if (sym == 256) return 0;
        sym -= 257; if (sym >= 29) return -1;
        u32 len = lbase[sym] + getbits(s, lext[sym]);
        int ds = decode(s, dh);
        if (ds < 0 || ds >= 30) return -1;
        u32 dist = dbase[ds] + getbits(s, dext[ds]);
        if (s->err || dist > o->pos) return -1;
        while (len--) put(o, o->p[o->pos - dist]);
    }
}
static int inflate(struct in *s, struct out *o) {
    static struct huff lh, dh;
    u8 lens[320];
    int last;
    do {
        last = (int)getbits(s, 1);
        int type = (int)getbits(s, 2);
        if (s->err) return -1;
        if (type == 0) {
            s->buf = 0; s->cnt = 0;
            if (s->pos + 4 > s->n) return -1;
            u32 len = s->p[s->pos] | (s->p[s->pos + 1] << 8), nlen = s->p[s->pos + 2] | (s->p[s->pos + 3] << 8);
            s->pos += 4;
            if ((len ^ 0xffffu) != nlen || s->pos + len > s->n) return -1;
            while (len--) put(o, s->p[s->pos++]);
        } else if (type == 1) {
            int i = 0;
            for (; i < 144; i++) lens[i] = 8;
            for (; i < 256; i++) lens[i] = 9;
            for (; i < 280; i++) lens[i] = 7;
            for (; i < 288; i++) lens[i] = 8;
            build(&lh, lens, 288);
            for (i = 0; i < 30; i++) lens[i] = 5;
            build(&dh, lens, 30);
            if (codes(s, o, &lh, &dh)) return -1;
        } else if (type == 2) {
            static const u8 order[19] = {16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15};
            int nlen = (int)getbits(s, 5) + 257, ndist = (int)getbits(s, 5) + 1, ncode = (int)getbits(s, 4) + 4;
            if (s->err || nlen > 286 || ndist > 30) return -1;
            int i;
            for (i = 0; i < 19; i++) lens[i] = 0;
            for (i = 0; i < ncode; i++) lens[order[i]] = (u8)getbits(s, 3);
            build(&lh, lens, 19);
            for (i = 0; i < nlen + ndist;) {
                int sym = decode(s, &lh);
                if (sym < 0) return -1;
                if (sym < 16) { lens[i++] = (u8)sym; continue; }
                int rep, val = 0;
                if (sym == 16) { if (i == 0) return -1; val = lens[i - 1]; rep = 3 + (int)getbits(s, 2); }
                else if (sym == 17) rep = 3 + (int)getbits(s, 3);
                else rep = 11 + (int)getbits(s, 7);
                if (i + rep > nlen + ndist) return -1;
                while (rep--) lens[i++] = (u8)val;
            }
            build(&lh, lens, nlen);
            build(&dh, lens + nlen, ndist);
            if (codes(s, o, &lh, &dh)) return -1;
        } else return -1;
        if (s->err) return -1;
    } while (!last);
    return 0;
}

/* Hand over like a cold flash boot: write every dirty D-cache line back to RAM (the loader we just wrote at 0 may
   still be in the cache), then disable MPU/D-cache/I-cache and invalidate the I-cache. ARMv7 set/way maintenance. */
static void caches_off(void) {
    u32 clidr, ccsidr, sctlr;
    __asm__ volatile("cpsid if" ::: "memory");          /* hand over with IRQ/FIQ masked, like a cold flash boot */
    __asm__ volatile("mrc p15, 1, %0, c0, c0, 1" : "=r"(clidr));
    for (u32 level = 0; level < 7; level++) {
        u32 ctype = (clidr >> (level * 3)) & 7;
        if (ctype == 0) break;
        if (ctype < 2) continue;                       /* no data cache at this level */
        __asm__ volatile("mcr p15, 2, %0, c0, c0, 0\n isb" :: "r"(level << 1));
        __asm__ volatile("mrc p15, 1, %0, c0, c0, 0" : "=r"(ccsidr));
        u32 lshift = (ccsidr & 7) + 4, ways = ((ccsidr >> 3) & 0x3ff) + 1, sets = ((ccsidr >> 13) & 0x7fff) + 1;
        u32 wshift = ways > 1 ? (u32)__builtin_clz(ways - 1) : 0;
        for (u32 w = 0; w < ways; w++)
            for (u32 st = 0; st < sets; st++)
                __asm__ volatile("mcr p15, 0, %0, c7, c14, 2" :: "r"((w << wshift) | (st << lshift) | (level << 1)));
    }
    __asm__ volatile("dsb" ::: "memory");
    __asm__ volatile("mrc p15, 0, %0, c1, c0, 0" : "=r"(sctlr));
    sctlr &= ~((1u << 0) | (1u << 2) | (1u << 12) | (1u << 13));   /* M (MPU), C, I caches, V (high vectors) */
    __asm__ volatile("mcr p15, 0, %0, c1, c0, 0\n isb" :: "r"(sctlr) : "memory");
    __asm__ volatile("mov r0, #0\n mcr p15, 0, r0, c7, c5, 0\n dsb\n isb" ::: "r0", "memory");
}

static u32 crc32(const u8 *p, u32 n) {
    u32 c = 0xffffffffu;
    while (n--) { c ^= *p++; for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u))); }
    return ~c;
}

/* The boot ROM leaves an asynchronous (imprecise) abort pending; the stock loader unmasks CPSR.A in its first
   routine (0x4070) and takes it as a data abort. Drain it here: temporary abort vector, unmask, wait, mask, restore.
   absorbed[0] = number taken, absorbed[1] = DFSR of the last one. */
volatile u32 absorbed[2];
extern void absorb_dabt(void);
static void drain_async_abort(void) {
    u32 cpsr, old;
    __asm__ volatile("mrs %0, cpsr" : "=r"(cpsr));
    __asm__ volatile("cps #0x17\n mov sp, %0\n msr cpsr_c, %1" :: "r"(0x41f7f000u), "r"(cpsr) : "memory");
    volatile u32 *vec = (volatile u32 *)((u32)dest_base + 0x30);     /* loader vector literal for data abort */
    old = *vec; *vec = (u32)absorb_dabt;
    __asm__ volatile("dsb\n isb\n cpsie a" ::: "memory");
    for (volatile u32 i = 0; i < 0x1000u; i++) { }
    __asm__ volatile("cpsid a\n dsb\n isb" ::: "memory");
    *vec = old;
    __asm__ volatile("dsb" ::: "memory");
}


#ifdef CRUMBS
/* Breadcrumbs in DRAM 0x43f00000 (layout: re/tools/crumbs.py; read with re/tools/sdcrumbs.py after the shutter-
   triggered flash boot). Non-cacheable under the ROM's MPU; every record ends with dsb. */
#define CR ((volatile u32 *)0x43f00000u)
static const u32 snap_regs[] = {
    0xfff98000u, 0xfff98008u, 0xfff88084u,
    0xfff44024u, 0xfff44028u, 0xfff4402cu, 0xfff44030u, 0xfff44034u, 0xfff44038u,
    0xfffb3000u, 0xfffb3004u, 0xfffb3008u, 0xfffb300cu, 0xfffb3080u, 0xfffb3084u, 0xfffb3088u, 0xfffb308cu,
    0xfffb3100u, 0xfffb3104u, 0xfffb3108u, 0xfffb310cu };
static void crumb_progress(u32 code, u32 bit) {
    CR[4] = code; CR[5] |= 1u << bit;
    __asm__ volatile("dsb" ::: "memory");
}
static void crumb_snapshot(volatile u32 *s) {
    u32 v, n, bits = 0;
    __asm__ volatile("mrs %0, cpsr" : "=r"(v)); s[0] = v;
    __asm__ volatile("mrc p15, 0, %0, c1, c0, 0" : "=r"(v)); s[1] = v;
    __asm__ volatile("mrc p15, 0, %0, c0, c0, 4" : "=r"(v)); s[2] = v;
    n = (v >> 8) & 0xff; if (n > 16) n = 16;
    for (u32 r = 0; r < n; r++) {
        __asm__ volatile("mcr p15, 0, %0, c6, c2, 0\n isb" :: "r"(r));
        __asm__ volatile("mrc p15, 0, %0, c6, c1, 2" : "=r"(v));
        bits |= (v & 1u) << r;
    }
    s[3] = bits;
    for (u32 i = 0; i < sizeof snap_regs / sizeof snap_regs[0]; i++) s[6 + i] = REG(snap_regs[i]);
    __asm__ volatile("dsb" ::: "memory");
}
static void crumbs_start(void) {
    for (int i = 0; i < 256; i++) CR[i] = 0;
    CR[0] = 0x52434453u; CR[1] = 1;                     /* 'SDCR', layout 1 */
    crumb_snapshot(CR + 8);                             /* boot-ROM state at 0x020 */
    crumb_progress(0x01, 0);
}
#else
#define crumbs_start() ((void)0)
#define crumb_progress(c, b) ((void)0)
#endif

void main(void) {
    crumbs_start();
    led_init();
    if (cfg.magic != 0x4e494843u || cfg.out_len == 0 || cfg.payload_off + cfg.payload_len > cfg.image_size) fail(6);
    u8 *dst = dest_base;
    struct in s = { _start + cfg.payload_off, cfg.payload_len, 0, 0, 0, 0 };
    struct out o = { dst, cfg.out_len, 0, 0 };
    if (inflate(&s, &o) || o.pos != cfg.out_len) fail(5);
    if (crc32(dst, cfg.out_len) != cfg.out_crc) fail(4);
    crumb_progress(0x02, 1);
    led(0);                                           /* verified: LED off, hand over (loader checkpoints take it from here) */
    caches_off();                                     /* also masks IRQ/FIQ and selects low vectors */
    drain_async_abort();
#ifdef CRUMBS
    CR[8 + 4] = absorbed[0]; CR[8 + 5] = absorbed[1];
#endif
    crumb_progress(0x03, 2);
#ifndef QUIET
    if (absorbed[0]) {                                /* tell the user: ORANGE x2 = a pending ROM abort was drained */
        for (int i = 0; i < 2; i++) { REG(GPIO15) = 0x00010000u; delay(); REG(GPIO15) = 0x00010001u; delay(); }
        delay();
    }
#endif
    __asm__ volatile("mov r0, #0\n mcr p15, 0, r0, c7, c5, 0\n dsb\n isb\n bx r0" ::: "r0", "memory");
    for (;;) { }
}
