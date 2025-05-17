#!/usr/bin/env python3
"""
auto_sub_solver.py  (v2 – “clean & stronger”)

• Mono‑alphabetic substitution cipher cracker
• Simulated annealing + quad‑gram log‑likelihood
• Zipf word‑frequency bonus (wordfreq)
• Optional cleaning step removes non‑letters for scoring
"""

import argparse, math, os, random, re, string, sys, urllib.request
from collections import defaultdict
from pathlib import Path

# ----------------------------------------------------------------------
# 0.  CONFIG  — tweak defaults here if desired
# ----------------------------------------------------------------------
# Default search settings (can be overridden with -r -i on CLI)
DEF_RESTARTS   = 80     # was 40
DEF_ITERS      = 8000   # was 6000
LAMBDA_DEFAULT = 1.5    # word‑score weight

# ----------------------------------------------------------------------
# 1.  Quad‑gram data (download once → cached)
# ----------------------------------------------------------------------
QUAD_URLS = [
    # GitHub mirrors first (fast, plain HTTP)
    "https://raw.githubusercontent.com/torognes/enigma/master/english_quadgrams.txt",
    "https://raw.githubusercontent.com/gibsjose/statistical-attack/master/english-quadgrams.txt",
    # Original PracticalCryptography (fallback)
    "http://practicalcryptography.com/media/cryptanalysis/files/english_quadgrams.txt",
]

CACHE_FILE = Path(__file__).with_name("english_quadgrams.txt")

def _download_quadgrams():
    for url in QUAD_URLS:
        try:
            print(f"[*] Fetching quadgram list from {url} …")
            with urllib.request.urlopen(url, timeout=15) as resp:
                CACHE_FILE.write_bytes(resp.read())
            print("[+] Quadgram list cached\n")
            return
        except Exception as e:
            print(f"[-] {e}")
    raise RuntimeError("All quadgram URLs failed.  Drop the file next to the script.")

def _load_quadgrams():
    if not CACHE_FILE.exists():
        _download_quadgrams()
    counts, total = defaultdict(int), 0
    with CACHE_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            g, c = line.split()
            counts[g] = int(c)
            total += int(c)
    return {g: math.log10(c / total) for g, c in counts.items()}

QUAD_LOGP  = _load_quadgrams()
FLOOR_LOGP = math.log10(0.01 / sum(10 ** p for p in QUAD_LOGP.values()))

def quad_score(text: str) -> float:
    return sum(
        QUAD_LOGP.get(text[i : i + 4], FLOOR_LOGP)
        for i in range(len(text) - 3)
    )

# ----------------------------------------------------------------------
# 2.  Zipf word‑frequency scorer
# ----------------------------------------------------------------------
try:
    from wordfreq import zipf_frequency
except ImportError:
    sys.exit("wordfreq missing – install with  pip install wordfreq")

def word_score(text: str) -> float:
    words = re.findall(r"[A-Z]{2,}", text)
    return sum(zipf_frequency(w.lower(), "en") for w in words)

# ----------------------------------------------------------------------
# 3.  Helpers for cleaning & keys
# ----------------------------------------------------------------------
LETTER_SPACE = set(string.ascii_uppercase + " ")

def clean(text: str) -> str:
    """Return uppercase string containing only A‑Z and space."""
    return "".join(ch for ch in text.upper() if ch in LETTER_SPACE)

ALPHA = string.ascii_uppercase

def random_key() -> str:
    return "".join(random.sample(ALPHA, 26))

def swap_two(key: str) -> str:
    a, b = random.sample(range(26), 2)
    lst = list(key)
    lst[a], lst[b] = lst[b], lst[a]
    return "".join(lst)

def decode(ct: str, key: str) -> str:
    return ct.upper().translate(str.maketrans(ALPHA, key))

# ----------------------------------------------------------------------
# 4.  Core cracking routine
# ----------------------------------------------------------------------
def crack(cipher: str, restarts, iters, lam, use_clean, temp0=20.0):
    best_s, best_key, best_raw = float("-inf"), None, ""
    for _ in range(restarts):
        key   = random_key()
        raw   = decode(cipher, key)
        txt   = clean(raw) if use_clean else raw.upper()
        score = quad_score(txt) + lam * word_score(txt)
        temp  = temp0
        for _ in range(iters):
            cand_key = swap_two(key)
            cand_raw = decode(cipher, cand_key)
            cand_txt = clean(cand_raw) if use_clean else cand_raw.upper()
            cand_s   = quad_score(cand_txt) + lam * word_score(cand_txt)
            d = cand_s - score
            if d > 0 or math.exp(d / temp) > random.random():
                key, raw, txt, score = cand_key, cand_raw, cand_txt, cand_s
            temp *= 0.995
        if score > best_s:
            best_key, best_raw, best_s = key, raw, score
    return best_key, best_raw, best_s

# ----------------------------------------------------------------------
# 5.  CLI
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Substitution‑cipher solver (clean & strong)")
    ap.add_argument("cipher", nargs="*", help="Ciphertext (or leave blank to read stdin)")
    ap.add_argument("-r", "--restarts", type=int, default=DEF_RESTARTS, help="Random restarts")
    ap.add_argument("-i", "--iters",    type=int, default=DEF_ITERS,    help="Iterations per restart")
    ap.add_argument("--lambda", dest="lam", type=float, default=LAMBDA_DEFAULT,
                    help="Word‑score weight (default 1.5)")
    ap.add_argument("--clean", action="store_true",
                    help="Strip non‑letters before scoring (recommended)")
    args   = ap.parse_args()
    cipher = " ".join(args.cipher) if args.cipher else sys.stdin.read()
    key, plain, s = crack(cipher, args.restarts, args.iters, args.lam, args.clean)
    print(f"\n[+] Best key  : {key}")
    print(f"[+] Score     : {s:.2f}")
    print("\n===== Decryption =====\n")
    print(plain)

if __name__ == "__main__":
    main()