#pragma once

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#ifdef _WIN32
#  ifndef NOMINMAX
#    define NOMINMAX
#  endif
#  include <windows.h>
#  include <bcrypt.h>
#  pragma comment(lib, "bcrypt")
#endif

#include <zlib.h>

namespace MaskConfig {
void DebugEncryptedConfig(const std::string& message);
}

namespace WinfoxConfigCrypto {

namespace {

constexpr size_t WINFOX_AES_BLOCKLEN = 16;
constexpr size_t WINFOX_AES256_KEYEXP_SIZE = 240;

struct WinfoxAES_ctx {
  uint8_t RoundKey[WINFOX_AES256_KEYEXP_SIZE];
  uint8_t Iv[WINFOX_AES_BLOCKLEN];
};

#define WINFOX_AES_NB 4
#define WINFOX_AES_NK 8
#define WINFOX_AES_NR 14

typedef uint8_t WinfoxAES_state_t[4][4];

constexpr uint8_t kEncryptionKey[32] = {
    0x6d, 0x13, 0x34, 0x9a, 0x27, 0x80, 0xee, 0x45,
    0x73, 0x2c, 0x9d, 0xb1, 0x14, 0x67, 0xca, 0x58,
    0xa4, 0x92, 0x0f, 0x36, 0x7b, 0xd8, 0x21, 0x5e,
    0xc9, 0x40, 0x18, 0xaf, 0x63, 0xf4, 0x2a, 0x85,
};

constexpr uint8_t kMacKey[32] = {
    0x3c, 0xa7, 0x51, 0x20, 0xd4, 0x6e, 0x8b, 0x17,
    0xf2, 0x49, 0x90, 0x2d, 0xbc, 0x74, 0x0a, 0xe1,
    0x65, 0x33, 0xc8, 0x5a, 0x19, 0x8f, 0xd0, 0x47,
    0xab, 0x26, 0x71, 0x9c, 0x04, 0xde, 0x58, 0x12,
};

constexpr char kBase64Table[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static const uint8_t WINFOX_AES_sbox[256] = {
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16};

static const uint8_t WINFOX_AES_rsbox[256] = {
    0x52,0x09,0x6a,0xd5,0x30,0x36,0xa5,0x38,0xbf,0x40,0xa3,0x9e,0x81,0xf3,0xd7,0xfb,
    0x7c,0xe3,0x39,0x82,0x9b,0x2f,0xff,0x87,0x34,0x8e,0x43,0x44,0xc4,0xde,0xe9,0xcb,
    0x54,0x7b,0x94,0x32,0xa6,0xc2,0x23,0x3d,0xee,0x4c,0x95,0x0b,0x42,0xfa,0xc3,0x4e,
    0x08,0x2e,0xa1,0x66,0x28,0xd9,0x24,0xb2,0x76,0x5b,0xa2,0x49,0x6d,0x8b,0xd1,0x25,
    0x72,0xf8,0xf6,0x64,0x86,0x68,0x98,0x16,0xd4,0xa4,0x5c,0xcc,0x5d,0x65,0xb6,0x92,
    0x6c,0x70,0x48,0x50,0xfd,0xed,0xb9,0xda,0x5e,0x15,0x46,0x57,0xa7,0x8d,0x9d,0x84,
    0x90,0xd8,0xab,0x00,0x8c,0xbc,0xd3,0x0a,0xf7,0xe4,0x58,0x05,0xb8,0xb3,0x45,0x06,
    0xd0,0x2c,0x1e,0x8f,0xca,0x3f,0x0f,0x02,0xc1,0xaf,0xbd,0x03,0x01,0x13,0x8a,0x6b,
    0x3a,0x91,0x11,0x41,0x4f,0x67,0xdc,0xea,0x97,0xf2,0xcf,0xce,0xf0,0xb4,0xe6,0x73,
    0x96,0xac,0x74,0x22,0xe7,0xad,0x35,0x85,0xe2,0xf9,0x37,0xe8,0x1c,0x75,0xdf,0x6e,
    0x47,0xf1,0x1a,0x71,0x1d,0x29,0xc5,0x89,0x6f,0xb7,0x62,0x0e,0xaa,0x18,0xbe,0x1b,
    0xfc,0x56,0x3e,0x4b,0xc6,0xd2,0x79,0x20,0x9a,0xdb,0xc0,0xfe,0x78,0xcd,0x5a,0xf4,
    0x1f,0xdd,0xa8,0x33,0x88,0x07,0xc7,0x31,0xb1,0x12,0x10,0x59,0x27,0x80,0xec,0x5f,
    0x60,0x51,0x7f,0xa9,0x19,0xb5,0x4a,0x0d,0x2d,0xe5,0x7a,0x9f,0x93,0xc9,0x9c,0xef,
    0xa0,0xe0,0x3b,0x4d,0xae,0x2a,0xf5,0xb0,0xc8,0xeb,0xbb,0x3c,0x83,0x53,0x99,0x61,
    0x17,0x2b,0x04,0x7e,0xba,0x77,0xd6,0x26,0xe1,0x69,0x14,0x63,0x55,0x21,0x0c,0x7d};

static const uint8_t WINFOX_AES_Rcon[15] = {0x00,0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1B,0x36,0x6C,0xD8,0xAB,0x4D};

inline uint8_t WINFOX_AES_xtime(uint8_t x) { return (uint8_t)((x << 1) ^ (((x >> 7) & 1U) * 0x1bU)); }
inline uint8_t WINFOX_AES_Multiply(uint8_t x, uint8_t y) {
  return (uint8_t)(((y & 1U) * x) ^ ((y >> 1 & 1U) * WINFOX_AES_xtime(x)) ^ ((y >> 2 & 1U) * WINFOX_AES_xtime(WINFOX_AES_xtime(x))) ^ ((y >> 3 & 1U) * WINFOX_AES_xtime(WINFOX_AES_xtime(WINFOX_AES_xtime(x)))) ^ ((y >> 4 & 1U) * WINFOX_AES_xtime(WINFOX_AES_xtime(WINFOX_AES_xtime(WINFOX_AES_xtime(x))))));
}

inline void WINFOX_AES_KeyExpansion(uint8_t* RoundKey, const uint8_t* Key) {
  unsigned i, j, k; uint8_t tempa[4];
  for (i = 0; i < WINFOX_AES_NK; ++i) {
    RoundKey[(i * 4U) + 0] = Key[(i * 4U) + 0]; RoundKey[(i * 4U) + 1] = Key[(i * 4U) + 1];
    RoundKey[(i * 4U) + 2] = Key[(i * 4U) + 2]; RoundKey[(i * 4U) + 3] = Key[(i * 4U) + 3];
  }
  for (i = WINFOX_AES_NK; i < WINFOX_AES_NB * (WINFOX_AES_NR + 1U); ++i) {
    k = (i - 1U) * 4U; tempa[0] = RoundKey[k + 0U]; tempa[1] = RoundKey[k + 1U]; tempa[2] = RoundKey[k + 2U]; tempa[3] = RoundKey[k + 3U];
    if (i % WINFOX_AES_NK == 0U) {
      uint8_t u8tmp = tempa[0U]; tempa[0U] = tempa[1U]; tempa[1U] = tempa[2U]; tempa[2U] = tempa[3U]; tempa[3U] = u8tmp;
      tempa[0U] = WINFOX_AES_sbox[tempa[0U]]; tempa[1U] = WINFOX_AES_sbox[tempa[1U]]; tempa[2U] = WINFOX_AES_sbox[tempa[2U]]; tempa[3U] = WINFOX_AES_sbox[tempa[3U]];
      tempa[0U] = (uint8_t)(tempa[0U] ^ WINFOX_AES_Rcon[i / WINFOX_AES_NK]);
    } else if (i % WINFOX_AES_NK == 4U) {
      tempa[0U] = WINFOX_AES_sbox[tempa[0U]]; tempa[1U] = WINFOX_AES_sbox[tempa[1U]]; tempa[2U] = WINFOX_AES_sbox[tempa[2U]]; tempa[3U] = WINFOX_AES_sbox[tempa[3U]];
    }
    j = i * 4U; k = (i - WINFOX_AES_NK) * 4U;
    RoundKey[j + 0U] = (uint8_t)(RoundKey[k + 0U] ^ tempa[0U]); RoundKey[j + 1U] = (uint8_t)(RoundKey[k + 1U] ^ tempa[1U]);
    RoundKey[j + 2U] = (uint8_t)(RoundKey[k + 2U] ^ tempa[2U]); RoundKey[j + 3U] = (uint8_t)(RoundKey[k + 3U] ^ tempa[3U]);
  }
}

inline void WINFOX_AES_AddRoundKey(uint8_t round, WinfoxAES_state_t* state, const uint8_t* RoundKey) {
  uint8_t i, j; for (i = 0; i < 4; ++i) for (j = 0; j < 4; ++j) (*state)[i][j] ^= RoundKey[(round * WINFOX_AES_NB * 4) + (i * WINFOX_AES_NB) + j];
}
inline void WINFOX_AES_InvSubBytes(WinfoxAES_state_t* state) {
  uint8_t i, j; for (i = 0; i < 4; ++i) for (j = 0; j < 4; ++j) (*state)[j][i] = WINFOX_AES_rsbox[(*state)[j][i]];
}
inline void WINFOX_AES_InvShiftRows(WinfoxAES_state_t* state) {
  uint8_t temp;
  temp = (*state)[1][3]; (*state)[1][3] = (*state)[1][2]; (*state)[1][2] = (*state)[1][1]; (*state)[1][1] = (*state)[1][0]; (*state)[1][0] = temp;
  temp = (*state)[2][0]; (*state)[2][0] = (*state)[2][2]; (*state)[2][2] = temp; temp = (*state)[2][1]; (*state)[2][1] = (*state)[2][3]; (*state)[2][3] = temp;
  temp = (*state)[3][0]; (*state)[3][0] = (*state)[3][1]; (*state)[3][1] = (*state)[3][2]; (*state)[3][2] = (*state)[3][3]; (*state)[3][3] = temp;
}
inline void WINFOX_AES_InvMixColumns(WinfoxAES_state_t* state) {
  int i; uint8_t a,b,c,d; for (i = 0; i < 4; ++i) { a = (*state)[i][0]; b = (*state)[i][1]; c = (*state)[i][2]; d = (*state)[i][3]; (*state)[i][0] = WINFOX_AES_Multiply(a,0x0e)^WINFOX_AES_Multiply(b,0x0b)^WINFOX_AES_Multiply(c,0x0d)^WINFOX_AES_Multiply(d,0x09); (*state)[i][1] = WINFOX_AES_Multiply(a,0x09)^WINFOX_AES_Multiply(b,0x0e)^WINFOX_AES_Multiply(c,0x0b)^WINFOX_AES_Multiply(d,0x0d); (*state)[i][2] = WINFOX_AES_Multiply(a,0x0d)^WINFOX_AES_Multiply(b,0x09)^WINFOX_AES_Multiply(c,0x0e)^WINFOX_AES_Multiply(d,0x0b); (*state)[i][3] = WINFOX_AES_Multiply(a,0x0b)^WINFOX_AES_Multiply(b,0x0d)^WINFOX_AES_Multiply(c,0x09)^WINFOX_AES_Multiply(d,0x0e); }
}
inline void WINFOX_AES_InvCipher(WinfoxAES_state_t* state, const uint8_t* RoundKey) {
  uint8_t round; WINFOX_AES_AddRoundKey(WINFOX_AES_NR, state, RoundKey);
  for (round = (uint8_t)(WINFOX_AES_NR - 1U); ; --round) { WINFOX_AES_InvShiftRows(state); WINFOX_AES_InvSubBytes(state); WINFOX_AES_AddRoundKey(round, state, RoundKey); if (round == 0U) break; WINFOX_AES_InvMixColumns(state); }
}
inline void WINFOX_AES_XorWithIv(uint8_t* buf, const uint8_t* Iv) { uint8_t i; for (i = 0; i < WINFOX_AES_BLOCKLEN; ++i) buf[i] ^= Iv[i]; }
inline void WinfoxAES_init_ctx_iv(struct WinfoxAES_ctx* ctx, const uint8_t* key, const uint8_t* iv) { WINFOX_AES_KeyExpansion(ctx->RoundKey, key); memcpy(ctx->Iv, iv, WINFOX_AES_BLOCKLEN); }
inline void WinfoxAES_CBC_decrypt_buffer(struct WinfoxAES_ctx* ctx, uint8_t* buf, uint32_t length) {
  uint8_t storeNextIv[WINFOX_AES_BLOCKLEN]; uint32_t i;
  for (i = 0; i < length; i += WINFOX_AES_BLOCKLEN) { memcpy(storeNextIv, buf + i, WINFOX_AES_BLOCKLEN); WINFOX_AES_InvCipher((WinfoxAES_state_t*)(buf + i), ctx->RoundKey); WINFOX_AES_XorWithIv(buf + i, ctx->Iv); memcpy(ctx->Iv, storeNextIv, WINFOX_AES_BLOCKLEN); }
}

struct SHA256Ctx {
  uint64_t bitlen;
  uint32_t state[8];
  uint8_t data[64];
  size_t datalen;
};

inline uint32_t rotr(uint32_t x, uint32_t n) {
  return (x >> n) | (x << (32 - n));
}

inline void Sha256Transform(SHA256Ctx& ctx, const uint8_t data[]) {
  static constexpr uint32_t k[64] = {
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b,
      0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
      0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7,
      0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
      0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152,
      0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
      0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
      0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
      0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
      0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f,
      0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
      0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
  uint32_t a, b, c, d, e, f, g, h, i, j, t1, t2, m[64];
  for (i = 0, j = 0; i < 16; ++i, j += 4) {
    m[i] = (static_cast<uint32_t>(data[j]) << 24) |
           (static_cast<uint32_t>(data[j + 1]) << 16) |
           (static_cast<uint32_t>(data[j + 2]) << 8) |
           static_cast<uint32_t>(data[j + 3]);
  }
  for (; i < 64; ++i) {
    uint32_t s0 = rotr(m[i - 15], 7) ^ rotr(m[i - 15], 18) ^ (m[i - 15] >> 3);
    uint32_t s1 = rotr(m[i - 2], 17) ^ rotr(m[i - 2], 19) ^ (m[i - 2] >> 10);
    m[i] = m[i - 16] + s0 + m[i - 7] + s1;
  }
  a = ctx.state[0]; b = ctx.state[1]; c = ctx.state[2]; d = ctx.state[3];
  e = ctx.state[4]; f = ctx.state[5]; g = ctx.state[6]; h = ctx.state[7];
  for (i = 0; i < 64; ++i) {
    uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    uint32_t ch = (e & f) ^ (~e & g);
    t1 = h + S1 + ch + k[i] + m[i];
    uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    t2 = S0 + maj;
    h = g; g = f; f = e; e = d + t1;
    d = c; c = b; b = a; a = t1 + t2;
  }
  ctx.state[0] += a; ctx.state[1] += b; ctx.state[2] += c; ctx.state[3] += d;
  ctx.state[4] += e; ctx.state[5] += f; ctx.state[6] += g; ctx.state[7] += h;
}

inline void Sha256Init(SHA256Ctx& ctx) {
  ctx.datalen = 0; ctx.bitlen = 0;
  ctx.state[0] = 0x6a09e667; ctx.state[1] = 0xbb67ae85;
  ctx.state[2] = 0x3c6ef372; ctx.state[3] = 0xa54ff53a;
  ctx.state[4] = 0x510e527f; ctx.state[5] = 0x9b05688c;
  ctx.state[6] = 0x1f83d9ab; ctx.state[7] = 0x5be0cd19;
}

inline void Sha256Update(SHA256Ctx& ctx, const uint8_t* data, size_t len) {
  for (size_t i = 0; i < len; ++i) {
    ctx.data[ctx.datalen++] = data[i];
    if (ctx.datalen == 64) {
      Sha256Transform(ctx, ctx.data);
      ctx.bitlen += 512;
      ctx.datalen = 0;
    }
  }
}

inline void Sha256Final(SHA256Ctx& ctx, uint8_t hash[32]) {
  size_t i = ctx.datalen;
  if (ctx.datalen < 56) {
    ctx.data[i++] = 0x80;
    while (i < 56) ctx.data[i++] = 0x00;
  } else {
    ctx.data[i++] = 0x80;
    while (i < 64) ctx.data[i++] = 0x00;
    Sha256Transform(ctx, ctx.data);
    memset(ctx.data, 0, 56);
  }
  ctx.bitlen += ctx.datalen * 8;
  ctx.data[63] = static_cast<uint8_t>(ctx.bitlen);
  ctx.data[62] = static_cast<uint8_t>(ctx.bitlen >> 8);
  ctx.data[61] = static_cast<uint8_t>(ctx.bitlen >> 16);
  ctx.data[60] = static_cast<uint8_t>(ctx.bitlen >> 24);
  ctx.data[59] = static_cast<uint8_t>(ctx.bitlen >> 32);
  ctx.data[58] = static_cast<uint8_t>(ctx.bitlen >> 40);
  ctx.data[57] = static_cast<uint8_t>(ctx.bitlen >> 48);
  ctx.data[56] = static_cast<uint8_t>(ctx.bitlen >> 56);
  Sha256Transform(ctx, ctx.data);
  for (i = 0; i < 4; ++i) {
    hash[i] = static_cast<uint8_t>((ctx.state[0] >> (24 - i * 8)) & 0xff);
    hash[i + 4] = static_cast<uint8_t>((ctx.state[1] >> (24 - i * 8)) & 0xff);
    hash[i + 8] = static_cast<uint8_t>((ctx.state[2] >> (24 - i * 8)) & 0xff);
    hash[i + 12] = static_cast<uint8_t>((ctx.state[3] >> (24 - i * 8)) & 0xff);
    hash[i + 16] = static_cast<uint8_t>((ctx.state[4] >> (24 - i * 8)) & 0xff);
    hash[i + 20] = static_cast<uint8_t>((ctx.state[5] >> (24 - i * 8)) & 0xff);
    hash[i + 24] = static_cast<uint8_t>((ctx.state[6] >> (24 - i * 8)) & 0xff);
    hash[i + 28] = static_cast<uint8_t>((ctx.state[7] >> (24 - i * 8)) & 0xff);
  }
}

inline void HmacSha256(const uint8_t* key, size_t keyLen, const uint8_t* data,
                       size_t dataLen, uint8_t out[32]) {
  uint8_t keyBlock[64]; memset(keyBlock, 0, sizeof(keyBlock));
  if (keyLen > 64) {
    SHA256Ctx hashCtx; Sha256Init(hashCtx); Sha256Update(hashCtx, key, keyLen); Sha256Final(hashCtx, keyBlock);
  } else {
    memcpy(keyBlock, key, keyLen);
  }
  uint8_t oPad[64], iPad[64];
  for (size_t i = 0; i < 64; ++i) { oPad[i] = static_cast<uint8_t>(keyBlock[i] ^ 0x5c); iPad[i] = static_cast<uint8_t>(keyBlock[i] ^ 0x36); }
  uint8_t innerHash[32]; SHA256Ctx ctx; Sha256Init(ctx); Sha256Update(ctx, iPad, sizeof(iPad)); Sha256Update(ctx, data, dataLen); Sha256Final(ctx, innerHash);
  Sha256Init(ctx); Sha256Update(ctx, oPad, sizeof(oPad)); Sha256Update(ctx, innerHash, sizeof(innerHash)); Sha256Final(ctx, out);
}

inline bool ConstantTimeEquals(const std::vector<uint8_t>& lhs,
                               const std::vector<uint8_t>& rhs) {
  if (lhs.size() != rhs.size()) return false;
  uint8_t diff = 0;
  for (size_t i = 0; i < lhs.size(); ++i) diff |= lhs[i] ^ rhs[i];
  return diff == 0;
}

inline bool Base64Decode(const std::string& input, std::vector<uint8_t>& output) {
  std::array<int, 256> reverseTable; reverseTable.fill(-1);
  for (size_t i = 0; i < 64; ++i) reverseTable[static_cast<unsigned char>(kBase64Table[i])] = static_cast<int>(i);
  int val = 0; int valb = -8; output.clear();
  for (unsigned char c : input) {
    if (c == '=') break;
    if (c == '\r' || c == '\n' || c == ' ' || c == '\t') continue;
    int decoded = reverseTable[c];
    if (decoded < 0) return false;
    val = (val << 6) + decoded; valb += 6;
    if (valb >= 0) { output.push_back(static_cast<uint8_t>((val >> valb) & 0xFF)); valb -= 8; }
  }
  return true;
}

inline bool RemovePkcs7Padding(std::vector<uint8_t>& data) {
  if (data.empty()) return false;
  uint8_t pad = data.back();
  if (pad == 0 || pad > WINFOX_AES_BLOCKLEN || pad > data.size()) return false;
  for (size_t i = data.size() - pad; i < data.size(); ++i) if (data[i] != pad) return false;
  data.resize(data.size() - pad);
  return true;
}

inline bool InflateZlib(const std::vector<uint8_t>& compressed, std::string& output) {
  if (compressed.empty()) { output.clear(); return true; }
  uLongf estimate = std::max<uLongf>(compressed.size() * 4, 1024);
  std::vector<uint8_t> buffer(estimate);
  while (true) {
    uLongf destLen = estimate;
    int rc = uncompress(buffer.data(), &destLen, compressed.data(), static_cast<uLong>(compressed.size()));
    if (rc == Z_OK) { output.assign(reinterpret_cast<const char*>(buffer.data()), destLen); return true; }
    if (rc != Z_BUF_ERROR || estimate > 16 * 1024 * 1024) return false;
    estimate *= 2; buffer.resize(estimate);
  }
}

#ifdef _WIN32
inline bool AesCbcDecryptWindows(const std::vector<uint8_t>& iv,
                                 std::vector<uint8_t>& cipher,
                                 std::string& outError) {
  BCRYPT_ALG_HANDLE alg = nullptr;
  BCRYPT_KEY_HANDLE key = nullptr;
  DWORD cbData = 0;
  DWORD objLen = 0;
  NTSTATUS status = BCryptOpenAlgorithmProvider(&alg, BCRYPT_AES_ALGORITHM,
                                                nullptr, 0);
  if (status < 0) {
    outError = "failed to open BCrypt AES provider";
    return false;
  }
  status = BCryptSetProperty(
      alg, BCRYPT_CHAINING_MODE,
      reinterpret_cast<PUCHAR>(const_cast<wchar_t*>(BCRYPT_CHAIN_MODE_CBC)),
      static_cast<ULONG>((wcslen(BCRYPT_CHAIN_MODE_CBC) + 1) * sizeof(wchar_t)),
      0);
  if (status < 0) {
    BCryptCloseAlgorithmProvider(alg, 0);
    outError = "failed to set BCrypt CBC mode";
    return false;
  }
  status = BCryptGetProperty(alg, BCRYPT_OBJECT_LENGTH,
                             reinterpret_cast<PUCHAR>(&objLen), sizeof(objLen),
                             &cbData, 0);
  if (status < 0 || objLen == 0) {
    BCryptCloseAlgorithmProvider(alg, 0);
    outError = "failed to get BCrypt object length";
    return false;
  }
  std::vector<uint8_t> keyObject(objLen);
  status = BCryptGenerateSymmetricKey(
      alg, &key, keyObject.data(), objLen,
      const_cast<PUCHAR>(reinterpret_cast<const UCHAR*>(kEncryptionKey)),
      sizeof(kEncryptionKey), 0);
  if (status < 0) {
    BCryptCloseAlgorithmProvider(alg, 0);
    outError = "failed to create BCrypt AES key";
    return false;
  }
  std::vector<uint8_t> ivCopy(iv.begin(), iv.end());
  std::vector<uint8_t> plain(cipher.size());
  ULONG plainLen = 0;
  status = BCryptDecrypt(key, cipher.data(), static_cast<ULONG>(cipher.size()),
                         nullptr, ivCopy.data(),
                         static_cast<ULONG>(ivCopy.size()), plain.data(),
                         static_cast<ULONG>(plain.size()), &plainLen, 0);
  BCryptDestroyKey(key);
  BCryptCloseAlgorithmProvider(alg, 0);
  if (status < 0) {
    outError = "BCrypt AES decryption failed";
    return false;
  }
  plain.resize(plainLen);
  cipher.swap(plain);
  return true;
}
#endif

inline std::string HexPrefix(const std::vector<uint8_t>& data, size_t count) {
  static const char* hex = "0123456789abcdef";
  std::string out;
  size_t limit = count < data.size() ? count : data.size();
  out.reserve(limit * 2);
  for (size_t i = 0; i < limit; ++i) {
    unsigned char b = data[i];
    out.push_back(hex[(b >> 4) & 0x0f]);
    out.push_back(hex[b & 0x0f]);
  }
  return out;
}

inline std::string HexSuffix(const std::vector<uint8_t>& data, size_t count) {
  static const char* hex = "0123456789abcdef";
  std::string out;
  size_t start = data.size() > count ? data.size() - count : 0;
  out.reserve((data.size() - start) * 2);
  for (size_t i = start; i < data.size(); ++i) {
    unsigned char b = data[i];
    out.push_back(hex[(b >> 4) & 0x0f]);
    out.push_back(hex[b & 0x0f]);
  }
  return out;
}

inline bool VerifyHmac(const std::vector<uint8_t>& iv,
                       const std::vector<uint8_t>& cipher,
                       const std::vector<uint8_t>& expectedMac) {
  std::vector<uint8_t> material;
  material.reserve(iv.size() + cipher.size());
  material.insert(material.end(), iv.begin(), iv.end());
  material.insert(material.end(), cipher.begin(), cipher.end());
  uint8_t mac[32];
  HmacSha256(kMacKey, sizeof(kMacKey), material.data(), material.size(), mac);
  return ConstantTimeEquals(std::vector<uint8_t>(mac, mac + sizeof(mac)), expectedMac);
}

}  // namespace

inline bool DecodeAndDecryptConfig(const std::string& mode,
                                   const std::string& ivBase64,
                                   const std::string& cipherBase64,
                                   const std::string& hmacBase64,
                                   std::string& outJson,
                                   std::string& outError) {
  if (mode != "cbc-hmac-zlib") { outError = "unsupported encrypted config mode"; return false; }
  std::vector<uint8_t> iv, cipher, mac;
  if (!Base64Decode(ivBase64, iv) || iv.size() != WINFOX_AES_BLOCKLEN) { outError = "invalid encrypted config IV"; return false; }
  if (!Base64Decode(cipherBase64, cipher) || cipher.empty() || (cipher.size() % WINFOX_AES_BLOCKLEN) != 0) { outError = "invalid encrypted config ciphertext"; return false; }
  if (!Base64Decode(hmacBase64, mac) || mac.size() != 32) { outError = "invalid encrypted config HMAC"; return false; }
  if (!VerifyHmac(iv, cipher, mac)) { outError = "encrypted config HMAC verification failed"; return false; }

#ifdef _WIN32
  if (!AesCbcDecryptWindows(iv, cipher, outError)) { return false; }
#else
  WinfoxAES_ctx ctx;
  WinfoxAES_init_ctx_iv(&ctx, kEncryptionKey, iv.data());
  WinfoxAES_CBC_decrypt_buffer(&ctx, cipher.data(), static_cast<uint32_t>(cipher.size()));
#endif
  MaskConfig::DebugEncryptedConfig(std::string("post-aes prefix=") + HexPrefix(cipher, 16));
  MaskConfig::DebugEncryptedConfig(std::string("post-aes suffix=") + HexSuffix(cipher, 16));
  if (!RemovePkcs7Padding(cipher)) { outError = "invalid encrypted config padding"; return false; }

  if (!InflateZlib(cipher, outJson)) { outError = "failed to decompress encrypted config"; return false; }
  return true;
}

}  // namespace WinfoxConfigCrypto
