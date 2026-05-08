#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "additions/camoucfg/WinfoxConfigCrypto.hpp"
int main(){
  const char* ivb="uyAU7QurOrjXt2+e6iUVKA==";
  const char* ctb="XW0LgxJGhgWabYK6dWLRmFkgwqb4pg2O5YQhc2Jh6F9kP7u/Fo21Ia40x2UVjCb13+BTbpkpSFSBz6bFm9TpyFPgT89ChNKl7c+/KNP/rrK/CjdQScSiFabWmDBjRd5yvjblB1Ga9ch6fAgHeBK2tvH8uyHz4kgruospxe4sBRqWYUtmxwdY/9rS3YB4/cP4gjbiUxrsBPAnXz1JbkKsFedge1aLL4MvZsikhLqUhdE=";
  const char* hmb="AeziNKfGZGofe9Z/O+XHoPlfGfAx4FSxnO6A/Fs99u0=";
  std::string out, err;
  bool ok = WinfoxConfigCrypto::DecodeAndDecryptConfig("cbc-hmac-zlib", ivb, ctb, hmb, out, err);
  printf("ok=%d\n", ok ? 1 : 0);
  if(ok) printf("out=%s\n", out.c_str()); else printf("err=%s\n", err.c_str());
  return 0;
}
